############################################################################
## Tool name: Transit Network Analysis Tools
## Created by: Melinda Morang, Esri
## Last updated: 23 June 2021
############################################################################
"""Run a Service Area analysis incrementing the time of day over a time window.
Save the output polygons to a single feature class that can be used to generate
a time lapse video or run the Create Percent Access Polygons tool.

This script should be launched by the CreateTimeLapsePolygonsInParallel.py
script as a subprocess. It computes the Service Areas in parallel for all time
increments and saves the final output.

This version of the tool is for ArcGIS Pro only and solves the Service Areas in
parallel. It was built based off Esri's Solve Large OD Cost Matrix sample script
available from https://github.com/Esri/large-network-analysis-tools under an Apache
2.0 license.

Copyright 2021 Esri
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
# pylint: disable=logging-fstring-interpolation
from concurrent import futures
import os
import sys
import uuid
import logging
import shutil
import itertools
import time
import traceback
import argparse
import pandas as pd
from multiprocessing import Manager

import arcpy

# Import OD Cost Matrix settings from config file
from CreateTimeLapsePolygons_SA_config import SA_PROPS, SA_PROPS_SET_BY_TOOL
import AnalysisHelpers

arcpy.env.overwriteOutput = True

# Set logging for the main process.
# LOGGER logs everything from the main process to stdout using a specific format that the SolveLargeODCostMatrix tool
# can parse and write to the geoprocessing message feed.
LOG_LEVEL = logging.INFO  # Set to logging.DEBUG to see verbose debug messages
LOGGER = logging.getLogger(__name__)  # pylint:disable=invalid-name
LOGGER.setLevel(LOG_LEVEL)
console_handler = logging.StreamHandler(stream=sys.stdout)
console_handler.setLevel(LOG_LEVEL)
# Used by script tool to split message text from message level to add correct message type to GP window
console_handler.setFormatter(logging.Formatter("%(levelname)s" + AnalysisHelpers.MSG_STR_SPLITTER + "%(message)s"))
LOGGER.addHandler(console_handler)

DELETE_INTERMEDIATE_SA_OUTPUTS = True  # Set to False for debugging purposes


def run_gp_tool(tool, tool_args=None, tool_kwargs=None, log_to_use=LOGGER):
    """Run a geoprocessing tool with nice logging.

    The purpose of this function is simply to wrap the call to a geoprocessing tool in a way that we can log errors,
    warnings, and info messages as well as tool run time into our logging. This helps pipe the messages back to our
    script tool dialog.

    Args:
        tool (arcpy geoprocessing tool class): GP tool class command, like arcpy.management.CreateFileGDB
        tool_args (list, optional): Ordered list of values to use as tool arguments. Defaults to None.
        tool_kwargs (dictionary, optional): Dictionary of tool parameter names and values that can be used as named
            arguments in the tool command. Defaults to None.
        log_to_use (logging.logger, optional): logger class to use for messages. Defaults to LOGGER. When calling this
            from the ODCostMatrix class, use self.logger instead so the messages go to the processes's log file instead
            of stdout.

    Returns:
        GP result object: GP result object returned from the tool run.

    Raises:
        arcpy.ExecuteError if the tool fails
    """
    # Try to retrieve and log the name of the tool
    tool_name = repr(tool)
    try:
        tool_name = tool.__esri_toolname__
    except Exception:  # pylint: disable=broad-except
        try:
            tool_name = tool.__name__
        except Exception:  # pylint: disable=broad-except
            # Probably the tool didn't have an __esri_toolname__ property or __name__. Just don't worry about it.
            pass
    log_to_use.debug(f"Running geoprocessing tool {tool_name}...")

    # Try running the tool, and log all messages
    try:
        if tool_args is None:
            tool_args = []
        if tool_kwargs is None:
            tool_kwargs = {}
        result = tool(*tool_args, **tool_kwargs)
        info_msgs = [msg for msg in result.getMessages(0).splitlines() if msg]
        warning_msgs = [msg for msg in result.getMessages(1).splitlines() if msg]
        for msg in info_msgs:
            log_to_use.debug(msg)
        for msg in warning_msgs:
            log_to_use.warning(msg)
    except arcpy.ExecuteError:
        log_to_use.error(f"Error running geoprocessing tool {tool_name}.")
        # First check if it's a tool error and if so, handle warning and error messages.
        info_msgs = [msg for msg in arcpy.GetMessages(0).strip("\n").splitlines() if msg]
        warning_msgs = [msg for msg in arcpy.GetMessages(1).strip("\n").splitlines() if msg]
        error_msgs = [msg for msg in arcpy.GetMessages(2).strip("\n").splitlines() if msg]
        for msg in info_msgs:
            log_to_use.debug(msg)
        for msg in warning_msgs:
            log_to_use.warning(msg)
        for msg in error_msgs:
            log_to_use.error(msg)
        raise
    except Exception:
        # Unknown non-tool error
        log_to_use.error(f"Error running geoprocessing tool {tool_name}.")
        errs = traceback.format_exc().splitlines()
        for err in errs:
            log_to_use.error(err)
        raise

    log_to_use.debug(f"Finished running geoprocessing tool {tool_name}.")
    return result


class ServiceArea:  # pylint:disable = too-many-instance-attributes
    """Used for solving a Service Area in parallel for a designated time of day."""

    def __init__(self, **kwargs):
        """Initialize the Service Area analysis for the given inputs.

        Expected arguments:
        - facilities
        - network_data_source
        - travel_mode
        - time_units
        - cutoffs
        - travel_direction
        - geometry_at_cutoff
        - geometry_at_overlap
        - output_folder
        - barriers
        """
        self.facilities = kwargs["facilities"]
        self.network_data_source = kwargs["network_data_source"]
        self.travel_mode = kwargs["travel_mode"]
        self.time_units = kwargs["time_units"]
        self.cutoffs = kwargs["cutoffs"]
        self.travel_direction = kwargs["travel_direction"]
        self.geometry_at_cutoff = kwargs["geometry_at_cutoff"]
        self.geometry_at_overlap = kwargs["geometry_at_overlap"]
        self.output_folder = kwargs["output_folder"]
        self.barriers = []
        if "barriers" in kwargs:
            self.barriers = kwargs["barriers"]

        # Create a job ID and a folder and scratch gdb for this job
        self.job_id = uuid.uuid4().hex
        self.job_folder = os.path.join(self.output_folder, self.job_id)
        os.mkdir(self.job_folder)
        self.od_workspace = os.path.join(self.job_folder, "scratch.gdb")

        # Setup the class logger. Logs for each parallel process are not written to the console but instead to a
        # process-specific log file.
        self.log_file = os.path.join(self.job_folder, 'ServiceArea.log')
        cls_logger = logging.getLogger("ServiceArea_" + self.job_id)
        self.setup_logger(cls_logger)
        self.logger = cls_logger

        # Set up other instance attributes
        self.is_service = AnalysisHelpers.is_nds_service(self.network_data_source)
        self.sa_solver = None

        # Create a network dataset layer
        self.nds_layer_name = "NetworkDatasetLayer"
        if not self.is_service:
            self._make_nds_layer()
            self.network_data_source = self.nds_layer_name

        # Prepare a dictionary to store info about the analysis results
        self.job_result = {
            "jobId": self.job_id,
            "jobFolder": self.job_folder,
            "solveSucceeded": False,
            "solveMessages": "",
            "logFile": self.log_file
        }

    def _make_nds_layer(self):
        """Create a network dataset layer if one does not already exist."""
        if self.is_service:
            return
        if arcpy.Exists(self.nds_layer_name):
            self.logger.debug(f"Using existing network dataset layer: {self.nds_layer_name}")
        else:
            self.logger.debug("Creating network dataset layer...")
            run_gp_tool(
                arcpy.na.MakeNetworkDatasetLayer,
                [self.network_data_source, self.nds_layer_name],
                log_to_use=self.logger
            )

    def initialize_sa_solver(self, time_of_day=None):
        """Initialize a Service Area solver object and set properties."""
        # For a local network dataset, we need to checkout the Network Analyst extension license.
        if not self.is_service:
            arcpy.CheckOutExtension("network")

        # Create a new Service Area object
        self.logger.debug("Creating Service Area object...")
        self.sa_solver = arcpy.nax.ServiceArea(self.network_data_source)

        # Set the OD cost matrix analysis properties.
        # Read properties from the CreateTimeLapsePolygons_SA_config.py config file for all properties not set in
        # the UI as parameters.
        # SA properties documentation: https://pro.arcgis.com/en/pro-app/latest/arcpy/network-analyst/servicearea.htm
        # The properties have been extracted to the config file to make them easier to find and set so users don't have
        # to dig through the code to change them.
        self.logger.debug("Setting Service Area analysis properties from SA config file...")
        for prop in SA_PROPS:
            if prop in SA_PROPS_SET_BY_TOOL:
                self.logger.warning(
                    f"SA config file property {prop} is handled explicitly by the tool parameters and will be ignored."
                )
                continue
            try:
                setattr(self.sa_solver, prop, SA_PROPS[prop])
            except Exception as ex:  # pylint: disable=broad-except
                self.logger.warning(f"Failed to set property {prop} from SA config file. Default will be used instead.")
                self.logger.warning(str(ex))
        # Set properties explicitly specified in the tool UI as arguments
        self.logger.debug("Setting Service Area analysis properties specified tool inputs...")
        self.sa_solver.travelMode = self.travel_mode
        self.sa_solver.timeUnits = self.time_units
        self.sa_solver.defaultImpedanceCutoffs = self.cutoffs
        self.sa_solver.travelDirection = self.travel_direction
        self.sa_solver.geometryAtCutoff = self.geometry_at_cutoff
        self.sa_solver.geometryAtOverlap = self.geometry_at_overlap
        # Set time of day, which is passed in as an OD solve parameter from our chunking mechanism
        self.sa_solver.timeOfDay = time_of_day

        # Ensure the travel mode has impedance units that are time-based.
        self._validate_travel_mode()

    def _validate_travel_mode(self):
        """Validate that the travel mode has time units.

        Raises:
            ValueError: If the travel mode's impedance units are not time based.
        """
        # Get the travel mode object from the already-instantiated OD solver object. This saves us from having to parse
        # the user's input travel mode from its string name, object, or json representation.
        travel_mode = self.sa_solver.travelMode
        impedance = travel_mode.impedance
        time_attribute = travel_mode.timeAttributeName
        if impedance != time_attribute:
            err = f"The impedance units of the selected travel mode {travel_mode.name} are not time based."
            self.logger.error(err)
            raise ValueError(err)

    def solve(self, time_of_day):
        """Create and solve a Service Area analysis for the designated time of day.

        Args:
            time_of_day (datetime): Time of day for this solve
        """
        # Initialize the OD solver object
        self.initialize_od_solver(time_of_day)

        # Load the facilities
        self.logger.debug("Loading facilities...")
        facilities_field_mappings = self.sa_solver.fieldMappings(
            arcpy.nax.ServiceAreaInputDataType.Facilities,
            True  # Use network location fields
        )
        self.sa_solver.load(
            arcpy.nax.ServiceAreaInputDataType.Facilities,
            self.facilities,
            facilities_field_mappings,
            False
        )

        # Load barriers
        for barrier_fc in self.barriers:
            self.logger.debug(f"Loading barriers feature class {barrier_fc}...")
            shape_type = arcpy.Describe(barrier_fc).shapeType
            if shape_type == "Polygon":
                class_type = arcpy.nax.ServiceAreaInputDataType.PolygonBarriers
            elif shape_type == "Polyline":
                class_type = arcpy.nax.ServiceAreaInputDataType.LineBarriers
            elif shape_type == "Point":
                class_type = arcpy.nax.ServiceAreaInputDataType.PointBarriers
            else:
                self.logger.warning(
                    f"Barrier feature class {barrier_fc} has an invalid shape type and will be ignored."
                )
                continue
            barriers_field_mappings = self.sa_solver.fieldMappings(class_type, True)
            self.sa_solver.load(class_type, barrier_fc, barriers_field_mappings, True)

        # Solve the Service Area analysis
        self.logger.debug("Solving Service Area...")
        solve_start = time.time()
        solve_result = self.sa_solver.solve()
        solve_end = time.time()
        self.logger.debug(f"Solving Service Area completed in {round(solve_end - solve_start, 3)} (seconds).")

        # Handle solve messages
        solve_msgs = [msg[-1] for msg in solve_result.solverMessages(arcpy.nax.MessageSeverity.All)]
        initial_num_msgs = len(solve_msgs)
        for msg in solve_msgs:
            self.logger.debug(msg)
        ## TODO: See if there is a Service Area equivalent
        # # Remove repetitive messages so they don't clog up the stdout pipeline when running the tool
        # # 'No "Destinations" found for "Location 1" in "Origins".' is a common message that tends to be repeated and is
        # # not particularly useful to see in bulk.
        # # Note that this will not work for localized software when this message is translated.
        # common_msg_prefix = 'No "Destinations" found for '
        # solve_msgs = [msg for msg in solve_msgs if not msg.startswith(common_msg_prefix)]
        # num_msgs_removed = initial_num_msgs - len(solve_msgs)
        # if num_msgs_removed:
        #     self.logger.debug(f"Repetitive messages starting with {common_msg_prefix} were consolidated.")
        #     solve_msgs.append(f"No destinations were found for {num_msgs_removed} origins.")
        # solve_msgs = "\n".join(solve_msgs)

        # Update the result dictionary
        self.job_result["solveMessages"] = solve_msgs
        if not solve_result.solveSucceeded:
            self.logger.debug("Solve failed.")
            return
        self.logger.debug("Solve succeeded.")
        self.job_result["solveSucceeded"] = True

        ## TODO: Save Service Area polygons to output feature classes

        self.logger.debug("Finished calculating Service Area.")

    def setup_logger(self, logger_obj):
        """Set up the logger used for logging messages for this process. Logs are written to a text file.

        Args:
            logger_obj: The logger instance.
        """
        logger_obj.setLevel(logging.DEBUG)
        if len(logger_obj.handlers) <= 1:
            file_handler = logging.FileHandler(self.log_file)
            file_handler.setLevel(logging.DEBUG)
            logger_obj.addHandler(file_handler)
            formatter = logging.Formatter("%(process)d | %(message)s")
            file_handler.setFormatter(formatter)
            logger_obj.addHandler(file_handler)


def solve_service_area(inputs, time_of_day):
    """Solve a Service Area analysis for the given time of day.

    Args:
        inputs (dict): Dictionary of keyword inputs suitable for initializing the ServiceArea class
        time_of_day (datetime.datetime): Start time and date for the Service Area

    Returns:
        dict: Dictionary of results from the ServiceArea class
    """
    sa = ServiceArea(**inputs)
    sa.logger.info((
        f"Processing start time {time_of_day} as job id {sa.job_id}"
    ))
    sa.solve(time_of_day)
    return sa.job_result


class ParallelSACalculator():
    """Solves a Service Area incrementally over a time window solving in parallel and combining results."""

    def __init__(  # pylint: disable=too-many-locals, too-many-arguments
        self, facilities, output_polygons, network_data_source, travel_mode, cutoffs, time_units,
        time_window_start_day, time_window_start_time, time_window_end_day, time_window_end_time, time_increment,
        travel_direction, geometry_at_cutoff, geometry_at_overlap, max_processes, barriers=None
    ):
        """Compute Service Areas around facilities in parallel for all increments in the time window and save the output
        polygons to the designated feature class.

        This class assumes that the inputs have already been pre-processed and validated.

        Args:
            facilities (str): Catalog path to facilities
            output_polygons (str): Catalog path to output polygons
            network_data_source (str): Network data source catalog path or URL
            travel_mode (str): String-based representation of a travel mode (name or JSON)
            cutoffs (list(float)): List of cutoffs for the Service Areas. Interpreted in time_units.
            time_units (str): String representation of time units
            time_window_start_day (str): English weekday name or YYYYMMDD date representing the weekday or start date of
                the time window
            time_window_start_time (str): HHMM time of day for the start of the time window
            time_window_end_day (str): English weekday name or YYYYMMDD date representing the weekday or end date of
                the time window
            time_window_end_time (str): HHMM time of day for the end of the time window
            time_increment (int): Number of minutes between each run of the OD Cost Matrix in the time window
            travel_direction (str): String representation of the travel direction (to or from facilities)
            geometry_at_cutoff (str): String representation of the geometry at cutoffs (rings or disks)
            geometry_at_overlap (str): String representation of the geometry at overlap (split, overlap, dissolve)
            max_processes (int): Maximum number of parallel processes allowed
            barriers (list(str), optional): List of catalog paths to point, line, and polygon barriers to use.
                Defaults to None.
        """
        self.facilities = facilities
        time_units = AnalysisHelpers.convert_time_units_str_to_enum(time_units)
        if not barriers:
            barriers = []
        self.max_processes = max_processes

        # Validate time window inputs and convert them into a list of times of day to run the analysis
        try:
            self.start_times = AnalysisHelpers.make_analysis_time_of_day_list(
                time_window_start_day, time_window_end_day, time_window_start_time, time_window_end_time,
                time_increment
            )
        except Exception as ex:
            err = "Error parsing input time window."
            LOGGER.error(err)
            LOGGER.error(str(ex))
            raise ValueError from ex

        # Scratch folder to store intermediate outputs from the OD Cost Matrix processes
        unique_id = uuid.uuid4().hex
        self.scratch_folder = os.path.join(
            arcpy.env.scratchFolder, "CalcAccMtx_" + unique_id)  # pylint: disable=no-member
        LOGGER.info(f"Intermediate outputs will be written to {self.scratch_folder}.")
        os.mkdir(self.scratch_folder)

        # Set up a where clause to eliminate destinations that will never contribute any values to the final solution.
        # Only applies if we're using a weight field.
        if self.weight_field:
            self.dest_where = f"{self.weight_field} IS NOT NULL and {self.weight_field} <> 0"
        else:
            self.dest_where = ""

        # Initialize the dictionary of inputs to send to each OD solve
        self.od_inputs = {
            "origins": self.origins,
            "destinations": self.destinations,
            "destination_where_clause": self.dest_where,
            "network_data_source": network_data_source,
            "travel_mode": travel_mode,
            "output_folder": self.scratch_folder,
            "time_units": time_units,
            "cutoff": cutoff,
            "barriers": barriers
        }

        # Construct OID ranges for chunks of origins and destinations
        origin_ranges = self._get_oid_ranges_for_input(self.origins, max_origins)
        destination_ranges = self._get_oid_ranges_for_input(self.destinations, max_destinations, self.dest_where)

        # Construct chunks consisting of (range of origin oids, range of destination oids, start time)
        self.chunks = itertools.product(origin_ranges, destination_ranges, self.start_times)
        # Calculate the total number of jobs to use in logging
        self.total_jobs = len(origin_ranges) * len(destination_ranges) * len(self.start_times)

    def _validate_od_settings(self):
        """Validate OD cost matrix settings before spinning up a bunch of parallel processes doomed to failure."""
        # Create a dummy ODCostMatrix object, initialize an OD solver object, and set properties. This allows us to
        # detect any errors prior to spinning up a bunch of parallel processes and having them all fail.
        LOGGER.debug("Validating OD Cost Matrix settings...")
        sa = None
        try:
            sa = ODCostMatrix(**self.od_inputs)
            sa.initialize_od_solver()
            LOGGER.debug("OD Cost Matrix settings successfully validated.")
        except Exception:
            LOGGER.error("Error initializing OD Cost Matrix analysis.")
            errs = traceback.format_exc().splitlines()
            for err in errs:
                LOGGER.error(err)
            raise
        finally:
            if sa:
                LOGGER.debug("Deleting temporary test OD Cost Matrix job folder...")
                shutil.rmtree(sa.job_result["jobFolder"], ignore_errors=True)
                del sa

    @staticmethod
    def _get_oid_ranges_for_input(input_fc, max_chunk_size, where=""):
        """Construct ranges of ObjectIDs for use in where clauses to split large data into chunks.

        Args:
            input_fc (str, layer): Data that needs to be split into chunks
            max_chunk_size (int): Maximum number of rows that can be in a chunk
            where (str, optional): Where clause to use to filter data before chunking. Defaults to "".

        Returns:
            list: list of ObjectID ranges for the current dataset representing each chunk. For example,
                [[1, 1000], [1001, 2000], [2001, 2478]] represents three chunks of no more than 1000 rows.
        """
        ranges = []
        num_in_range = 0
        current_range = [0, 0]
        # Loop through all OIDs of the input and construct tuples of min and max OID for each chunk
        # We do it this way and not by straight-up looking at the numerical values of OIDs to account
        # for definition queries, selection sets, or feature layers with gaps in OIDs
        for row in arcpy.da.SearchCursor(input_fc, "OID@", where):  # pylint: disable=no-member
            oid = row[0]
            if num_in_range == 0:
                # Starting new range
                current_range[0] = oid
            # Increase the count of items in this range and set the top end of the range to the current oid
            num_in_range += 1
            current_range[1] = oid
            if num_in_range == max_chunk_size:
                # Finishing up a chunk
                ranges.append(current_range)
                # Reset range trackers
                num_in_range = 0
                current_range = [0, 0]
        # After looping, close out the last range if we still have one open
        if current_range != [0, 0]:
            ranges.append(current_range)

        return ranges

    def solve_od_in_parallel(self):
        """Solve the OD Cost Matrix in chunks and post-process the results."""
        # Validate OD Cost Matrix settings. Essentially, create a dummy ODCostMatrix class instance and set up the
        # solver object to ensure this at least works. Do this up front before spinning up a bunch of parallel processes
        # the optimized that are guaranteed to all fail.
        self._validate_od_settings()

        # The multiprocessing module's Manager allows us to share a managed dictionary across processes, including
        # writing to it. This allows us to track which destinations are accessible to each origin and for how many of
        # our start times without having to write out and post-process a bunch of tables.
        with Manager() as manager:
            # Initialize a special dictionary of {(Origin OID, Destination OID): Number of times reached} that will be
            # shared across processes
            shared_dict = manager.dict({})
            for row_o in arcpy.da.SearchCursor(self.origins, ["OID@"]):  # pylint: disable=no-member
                for row_d in arcpy.da.SearchCursor(self.destinations, ["OID@"]):  # pylint: disable=no-member
                    shared_dict[(row_o[0], row_d[0])] = 0

            # Compute OD cost matrix in parallel
            LOGGER.info("Solving OD Cost Matrix chunks in parallel...")
            completed_jobs = 0  # Track the number of jobs completed so far to use in logging
            # Use the concurrent.futures ProcessPoolExecutor to spin up parallel processes that solve the OD cost
            # matrices
            with futures.ProcessPoolExecutor(max_workers=self.max_processes) as executor:
                # Each parallel process calls the solve_od_cost_matrix() function with the od_inputs dictionary for the
                # given origin and destination OID ranges and time of day.
                jobs = {executor.submit(
                    solve_od_cost_matrix, self.od_inputs, shared_dict, chunks): chunks for chunks in self.chunks}
                # As each job is completed, add some logging information and store the results to post-process later
                for future in futures.as_completed(jobs):
                    completed_jobs += 1
                    LOGGER.info(
                        f"Finished OD Cost Matrix calculation {completed_jobs} of {self.total_jobs}.")
                    try:
                        # The OD cost matrix job returns a results dictionary. Retrieve it.
                        result = future.result()
                    except Exception:
                        # If we couldn't retrieve the result, some terrible error happened. Log it.
                        LOGGER.error("Failed to get OD Cost Matrix result from parallel processing.")
                        errs = traceback.format_exc().splitlines()
                        for err in errs:
                            LOGGER.error(err)
                        raise

                    # Log failed solves
                    if not result["solveSucceeded"]:
                        LOGGER.warning(f"Solve failed for job id {result['jobId']}")
                        msgs = result["solveMessages"]
                        LOGGER.warning(msgs)

            # Calculate statistics from the results of the OD Cost Matrix calculations present in the shared dictionary
            # and write them to the output fields in the Origins table.
            self._add_results_to_output(shared_dict)

        # Cleanup
        # Delete the job folders if the job succeeded
        if DELETE_INTERMEDIATE_OD_OUTPUTS:
            LOGGER.info("Deleting intermediate outputs...")
            try:
                shutil.rmtree(self.scratch_folder, ignore_errors=True)
            except Exception:  # pylint: disable=broad-except
                # If deletion doesn't work, just throw a warning and move on. This does not need to kill the tool.
                LOGGER.warning(f"Unable to delete intermediate OD Cost Matrix output folder {self.scratch_folder}.")

        LOGGER.info("Finished calculating OD Cost Matrices.")

    def _add_results_to_output(self, shared_dict):
        """Calculate accessibility statistics and write them to the Origins table.

        Args:
            shared_dict (Managed dict): Multiprocessing managed dictionary of
                {(OriginOID, DestinationOID): times reached}
        """
        LOGGER.info("Calculating statistics for final output...")

        if self.weight_field:
            # Convert the shared dictionary to a pandas dataframe for easier processing
            result_df = pd.DataFrame.from_records(
                [(key[0], key[1], shared_dict[key]) for key in shared_dict],
                columns=["OriginOID", "DestinationOID", "TimesReached"]
            )
            # Delete the shared dictionary to clear up memory
            del shared_dict

            # Read in the weight field values and join them into the result table
            LOGGER.debug("Joining weight field from destinations to results dataframe...")
            with arcpy.da.SearchCursor(  # pylint: disable=no-member
                    self.destinations, ["OID@", self.weight_field]) as cur:
                w_df = pd.DataFrame(cur, columns=["DestinationOID", "Weight"])

            # Calculate the total number of destinations based on weight and store this for later use
            total_dests = w_df["Weight"].sum()

            # Join the Weight field into the results dataframe
            w_df.set_index("DestinationOID", inplace=True)
            result_df = result_df.join(w_df, "DestinationOID")
            del w_df

            # We don't need this field anymore
            result_df.drop(["DestinationOID"], axis="columns", inplace=True)

        else:
            # Convert the shared dictionary to a pandas dataframe for easier processing
            # Don't bother reading in the DestinationOID field at all for this case since we don't need it for anything.
            result_df = pd.DataFrame.from_records(
                [(key[0], shared_dict[key]) for key in shared_dict],
                columns=["OriginOID", "TimesReached"]
            )
            # Delete the shared dictionary to clear up memory
            del shared_dict

            # Count every row as 1 since we're not using a weight field
            result_df["Weight"] = 1

            # Set the total number of destinations to the number of rows in the destinations table.
            total_dests = int(arcpy.management.GetCount(self.destinations).getOutput(0))

        # Create the output dataframe indexed by the OriginOID
        LOGGER.debug("Creating output dataframe indexed by OriginOID...")
        unique = result_df["OriginOID"].unique()
        output_df = pd.DataFrame(unique, columns=["OriginOID"])
        del unique
        output_df.set_index("OriginOID", inplace=True)

        # Calculate the total destinations found for each origin using the weight field
        LOGGER.debug("Calculating TotalDests and PercDests...")
        output_df["TotalDests"] = result_df[result_df["TimesReached"] > 0].groupby("OriginOID")["Weight"].sum()
        # Calculate the percentage of destinations reached
        output_df["PercDests"] = 100.0 * output_df["TotalDests"] / total_dests

        # Calculate the number of destinations accessible at different thresholds
        LOGGER.debug("Calculating the number of destinations accessible at different thresholds...")
        for perc in range(10, 100, 10):
            total_field = f"DsAL{perc}Perc"
            perc_field = f"PsAL{perc}Perc"
            threshold = len(self.start_times) * perc / 100
            output_df[total_field] = result_df[result_df["TimesReached"] >= threshold].groupby(
                "OriginOID")["Weight"].sum()
            output_df[perc_field] = 100.0 * output_df[total_field] / total_dests
        # Fill empty cells with 0
        output_df.fillna(0, inplace=True)
        # Clean up
        del result_df

        # Write the calculated values to output
        output_df = output_df.to_records()
        arcpy.da.ExtendTable(  # pylint: disable=no-member
            self.origins, arcpy.Describe(self.origins).oidFieldName, output_df, "OriginOID", False)

        LOGGER.info(f"Accessibility statistics fields were added to Origins table {self.origins}.")


def launch_parallel_od():
    """Read arguments passed in via subprocess and run the parallel OD Cost Matrix.

    This script is intended to be called via subprocess via the CalculateAccessibilityMatrixInParallel.py module, which
    does essential preprocessing and validation. Users should not call this script directly from the command line.

    We must launch this script via subprocess in order to support parallel processing from an ArcGIS Pro script tool,
    which cannot do parallel processing directly.
    """
    # Create the parser
    parser = argparse.ArgumentParser(description=globals().get("__doc__", ""), fromfile_prefix_chars='@')

    # Define Arguments supported by the command line utility

    # --origins parameter
    help_string = "The full catalog path to the feature class containing the origins. Output fields will be added."
    parser.add_argument("-o", "--origins", action="store", dest="origins", help=help_string, required=True)

    # --destinations parameter
    help_string = "The full catalog path to the feature class containing the destinations."
    parser.add_argument("-d", "--destinations", action="store", dest="destinations", help=help_string, required=True)

    # --network-data-source parameter
    help_string = "The full catalog path to the network dataset or a portal url that will be used for the analysis."
    parser.add_argument(
        "-n", "--network-data-source", action="store", dest="network_data_source", help=help_string, required=True)

    # --travel-mode parameter
    help_string = (
        "The name or JSON string representation of the travel mode from the network data source that will be used for "
        "the analysis."
    )
    parser.add_argument("-tm", "--travel-mode", action="store", dest="travel_mode", help=help_string, required=True)

    # --time-units parameter
    help_string = "String name of the time units for the analysis. These units will be used in the output."
    parser.add_argument("-tu", "--time-units", action="store", dest="time_units", help=help_string, required=True)

    # --max-origins parameter
    help_string = (
        "Maximum number of origins that can be in one chunk for parallel processing of OD Cost Matrix solves. "
        "For example, 1000 means that a chunk consists of no more than 1000 origins and max-destination destinations."
    )
    parser.add_argument(
        "-mo", "--max-origins", action="store", dest="max_origins", type=int, help=help_string, required=True)

    # --max-destinations parameter
    help_string = (
        "Maximum number of destinations that can be in one chunk for parallel processing of OD Cost Matrix solves. "
        "For example, 1000 means that a chunk consists of no more than max-origin origins and 1000 destinations."
    )
    parser.add_argument(
        "-md", "--max-destinations", action="store", dest="max_destinations", type=int, help=help_string, required=True)

    # --max-processes parameter
    help_string = "Maximum number parallel processes to use for the OD Cost Matrix solves."
    parser.add_argument(
        "-mp", "--max-processes", action="store", dest="max_processes", type=int, help=help_string, required=True)

    # --time-window-start-day parameter
    help_string = "Time window start day of week or YYYYMMDD date."
    parser.add_argument("-twsd", "--time-window-start-day", action="store", dest="time_window_start_day",
                        help=help_string, required=True)

    # --time-window-start-time parameter
    help_string = "Time window start time as hh:mm."
    parser.add_argument("-twst", "--time-window-start-time", action="store", dest="time_window_start_time",
                        help=help_string, required=True)

    # --time-window-end-day parameter
    help_string = "Time window end day of week or YYYYMMDD date."
    parser.add_argument("-twed", "--time-window-end-day", action="store", dest="time_window_end_day",
                        help=help_string, required=True)

    # --time-window-end-time parameter
    help_string = "Time window end time as hh:mm."
    parser.add_argument("-twet", "--time-window-end-time", action="store", dest="time_window_end_time",
                        help=help_string, required=True)

    # --time-increment
    help_string = "Time increment in minutes"
    parser.add_argument("-ti", "--time-increment", action="store", dest="time_increment", type=int,
                        help=help_string, required=True)

    # --cutoff parameter
    help_string = (
        "Impedance cutoff to limit the OD cost matrix search distance. Should be specified in the same units as the "
        "time-units parameter if the travel mode's impedance is in units of time or in the same units as the "
        "distance-units parameter if the travel mode's impedance is in units of distance. Otherwise, specify this in "
        "the units of the travel mode's impedance attribute."
    )
    parser.add_argument(
        "-co", "--cutoff", action="store", dest="cutoff", type=float, help=help_string, required=True)

    # --weight-field parameter
    help_string = "The name of the field in the input destinations that indicates the destination's weight."
    parser.add_argument(
        "-wf", "--weight-field", action="store", dest="weight_field", help=help_string, required=False)

    # --barriers parameter
    help_string = "A list of catalog paths to the feature classes containing barriers to use in the OD Cost Matrix."
    parser.add_argument(
        "-b", "--barriers", action="store", dest="barriers", help=help_string, nargs='*', required=False)

    # Get arguments as dictionary.
    args = vars(parser.parse_args())

    # Initialize a parallel OD Cost Matrix calculator class
    od_calculator = ParallelODCalculator(**args)
    # Solve the OD Cost Matrix in parallel chunks
    start_time = time.time()
    od_calculator.solve_od_in_parallel()
    LOGGER.info(f"Parallel OD Cost Matrix calculation completed in {round((time.time() - start_time) / 60, 2)} minutes")


if __name__ == "__main__":
    # This script should always be launched via subprocess as if it were being called from the command line.
    launch_parallel_od()
