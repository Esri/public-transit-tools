############################################################################
## Tool name: Transit Network Analysis Tools
## Created by: Melinda Morang, Esri
## Last updated: 6 January 2023
############################################################################
"""Run a Service Area analysis incrementing the time of day over a time window.
Save the output polygons to a single feature class that can be used to generate
a time lapse video or run the Create Percent Access Polygons tool.

This script parses the inputs and validates them and launches the parallelized
Service Area solve as a subprocess.

This version of the tool is for ArcGIS Pro only and solves the Service Areas in
parallel. It was built based off Esri's Solve Large OD Cost Matrix sample script
available from https://github.com/Esri/large-network-analysis-tools under an Apache
2.0 license.

Copyright 2023 Esri
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
from CreateTimeLapsePolygons_SA_config import SA_PROPS  # Import Service Area settings from config file

arcpy.env.overwriteOutput = True


class ServiceAreaSolver():  # pylint: disable=too-many-instance-attributes, too-few-public-methods
    """Compute Service Areas in parallel and combine results.

    This class preprocesses and validate inputs and then spins up a subprocess to do the actual Service Area
    calculations. This is necessary because the a script tool running in the ArcGIS Pro UI cannot directly call
    multiprocessing using concurrent.futures. We must spin up a subprocess, and the subprocess must spawn parallel
    processes for the calculations. Thus, this class does all the pre-processing, passes inputs to the subprocess,
    and handles messages returned by the subprocess. The subprocess actually does the calculations.
    """

    def __init__(  # pylint: disable=too-many-locals, too-many-arguments
        self, facilities, cutoffs, time_units, output_polygons, time_window_start_day, time_window_start_time,
        time_window_end_day, time_window_end_time, time_increment, network_data_source, travel_mode,
        travel_direction, geometry_at_cutoff, geometry_at_overlap,
        max_processes, precalculate_network_locations=True, barriers=None
    ):
        """Initialize the ServiceAreaSolver class.

        Args:
            facilities (str, layer): Catalog path or layer for the input facilities
            cutoffs (list(float)): List of time cutoffs for the Service Area. Interpreted in the time_units.
            time_units (str): String representation of time units
            time_window_start_day (str): English weekday name or YYYYMMDD date representing the weekday or start date of
                the time window
            time_window_start_time (str): HHMM time of day for the start of the time window
            time_window_end_day (str): English weekday name or YYYYMMDD date representing the weekday or end date of
                the time window
            time_window_end_time (str): HHMM time of day for the end of the time window
            time_increment (int): Number of minutes between each run of the OD Cost Matrix in the time window
            network_data_source (str, layer): Catalog path, layer, or URL for the input network dataset
            travel_mode (str, travel mode): Travel mode object, name, or json string representation
            travel_direction (str): String representation of the travel direction (to or from facilities)
            geometry_at_cutoff (str): String representation of the geometry at cutoffs (rings or disks)
            geometry_at_overlap (str): String representation of the geometry at overlap (split, overlap, dissolve)
            max_processes (int): Maximum number of allowed parallel processes
            precalculate_network_locations (bool, optional): Whether to precalculate network location fields for all
                inputs. Defaults to True. Should be false if the network_data_source is a service.
            barriers (list(str, layer), optional): List of catalog paths or layers for point, line, and polygon barriers
                 to use. Defaults to None.
        """
        self.facilities = facilities
        self.cutoffs = cutoffs
        self.time_units = time_units
        self.output_polygons = output_polygons
        self.network_data_source = network_data_source
        self.travel_mode = travel_mode
        self.travel_direction = travel_direction
        self.geometry_at_cutoff = geometry_at_cutoff
        self.geometry_at_overlap = geometry_at_overlap
        self.max_processes = max_processes

        self.should_precalc_network_locations = precalculate_network_locations
        self.barriers = barriers if barriers else []

        # Create a temporary output location for facilities so we can calculate network location fields and not
        # overwrite the input
        self.temp_facilities = os.path.join(
            arcpy.env.scratchGDB,  # pylint: disable=no-member
            arcpy.CreateUniqueName("TempFacs", arcpy.env.scratchGDB)  # pylint: disable=no-member
        )

        self.time_window_start_day = time_window_start_day
        self.time_window_start_time = time_window_start_time
        self.time_window_end_day = time_window_end_day
        self.time_window_end_time = time_window_end_time
        self.time_increment = time_increment

        self.is_service = AnalysisHelpers.is_nds_service(self.network_data_source)
        self.service_limits = None
        self.is_agol = False

    def _validate_inputs(self):
        """Validate the Service Area inputs."""
        # Validate input numerical values
        if self.max_processes < 1:
            err = "Maximum allowed parallel processes must be greater than 0."
            arcpy.AddError(err)
            raise ValueError(err)
        if self.max_processes > AnalysisHelpers.MAX_ALLOWED_MAX_PROCESSES:
            err = (
                f"The maximum allowed parallel processes cannot exceed {AnalysisHelpers.MAX_ALLOWED_MAX_PROCESSES:} "
                "due to limitations imposed by Python's concurrent.futures module."
            )
            arcpy.AddError(err)
            raise ValueError(err)
        for cutoff in self.cutoffs:
            if cutoff <= 0:
                err = "Impedance cutoff must be greater than 0."
                arcpy.AddError(err)
                raise ValueError(err)
        if self.time_increment <= 0:
            err = "The time increment must be greater than 0."
            arcpy.AddError(err)
            raise ValueError(err)

        # Validate facilities and barriers
        AnalysisHelpers.validate_input_feature_class(self.facilities)
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

        # Validate Service Area settings and convert travel mode to a JSON string
        self.travel_mode = self._validate_sa_settings()

        # For a services solve, get tool limits and validate max processes and chunk size
        if self.is_service:
            self._get_tool_limits_and_is_agol()
            if self.is_agol and self.max_processes > AnalysisHelpers.MAX_AGOL_PROCESSES:
                arcpy.AddWarning((
                    f"The specified maximum number of parallel processes, {self.max_processes}, exceeds the limit "
                    f"of {AnalysisHelpers.MAX_AGOL_PROCESSES} allowed when using as the network data source the "
                    "ArcGIS Online services or a hybrid portal whose network analysis services fall back to the ArcGIS "
                    "Online services. The maximum number of parallel processes has been reduced to "
                    f"{AnalysisHelpers.MAX_AGOL_PROCESSES}."))
                self.max_processes = AnalysisHelpers.MAX_AGOL_PROCESSES
            if self.should_precalc_network_locations:
                arcpy.AddWarning(
                    "Cannot precalculate network location fields when the network data source is a service.")
                self.should_precalc_network_locations = False

    def _validate_sa_settings(self):
        """Validate Service Area settings by spinning up a dummy Service Area object.

        Raises:
            ValueError: If the travel mode doesn't have a name
            ValueError: If input settings cannot be converted to proper arcpy.nax enums

        Returns:
            str: JSON string representation of the travel mode
        """
        arcpy.AddMessage("Validating Service Area settings...")
        # Validate string inputs and convert to enums
        time_units = AnalysisHelpers.convert_time_units_str_to_enum(self.time_units)
        travel_direction = AnalysisHelpers.convert_travel_direction_str_to_enum(self.travel_direction)
        geometry_at_cutoff = AnalysisHelpers.convert_geometry_at_cutoff_str_to_enum(self.geometry_at_cutoff)
        geometry_at_overlap = AnalysisHelpers.convert_geometry_at_overlap_str_to_enum(self.geometry_at_overlap)
        # Create a dummy ServiceArea object and set properties
        try:
            sa = arcpy.nax.ServiceArea(self.network_data_source)
            sa.travelMode = self.travel_mode
            sa.timeUnits = time_units
            sa.defaultImpedanceCutoffs = self.cutoffs
            sa.travelDirection = travel_direction
            sa.geometryAtCutoff = geometry_at_cutoff
            sa.geometryAtOverlap = geometry_at_overlap
        except Exception:
            arcpy.AddError("Invalid Service Area settings.")
            errs = traceback.format_exc().splitlines()
            for err in errs:
                arcpy.AddError(err)
            raise

        # Return a JSON string representation of the travel mode to pass to the subprocess
        return sa.travelMode._JSON  # pylint: disable=protected-access

    def _get_tool_limits_and_is_agol(
            self, service_name="asyncServiceArea", tool_name="GenerateServiceAreas"):
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

        arcpy.AddMessage(f"Precalculating network location fields for facilities...")

        # Get location settings from config file if present
        search_tolerance = None
        if "searchTolerance" in SA_PROPS and "searchToleranceUnits" in SA_PROPS:
            search_tolerance = f"{SA_PROPS['searchTolerance']} {SA_PROPS['searchToleranceUnits'].name}"
        search_query = SA_PROPS.get("search_query", None)

        # Calculate network location fields if network data source is local
        arcpy.na.CalculateLocations(
            input_features, self.network_data_source,
            search_tolerance=search_tolerance,
            search_query=search_query,
            travel_mode=self.travel_mode
        )

    def _preprocess_inputs(self):
        """Preprocess the input feature classes to prepare them for use in the Service Area."""
        # Copy Facilities to a temporary location
        arcpy.AddMessage("Preprocessing facilities...")
        arcpy.conversion.FeatureClassToFeatureClass(
            self.facilities,
            os.path.dirname(self.temp_facilities),
            os.path.basename(self.temp_facilities)
        )

        # Precalculate network location fields for inputs
        if not self.is_service and self.should_precalc_network_locations:
            self._precalculate_network_locations(self.temp_facilities)
            for barrier_fc in self.barriers:
                self._precalculate_network_locations(barrier_fc)

    def _execute_solve(self):
        """Solve the Service Area analysis."""
        # Launch the parallel_sa script as a subprocess so it can spawn parallel processes. We have to do this because
        # a tool running in the Pro UI cannot call concurrent.futures without opening multiple instances of Pro.
        cwd = os.path.dirname(os.path.abspath(__file__))
        sa_inputs = [
            os.path.join(sys.exec_prefix, "python.exe"),
            os.path.join(cwd, "parallel_sa.py"),
            "--facilities", self.temp_facilities,
            "--output-polygons", self.output_polygons,
            "--network-data-source", self.network_data_source,
            "--travel-mode", self.travel_mode,
            "--cutoffs"] + [str(cutoff) for cutoff in self.cutoffs] + [
            "--time-units", self.time_units,
            "--travel-direction", self.travel_direction,
            "--geometry-at-cutoff", self.geometry_at_cutoff,
            "--geometry-at-overlap", self.geometry_at_overlap,
            "--max-processes", str(self.max_processes),
            "--time-window-start-day", self.time_window_start_day,
            "--time-window-start-time", self.time_window_start_time,
            "--time-window-end-day", self.time_window_end_day,
            "--time-window-end-time", self.time_window_end_time,
            "--time-increment", str(self.time_increment)
        ]
        if self.barriers:
            sa_inputs += ["--barriers"]
            sa_inputs += self.barriers
        # We do not want to show the console window when calling the command line tool from within our GP tool.
        # This can be done by setting this hex code.
        create_no_window = 0x08000000
        with subprocess.Popen(
            sa_inputs,
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
                arcpy.AddError("Service Area script failed.")

    def solve_service_areas_in_parallel(self):
        """Solve the Service Areas in parallel over a time window."""
        # Set the progressor so the user is informed of progress
        arcpy.SetProgressor("default")

        try:
            arcpy.SetProgressorLabel("Validating inputs...")
            self._validate_inputs()
            arcpy.AddMessage("Inputs successfully validated.")
        except Exception:  # pylint: disable=broad-except
            arcpy.AddError("Invalid inputs.")
            return

        # Preprocess inputs
        arcpy.SetProgressorLabel("Preprocessing inputs...")
        self._preprocess_inputs()
        arcpy.AddMessage("Inputs successfully preprocessed.")

        # Solve the analysis
        arcpy.SetProgressorLabel("Solving analysis in parallel...")
        self._execute_solve()

        # Delete temporary facilities (clean up)
        try:
            arcpy.management.Delete(self.temp_facilities)
        except Exception:  # pylint: disable=broad-except
            # If deletion doesn't work, just skip it. This does not need to kill the tool.
            pass
