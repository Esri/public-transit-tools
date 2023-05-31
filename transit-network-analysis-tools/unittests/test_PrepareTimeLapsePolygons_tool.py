"""Unit tests for the Prepare Time Lapse Polygons script tool.

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


class TestPrepareTimeLapsePolygonsTool(unittest.TestCase):
    """Test cases for the Prepare Time Lapse Polygons script tool."""

    @classmethod
    def setUpClass(self):  # pylint: disable=bad-classmethod-argument
        self.maxDiff = None

        tbx_path = os.path.join(os.path.dirname(CWD), "Transit Network Analysis Tools.pyt")
        arcpy.ImportToolbox(tbx_path)

        self.input_data_folder = os.path.join(CWD, "TestInput")
        input_data_helper.make_feature_classes_from_json(self.input_data_folder)
        in_gdb = os.path.join(self.input_data_folder, "CincinnatiTransitNetwork.gdb")
        self.facilities = os.path.join(in_gdb, "TestOrigins_Subset")
        self.num_facilities = int(arcpy.management.GetCount(self.facilities).getOutput(0))
        self.local_nd = os.path.join(in_gdb, "TransitNetwork", "TransitNetwork_ND")

        # Create a unique output directory and gdb for this test
        self.scratch_folder = os.path.join(
            CWD, "TestOutput",
            "Output_PTLP_Tool_" + datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S"))
        os.makedirs(self.scratch_folder)
        self.output_gdb = os.path.join(self.scratch_folder, "outputs.gdb")
        arcpy.management.CreateFileGDB(os.path.dirname(self.output_gdb), os.path.basename(self.output_gdb))

    def test_tool(self):
        """Test the tool."""
        out_fc = os.path.join(self.output_gdb, "TimeLapsePolys")
        # Use a custom travel mode object
        tm = arcpy.nax.TravelMode(arcpy.nax.GetTravelModes(self.local_nd)["Public transit time"])
        attr_params = tm.attributeParameters
        attr_params[('PublicTransitTime', 'Exclude lines')] = "1"
        tm.attributeParameters = attr_params
        # Run the tool
        arcpy.TransitNetworkAnalysisTools.PrepareTimeLapsePolygons(  # pylint: disable=no-member
            self.facilities,
            out_fc,
            self.local_nd,
            tm,
            [30, 45],
            "Minutes",
            "Wednesday",
            "08:00",
            "Wednesday",
            "08:02",
            1,
            "Away From Facilities",
            "Rings",
            "Overlap",
            4,  # Parallel processes
            None,  # Barriers
            True  # Precalculate network locations
        )
        self.assertTrue(arcpy.Exists(out_fc))
        # 4 facilities, 2 cutoffs, 3 time slices = 24 total output polygons
        expected_num_polygons = 24
        self.assertEqual(expected_num_polygons, int(arcpy.management.GetCount(out_fc).getOutput(0)))


if __name__ == '__main__':
    unittest.main()
