"""Unit tests for the Create Percent Access Polygons script tool.

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
        self.assertTrue(arcpy.Exists(out_fc))
        self.assertTrue(arcpy.Exists(out_fc_th))
        self.assertEqual(2, int(arcpy.management.GetCount(out_fc_th).getOutput(0)))


if __name__ == '__main__':
    unittest.main()
