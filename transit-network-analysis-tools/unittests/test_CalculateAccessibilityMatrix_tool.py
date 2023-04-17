"""Unit tests for the Calculate Accessibility Matrix script tool.

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


class TestCalculateAccessibilityMatrixTool(unittest.TestCase):
    """Test cases for the CalculateAccessibilityMatrix script tool."""

    @classmethod
    def setUpClass(self):  # pylint: disable=bad-classmethod-argument
        self.maxDiff = None

        tbx_path = os.path.join(os.path.dirname(CWD), "Transit Network Analysis Tools.pyt")
        arcpy.ImportToolbox(tbx_path)

        self.input_data_folder = os.path.join(CWD, "TestInput")
        input_data_helper.make_feature_classes_from_json(self.input_data_folder)
        in_gdb = os.path.join(self.input_data_folder, "CincinnatiTransitNetwork.gdb")
        self.origins = os.path.join(in_gdb, "TestOrigins")
        self.destinations = os.path.join(in_gdb, "TestDestinations")
        self.num_origins = int(arcpy.management.GetCount(self.origins).getOutput(0))
        self.num_dests = int(arcpy.management.GetCount(self.destinations).getOutput(0))
        self.local_nd = os.path.join(in_gdb, "TransitNetwork", "TransitNetwork_ND")
        self.local_tm_time = "Public transit time"

        # Create a unique output directory and gdb for this test
        self.scratch_folder = os.path.join(
            CWD, "TestOutput",
            "Output_CAM_Tool_" + datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S"))
        os.makedirs(self.scratch_folder)
        self.output_gdb = os.path.join(self.scratch_folder, "outputs.gdb")
        arcpy.management.CreateFileGDB(os.path.dirname(self.output_gdb), os.path.basename(self.output_gdb))

    def check_tool_output(self, out_origins, weighted, expected_num_origins, num_dests):
        """Do some basic checks of the output origins."""
        self.assertTrue(arcpy.Exists(out_origins), "Output origins does not exist.")
        self.assertEqual(
            expected_num_origins, int(arcpy.management.GetCount(out_origins).getOutput(0)),
            "Incorrect number of output origins."
        )
        expected_cam_fields = ["TotalDests", "PercDests"] + \
                              [f"DsAL{p}Perc" for p in range(10, 100, 10)] + \
                              [f"PsAL{p}Perc" for p in range(10, 100, 10)]
        self.assertTrue(
            set(expected_cam_fields).issubset({f.name for f in arcpy.ListFields(out_origins)}),
            "Incorrect fields in origins after Calculate Accessibility Matrix"
        )
        max_dests = 0
        for row in arcpy.da.SearchCursor(out_origins, expected_cam_fields):
            for val in row:
                self.assertIsNotNone(val, "Unexpected null value in output field.")
            max_dests = max(row[0], max_dests)
        if weighted:
            # Because this calculation used a weight field, the number of destinations found for some origins should
            # exceed the number of destination records in the input feature class.  Don't check specific results, but at
            # least verify that the weight field was used and that results are generally correct.
            self.assertGreater(max_dests, num_dests)
        else:
            # Because this calculation did not use a weight field, the number of destinations found for any origins
            # should not exceed the number of destination records in the input feature class.  Don't check specific
            # results, but at least verify that the number of destinations found is generally correct.
            self.assertGreater(max_dests, 0)
            self.assertLessEqual(max_dests, self.num_dests)

    def test_diff_points_unweighted(self):
        """Test that the tool runs with different origin and destination points not using a weight field."""
        out_origins = os.path.join(self.output_gdb, "Origins_pts_unweighted")
        arcpy.TransitNetworkAnalysisTools.CalculateAccessibilityMatrix(  # pylint: disable=no-member
            self.origins,
            self.destinations,
            out_origins,
            self.local_nd,
            self.local_tm_time,
            30,  # Cutoff
            "Minutes",
            "Wednesday",
            "08:00",
            "Wednesday",
            "08:03",
            1,
            10,  # Chunk size,
            4,  # Parallel processes
            None,  # Weight field
            None,  # Barriers
            True  # Precalculate network locations
        )
        self.check_tool_output(out_origins, False, self.num_origins, self.num_dests)

    def test_diff_points_weighted(self):
        """Test that the tool runs with different origin and destination points using a weight field."""
        out_origins = os.path.join(self.output_gdb, "Origins_pts_weighted")
        arcpy.TransitNetworkAnalysisTools.CalculateAccessibilityMatrix(  # pylint: disable=no-member
            self.origins,
            self.destinations,
            out_origins,
            self.local_nd,
            self.local_tm_time,
            30,  # Cutoff
            "Minutes",
            "Wednesday",
            "08:00",
            "Wednesday",
            "08:03",
            1,
            10,  # Chunk size,
            4,  # Parallel processes
            "NumJobs",  # Weight field
            None,  # Barriers
            True  # Precalculate network locations
        )
        self.check_tool_output(out_origins, True, self.num_origins, self.num_dests)

    def test_same_origins_destinations(self):
        """Test when the origins and destinations are the same."""
        out_origins = os.path.join(self.output_gdb, "Origins_same")
        arcpy.TransitNetworkAnalysisTools.CalculateAccessibilityMatrix(  # pylint: disable=no-member
            self.origins,
            self.origins,
            out_origins,
            self.local_nd,
            self.local_tm_time,
            30,  # Cutoff
            "Minutes",
            "Wednesday",
            "08:00",
            "Wednesday",
            "08:03",
            1,
            10,  # Chunk size,
            4,  # Parallel processes
            None,  # Weight field
            None,  # Barriers
            True  # Precalculate network locations
        )
        self.check_tool_output(out_origins, False, self.num_origins, self.num_origins)

    def test_unchunked(self):
        """Test that the tool runs correctly when origins and destinations can be handled in one chunk.

        Also use a specific date.
        """
        out_origins = os.path.join(self.output_gdb, "Origins_unchunked")
        arcpy.TransitNetworkAnalysisTools.CalculateAccessibilityMatrix(  # pylint: disable=no-member
            self.origins,
            self.destinations,
            out_origins,
            self.local_nd,
            self.local_tm_time,
            30,  # Cutoff
            "Minutes",
            "20190501",
            "08:00",
            "20190501",
            "08:03",
            1,
            1000,  # Chunk size,
            4,  # Parallel processes
            "NumJobs",  # Weight field
            None,  # Barriers
            True  # Precalculate network locations
        )
        self.check_tool_output(out_origins, True, self.num_origins, self.num_dests)

    def test_polygon_inputs(self):
        """Test using polygon feature classes as inputs."""
        out_origins = os.path.join(self.output_gdb, "Origins_polygons")
        arcpy.TransitNetworkAnalysisTools.CalculateAccessibilityMatrix(  # pylint: disable=no-member
            self.origins + "_Polygons",
            self.destinations + "_Polygons",
            out_origins,
            self.local_nd,
            self.local_tm_time,
            30,  # Cutoff
            "Minutes",
            "Wednesday",
            "08:00",
            "Wednesday",
            "08:03",
            1,
            10,  # Chunk size,
            4,  # Parallel processes
            None,  # Weight field
            None,  # Barriers
            True  # Precalculate network locations
        )
        self.check_tool_output(out_origins, False, self.num_origins, self.num_dests)
        # Verify shape type of output origins
        self.assertEqual("Polygon", arcpy.Describe(out_origins).shapeType)


if __name__ == '__main__':
    unittest.main()
