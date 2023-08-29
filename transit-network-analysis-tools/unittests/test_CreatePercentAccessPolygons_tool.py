"""Unit tests for the Create Percent Access Polygons script tool.

The input data for these tests is made up and intended to be simple to verify.
The tests don't attempt to compare geometry exactly because small changes to ArcGIS Pro could cause those checks to be
flaky over time.  They just ensure that the output is generally correct.  If you're going to make significant changes to
the logic of this tool, you will likely need to create some more exhaustive tests that compare the actual
output geometry before and after the changes.

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
# pylint: disable=import-error, invalid-name

import os
import datetime
import unittest
import arcpy
import input_data_helper

CWD = os.path.dirname(os.path.abspath(__file__))


class TestCreatePercentAccessPolygonsTool(unittest.TestCase):
    """Test cases for the Create Percent Access Polygons script tool."""

    @classmethod
    def setUpClass(self):  # pylint: disable=bad-classmethod-argument
        self.maxDiff = None

        tbx_path = os.path.join(os.path.dirname(CWD), "Transit Network Analysis Tools.pyt")
        arcpy.ImportToolbox(tbx_path)

        self.input_data_folder = os.path.join(CWD, "TestInput")
        input_data_helper.make_feature_classes_from_json(self.input_data_folder)
        self.in_gdb = os.path.join(self.input_data_folder, "CincinnatiTransitNetwork.gdb")

        # Create a unique output directory and gdb for this test
        self.scratch_folder = os.path.join(
            CWD, "TestOutput",
            "Output_CPAP_Tool_" + datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S"))
        os.makedirs(self.scratch_folder)
        self.output_gdb = os.path.join(self.scratch_folder, "outputs.gdb")
        arcpy.management.CreateFileGDB(os.path.dirname(self.output_gdb), os.path.basename(self.output_gdb))

    def check_output(self, out_fc, expected_percents):
        """Check the output feature class."""
        self.assertTrue(arcpy.Exists(out_fc))
        self.assertEqual(len(expected_percents), int(arcpy.management.GetCount(out_fc).getOutput(0)))
        self.assertIn("Percent", [f.name for f in arcpy.ListFields(out_fc)])
        actual_percents = []
        for row in arcpy.da.SearchCursor(out_fc, "Percent"):
            actual_percents.append(row[0])
        actual_percents = sorted(actual_percents)
        self.assertEqual(expected_percents, actual_percents)

    def make_percent_shape_dict(self, out_fc):
        """Make a dictionary of {percent: shape geometry} for the output feature class."""
        shapes = {}
        for row in arcpy.da.SearchCursor(out_fc, ["Percent", "SHAPE@"]):
            shapes[row[0]] = row[1]
        return shapes

    def test_tool(self):
        """Test the tool."""
        in_fc = os.path.join(self.in_gdb, "TimeLapsePolys_1Fac_1Cutoff")
        out_fc = os.path.join(self.output_gdb, "CPAP_1Fac_1Cutoff")
        out_fc_th = os.path.join(self.output_gdb, "CPAP_Th_1Fac_1Cutoff")
        # Run the tool
        arcpy.TransitNetworkAnalysisTools.CreatePercentAccessPolygons(  # pylint: disable=no-member
            in_fc,
            out_fc,
            "100 Meters",
            4,  # Parallel processes
            out_fc_th,
            [50, 75]
        )

        # Do some basic checks of outputs
        all_percents = [25, 50, 75, 100]
        self.check_output(out_fc, all_percents)
        self.check_output(out_fc_th, [50, 75])

        # Check the relationships of the shapes in the output
        out_shapes = self.make_percent_shape_dict(out_fc)
        th_shapes = self.make_percent_shape_dict(out_fc_th)
        # For the main output, none of the polygons should overlap.
        for percent1 in all_percents:
            shape1 = out_shapes[percent1]
            for percent2 in [p for p in all_percents if p > percent1]:
                shape2 = out_shapes[percent2]
                self.assertFalse(shape1.overlaps(shape2), "Shapes should not overlap.")
        # For the threshold output, the 75% polygon should be fully contained within the 50% polygon
        self.assertTrue(th_shapes[50].contains(th_shapes[75]), "Smaller threshold polygon should contain larger.")
        # The threshold polygons should contain all the main polygons of larger percentages
        for percent in [50, 75, 100]:
            self.assertTrue(th_shapes[50].contains(out_shapes[percent]))
        for percent in [75, 100]:
            self.assertTrue(th_shapes[75].contains(out_shapes[percent]))


if __name__ == '__main__':
    unittest.main()
