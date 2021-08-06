################################################################################
## Toolbox: Transit Network Analysis Tools
## Tool name: Create Percent Access Polygons
## Created by: David Wasserman, Fehr & Peers, https://github.com/d-wasserman
##        and: Melinda Morang, Esri
## Last updated: 17 June 2019
################################################################################
''''''
################################################################################
'''Copyright 2018 Fehr & Peers
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at
       http://www.apache.org/licenses/LICENSE-2.0
   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.'''
################################################################################
################################################################################
'''Copyright 2019 Esri
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at
       http://www.apache.org/licenses/LICENSE-2.0
   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.'''
################################################################################

import sys
import os
import time
import uuid
import subprocess
import arcpy

import AnalysisHelpers

# Create a GUID for temporary outputs (avoids naming conflicts)
guid = uuid.uuid4().hex


def create_polygon_raster_template(in_polys, outgdb, cell_size):
    '''Creates a raster-like polygon feature class covering the area of the original time lapse polygons.  Each polygon
    in the output is equivalent to one square of a raster.  The dataset is meant to be used with Spatial Join with the 
    original time lapse polygon dataset in order to count the number of original polygons overlapping that cell.
    Params:
    in_polys: path to the input time lapse polygon dataset generated from the Prepare Time Lapse Polygons tool.
    outgdb: path of workspace being used to store output from this tool
    cell_size: The length or width (not area) of the desired raster cell, in the units of the spatial reference of the
    '''

    # Convert the full time lapse dataset into a temporary raster. The cell values are irrelvant.
    poly_oid = arcpy.Describe(in_polys).OIDFieldName
    temp_raster = os.path.join(outgdb, "Temp_" + guid + "_InitialRaster")
    arcpy.conversion.FeatureToRaster(in_polys, poly_oid, temp_raster, cell_size=cell_size)

    # Create a temporary point dataset with one point for the centroid of every raster cell
    # The value of the points is irrelevant. We just need their geometry and an OID.
    temp_points = os.path.join(outgdb, "Temp_" + guid + "_Points")
    arcpy.conversion.RasterToPoint(temp_raster, temp_points)

    # Create a new raster from the points with the same cell size as the initial raster. Set the value of each cell
    # equal to the value of the OID of the point it was created from.  This way, each cell has a unique value.
    pt_oid = arcpy.Describe(temp_points).OIDFieldName
    temp_raster2 = os.path.join(outgdb, "Temp_" + guid + "_ProcessedRaster")
    arcpy.conversion.FeatureToRaster(temp_points, pt_oid, temp_raster2, cell_size=cell_size)

    # Convert this raster to polygons.  The result contains one square polygon per raster cell and can be used for
    # calculating spatial joins with the original time lapse polygon dataset.
    poly_raster_template_fc = os.path.join(outgdb, "Temp_" + guid + "_PolyRasterTemplate")
    arcpy.conversion.RasterToPolygon(temp_raster2, poly_raster_template_fc, simplify=False)

    # Clean up intermediate outputs
    clean_up = [temp_raster, temp_points, temp_raster2]
    for temp_output in clean_up:
        arcpy.management.Delete(temp_output)

    return poly_raster_template_fc


def create_percent_access_polys(raw_cell_counts, percents, out_fc, fields_to_preserve, scratch_workspace):
    '''For each percent threshold, dissolve the cells where the number of times reached exceeds the threshold. Each
    threshold gets its own polygon, and they are all output to the same feature class.
    Params:
    raw_cell_counts: Feature class of cell-like polygons with counts generated from create_raw_cell_counts_fc()
    count_field: The field in raw_cell_counts containing the number of times the cell was reached
    percents: List of percents to calculate results for. Example: 80 means crate a polygon representing the area that
        could be reached for at least 80% of start times.
    num_time_steps: The total number of time steps present in the input time lapse polygon dataset
    out_fc: Path of the output feature class for storing the percent access polygons
    '''

    first = True
    temp_out_dissolve_fc = os.path.join(scratch_workspace, "Temp_" + guid + "_Dissolve")
    for percent in sorted(percents):

        # Select all the cells where the number of times with access is >= our percent threshold
        # The result is all the cells that are reachable at least X% of start times
        query = arcpy.AddFieldDelimiters(raw_cell_counts, "Percent") + " >= " + str(percent)
        percent_layer = arcpy.management.MakeFeatureLayer(raw_cell_counts, "PercentLayer", query).getOutput(0)

        # Dissolve everything that meets the threshold into one polygon
        if first:
            out_Dissolve = out_fc
        else:
            out_Dissolve = temp_out_dissolve_fc
        arcpy.management.Dissolve(percent_layer, out_Dissolve, fields_to_preserve)

        percent_field = "Percent"
        arcpy.management.AddField(out_Dissolve, percent_field, "DOUBLE")
        arcpy.management.CalculateField(out_Dissolve, percent_field, str(percent))

        if not first:
            # If this wasn't the first percent output, append it to the master output fc
            arcpy.management.Append(out_Dissolve, out_fc, "TEST")
        first = False

    # Clean up temporary output
    if arcpy.Exists(temp_out_dissolve_fc):
        arcpy.management.Delete(temp_out_dissolve_fc)


def main(in_time_lapse_polys, out_cell_counts_fc, cell_size, max_processes, out_percents_fc=None, percents=None):
    """Create 'typical access polygons' that represent the area reachable by transit across a time window.

    The tool attempts to account for the dynamic nature of transit schedules by overlaying service area polygons from
    multiple times of day and summarizing the results in terms of the number or percentage of the input polygons that
    cover an area. Areas covered by a larger percentage of input polygons were reached at more start times and are
    consequently more frequently accessible to travelers.

    The tool output will show you the percentage of times any given area was reached, and you can also choose to
    summarize these results for different percentage thresholds. For example, you can find out what area can be reached
    at least 75% of start times.

    Parameters:
    in_time_lapse_polys: A polygon feature class created using the Prepare Time Lapse Polygons tool that you wish to
        summarize. The feature class must be in a projected coordinate system.
    out_cell_counts_fc: The main output feature class of the tool. Must be in a geodatabase; it cannot be a shapefile.
    cell_size: This tool rasterizes the input polygons, essentially turning the study area into little squares. This is
        the size for these squares. The cell size refers to the width or length of the cell, not the area. The units for
        the cell size are the linear units of the projected coordinate system of the input time lapse polygons.
    out_percents_fc: Optional output feature class that further summarizes the output percent access polygons feature
        class. If you specify one or more percentage thresholds, this output contains polygons showing the area reached
        at least as often as your designated percentage thresholds. There will be a separate feature for each percentage
        threshold for each unique combination of FacilityID, FromBreak, and ToBreak in the input data.
    percents: You can choose to summarize the tool's raw output for different percentage thresholds. For example, you
        can find out what area can be reached at least 75% of start times by setting 75 as one of your percentage
        thresholds. Specified as a list of percents.

    """
    arcpy.env.overwriteOutput = True
    # Use the scratchGDB as a holder for temporary output
    scratchgdb = arcpy.env.scratchGDB

    # Create the raster-like polygons we'll use later with spatial joins.
    arcpy.AddMessage("Rasterizing time lapse polygons...")
    poly_raster_template_fc = create_polygon_raster_template(in_time_lapse_polys, scratchgdb, cell_size)

    # Launch the parallel_cpap script as a subprocess so it can spawn parallel processes. We have to do this because
    # a tool running in the Pro UI cannot call concurrent.futures without opening multiple instances of Pro.
    arcpy.AddMessage("Launching parallel processing...")
    cwd = os.path.dirname(os.path.abspath(__file__))
    sa_inputs = [
        os.path.join(sys.exec_prefix, "python.exe"),
        os.path.join(cwd, "parallel_cpap.py"),
        "--time-lapse-polygons", AnalysisHelpers.get_catalog_path(in_time_lapse_polys),
        "--raster-template", poly_raster_template_fc,
        "--output-fc", out_cell_counts_fc,
        "--max-processes", str(max_processes)
    ]
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
            time.sleep(.5)

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
            arcpy.AddError("Create Percent Access Polygons parallelization script failed.")
            return

    # At this point, the main output feature class should exist
    if not arcpy.Exists(out_cell_counts_fc):
        arcpy.AddError((
            "Create Percent Access Polygons parallelization completed successfully, but output feature class does not "
            "exist."))
        return

    # Dissolve the cell-like polygons that were accessible >= X% of times if desired
    if out_percents_fc and percents:
        arcpy.AddMessage("Creating percent access polygons...")
        create_percent_access_polys(
            out_cell_counts_fc, percents, out_percents_fc, AnalysisHelpers.FIELDS_TO_PRESERVE, scratchgdb)

    # # Clean up intermediate outputs
    # clean_up = [
    #     poly_raster_template_fc,
    #     temp_spatial_join_fc,
    #     temp_raw_dissolve_fc
    #     ]
    # for temp_output in clean_up:
    #     if arcpy.Exists(temp_output):
            # arcpy.management.Delete(temp_output)

if __name__ == '__main__':
    # Feature class of polygons created by the Prepare Time Lapse Polygons tool
    # The feature class must be in a projected coordinate system, but this is checked in tool validation
    in_time_lapse_polys = sys.argv[1]
    out_cell_counts_fc = sys.argv[2]
    # Raster cell size for output (length or width of cell, not area)
    cell_size = sys.argv[3]
    out_percents_fc = sys.argv[4]
    max_processes = sys.argv[5]
    # List of percent of times accessed to summarize in results
    percents = sys.argv[5]
    main(in_time_lapse_polys, out_cell_counts_fc, cell_size, max_processes, out_percents_fc, percents)
