################################################################################
## Toolbox: Transit Network Analysis Tools
## Tool name: Create Percent Access Polygons
## Created by: David Wasserman, Fehr & Peers, https://github.com/d-wasserman
##        and: Melinda Morang, Esri
## Last updated: 29 August 2023
################################################################################
################################################################################
"""Copyright 2018 Fehr & Peers
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at
       http://www.apache.org/licenses/LICENSE-2.0
   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License."""
################################################################################
################################################################################
"""Copyright 2023 Esri
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at
       http://www.apache.org/licenses/LICENSE-2.0
   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License."""
################################################################################
import sys
import os
import time
import subprocess
import arcpy

import AnalysisHelpers


class PercentAccessPolygonCalculator():
    """Main logic for the Create Percent Access Polygons tool.

    The tool creates 'typical access polygons' that represent the area reachable by transit across a time window.

    The tool attempts to account for the dynamic nature of transit schedules by overlaying service area polygons from
    multiple times of day and summarizing the results in terms of the number or percentage of the input polygons that
    cover an area. Areas covered by a larger percentage of input polygons were reached at more start times and are
    consequently more frequently accessible to travelers.

    The tool output will show you the percentage of times any given area was reached, and you can also choose to
    summarize these results for different percentage thresholds. For example, you can find out what area can be reached
    at least 75% of start times.
    """

    def __init__(
        self, in_time_lapse_polys, out_cell_counts_fc, cell_size_in_meters, max_processes, out_percents_fc=None,
        percents=None
    ):
        """Initialize percent access polygon calculator.

        Args:
            in_time_lapse_polys (feature class or layer): Input time lapse polygons
            out_cell_counts_fc (catalog path): Main tool output feature class
            cell_size_in_meters (double): Cell size in meters
            max_processes (int): Maximum number of allowed parallel processes
            out_percents_fc (catalog path, optional): Optional output for threshold percent polygons. Defaults to None.
            percents (list(double), optional): List of percent access thresholds. Defaults to None.
        """
        self.in_time_lapse_polys = in_time_lapse_polys
        self.out_cell_counts_fc = out_cell_counts_fc
        self.cell_size = cell_size_in_meters
        self.max_processes = max_processes
        self.out_percents_fc = out_percents_fc
        self.percents = percents

        self.raster_template = None
        self.projected_polygons = None
        self.temp_outputs = []

    def execute(self):
        """Execute to tool."""
        # Create the raster-like polygons we'll use later with spatial joins.
        arcpy.AddMessage("Rasterizing time lapse polygons...")
        self._create_polygon_raster_template()

        # Calculate percent access in parallel.
        arcpy.AddMessage("Calculating percent access polygons in parallel...")
        self._calculate_percent_access_in_parallel()

        # If desired, create polygons dissolved for percent access levels.
        if self.out_percents_fc and self.percents:
            arcpy.AddMessage("Creating polygons for designated percent thresholds...")
            self._make_percent_polygons()

        # Clean up intermediate outputs
        if self.temp_outputs:
            try:
                arcpy.management.Delete(self.temp_outputs)
            except Exception:  # pylint: disable=broad-except
                # If this doesn't work for some reason, don't worry about it, and don't make the tool fail.
                pass

    def _create_polygon_raster_template(self):
        """Create a raster-like polygon feature class covering the area of the original time lapse polygons.

        Each polygon in the output is equivalent to one square of a raster.  The dataset is meant to be used with
        Spatial Join with the original time lapse polygon dataset in order to count the number of original polygons
        overlapping that cell.
        """
        try:
            # Project to World Cylindrical Equal Area (WKID 54034), which preserves area reasonably well worldwide and
            # has units of meters
            sr_world_cylindrical = arcpy.SpatialReference(54034)
            self.projected_polygons = self._make_temporary_output_path("ProjectedPolys")
            arcpy.management.Project(self.in_time_lapse_polys, self.projected_polygons, sr_world_cylindrical)

            # Convert the full time lapse dataset into a temporary raster. The cell values are irrelevant.
            poly_oid = arcpy.Describe(self.projected_polygons).OIDFieldName
            temp_raster = self._make_temporary_output_path("InitialRaster")
            arcpy.conversion.FeatureToRaster(self.projected_polygons, poly_oid, temp_raster, cell_size=self.cell_size)

            # Create a temporary point dataset with one point for the centroid of every raster cell
            # The value of the points is irrelevant. We just need their geometry and an OID.
            temp_points = self._make_temporary_output_path("Points")
            arcpy.conversion.RasterToPoint(temp_raster, temp_points)

            # Create a new raster from the points with the same cell size as the initial raster. Set the value of each
            # cell equal to the value of the OID of the point it was created from.  This way, each cell has a unique
            # value.
            pt_oid = arcpy.Describe(temp_points).OIDFieldName
            temp_raster2 = self._make_temporary_output_path("ProcessedRaster")
            arcpy.conversion.FeatureToRaster(temp_points, pt_oid, temp_raster2, cell_size=self.cell_size)

            # Convert this raster to polygons.  The result contains one square polygon per raster cell and can be used
            # for calculating spatial joins with the original time lapse polygon dataset.
            self.raster_template = self._make_temporary_output_path("PolyRasterTemplate")
            arcpy.conversion.RasterToPolygon(temp_raster2, self.raster_template, simplify=False)

        except arcpy.ExecuteError:
            # Catch any errors from GP tools and pass them through cleanly so we don't get a nasty traceback.
            # Any number of odd geometry errors could occur here.
            arcpy.AddError("Failed to rasterize time lapse polygons.")
            raise AnalysisHelpers.GPError()

    def _calculate_percent_access_in_parallel(self):
        """Calculate the percent access polygons in parallel."""
        # Launch the parallel_cpap.py script as a subprocess so it can spawn parallel processes. We have to do this
        # because a tool running in the Pro UI cannot call concurrent.futures without opening multiple instances of Pro.
        cwd = os.path.dirname(os.path.abspath(__file__))
        sa_inputs = [
            os.path.join(sys.exec_prefix, "python.exe"),
            os.path.join(cwd, "parallel_cpap.py"),
            "--time-lapse-polygons", self.projected_polygons,
            "--raster-template", self.raster_template,
            "--output-fc", self.out_cell_counts_fc,
            "--max-processes", str(self.max_processes)
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
                    msg_string = output.strip().decode(encoding="utf-8")
                    AnalysisHelpers.parse_std_and_write_to_gp_ui(msg_string)
                time.sleep(.1)

            # Once the process is finished, check if any additional errors were returned. Messages that came after the
            # last process.poll() above will still be in the queue here. This is especially important for detecting
            # messages from raised exceptions, especially those with tracebacks.
            output, _ = process.communicate()
            if output:
                out_msgs = output.decode(encoding="utf-8").splitlines()
                for msg in out_msgs:
                    AnalysisHelpers.parse_std_and_write_to_gp_ui(msg)

            # In case something truly horrendous happened and none of the logging caught our errors, at least fail the
            # tool when the subprocess returns an error code. That way the tool at least doesn't happily succeed but not
            # actually do anything.
            return_code = process.returncode
            if return_code != 0:
                arcpy.AddError("Create Percent Access Polygons parallelization script failed.")
                sys.exit()

        # At this point, the main output feature class should exist
        if not arcpy.Exists(self.out_cell_counts_fc):
            arcpy.AddError((
                "Create Percent Access Polygons parallelization completed successfully, but output feature class does "
                "not exist."))
            sys.exit()

    def _make_percent_polygons(self):
        """Create dissolved polygons representing each designated percent threshold.

        For each percent threshold, dissolve the cells where the number of times reached exceeds the threshold. Each
        threshold gets its own polygon, and they are all output to the same feature class.
        """
        first = True
        temp_out_dissolve_fc = self._make_temporary_output_path("Dissolve")
        for percent in sorted(self.percents):
            # Select all the cells where the number of times with access is >= our percent threshold
            # The result is all the cells that are reachable at least X% of start times
            query = arcpy.AddFieldDelimiters(self.out_cell_counts_fc, "Percent") + " >= " + str(percent)
            percent_layer_name = "PercentLayer"
            with arcpy.EnvManager(overwriteOutput=True):
                percent_layer = arcpy.management.MakeFeatureLayer(self.out_cell_counts_fc, percent_layer_name, query)

            # Dissolve everything that meets the threshold into one polygon
            if first:
                out_dissolve = self.out_percents_fc
            else:
                out_dissolve = temp_out_dissolve_fc
            with arcpy.EnvManager(overwriteOutput=True):
                arcpy.management.Dissolve(percent_layer, out_dissolve, AnalysisHelpers.FIELDS_TO_PRESERVE)

            # Calculate the percent field
            percent_field = "Percent"
            arcpy.management.AddField(out_dissolve, percent_field, "DOUBLE")
            arcpy.management.CalculateField(out_dissolve, percent_field, str(percent))

            if not first:
                # If this wasn't the first percent output, append it to the master output fc
                arcpy.management.Append(out_dissolve, self.out_percents_fc, "TEST")
            first = False

    def _make_temporary_output_path(self, name):
        """Make a path in the scratch gdb for a temporary intermediate output and track it for later deletion."""
        name = arcpy.CreateUniqueName(name, arcpy.env.scratchGDB)  # pylint: disable=no-member
        temp_output = os.path.join(arcpy.env.scratchGDB, name)  # pylint: disable=no-member
        self.temp_outputs.append(temp_output)
        return temp_output


if __name__ == '__main__':
    in_time_lapse_polys = sys.argv[1]
    out_cell_counts_fc = sys.argv[2]
    cell_size_in_meters = sys.argv[3]
    max_processes = sys.argv[4]
    out_percents_fc = sys.argv[5]
    percents = sys.argv[6]
    cpap_calculator = PercentAccessPolygonCalculator(
            in_time_lapse_polys, out_cell_counts_fc, cell_size_in_meters, max_processes, out_percents_fc, percents)
    cpap_calculator.execute()
