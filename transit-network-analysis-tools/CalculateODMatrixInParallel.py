############################################################################
## Tool name: Transit Network Analysis Tools
## Created by: Melinda Morang, Esri
## Last updated: 3 May 2022
############################################################################
"""Calculate an OD Cost Matrix in parallel.

This script is the entry point for the Calculate Accessibility Matrix and
Calculate Travel Time Statistics (OD Cost Matrix) tools.  The classes
here parse and validate the inputs and launch the parallelized
OD Cost Matrix solve as a subprocess.

-- Calculate Accessibility Matrix --
Count the number of destinations reachable from each origin by transit and
walking. The tool calculates an Origin-Destination Cost Matrix for each start
time within a time window because the reachable destinations change depending
on the time of day because of the transit schedules.  The output gives the
total number of destinations reachable at least once as well as the number of
destinations reachable at least 10%, 20%, ...90% of start times during the time
window.  The number of reachable destinations can be weighted based on a field,
such as the number of jobs available at each destination.  The tool also
calculates the percentage of total destinations reachable.

-- Calculate Travel Time Statistics (OD Cost Matrix) --
Solve the OD Cost Matrix incrementally over a time window and calculate statistics
about the results for each OD pair:
- minimum travel time
- maximum travel time
- mean travel time
- number of times the origin-destination pair or route was considered
Optionally store the output of each solve for further analysis.

This code is for ArcGIS Pro only and solves the OD Cost Matrices in
parallel. It was built based off Esri's Solve Large OD Cost Matrix sample script
available from https://github.com/Esri/large-network-analysis-tools under an Apache
2.0 license.

Copyright 2022 Esri
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at
       http://www.apache.org/licenses/LICENSE-2.0
   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""
import os
import sys
import time
import traceback
import subprocess

import arcpy

import AnalysisHelpers
# Import OD Cost Matrix settings from config files
import CalculateAccessibilityMatrix_OD_config
import CalculateTravelTimeStatistics_OD_config

arcpy.env.overwriteOutput = True


class ODCostMatrixSolver:  # pylint: disable=too-many-instance-attributes, too-few-public-methods
    """Compute OD Cost Matrices between Origins and Destinations in parallel and combine results.

    This is a base class holding methods and variables relevant to multiple tools.
    """

    def __init__(  # pylint: disable=too-many-locals, too-many-arguments
        self, origins, destinations, time_window_start_day, time_window_start_time, time_window_end_day,
        time_window_end_time, time_increment, network_data_source, travel_mode, chunk_size, max_processes,
        precalculate_network_locations=True, barriers=None
    ):
        """Initialize the ODCostMatrixSolver class.

        Args:
            origins (str, layer): Catalog path or layer for the input origins
            destinations (str, layer): Catalog path or layer for the input destinations
            time_window_start_day (str): English weekday name or YYYYMMDD date representing the weekday or start date of
                the time window
            time_window_start_time (str): HHMM time of day for the start of the time window
            time_window_end_day (str): English weekday name or YYYYMMDD date representing the weekday or end date of
                the time window
            time_window_end_time (str): HHMM time of day for the end of the time window
            time_increment (int): Number of minutes between each run of the OD Cost Matrix in the time window
            network_data_source (str, layer): Catalog path, layer, or URL for the input network dataset
            travel_mode (str, travel mode): Travel mode object, name, or json string representation
            chunk_size (int): Maximum number of origins and destinations that can be in one chunk
            max_processes (int): Maximum number of allowed parallel processes
            precalculate_network_locations (bool, optional): Whether to precalculate network location fields for all
                inputs. Defaults to True. Should be false if the network_data_source is a service.
            barriers (list(str, layer), optional): List of catalog paths or layers for point, line, and polygon barriers
                 to use. Defaults to None.
        """
        self.origins = origins
        self.destinations = destinations
        self.network_data_source = network_data_source
        self.travel_mode = travel_mode
        self.chunk_size = chunk_size
        self.max_processes = max_processes
        self.should_precalc_network_locations = precalculate_network_locations
        self.barriers = barriers if barriers else []

        self.time_window_start_day = time_window_start_day
        self.time_window_start_time = time_window_start_time
        self.time_window_end_day = time_window_end_day
        self.time_window_end_time = time_window_end_time
        self.time_increment = time_increment

        # Check if origins and destinations are the same. We can skip certain steps if so.
        # The origins and destinations can be either catalog paths or layers. If they are catalog paths, compare them
        # directly. If they are layers, they are only equal if both their dataSources and layer names are the same. It
        # is conceivable that someone might have two layers referencing the same data that each have a different
        # selection set or definition query, and those should not be considered the same.
        origins_catalog = self.origins.dataSource if hasattr(self.origins, "dataSource") else self.origins
        dests_catalog = self.destinations.dataSource if hasattr(self.destinations, "dataSource") else self.destinations
        origins_name = self.origins.name if hasattr(self.origins, "name") else self.origins
        dests_name = self.destinations.name if hasattr(self.destinations, "name") else self.destinations
        self.same_origins_destinations = bool(origins_catalog == dests_catalog) and bool(origins_name == dests_name)

        self.max_origins = self.chunk_size
        self.max_destinations = self.chunk_size

        self.is_service = AnalysisHelpers.is_nds_service(self.network_data_source)
        self.service_limits = None
        self.is_agol = False

        self.temp_outputs = []  # For storing intermediate outputs to delete later
        self.od_props = {}  # Should be set in the child class using the imported config file
        self.tool_specific_od_inputs = []  # Should be set in the child class

    def _validate_inputs(self):
        """Validate the OD Cost Matrix inputs."""
        # Validate input numerical values
        if self.chunk_size < 1:
            err = "Chunk size must be greater than 0."
            arcpy.AddError(err)
            raise ValueError(err)
        if self.max_processes < 1:
            err = "Maximum allowed parallel processes must be greater than 0."
            arcpy.AddError(err)
            raise ValueError(err)
        if self.time_increment <= 0:
            err = "The time increment must be greater than 0."
            arcpy.AddError(err)
            raise ValueError(err)

        # Validate origins, destinations, and barriers
        AnalysisHelpers.validate_input_feature_class(self.origins)
        AnalysisHelpers.validate_input_feature_class(self.destinations)
        for barrier_fc in self.barriers:
            AnalysisHelpers.validate_input_feature_class(barrier_fc)
        # If the barriers are layers, convert them to catalog paths so we can pass them to the subprocess
        self.barriers = [AnalysisHelpers.get_catalog_path(barrier_fc) for barrier_fc in self.barriers]

        # Validate network
        if not self.is_service and not arcpy.Exists(self.network_data_source):
            err = f"Input network dataset {self.network_data_source} does not exist."
            arcpy.AddError(err)
            raise ValueError(err)
        if not self.is_service:
            # Try to check out the Network Analyst extension
            try:
                arcpy.CheckOutExtension("network")
            except Exception as ex:
                err = "Unable to check out Network Analyst extension license."
                arcpy.AddError(err)
                raise RuntimeError(err) from ex

        # Validate OD Cost Matrix settings and convert travel mode to a JSON string
        self.travel_mode = self._validate_od_settings()

        # For a services solve, get tool limits and validate max processes and chunk size
        if self.is_service:
            self._get_tool_limits_and_is_agol()
            if self.is_agol and self.max_processes > AnalysisHelpers.MAX_AGOL_PROCESSES:
                arcpy.AddWarning((
                    f"The specified maximum number of parallel processes, {self.max_processes}, exceeds the limit of "
                    f"{AnalysisHelpers.MAX_AGOL_PROCESSES} allowed when using as the network data source the ArcGIS "
                    "Online services or a hybrid portal whose network analysis services fall back to the ArcGIS Online "
                    "services. The maximum number of parallel processes has been reduced to "
                    f"{AnalysisHelpers.MAX_AGOL_PROCESSES}."))
                self.max_processes = AnalysisHelpers.MAX_AGOL_PROCESSES
            self._update_max_inputs_for_service()
            if self.should_precalc_network_locations:
                arcpy.AddWarning(
                    "Cannot precalculate network location fields when the network data source is a service.")
                self.should_precalc_network_locations = False

    def _validate_od_settings(self):
        """Validate OD cost matrix settings by spinning up a dummy OD Cost Matrix object.

        Raises:
            ValueError: If the travel mode doesn't have a name

        Returns:
            str: JSON string representation of the travel mode
        """
        arcpy.AddMessage("Validating OD Cost Matrix settings...")
        # Create a dummy ODCostMatrix object, initialize an OD solver object, and set properties
        try:
            odcm = arcpy.nax.OriginDestinationCostMatrix(self.network_data_source)
            odcm.travelMode = self.travel_mode
            odcm = self._set_od_tool_settings(odcm)
        except Exception:
            arcpy.AddError("Invalid OD Cost Matrix settings.")
            errs = traceback.format_exc().splitlines()
            for err in errs:
                arcpy.AddError(err)
            raise

        # Return a JSON string representation of the travel mode to pass to the subprocess
        return odcm.travelMode._JSON  # pylint: disable=protected-access

    def _set_od_tool_settings(self, odcm):
        """Set ODCostMatrix solver object properties specific to the tool being run.

        Args:
            odcm (ODCostMatrix solver object): ODCostMatrix solver object whose properties you want to set.
        """
        # Child classes for specific tools should implement this as needed.
        return odcm

    def _get_tool_limits_and_is_agol(
            self, service_name="asyncODCostMatrix", tool_name="GenerateOriginDestinationCostMatrix"):
        """Retrieve a dictionary of various limits supported by a portal tool and whether the portal uses AGOL services.

        Assumes that we have already determined that the network data source is a service.

        Args:
            service_name (str, optional): Name of the service. Defaults to "asyncODCostMatrix".
            tool_name (str, optional): Tool name for the designated service. Defaults to
                "GenerateOriginDestinationCostMatrix".
        """
        arcpy.AddMessage("Getting tool limits from the portal...")
        if not self.network_data_source.endswith("/"):
            self.network_data_source = self.network_data_source + "/"
        try:
            tool_info = arcpy.nax.GetWebToolInfo(service_name, tool_name, self.network_data_source)
            # serviceLimits returns the maximum origins and destinations allowed by the service, among other things
            self.service_limits = tool_info["serviceLimits"]
            # isPortal returns True for Enterprise portals and False for AGOL or hybrid portals that fall back to using
            # the AGOL services
            self.is_agol = not tool_info["isPortal"]
        except Exception:
            arcpy.AddError("Error getting tool limits from the portal.")
            errs = traceback.format_exc().splitlines()
            for err in errs:
                arcpy.AddError(err)
            raise

    def _update_max_inputs_for_service(self):
        """Check the user's specified max origins and destinations and reduce max to portal limits if required."""
        lim_max_origins = self.service_limits["maximumOrigins"]
        if lim_max_origins:
            lim_max_origins = int(lim_max_origins)
            if lim_max_origins < self.max_origins:
                self.max_origins = lim_max_origins
                arcpy.AddMessage(
                    f"Max origins per chunk has been updated to {self.max_origins} to accommodate service limits.")
        lim_max_destinations = self.service_limits["maximumDestinations"]
        if lim_max_destinations:
            lim_max_destinations = int(lim_max_destinations)
            if lim_max_destinations < self.max_destinations:
                self.max_destinations = lim_max_destinations
                arcpy.AddMessage((
                    f"Max destinations per chunk has been updated to {self.max_destinations} to accommodate service "
                    "limits."
                ))

    def _precalculate_network_locations(self, input_features):
        """Precalculate network location fields if possible for faster loading and solving later.

        Cannot be used if the network data source is a service. Uses the searchTolerance, searchToleranceUnits, and
        searchQuery properties set in the OD config file.

        Args:
            input_features (feature class catalog path): Feature class to calculate network locations for
            network_data_source (network dataset catalog path): Network dataset to use to calculate locations
            travel_mode (travel mode): Travel mode name, object, or json representation to use when calculating
            locations.
        """
        if self.is_service:
            arcpy.AddMessage(
                "Skipping precalculating network location fields because the network data source is a service.")
            return

        arcpy.AddMessage(f"Precalculating network location fields for {input_features}...")

        # Get location settings from config file if present
        search_tolerance = None
        if "searchTolerance" in self.od_props and "searchToleranceUnits" in self.od_props:
            search_tolerance = f"{self.od_props['searchTolerance']} {self.od_props['searchToleranceUnits'].name}"
        search_query = self.od_props.get("search_query", None)

        # Calculate network location fields if network data source is local
        arcpy.na.CalculateLocations(
            input_features, self.network_data_source,
            search_tolerance=search_tolerance,
            search_query=search_query,
            travel_mode=self.travel_mode
        )

    def _preprocess_inputs(self):
        """Preprocess the input feature classes to prepare them for use in the OD Cost Matrix."""
        # Should be implemented in the child class for the needs of the specific tool.
        raise NotImplementedError

    def _copy_input_to_temp(self, input_fc):
        """Make a temporary copy of an input and convert from polygons to points if needed."""
        # Make a temporary copy of the input so location fields can be calculated without modifying it.
        # Also convert from polygons if needed.
        shape_type = arcpy.Describe(input_fc).shapeType
        temp_input = self._make_temporary_output_path("TNAT_TempInput")
        if shape_type == "Polygon":
            self._polygons_to_points(input_fc, temp_input)
        else:
            arcpy.conversion.FeatureClassToFeatureClass(
                input_fc,
                os.path.dirname(temp_input),
                os.path.basename(temp_input)
            )
        return temp_input

    @staticmethod
    def _polygons_to_points(in_fc, out_fc):
        """Convert polygon inputs to a point feature class."""
        arcpy.AddMessage(
            f"Converting polygon-based input {in_fc} to points for use in the OD Cost Matrix analysis...")
        try:
            arcpy.management.FeatureToPoint(in_fc, out_fc, "INSIDE")
        except arcpy.ExecuteError:
            # Weird geometry problems in the input polygons can cause Feature To Point to fail. The user should run
            # Repair Geometry and try again.
            arcpy.AddError((
                f"Failed to convert polygon-based input {in_fc} to points for use in the OD Cost Matrix analysis. "
                "Try running the Repair Geometry tool on the input polygons."
            ))
            # Use AddReturnMessage to pass through GP errors.
            # This ensures that the hyperlinks to the message IDs will work in the UI.
            for msg in range(0, arcpy.GetMessageCount()):
                if arcpy.GetSeverity(msg) == 2:
                    arcpy.AddReturnMessage(msg)
                raise arcpy.ExecuteError

    def _execute_solve(self):
        """Solve the OD Cost Matrix analysis."""
        # Launch the parallel_odcm script as a subprocess so it can spawn parallel processes. We have to do this because
        # a tool running in the Pro UI cannot call concurrent.futures without opening multiple instances of Pro.
        cwd = os.path.dirname(os.path.abspath(__file__))
        # Define some shared inputs for the parallel OD script. The rest should be specified in the child class's
        # implementation of self.tool_specific_od_inputs.
        odcm_inputs = [
            os.path.join(sys.exec_prefix, "python.exe"),
            os.path.join(cwd, "parallel_odcm.py"),
            "--network-data-source", self.network_data_source,
            "--travel-mode", self.travel_mode,
            "--max-origins", str(self.max_origins),
            "--max-destinations", str(self.max_destinations),
            "--max-processes", str(self.max_processes),
            "--time-window-start-day", self.time_window_start_day,
            "--time-window-start-time", self.time_window_start_time,
            "--time-window-end-day", self.time_window_end_day,
            "--time-window-end-time", self.time_window_end_time,
            "--time-increment", str(self.time_increment)
        ] + self.tool_specific_od_inputs
        if self.barriers:
            odcm_inputs += ["--barriers"]
            odcm_inputs += self.barriers
        # We do not want to show the console window when calling the command line tool from within our GP tool.
        # This can be done by setting this hex code.
        create_no_window = 0x08000000
        with subprocess.Popen(
            odcm_inputs,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=create_no_window
        ) as process:
            # The while loop reads the subprocess's stdout in real time and writes the stdout messages to the GP UI.
            # This is the only way to write the subprocess's status messages in a way that a user running the tool from
            # the ArcGIS Pro UI can actually see them.
            # When process.poll() returns anything other than None, the process has completed, and we should stop
            # checking and move on.
            while process.poll() is None:
                output = process.stdout.readline()
                if output:
                    msg_string = output.strip().decode()
                    AnalysisHelpers.parse_std_and_write_to_gp_ui(msg_string)
                time.sleep(.1)

            # Once the process is finished, check if any additional errors were returned. Messages that came after the
            # last process.poll() above will still be in the queue here. This is especially important for detecting
            # messages from raised exceptions, especially those with tracebacks.
            output, _ = process.communicate()
            if output:
                out_msgs = output.decode().splitlines()
                for msg in out_msgs:
                    AnalysisHelpers.parse_std_and_write_to_gp_ui(msg)

            # In case something truly horrendous happened and none of the logging caught our errors, at least fail the
            # tool when the subprocess returns an error code. That way the tool at least doesn't happily succeed but not
            # actually do anything.
            return_code = process.returncode
            if return_code != 0:
                arcpy.AddError("OD Cost Matrix script failed.")

    def _delete_intermediate_outputs(self):
        """Clean up intermediate outputs."""
        if self.temp_outputs:
            try:
                arcpy.AddMessage("Deleting intermediate outputs...")
                arcpy.management.Delete(self.temp_outputs)
            except Exception:  # pylint: disable=broad-except
                # If deletion doesn't work, just throw a warning and move on. This does not need to kill the tool.
                arcpy.AddWarning("Unable to delete intermediate outputs.")

    def _make_temporary_output_path(self, name):
        """Make a path in the scratch gdb for a temporary intermediate output and track it for later deletion."""
        name = arcpy.CreateUniqueName(name, arcpy.env.scratchGDB)  # pylint: disable=no-member
        temp_output = os.path.join(arcpy.env.scratchGDB, name)  # pylint: disable=no-member
        self.temp_outputs.append(temp_output)
        return temp_output

    def solve_large_od_cost_matrix(self):
        """Solve the large OD Cost Matrix in parallel."""
        try:
            self._validate_inputs()
            arcpy.AddMessage("Inputs successfully validated.")
        except Exception:  # pylint: disable=broad-except
            arcpy.AddError("Invalid inputs.")
            return

        # Preprocess inputs
        self._preprocess_inputs()

        # Solve the analysis
        self._execute_solve()

        # Clean up
        self._delete_intermediate_outputs()


class CalculateAccessibilityMatrix(ODCostMatrixSolver):  # pylint: disable=too-many-instance-attributes, too-few-public-methods
    """Run the Calculate Accessibility Matrix tool.

    This class preprocesses and validate inputs and then spins up a subprocess to do the actual OD Cost Matrix
    calculations. This is necessary because the a script tool running in the ArcGIS Pro UI cannot directly call
    multiprocessing using concurrent.futures. We must spin up a subprocess, and the subprocess must spawn parallel
    processes for the calculations. Thus, this class does all the pre-processing, passes inputs to the subprocess, and
    handles messages returned by the subprocess. The subprocess actually does the calculations.
    """

    def __init__(  # pylint: disable=too-many-locals, too-many-arguments
        self, origins, destinations, output_origins, time_window_start_day, time_window_start_time, time_window_end_day,
        time_window_end_time, time_increment, network_data_source, travel_mode, chunk_size, max_processes, time_units,
        cutoff, weight_field=None, precalculate_network_locations=True, barriers=None
    ):
        """Initialize the ODCostMatrixSolver class.

        Args:
            origins (str, layer): Catalog path or layer for the input origins
            destinations (str, layer): Catalog path or layer for the input destinations
            output_origins (str): Catalog path to the output Origins feature class
            time_window_start_day (str): English weekday name or YYYYMMDD date representing the weekday or start date of
                the time window
            time_window_start_time (str): HHMM time of day for the start of the time window
            time_window_end_day (str): English weekday name or YYYYMMDD date representing the weekday or end date of
                the time window
            time_window_end_time (str): HHMM time of day for the end of the time window
            time_increment (int): Number of minutes between each run of the OD Cost Matrix in the time window
            network_data_source (str, layer): Catalog path, layer, or URL for the input network dataset
            travel_mode (str, travel mode): Travel mode object, name, or json string representation
            chunk_size (int): Maximum number of origins and destinations that can be in one chunk
            max_processes (int): Maximum number of allowed parallel processes
            time_units (str): String representation of time units
            cutoff (float): Time cutoff to limit the OD Cost Matrix solve. Interpreted in the time_units.
            precalculate_network_locations (bool, optional): Whether to precalculate network location fields for all
                inputs. Defaults to True. Should be false if the network_data_source is a service.
            barriers (list(str, layer), optional): List of catalog paths or layers for point, line, and polygon barriers
                 to use. Defaults to None.
        """
        super().__init__(
            origins, destinations, time_window_start_day, time_window_start_time, time_window_end_day,
            time_window_end_time, time_increment, network_data_source, travel_mode, chunk_size, max_processes,
            precalculate_network_locations, barriers
            )
        self.weight_field = weight_field
        self.output_origins = output_origins
        self.time_units = time_units
        self.cutoff = cutoff

        self.temp_destinations = None
        # If the input origins are polygons, this variable will be set differently and post-processed
        self.origins_for_od = self.output_origins

        self.od_props = CalculateAccessibilityMatrix_OD_config.OD_PROPS
        self.tool_specific_od_inputs = []  # Set later
        self.out_fields = ["TotalDests", "PercDests"] + \
                          [f"DsAL{perc}Perc" for perc in range(10, 100, 10)] + \
                          [f"PsAL{perc}Perc" for perc in range(10, 100, 10)]

    def _validate_inputs(self):
        """Validate the OD Cost Matrix inputs."""
        if self.cutoff not in ["", None] and self.cutoff <= 0:
            err = "Impedance cutoff must be greater than 0."
            arcpy.AddError(err)
            raise ValueError(err)
        super()._validate_inputs()
        self._validate_weight_field()

    def _validate_weight_field(self):
        """Validate that the designated weight field is present in the destinations table and has a valid type.

        Raises:
            ValueError: If the destinations dataset is missing the designated weight field
            TypeError: If any of the weight field has an invalid (non-numerical) type
        """
        if not self.weight_field:
            # The weight field isn't being used for this analysis, so just do nothing.
            return

        arcpy.AddMessage(f"Validating weight field {self.weight_field} in destinations dataset...")

        # Make sure the weight field exists.
        fields = arcpy.ListFields(self.destinations, self.weight_field)
        if self.weight_field not in [f.name for f in fields]:
            err = (f"The destinations feature class {self.destinations} is missing the designated weight field "
                   f"{self.weight_field}.")
            arcpy.AddError(err)
            raise ValueError(err)

        # Make sure the weight field has a valid type
        weight_field_object = [f for f in fields if f.name == self.weight_field][0]
        valid_types = ["Double", "Integer", "SmallInteger", "Single"]
        if weight_field_object.type not in valid_types:
            err = (f"The weight field {self.weight_field} in the destinations feature class {self.destinations} is not "
                   "numerical.")
            arcpy.AddError(err)
            raise TypeError(err)

        # Log a warning if any rows have null values for the weight field.
        where = f"{self.weight_field} IS NULL"
        temp_layer = arcpy.management.MakeFeatureLayer(self.destinations, "NullDestLayer", where)
        num_null = int(arcpy.management.GetCount(temp_layer).getOutput(0))
        if num_null > 0:
            arcpy.AddWarning((f"{num_null} destinations have null values for the weight field {self.weight_field}. "
                              "These destinations will be counted with a weight of 0."))

    def _set_od_tool_settings(self, odcm):
        """Set ODCostMatrix solver object properties specific to this tool.

        Args:
            odcm (ODCostMatrix solver object): ODCostMatrix solver object whose properties you want to set.
        """
        time_units = AnalysisHelpers.convert_time_units_str_to_enum(self.time_units)
        odcm.timeUnits = time_units
        odcm.defaultImpedanceCutoff = self.cutoff
        return odcm

    def _preprocess_inputs(self):
        """Preprocess the input feature classes to prepare them for use in the OD Cost Matrix."""
        # Copy Origins to output
        arcpy.AddMessage("Copying origins to output...")
        arcpy.conversion.FeatureClassToFeatureClass(
            self.origins,
            os.path.dirname(self.output_origins),
            os.path.basename(self.output_origins)
        )
        self._delete_existing_output_fields(self.output_origins)
        origin_shape_type = arcpy.Describe(self.origins).shapeType
        if origin_shape_type == "Polygon":
            # Special handling if the input origins were polygons. In this case, convert the polygons to points
            # for use with the OD Cost Matrix. Later, we will rejoin the output fields to the output polygons.
            self.origins_for_od = self._make_temporary_output_path("TempOrigins")
            self._polygons_to_points(self.output_origins, self.origins_for_od)

        # Make a temporary copy of the destinations so location fields can be calculated without modifying
        # the input. Also convert from polygons if needed.
        if not self.same_origins_destinations:
            self.temp_destinations = self._copy_input_to_temp(self.destinations)
        else:
            self.temp_destinations = self.origins_for_od

        # Precalculate network location fields for inputs
        if not self.is_service and self.should_precalc_network_locations:
            self._precalculate_network_locations(self.origins_for_od)
            if not self.same_origins_destinations:
                self._precalculate_network_locations(self.temp_destinations)
            for barrier_fc in self.barriers:
                self._precalculate_network_locations(barrier_fc)

    def _delete_existing_output_fields(self, origin_fc):
        """Delete pre-existing output fields in origins."""
        # This way we can calculate them afresh and ensure correct type.
        origin_fields = [f.name for f in arcpy.ListFields(origin_fc)]
        fields_to_delete = [f for f in origin_fields if f in self.out_fields + ["ORIG_FID"]]
        if fields_to_delete:
            arcpy.AddMessage("Deleting pre-existing output fields...")
            arcpy.management.DeleteField(origin_fc, fields_to_delete)

    def _execute_solve(self):  # pylint: disable=arguments-differ
        """Solve the OD Cost Matrix analysis."""
        self.tool_specific_od_inputs = [
            "--tool", AnalysisHelpers.ODTool.CalculateAccessibilityMatrix.name,
            "--origins", self.origins_for_od,
            "--destinations", self.temp_destinations,
            "--time-units", self.time_units,
            "--cutoff", str(self.cutoff)
        ]
        if self.weight_field:
            self.tool_specific_od_inputs += ["--weight-field", self.weight_field]
        super()._execute_solve()

        # If the input origins were polygons, post-process the OD points to join the output fields back
        # to the polygon feature class
        if self.output_origins != self.origins_for_od:
            arcpy.AddMessage("Joining output fields to final polygon output Origins...")
            origins_oid = arcpy.Describe(self.output_origins).oidFieldName
            arcpy.management.JoinField(
                self.output_origins, origins_oid,
                self.origins_for_od, "ORIG_FID",
                self.out_fields
            )


class CalculateTravelTimeStatistics(ODCostMatrixSolver):  # pylint: disable=too-many-instance-attributes, too-few-public-methods
    """Run the Calculate Travel Time Statistics (OD Cost Matrix) tool.

    This class preprocesses and validate inputs and then spins up a subprocess to do the actual OD Cost Matrix
    calculations. This is necessary because the a script tool running in the ArcGIS Pro UI cannot directly call
    multiprocessing using concurrent.futures. We must spin up a subprocess, and the subprocess must spawn parallel
    processes for the calculations. Thus, this class does all the pre-processing, passes inputs to the subprocess, and
    handles messages returned by the subprocess. The subprocess actually does the calculations.
    """

    def __init__(  # pylint: disable=too-many-locals, too-many-arguments
        self, origins, destinations, out_csv_file, time_window_start_day, time_window_start_time, time_window_end_day,
        time_window_end_time, time_increment, network_data_source, travel_mode, chunk_size, max_processes,
        out_na_folder, precalculate_network_locations=True, barriers=None
    ):
        """Initialize the ODCostMatrixSolver class.

        Args:
            origins (str, layer): Catalog path or layer for the input origins
            destinations (str, layer): Catalog path or layer for the input destinations
            out_csv_file (str): Catalog path to the output CSV file
            time_window_start_day (str): English weekday name or YYYYMMDD date representing the weekday or start date of
                the time window
            time_window_start_time (str): HHMM time of day for the start of the time window
            time_window_end_day (str): English weekday name or YYYYMMDD date representing the weekday or end date of
                the time window
            time_window_end_time (str): HHMM time of day for the end of the time window
            time_increment (int): Number of minutes between each run of the OD Cost Matrix in the time window
            network_data_source (str, layer): Catalog path, layer, or URL for the input network dataset
            travel_mode (str, travel mode): Travel mode object, name, or json string representation
            chunk_size (int): Maximum number of origins and destinations that can be in one chunk
            max_processes (int): Maximum number of allowed parallel processes
            out_na_folder (str, optional): Folder for storing output individual analysis results
            precalculate_network_locations (bool, optional): Whether to precalculate network location fields for all
                inputs. Defaults to True. Should be false if the network_data_source is a service.
            barriers (list(str, layer), optional): List of catalog paths or layers for point, line, and polygon barriers
                 to use. Defaults to None.
        """
        super().__init__(
            origins, destinations, time_window_start_day, time_window_start_time, time_window_end_day,
            time_window_end_time, time_increment, network_data_source, travel_mode, chunk_size, max_processes,
            precalculate_network_locations, barriers
            )
        self.out_csv_file = out_csv_file
        self.out_na_folder = out_na_folder

        self.temp_origins = None
        self.temp_destinations = None
        self.od_props = CalculateTravelTimeStatistics_OD_config.OD_PROPS
        self.tool_specific_od_inputs = []  # Set later

    def _preprocess_inputs(self):
        """Preprocess the input feature classes to prepare them for use in the OD Cost Matrix."""
        # Make a temporary copy of the inputs so location fields can be calculated without modifying the input.
        # Also convert from polygons if needed.
        self.temp_origins = self._copy_input_to_temp(self.origins)
        if not self.same_origins_destinations:
            self.temp_destinations = self._copy_input_to_temp(self.destinations)
        else:
            self.temp_destinations = self.temp_origins

        # Precalculate network location fields for inputs
        if not self.is_service and self.should_precalc_network_locations:
            self._precalculate_network_locations(self.temp_origins)
            if not self.same_origins_destinations:
                self._precalculate_network_locations(self.temp_destinations)
            for barrier_fc in self.barriers:
                self._precalculate_network_locations(barrier_fc)

    def _execute_solve(self):  # pylint: disable=arguments-differ
        """Solve the OD Cost Matrix analysis."""
        self.tool_specific_od_inputs = [
            "--tool", AnalysisHelpers.ODTool.CalculateTravelTimeStatistics.name,
            "--origins", self.temp_origins,
            "--destinations", self.temp_destinations,
            "--out-csv-file", self.out_csv_file,
            "--out-na-folder", self.out_na_folder
        ]
        super()._execute_solve()
