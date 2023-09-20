############################################################################
## Tool name: Transit Network Analysis Tools
## Created by: Melinda Morang, Esri
## Last updated: 20 September 2023
############################################################################
"""Do the core logic for the Create Percent Access Polygons tool in parallel
for maximum efficiency.

This version of the tool is for ArcGIS Pro only.

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
import time
import uuid
import shutil
import traceback
import argparse
import logging
import arcpy
import AnalysisHelpers
from AnalysisHelpers import FACILITY_ID_FIELD, FROM_BREAK_FIELD, TO_BREAK_FIELD, TIME_FIELD, FIELDS_TO_PRESERVE

DELETE_INTERMEDIATE_OUTPUTS = True  # Set to False for debugging purposes

# Change logging.INFO to logging.DEBUG to see verbose debug messages
LOG_LEVEL = logging.INFO


class ParallelCounter(AnalysisHelpers.JobFolderMixin, AnalysisHelpers.LoggingMixin):
    """Calculate percent access polygons for the designated facility, from break, to break combo."""

    def __init__(self, time_lapse_polygons, raster_template, facility_id, from_break, to_break, scratch_folder):
        """Initialize the parallel counter for the given inputs.

        Args:
            time_lapse_polygons (feature class catalog path): Time lapse polygons
            raster_template (feature class catalog path): Raster-like polygons template
            facility_id (int): ID of the Service Area facility to select for processing this chunk
            from_break (float): Service Area FromBreak field value to select for processing this chunk
            to_break (float): Service Area ToBreak field value to select for processing this chunk
            scratch_folder (folder): Folder location to write intermediate outputs
        """
        self.time_lapse_polygons = time_lapse_polygons
        self.raster_template = raster_template
        self.facility_id = facility_id
        self.from_break = from_break
        self.to_break = to_break
        self.scratch_folder = scratch_folder

        # Create a job ID and a folder for this job
        self._create_job_folder()
        self.scratch_gdb = None  # Set later

        # Setup the class logger. Logs for each parallel process are not written to the console but instead to a
        # process-specific log file.
        self.setup_logger("PercAccPoly")

        # Prepare a dictionary to store info about the analysis results
        self.job_result = {
            "jobId": self.job_id,
            "jobFolder": self.job_folder,
            "logFile": self.log_file,
            "polygons": None  # Set later
        }

    def make_percent_access_polygons(self):
        """Calculate percent access polygons for the designated facility, from break, to break combo."""
        self.logger.info(
            f"Processing FacilityID {self.facility_id}, FromBreak {self.from_break}, ToBreak {self.to_break}...")
        self.scratch_gdb = self._create_output_gdb()
        selected_polygons = self._select_polygons()
        joined_polygons = self._join_polygons(selected_polygons)
        dissolved_polygons = self._dissolve_cells(joined_polygons)
        self.job_result["polygons"] = dissolved_polygons

    def _select_polygons(self):
        """Select the subset of polygons for this FacilityID/FromBreak/ToBreak combo and return the layer."""
        selected_polys_layer = "SelectedPolys_" + self.job_id
        if self.facility_id is None:
            facility_query = arcpy.AddFieldDelimiters(self.time_lapse_polygons, FACILITY_ID_FIELD) + " IS NULL"
        else:
            facility_query = arcpy.AddFieldDelimiters(self.time_lapse_polygons, FACILITY_ID_FIELD) + " = " + \
                str(self.facility_id)
        query = facility_query + " AND " + \
            arcpy.AddFieldDelimiters(self.time_lapse_polygons, FROM_BREAK_FIELD) + " = " + str(self.from_break) + \
            " AND " + \
            arcpy.AddFieldDelimiters(self.time_lapse_polygons, TO_BREAK_FIELD) + " = " + str(self.to_break)
        arcpy.management.MakeFeatureLayer(self.time_lapse_polygons, selected_polys_layer, where_clause=query)
        self.logger.info(
            f"{int(arcpy.management.GetCount(selected_polys_layer).getOutput(0))} time lapse polygons selected.")
        return selected_polys_layer

    def _join_polygons(self, selected_polygons):
        """Spatially join polygons and return the path to the output feature class."""
        # Do a spatial join in order to count the number of time lapse polygons intersect each "cell" in the raster-like
        # polygon template.  We are effectively applying the template to a specific set of time lapse polygons, doing the
        # count, and creating the raw output.  The result is a polygon feature class of raster-like cells with a field
        # called Join_Count that shows the number of input time lapse polygons that intersect the cell using the specified
        # match_option.
        # Create a FieldMappings object for Spatial Join to preserve informational input fields
        field_mappings = arcpy.FieldMappings()
        for field in FIELDS_TO_PRESERVE:
            fmap = arcpy.FieldMap()
            fmap.addInputField(self.time_lapse_polygons, field)
            fmap.mergeRule = "First"
            field_mappings.addFieldMap(fmap)
        # Do the spatial join
        temp_spatial_join_fc = os.path.join(self.scratch_gdb, "SpatialJoin")
        t0 = time.time()
        arcpy.analysis.SpatialJoin(
            self.raster_template,
            selected_polygons,
            temp_spatial_join_fc,
            "JOIN_ONE_TO_ONE",  # Output keeps only one copy of each "cell" when multiple time lapse polys intersect it
            "KEEP_COMMON",  # Delete any "cells" that don't overlap the time lapse polys being considered
            field_mapping=field_mappings,  # Preserve some fields from the original data
            match_option="HAVE_THEIR_CENTER_IN"
        )
        self.logger.info(f"Finished spatial join in {time.time() - t0} seconds.")
        return temp_spatial_join_fc

    def _dissolve_cells(self, joined_polygons):
        """Dissolve percent access cells with the same values and return the path to the output feature class."""
        # Dissolve all the little cells that were reached the same number of times to make the output more manageable
        # Currently, the feature class contains a large number of little square polygons representing raster cells. The
        # Join_Count field added by Spatial Join says how many of the input time lapse polygons overlapped the cell.  We
        # don't need all the little squares.  We can dissolve them so that we have one polygon per unique value of
        # Join_Count.
        dissolved_polygons = os.path.join(self.scratch_gdb, "DissolvedPolys")
        t0 = time.time()
        arcpy.management.Dissolve(joined_polygons, dissolved_polygons, FIELDS_TO_PRESERVE + ["Join_Count"])
        self.logger.info(f"Finished dissolve in {time.time() - t0} seconds.")
        return dissolved_polygons


def parallel_calculate_access(combo, time_lapse_polygons, raster_template, scratch_folder):
    """Calculate the percent access polygons for this chunk.

    Args:
        combo (list): facility_id, from_break, to_break
        time_lapse_polygons (feature class catalog path): Time lapse polygons
        raster_template (feature class catalog path): Raster-like polygons template
        scratch_folder (folder): Folder location to write intermediate outputs

    Returns:
        dict: job result parameters
    """
    facility_id, from_break, to_break = combo
    cpap_counter = ParallelCounter(
        time_lapse_polygons, raster_template, facility_id, from_break, to_break, scratch_folder)
    cpap_counter.make_percent_access_polygons()
    cpap_counter.teardown_logger()
    return cpap_counter.job_result


def count_percent_access_polygons(logger, time_lapse_polygons, raster_template, output_fc, max_processes):
    """Add counts to percent access polygons using parallel processing.

    Args:
        logger (logging.logger): Logger class to use for messages that get written to the GP window. Set up using
            AnalysisHelpers.configure_global_logger().
        time_lapse_polygons (feature class catalog path): Time lapse polygons
        raster_template (feature class catalog path): Raster template
        output_fc (catalog path): Path to final output feature class
        max_processes (int): Number of allowed parallel processes.
    """
    # Scratch folder to store intermediate outputs from the parallel processes
    scratch_folder = os.path.join(
        arcpy.env.scratchFolder, "PercAccPoly_" + uuid.uuid4().hex)  # pylint: disable=no-member
    logger.info(f"Intermediate outputs for parallel processes will be written to {scratch_folder}.")
    os.mkdir(scratch_folder)

    # Figure out the unique combinations of FacilityID, FromBreak, and ToBreak in the input data. Each of these
    # will be processed separately and get a separate output. Also count the number of unique times of day that
    # were used in the original analysis so we can calculate % later.
    unique_output_combos = []
    unique_times = []
    fields = [
        FACILITY_ID_FIELD,
        FROM_BREAK_FIELD,
        TO_BREAK_FIELD,
        TIME_FIELD
    ]
    for row in arcpy.da.SearchCursor(time_lapse_polygons, fields):  # pylint: disable=no-member
        unique_output_combos.append((row[0], row[1], row[2]))
        unique_times.append(row[3])
    unique_output_combos = sorted(set(unique_output_combos))
    total_jobs = len(unique_output_combos)
    num_time_steps = len(set(unique_times))

    # For each set of time lapse polygons, generate the cell-like counts. Do this in parallel for maximum efficiency.
    job_results = AnalysisHelpers.run_parallel_processes(
        logger, parallel_calculate_access, [time_lapse_polygons, raster_template, scratch_folder], unique_output_combos,
        total_jobs, max_processes,
        "Counting polygons overlapping each cell", "polygon cell calculation"
    )

    # Retrieve and store results
    all_polygons = []
    for result in job_results:
        if not result["polygons"]:
            # Log failed analysis
            logger.warning(f"No output polygons generated for job id {result['jobId']}")
        else:
            all_polygons.append(result["polygons"])

    # Merge all individual output feature classes into one feature class.
    logger.info("Parallel processing complete. Merging results to output feature class...")
    arcpy.management.Merge(all_polygons, output_fc)
    # Calculate a field showing the Percent of times each polygon was reached.
    percent_field = "Percent"
    arcpy.management.AddField(output_fc, percent_field, "DOUBLE")
    expression = f"float(!Join_Count!) * 100.0 / float({num_time_steps})"
    arcpy.management.CalculateField(output_fc, percent_field, expression)
    logger.info(f"Output feature class successfully created at {output_fc}")

    # Cleanup
    # Delete the job folders if the job succeeded
    if DELETE_INTERMEDIATE_OUTPUTS:
        logger.info("Deleting intermediate outputs...")
        try:
            shutil.rmtree(scratch_folder, ignore_errors=True)
        except Exception:  # pylint: disable=broad-except
            # If deletion doesn't work, just throw a warning and move on. This does not need to kill the tool.
            logger.warning(f"Unable to delete intermediate output folder {scratch_folder}.")


if __name__ == "__main__":
    # This script should always be launched via subprocess as if it were being called from the command line.
    # Create the parser
    parser = argparse.ArgumentParser(description=globals().get("__doc__", ""), fromfile_prefix_chars='@')

    # Define Arguments supported by the command line utility

    # --time-lapse-polygons parameter
    help_string = "The full catalog path to the feature class containing input time lapse polygons."
    parser.add_argument(
        "-p", "--time-lapse-polygons", action="store", dest="time_lapse_polygons", help=help_string, required=True)

    # --raster-template parameter
    help_string = "The full catalog path to the polygon raster template created in earlier steps."
    parser.add_argument(
        "-r", "--raster-template", action="store", dest="raster_template", help=help_string, required=True)

    # --output-fc parameter
    help_string = "The full catalog path to the output feature class."
    parser.add_argument(
        "-o", "--output-fc", action="store", dest="output_fc", help=help_string, required=True)

    # --max-processes parameter
    help_string = "Maximum number parallel processes to use."
    parser.add_argument(
        "-mp", "--max-processes", action="store", dest="max_processes", type=int, help=help_string, required=True)

    # Count intersecting percent access polygon cells in parallel
    try:
        logger = AnalysisHelpers.configure_global_logger(LOG_LEVEL)

        # Get arguments as dictionary.
        args = vars(parser.parse_args())
        args["logger"] = logger

        start_time = time.time()
        count_percent_access_polygons(**args)
        run_time = round((time.time() - start_time) / 60, 2)
        logger.info(f"Parallel percent access polygon cell calculation completed in {run_time} minutes")

    except Exception:  # pylint: disable=broad-except
        errs = traceback.format_exc().splitlines()
        for err in errs:
            logger.error(err)
        raise

    finally:
        AnalysisHelpers.teardown_logger(logger)
