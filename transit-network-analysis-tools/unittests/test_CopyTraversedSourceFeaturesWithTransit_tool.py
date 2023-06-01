"""Unit tests for the Copy Traversed Source Features With Transit script tool.

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


class TestCopyTraversedSourceFeaturesWithTransitTool(unittest.TestCase):
    """Test cases for the Copy Traversed Source Features With Transit script tool."""

    @classmethod
    def setUpClass(self):  # pylint: disable=bad-classmethod-argument
        self.maxDiff = None

        tbx_path = os.path.join(os.path.dirname(CWD), "Transit Network Analysis Tools.pyt")
        arcpy.ImportToolbox(tbx_path)

        self.input_data_folder = os.path.join(CWD, "TestInput")
        input_data_helper.make_feature_classes_from_json(self.input_data_folder)
        self.in_gdb = os.path.join(self.input_data_folder, "CincinnatiTransitNetwork.gdb")
        self.local_nd = os.path.join(self.in_gdb, "TransitNetwork", "TransitNetwork_ND")
        self.local_tm_time = "Public transit time"

        # Create a unique output directory and gdb for this test
        self.scratch_folder = os.path.join(
            CWD, "TestOutput",
            "Output_CTSFWT_Tool_" + datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S"))
        os.makedirs(self.scratch_folder)
        self.output_gdb = os.path.join(self.scratch_folder, "outputs.gdb")
        arcpy.management.CreateFileGDB(os.path.dirname(self.output_gdb), os.path.basename(self.output_gdb))
        arcpy.env.workspace = self.output_gdb

        self.expected_fields = ["WalkTime", "RideTime", "WaitTime", "RunID", "RunDepTime", "RunArrTime"]

    def check_results(self, out_edges, expect_nulls):
        """Check that the results are generally correct.

        These tests use real-world tutorial data, so don't verify the exact output.
        """
        self.assertTrue(arcpy.Exists(out_edges))
        self.assertTrue(
            set(self.expected_fields).issubset({f.name for f in arcpy.ListFields(out_edges)}),
            "Expected fields weren't added to traversal result."
        )
        ride_time_idx = self.expected_fields.index("RideTime")
        wait_time_idx = self.expected_fields.index("WaitTime")
        some_transit_used = False
        some_transit_data_populated = False
        for row in arcpy.da.SearchCursor(
            out_edges, self.expected_fields + ["Attr_PublicTransitTime", "SourceName", "OID@"]
        ):
            oid = row[-1]
            source = row[-2]
            impedance = row[-3]
            if source == "LineVariantElements":
                some_transit_used = True
                for idx, field in enumerate(self.expected_fields):
                    if not expect_nulls:
                        self.assertIsNotNone(row[idx], f"Null transit field value for a transit edge. OID {oid}")
                    if field == "WalkTime":
                        self.assertEqual(0, row[idx], f"WalkTime should be 0 for a transit edge. OID {oid}")
                run_time = row[ride_time_idx]
                if run_time is not None:
                    some_transit_data_populated = True
                    self.assertAlmostEqual(
                        impedance, row[ride_time_idx] + row[wait_time_idx], 2,
                        f"Ride time + wait time does not equal impedance. OID {oid}")
            else:
                for idx, field in enumerate(self.expected_fields):
                    if field == "WalkTime":
                        self.assertEqual(impedance, row[idx], f"Incorrect WalkTime for a non-transit edge. OID {oid}")
                    else:
                        self.assertIsNone(row[idx], f"Transit fields should be null for a non-transit edge. OID {oid}")
        self.assertTrue(
            some_transit_used, "No transit was used at all in this analysis, so the test case is probably invalid.")
        self.assertTrue(
            some_transit_data_populated,
            "No transit fields were successfully populated even though transit was used."
        )

    def test_cf_layer(self):
        """Test the tool with a closest facility layer."""
        # Create and solve a closest facility layer
        layer_name = "CF"
        lyr = arcpy.na.MakeClosestFacilityAnalysisLayer(
            self.local_nd, layer_name, self.local_tm_time,
            number_of_facilities_to_find=1,
            time_of_day=datetime.datetime(1900, 1, 3, 17, 0, 0),
            time_of_day_usage="START_TIME"
        ).getOutput(0)
        arcpy.na.AddLocations(
            lyr,
            "Incidents",
            os.path.join(self.in_gdb, "TestOrigins_Subset")
        )
        arcpy.na.AddLocations(
            lyr,
            "Facilities",
            os.path.join(self.in_gdb, "TestDestinations_Subset")
        )
        arcpy.na.Solve(lyr)
        # Run the tool
        out_edges = layer_name + "_Edges"
        arcpy.TransitNetworkAnalysisTools.CopyTraversedSourceFeaturesWithTransit(  # pylint: disable=no-member
            lyr,
            self.output_gdb,
            out_edges,
            layer_name + "_Junctions",
            layer_name + "_Turns",
        )
        warnings = arcpy.GetMessages(1)
        expect_nulls = "Could not find public transit traversal information" in warnings
        self.check_results(out_edges, expect_nulls)

    def test_sa_layer(self):
        """Test the tool with a service area layer."""
        # Create and solve a service layer
        layer_name = "SA"
        lyr = arcpy.na.MakeServiceAreaAnalysisLayer(
            self.local_nd, layer_name, self.local_tm_time,
            cutoffs=[30],
            time_of_day=datetime.datetime(1900, 1, 3, 17, 0, 0),
            output_type="LINES"
        ).getOutput(0)
        facilities_lyr = "InFacilities"
        arcpy.management.MakeFeatureLayer(
            os.path.join(self.in_gdb, "TestOrigins_Subset"),
            facilities_lyr,
            "ObjectID = 1"
        )
        arcpy.na.AddLocations(
            lyr,
            "Facilities",
            facilities_lyr
        )
        arcpy.na.Solve(lyr)
        # Run the tool
        out_edges = layer_name + "_Edges"
        arcpy.TransitNetworkAnalysisTools.CopyTraversedSourceFeaturesWithTransit(  # pylint: disable=no-member
            lyr,
            self.output_gdb,
            out_edges,
            layer_name + "_Junctions",
            layer_name + "_Turns",
        )
        warnings = arcpy.GetMessages(1)
        expect_nulls = "Could not find public transit traversal information" in warnings
        self.check_results(out_edges, expect_nulls)

    def test_rt_layer(self):
        """Test the tool with a route layer."""
        # Create and solve a service layer
        layer_name = "RT"
        lyr = arcpy.na.MakeRouteAnalysisLayer(
            self.local_nd, layer_name, self.local_tm_time,
            time_of_day=datetime.datetime(1900, 1, 3, 17, 0, 0)
        ).getOutput(0)
        stop_1_lyr = "Stops1"
        arcpy.management.MakeFeatureLayer(
            os.path.join(self.in_gdb, "TestOrigins_Subset"),
            stop_1_lyr,
            "ObjectID = 3"
        )
        arcpy.na.AddLocations(
            lyr,
            "Stops",
            stop_1_lyr
        )
        stop_2_lyr = "Stops2"
        arcpy.management.MakeFeatureLayer(
            os.path.join(self.in_gdb, "TestDestinations_Subset"),
            stop_2_lyr,
            "ObjectID = 2"
        )
        arcpy.na.AddLocations(
            lyr,
            "Stops",
            stop_2_lyr
        )
        arcpy.na.Solve(lyr)
        # Run the tool
        out_edges = layer_name + "_Edges"
        out_junctions = layer_name + "_Junctions"
        out_turns = layer_name + "_Turns"
        result = arcpy.TransitNetworkAnalysisTools.CopyTraversedSourceFeaturesWithTransit(  # pylint: disable=no-member
            lyr,
            self.output_gdb,
            out_edges,
            out_junctions,
            out_turns,
        )
        warnings = arcpy.GetMessages(1)
        expect_nulls = "Could not find public transit traversal information" in warnings
        self.check_results(out_edges, expect_nulls)
        # Check derived outputs
        self.assertEqual(
            os.path.join(self.output_gdb, out_edges), result.getOutput(0), "Incorrect derived output edges.")
        out_junctions_path = os.path.join(self.output_gdb, out_junctions)
        self.assertEqual(out_junctions_path, result.getOutput(1), "Incorrect derived output junctions.")
        self.assertTrue(arcpy.Exists(out_junctions_path), "Output junctions does not exist.")
        out_turns_path = os.path.join(self.output_gdb, out_turns)
        self.assertEqual(out_turns_path, result.getOutput(2), "Incorrect derived output turns.")
        self.assertTrue(arcpy.Exists(out_turns_path), "Output turns does not exist.")
        self.assertTrue(result.getOutput(3).isNetworkAnalystLayer, "Derived output is not an NA layer.")


if __name__ == '__main__':
    unittest.main()
