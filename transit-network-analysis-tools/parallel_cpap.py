############################################################################
## Tool name: Transit Network Analysis Tools
## Created by: Melinda Morang, Esri
## Last updated: 6 August 2021
############################################################################
"""Do the core logic for the Create Percent Access Polygons tool in parallel
for maximum efficiency.

This version of the tool is for ArcGIS Pro only.

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
import sys
import os
import time
import uuid
import shutil
import traceback
import argparse
import logging
import arcpy

from AnalysisHelpers import FACILITY_ID_FIELD, FROM_BREAK_FIELD, TO_BREAK_FIELD, TIME_FIELD, FIELDS_TO_PRESERVE, \
                            MSG_STR_SPLITTER

# Set logging for the main process.
# LOGGER logs everything from the main process to stdout using a specific format that the tool
# can parse and write to the geoprocessing message feed.
LOG_LEVEL = logging.INFO  # Set to logging.DEBUG to see verbose debug messages
LOGGER = logging.getLogger(__name__)  # pylint:disable=invalid-name
LOGGER.setLevel(LOG_LEVEL)
console_handler = logging.StreamHandler(stream=sys.stdout)
console_handler.setLevel(LOG_LEVEL)
# Used by script tool to split message text from message level to add correct message type to GP window
console_handler.setFormatter(logging.Formatter("%(levelname)s" + MSG_STR_SPLITTER + "%(message)s"))
LOGGER.addHandler(console_handler)

DELETE_INTERMEDIATE_OD_OUTPUTS = True  # Set to False for debugging purposes


def parallel_counter(time_lapse_polygons, raster_template, scratch_folder, combo):
    """Calculate percent access polygons for the designated facility, from break, to break combo.

    Args:
        time_lapse_polygons (feature class catalog path): Time lapse polygons
        raster_template (feature class catalog path): Raster-like polygons template
        scratch_folder (folder): Folder location to write intermediate outputs
        combo (list): facility_id, from_break, to_break

    Returns:
        dict: job result parameters
    """
    # Create a job ID and a folder and scratch gdb for this job
    job_id = uuid.uuid4().hex
    job_folder = os.path.join(scratch_folder, job_id)
    os.mkdir(job_folder)
    scratch_gdb = os.path.join(job_folder, "scratch.gdb")
    arcpy.management.CreateFileGDB(job_folder, "scratch.gdb")

    # Setup the logger. Logs for each parallel process are not written to the console but instead to a
    # process-specific log file.
    log_file = os.path.join(job_folder, 'log.log')
    logger = logging.getLogger("PercAccPoly_" + job_id)
    logger.setLevel(logging.DEBUG)
    if len(logger.handlers) <= 1:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)
        formatter = logging.Formatter("%(process)d | %(message)s")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Prepare a dictionary to store info about the analysis results
    job_result = {
        "jobId": job_id,
        "jobFolder": job_folder,
        "logFile": log_file,
        "polygons": None
    }

    # Parse parameters for this process
    facility_id, from_break, to_break = combo
    logger.info(f"Processing FacilityID {facility_id}, FromBreak {from_break}, ToBreak {to_break}...")

    # Select the subset of polygons for this FacilityID/FromBreak/ToBreak combo
    selected_polys_layer = "SelectedPolys_" + job_id
    if facility_id is None:
        facility_query = arcpy.AddFieldDelimiters(time_lapse_polygons, FACILITY_ID_FIELD) + " IS NULL"
    else:
        facility_query = arcpy.AddFieldDelimiters(time_lapse_polygons, FACILITY_ID_FIELD) + " = " + str(facility_id)
    query = facility_query + " AND " + \
        arcpy.AddFieldDelimiters(time_lapse_polygons, FROM_BREAK_FIELD) + " = " + str(from_break) + " AND " + \
        arcpy.AddFieldDelimiters(time_lapse_polygons, TO_BREAK_FIELD) + " = " + str(to_break)
    arcpy.management.MakeFeatureLayer(time_lapse_polygons, selected_polys_layer, where_clause=query)
    logger.info(f"{int(arcpy.management.GetCount(selected_polys_layer).getOutput(0))} time lapse polygons selected.")

    # Do a spatial join in order to count the number of time lapse polygons intersect each "cell" in the raster-like
    # polygon template.  We are effectively applying the template to a specific set of time lapse polygons, doing the
    # count, and creating the raw output.  The result is a polygon feature class of raster-like cells with a field
    # called Join_Count that shows the number of input time lapse polygons that intersect the cell using the specified
    # match_option.
    # Create a FieldMappings object for Spatial Join to preserve informational input fields
    field_mappings = arcpy.FieldMappings()
    for field in FIELDS_TO_PRESERVE:
        fmap = arcpy.FieldMap()
        fmap.addInputField(time_lapse_polygons, field)
        fmap.mergeRule = "First"
        field_mappings.addFieldMap(fmap)
    # Do the spatial join
    temp_spatial_join_fc = os.path.join(scratch_gdb, "SpatialJoin")
    t0 = time.time()
    arcpy.analysis.SpatialJoin(
        raster_template,
        selected_polys_layer,
        temp_spatial_join_fc,
        "JOIN_ONE_TO_ONE",  # Output keeps only one copy of each "cell" when multiple time lapse polys intersect it
        "KEEP_COMMON",  # Delete any "cells" that don't overlap the time lapse polys being considered
        field_mapping=field_mappings,  # Preserve some fields from the original data
        match_option="HAVE_THEIR_CENTER_IN"
    )
    logger.info(f"Finished spatial join in {time.time() - t0} seconds.")

    # Dissolve all the little cells that were reached the same number of times to make the output more manageable
    # Currently, the feature class contains a large number of little square polygons representing raster cells. The
    # Join_Count field added by Spatial Join says how many of the input time lapse polygons overlapped the cell.  We
    # don't need all the little squares.  We can dissolve them so that we have one polygon per unique value of
    # Join_Count.
    dissolved_polygons = os.path.join(scratch_gdb, "DissolvedPolys")
    t0 = time.time()
    arcpy.management.Dissolve(temp_spatial_join_fc, dissolved_polygons, FIELDS_TO_PRESERVE + ["Join_Count"])
    logger.info(f"Finished dissolve in {time.time() - t0} seconds.")
    job_result["polygons"] = dissolved_polygons

    # Clean up and close the logger.
    for handler in logger.handlers:
        handler.close()
        logger.removeHandler(handler)

    return job_result


def count_percent_access_polygons(time_lapse_polygons, raster_template, output_fc, max_processes):
    """Add counts to percent access polygons using parallel processing.

    Args:
        time_lapse_polygons (feature class catalog path): Time lapse polygons
        raster_template (feature class catalog path): Raster template
        output_fc (catalog path): Path to final output feature class
        max_processes (int): Number of allowed parallel processes.
    """
    # Scratch folder to store intermediate outputs from the parallel processes
    scratch_folder = os.path.join(
        arcpy.env.scratchFolder, "PercAccPoly_" + uuid.uuid4().hex)  # pylint: disable=no-member
    LOGGER.info(f"Intermediate outputs for parallel processes will be written to {scratch_folder}.")
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
    LOGGER.info("Counting polygons overlapping each cell parallel...")
    completed_jobs = 0  # Track the number of jobs completed so far to use in logging
    all_polygons = []
    # Use the concurrent.futures ProcessPoolExecutor to spin up parallel processes
    with futures.ProcessPoolExecutor(max_workers=max_processes) as executor:
        # Each parallel process calls the solve_od_cost_matrix() function with the od_inputs dictionary for the
        # given origin and destination OID ranges and time of day.
        jobs = {executor.submit(
            parallel_counter, time_lapse_polygons, raster_template, scratch_folder, combo
        ): combo for combo in unique_output_combos}
        # As each job is completed, add some logging information and store the results to post-process later
        for future in futures.as_completed(jobs):
            completed_jobs += 1
            LOGGER.info(f"Finished polygon cell calculation chunk {completed_jobs} of {total_jobs}.")
            try:
                # The OD cost matrix job returns a results dictionary. Retrieve it.
                result = future.result()
            except Exception:
                # If we couldn't retrieve the result, some terrible error happened. Log it.
                LOGGER.error("Failed to get result from parallel processing.")
                errs = traceback.format_exc().splitlines()
                for err in errs:
                    LOGGER.error(err)
                raise

            # Log failed analysis
            if not result["polygons"]:
                LOGGER.warning(f"No output polygons generated for job id {result['jobId']}")
            else:
                all_polygons.append(result["polygons"])

    LOGGER.info("Parallel processing complete. Merging results to output feature class...")

    # Merge all individual output feature classes into one feature class.
    arcpy.management.Merge(all_polygons, output_fc)
    # Calculate a field showing the Percent of times each polygon was reached.
    percent_field = "Percent"
    arcpy.management.AddField(output_fc, percent_field, "DOUBLE")
    expression = f"float(!Join_Count!) * 100.0 / float({num_time_steps})"
    arcpy.management.CalculateField(output_fc, percent_field, expression)
    LOGGER.info(f"Output feature class successfully created at {output_fc}")

    # Cleanup
    # Delete the job folders if the job succeeded
    if DELETE_INTERMEDIATE_OD_OUTPUTS:
        LOGGER.info("Deleting intermediate outputs...")
        try:
            shutil.rmtree(scratch_folder, ignore_errors=True)
        except Exception:  # pylint: disable=broad-except
            # If deletion doesn't work, just throw a warning and move on. This does not need to kill the tool.
            LOGGER.warning(f"Unable to delete intermediate output folder {scratch_folder}.")


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

    # Get arguments as dictionary.
    args = vars(parser.parse_args())

    # Count intersecting percent access polygon cells in parallel
    try:
        start_time = time.time()
        count_percent_access_polygons(**args)
        run_time = round((time.time() - start_time) / 60, 2)
        LOGGER.info(f"Parallel percent access polygon cell calculation completed in {run_time} minutes")

    except Exception:  # pylint: disable=broad-except
        errs = traceback.format_exc().splitlines()
        for err in errs:
            LOGGER.error(err)
        raise
