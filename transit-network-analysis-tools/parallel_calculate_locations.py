"""Calculate the network locations for a large dataset by chunking the
inputs and solving in parallel.

This is a sample script users can modify to fit their specific needs.

Note: Unlike in the core Calculate Locations tool, this tool generates
a new feature class instead of merely adding fields to the original.
A new feature class must be generated during the parallel processing,
and as a result, the ObjectIDs may change, so we ask the user to specify
an output feature class path instead of overwriting the original.  If you
need the original ObjectIDs, please calculate an additional field to track
them before calling this tool.  We also do this to avoid accidentally deleting
the user's original data if the tool errors.

This script is intended to be called as a subprocess from a other scripts
so that it can launch parallel processes with concurrent.futures. It must be
called as a subprocess because the main script tool process, when running
within ArcGIS Pro, cannot launch parallel subprocesses on its own.

This script should not be called directly from the command line.

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
# pylint: disable=logging-fstring-interpolation
import os
import uuid
import logging
import shutil
import time
import traceback
import argparse

import arcpy

import AnalysisHelpers

DELETE_INTERMEDIATE_OUTPUTS = True  # Set to False for debugging purposes

# Change logging.INFO to logging.DEBUG to see verbose debug messages
LOGGER = AnalysisHelpers.configure_global_logger(logging.INFO)


class LocationCalculator(
    AnalysisHelpers.JobFolderMixin, AnalysisHelpers.LoggingMixin, AnalysisHelpers.MakeNDSLayerMixin
):  # pylint:disable = too-many-instance-attributes
    """Used for calculating network locations for a designated chunk of the input datasets."""

    def __init__(self, **kwargs):
        """Initialize the location calculator for the given inputs.

        Expected arguments:
        - input_fc
        - network_data_source
        - travel_mode
        - search_tolerance
        - search_criteria
        - search_query
        - scratch_folder
        """
        self.input_fc = kwargs["input_fc"]
        self.network_data_source = kwargs["network_data_source"]
        self.travel_mode = kwargs["travel_mode"]
        self.scratch_folder = kwargs["scratch_folder"]
        self.search_tolerance = kwargs.get("search_tolerance", None)
        self.search_criteria = kwargs.get("search_criteria", None)
        self.search_query = kwargs.get("search_query", None)

        # Create a job ID and a folder for this job
        self._create_job_folder()

        # Setup the class logger. Logs for each parallel process are not written to the console but instead to a
        # process-specific log file.
        self.setup_logger("CalcLocs")

        # Create a network dataset layer if needed
        self._make_nds_layer()

        # Define output feature class path for this chunk (set during feature selection)
        self.out_fc = None

        # Prepare a dictionary to store info about the analysis results
        self.job_result = {
            "jobId": self.job_id,
            "jobFolder": self.job_folder,
            "outputFC": "",
            "oidRange": None,
            "logFile": self.log_file
        }

    def _subset_inputs(self, oid_range):
        """Create a layer from the input feature class that contains only the OIDs for this chunk.

        Args:
            oid_range (list): Input feature class ObjectID range to select for this chunk
        """
        # Copy the subset of features in this OID range to a feature class in the job gdb so we can calculate locations
        # on it without interference from other parallel processes
        self.logger.debug("Subsetting features for this chunk...")
        out_gdb = self._create_output_gdb()
        self.out_fc = os.path.join(out_gdb, f"Locs_{oid_range[0]}_{oid_range[1]}")
        oid_field_name = arcpy.Describe(self.input_fc).oidFieldName
        where_clause = (
            f"{oid_field_name} >= {oid_range[0]} "
            f"And {oid_field_name} <= {oid_range[1]}"
        )
        self.logger.debug(f"Where clause: {where_clause}")
        arcpy.conversion.FeatureClassToFeatureClass(
            self.input_fc,
            os.path.dirname(self.out_fc),
            os.path.basename(self.out_fc),
            where_clause
        )

    def calculate_locations(self, oid_range):
        """Calculate locations for a chunk of the input feature class with the designated OID range."""
        self._subset_inputs(oid_range)
        self.logger.debug("Calculating locations...")
        AnalysisHelpers.run_gp_tool(
            self.logger,
            arcpy.na.CalculateLocations,
            [
                self.out_fc,
                self.network_data_source
            ], {
                "search_tolerance": self.search_tolerance,
                "search_criteria": self.search_criteria,
                "search_query": self.search_query,
                "travel_mode": self.travel_mode
            }
        )
        self.job_result["outputFC"] = self.out_fc
        self.job_result["oidRange"] = tuple(oid_range)


def calculate_locations_for_chunk(chunk, calc_locs_settings):
    """Calculate locations for a range of OIDs in the input dataset.

    Args:
        chunk (list): OID range to calculate locations for. Specified as a list of [start range, end range], inclusive.
        calc_locs_settings (dict): Dictionary of kwargs for the LocationCalculator class.

    Returns:
        dict: Dictionary of job results for the chunk
    """
    location_calculator = LocationCalculator(**calc_locs_settings)
    location_calculator.calculate_locations(chunk)
    location_calculator.teardown_logger()
    return location_calculator.job_result


class ParallelLocationCalculator:
    """Calculate network locations for a large dataset by chunking the dataset and calculating in parallel."""

    def __init__(  # pylint: disable=too-many-locals, too-many-arguments
        self, input_features, output_features, network_data_source, chunk_size, max_processes,
        travel_mode=None, search_tolerance=None, search_criteria=None, search_query=None
    ):
        """Calculate network locations for the input features in parallel.

        Run the Calculate Locations tool on chunks of the input dataset in parallel and and recombine the results.
        Refer to the Calculate Locations tool documentation for more information about the input parameters.
        https://pro.arcgis.com/en/pro-app/latest/tool-reference/network-analyst/calculate-locations.htm

        Args:
            input_features (str): Catalog path to input features to calculate locations for
            output_features (str): Catalog path to the location where the output updated feature class will be saved.
                Unlike in the core Calculate Locations tool, this tool generates a new feature class instead of merely
                adding fields to the original.  A new feature class must be generated during the parallel processing,
                and as a result, the ObjectIDs may change, so we ask the user to specify an output feature class path
                instead of overwriting the original.  If you need the original ObjectIDs, please calculate an additional
                field to track them before calling this tool.
            network_data_source (str): Network data source catalog path
            chunk_size (int): Maximum features to be processed in one chunk
            max_processes (int): Maximum number of parallel processes allowed
            travel_mode (str, optional): String-based representation of a travel mode (name or JSON)
            search_tolerance (str, optional): Linear Unit string representing the search distance to use when locating
            search_criteria (list, optional): Defines the network sources that can be used for locating
            search_query (list, optional): Defines queries to use per network source when locating.
        """
        self.input_features = input_features
        self.output_features = output_features
        self.max_processes = max_processes

        # Scratch folder to store intermediate outputs from the OD Cost Matrix processes
        unique_id = uuid.uuid4().hex
        self.scratch_folder = os.path.join(
            arcpy.env.scratchFolder, "CalcLocs_" + unique_id)  # pylint: disable=no-member
        LOGGER.info(f"Intermediate outputs will be written to {self.scratch_folder}.")
        os.mkdir(self.scratch_folder)

        # Dictionary of static input settings to send to the parallel location calculator
        self.calc_locs_inputs = {
            "input_fc": self.input_features,
            "network_data_source": network_data_source,
            "travel_mode": travel_mode,
            "search_tolerance": search_tolerance,
            "search_criteria": search_criteria,
            "search_query": search_query,
            "scratch_folder": self.scratch_folder
        }

        # List of intermediate output feature classes created by each process
        self.temp_out_fcs = {}

        # Construct OID ranges for the input data chunks
        self.ranges = AnalysisHelpers.get_oid_ranges_for_input(self.input_features, chunk_size)

    def calc_locs_in_parallel(self):
        """Calculate locations in parallel."""
        # Calculate locations in parallel
        job_results = AnalysisHelpers.run_parallel_processes(
            LOGGER, calculate_locations_for_chunk, [self.calc_locs_inputs], self.ranges,
            len(self.ranges), self.max_processes,
            "Calculating locations", "Calculate Locations"
        )
        for result in job_results:
            # Parse the results dictionary and store components for post-processing.
            # Store the ranges as dictionary keys to facilitate sorting.
            self.temp_out_fcs[result["oidRange"]] = result["outputFC"]

        # Rejoin the chunked feature classes into one.
        LOGGER.info("Rejoining chunked data...")
        self._rejoin_chunked_output()

        # Clean up
        # Delete the job folders if the job succeeded
        if DELETE_INTERMEDIATE_OUTPUTS:
            LOGGER.info("Deleting intermediate outputs...")
            try:
                shutil.rmtree(self.scratch_folder, ignore_errors=True)
            except Exception:  # pylint: disable=broad-except
                # If deletion doesn't work, just throw a warning and move on. This does not need to kill the tool.
                LOGGER.warning(
                    f"Unable to delete intermediate Calculate Locations output folder {self.scratch_folder}.")

        LOGGER.info("Finished calculating locations in parallel.")

    def _rejoin_chunked_output(self):
        """Merge the chunks into a single feature class.

        Create an empty final output feature class and populate it using InsertCursor, as this tends to be faster than
        using the Merge geoprocessing tool.
        """
        # Create the final output feature class
        LOGGER.debug("Creating output feature class...")
        template_fc = self.temp_out_fcs[tuple(self.ranges[0])]
        desc = arcpy.Describe(template_fc)
        AnalysisHelpers.run_gp_tool(
            LOGGER,
            arcpy.management.CreateFeatureclass, [
                os.path.dirname(self.output_features),
                os.path.basename(self.output_features),
                "POINT",
                template_fc,  # template feature class to transfer full schema
                "SAME_AS_TEMPLATE",
                "SAME_AS_TEMPLATE",
                desc.spatialReference
            ]
        )

        # Insert the rows from all the individual output feature classes into the final output
        LOGGER.debug("Inserting rows into output feature class from output chunks...")
        fields = ["SHAPE@"] + [f.name for f in desc.fields]
        with arcpy.da.InsertCursor(self.output_features, fields) as cur:  # pylint: disable=no-member
            # Get rows from the output feature class from each chunk in the original order
            for chunk in self.ranges:
                for row in arcpy.da.SearchCursor(self.temp_out_fcs[tuple(chunk)], fields):  # pylint: disable=no-member
                    cur.insertRow(row)


def launch_parallel_calc_locs():
    """Read arguments passed in via subprocess and run the parallel calculate locations.

    This script is intended to be called via subprocess via a client module.  Users should not call this script
    directly from the command line.

    We must launch this script via subprocess in order to support parallel processing from an ArcGIS Pro script tool,
    which cannot do parallel processing directly.
    """
    # Create the parser
    parser = argparse.ArgumentParser(description=globals().get("__doc__", ""), fromfile_prefix_chars='@')

    # Define Arguments supported by the command line utility

    # --input-features parameter
    help_string = "The full catalog path to the input features to calculate locations for."
    parser.add_argument(
        "-if", "--input-features", action="store", dest="input_features", help=help_string, required=True)

    # --output-features parameter
    help_string = "The full catalog path to the output features."
    parser.add_argument(
        "-of", "--output-features", action="store", dest="output_features", help=help_string, required=True)

    # --network-data-source parameter
    help_string = "The full catalog path to the network dataset that will be used for calculating locations."
    parser.add_argument(
        "-n", "--network-data-source", action="store", dest="network_data_source", help=help_string, required=True)

    # --chunk-size parameter
    help_string = "Maximum number of features that can be in one chunk for parallel processing."
    parser.add_argument(
        "-ch", "--chunk-size", action="store", dest="chunk_size", type=int, help=help_string, required=True)

    # --max-processes parameter
    help_string = "Maximum number parallel processes to use for calculating locations."
    parser.add_argument(
        "-mp", "--max-processes", action="store", dest="max_processes", type=int, help=help_string, required=True)

    # --travel-mode parameter
    help_string = (
        "The name or JSON string representation of the travel mode from the network data source that will be used for "
        "calculating locations."
    )
    parser.add_argument("-tm", "--travel-mode", action="store", dest="travel_mode", help=help_string, required=False)

    # --search-tolerance parameter
    help_string = "Linear Unit string representing the search distance to use when locating."
    parser.add_argument(
        "-st", "--search-tolerance", action="store", dest="search_tolerance", help=help_string, required=False)

    # --search-criteria parameter
    help_string = "Defines the network sources that can be used for locating."
    parser.add_argument(
        "-sc", "--search-criteria", action="store", dest="search_criteria", help=help_string, required=False)

    # --search-query parameter
    help_string = "Defines queries to use per network source when locating."
    parser.add_argument(
        "-sq", "--search-query", action="store", dest="search_query", help=help_string, required=False)

    try:
        # Get arguments as dictionary.
        args = vars(parser.parse_args())

        # Initialize a parallel location calculator class
        cl_calculator = ParallelLocationCalculator(**args)
        # Calculate network locations in parallel chunks
        start_time = time.time()
        cl_calculator.calc_locs_in_parallel()
        LOGGER.info(f"Parallel Calculate Locations completed in {round((time.time() - start_time) / 60, 2)} minutes")

    except Exception:  # pylint: disable=broad-except
        LOGGER.error("Error in parallelization subprocess.")
        errs = traceback.format_exc().splitlines()
        for err in errs:
            LOGGER.error(err)
        raise


if __name__ == "__main__":
    # This script should always be launched via subprocess as if it were being called from the command line.
    with arcpy.EnvManager(overwriteOutput=True):
        launch_parallel_calc_locs()
