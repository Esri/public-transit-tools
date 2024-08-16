"""Unit tests for the Replace Route Geometry With LVEShapes script tool.

Copyright 2024 Esri
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
import random
import arcpy
import input_data_helper

CWD = os.path.dirname(os.path.abspath(__file__))


class TestReplaceRouteGeometryWithLVEShapesTool(unittest.TestCase):
    """Test cases for the Replace Route Geometry With LVEShapes script tool."""

    @classmethod
    def setUpClass(self):  # pylint: disable=bad-classmethod-argument
        self.maxDiff = None
        arcpy.CheckOutExtension("network")

        tbx_path = os.path.join(os.path.dirname(CWD), "Transit Network Analysis Tools.pyt")
        arcpy.ImportToolbox(tbx_path)

        self.input_data_folder = os.path.join(CWD, "TestInput")
        input_data_helper.extract_toy_network(self.input_data_folder)
        self.toy_gdb = os.path.join(self.input_data_folder, "TransitToyNetwork.gdb")
        self.toy_nd = os.path.join(self.toy_gdb, "TransitNetwork", "Transit_Network_ND")
        self.toy_tm_transit = arcpy.nax.GetTravelModes(self.toy_nd)["Transit"]
        self.test_points_1 = os.path.join(self.toy_gdb, "TestPoints1")
        self.test_points_2 = os.path.join(self.toy_gdb, "TestPoints2")

        # Create a unique output directory and gdb for this test
        self.scratch_folder = os.path.join(
            CWD, "TestOutput",
            "Output_RRGWL_Tool_" + datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S"))
        os.makedirs(self.scratch_folder)
        self.output_gdb = os.path.join(self.scratch_folder, "outputs.gdb")
        arcpy.management.CreateFileGDB(os.path.dirname(self.output_gdb), os.path.basename(self.output_gdb))
        arcpy.env.workspace = self.output_gdb

    def test_cf_layer(self):
        """Test the tool with a closest facility layer."""
        # Create and solve a closest facility layer
        layer_name = "CF"
        lyr = arcpy.na.MakeClosestFacilityAnalysisLayer(
            self.toy_nd, layer_name, self.toy_tm_transit,
            number_of_facilities_to_find=1,
            time_of_day=datetime.datetime(1900, 1, 3, 7, 56, 0),
            time_of_day_usage="START_TIME"
        ).getOutput(0)
        arcpy.na.AddLocations(lyr, "Incidents", self.test_points_1)
        arcpy.na.AddLocations(lyr, "Facilities", self.test_points_2)
        arcpy.na.Solve(lyr)
        # Check initial stats for route shapes before updating
        rt_sublayer = arcpy.na.GetNASublayer(lyr, "CFRoutes")
        orig_num_routes = int(arcpy.management.GetCount(rt_sublayer).getOutput(0))
        rt_pt_counts = {}
        for row in arcpy.da.SearchCursor(rt_sublayer, ["OID@", "SHAPE@"]):
            rt_pt_counts[row[0]] = row[1].pointCount
        # Run the tool
        out_lyr = arcpy.TransitNetworkAnalysisTools.ReplaceRouteGeometryWithLVEShapes(  # pylint: disable=no-member
            lyr).getOutput(0)
        out_lyr.saveACopy(os.path.join(self.scratch_folder, layer_name + ".lyrx"))
        # Check stats for updated route shapes
        rt_sublayer = arcpy.na.GetNASublayer(out_lyr, "CFRoutes")
        updated_num_routes = int(arcpy.management.GetCount(rt_sublayer).getOutput(0))
        self.assertEqual(orig_num_routes, updated_num_routes, "Route count is different.")
        for row in arcpy.da.SearchCursor(rt_sublayer, ["OID@", "SHAPE@"]):
            shape = row[1]
            self.assertIsNotNone(shape, "Route shape is null.")
            self.assertGreater(shape.length, 0, "Route shape length is 0.")
            self.assertGreater(
                shape.pointCount, rt_pt_counts[row[0]],
                "pointCount of shape did not increase after geometry was swapped."
            )

    def test_rt_layer(self):
        """Test the tool with a route layer."""
        # Create and solve a route layer
        layer_name = "Route"
        lyr = arcpy.na.MakeRouteAnalysisLayer(
            self.toy_nd, layer_name, self.toy_tm_transit,
            time_of_day=datetime.datetime(1900, 1, 3, 7, 56, 0)
        ).getOutput(0)
        arcpy.na.AddLocations(lyr, "Stops", self.test_points_1)
        arcpy.na.AddLocations(lyr, "Stops", self.test_points_2)
        arcpy.na.Solve(lyr)
        # Check initial stats for route shapes before updating
        rt_sublayer = arcpy.na.GetNASublayer(lyr, "Routes")
        orig_num_routes = int(arcpy.management.GetCount(rt_sublayer).getOutput(0))
        rt_pt_counts = {}
        for row in arcpy.da.SearchCursor(rt_sublayer, ["OID@", "SHAPE@"]):
            rt_pt_counts[row[0]] = row[1].pointCount
        # Run the tool
        out_lyr = arcpy.TransitNetworkAnalysisTools.ReplaceRouteGeometryWithLVEShapes(  # pylint: disable=no-member
            lyr).getOutput(0)
        out_lyr.saveACopy(os.path.join(self.scratch_folder, layer_name + ".lyrx"))
        # Check stats for updated route shapes
        rt_sublayer = arcpy.na.GetNASublayer(out_lyr, "Routes")
        updated_num_routes = int(arcpy.management.GetCount(rt_sublayer).getOutput(0))
        self.assertEqual(orig_num_routes, updated_num_routes, "Route count is different.")
        for row in arcpy.da.SearchCursor(rt_sublayer, ["OID@", "SHAPE@"]):
            shape = row[1]
            self.assertIsNotNone(shape, "Route shape is null.")
            self.assertGreater(shape.length, 0, "Route shape length is 0.")
            self.assertGreater(
                shape.pointCount, rt_pt_counts[row[0]],
                "pointCount of shape did not increase after geometry was swapped."
            )

    def test_wrong_solver(self):
        """Check for correct error when an incorrect solver type is used."""
        # Create a layer of one of the unsupported types
        # Don't attempt to test VRP because the test network doesn't even support VRP.
        layer_name = "WrongType"
        solver_tool = random.choice([
            arcpy.na.MakeODCostMatrixAnalysisLayer,
            arcpy.na.MakeLocationAllocationAnalysisLayer,
            arcpy.na.MakeServiceAreaAnalysisLayer
        ])
        lyr = solver_tool(self.toy_nd, layer_name, self.toy_tm_transit)
        # Run the tool
        with self.assertRaises(arcpy.ExecuteError):
            arcpy.TransitNetworkAnalysisTools.ReplaceRouteGeometryWithLVEShapes(  # pylint: disable=no-member
                lyr)
        expected_message = "The Input Network Analysis Layer must be a Route or Closest Facility layer."
        actual_messages = arcpy.GetMessages(2)
        self.assertIn(expected_message, actual_messages)


if __name__ == '__main__':
    unittest.main()
