"""Unit tests for the Calculate Travel Time Statistics (OD Cost Matrix) script tool.

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
from glob import glob
import pandas as pd
import arcpy
import input_data_helper

CWD = os.path.dirname(os.path.abspath(__file__))


class TestCalculateTravelTimeStatisticsODTool(unittest.TestCase):
    """Test cases for the Calculate Travel Time Statistics (OD Cost Matrix) script tool."""

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
            "Output_CTTSOD_Tool_" + datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S"))
        os.makedirs(self.scratch_folder)
        self.output_gdb = os.path.join(self.scratch_folder, "outputs.gdb")
        arcpy.management.CreateFileGDB(os.path.dirname(self.output_gdb), os.path.basename(self.output_gdb))

    def check_tool_output(self, out_csv, out_na_data_folder=None):
        """Do some basic checks of the output origins."""
        self.assertTrue(os.path.exists(out_csv), "Output CSV file does not exist.")
        df = pd.read_csv(out_csv)
        self.assertGreater(df.shape[0], 0, "CSV file has no rows.")
        expected_ctts_columns = ["OriginOID", "DestinationOID", "count", "min", "max", "mean"]
        self.assertEqual(expected_ctts_columns, df.columns.tolist(), "Incorrect columns in CSV")
        if out_na_data_folder:
            self.assertTrue(os.path.exists(out_na_data_folder), "Output CSV NA data folder does not exist.")
            na_files = glob(os.path.join(out_na_data_folder, "ODLines_*.csv"))
            self.assertGreater(len(na_files), 0, "Output NA data folder contains no CSV files.")
        return df  # Return dataframe for further checks

    def test_basic_points(self):
        """Test with basic point datasets as input."""
        out_csv = os.path.join(self.scratch_folder, "CTTS_Points.csv")
        na_results_folder = os.path.join(self.scratch_folder, "CTTS_Points_NA_Results")
        arcpy.TransitNetworkAnalysisTools.CalculateTravelTimeStatisticsOD(  # pylint: disable=no-member
            self.origins,
            self.destinations,
            out_csv,
            self.local_nd,
            self.local_tm_time,
            "Wednesday",
            "08:00",
            "Wednesday",
            "08:03",
            1,
            10,  # Chunk size,
            4,  # Parallel processes
            True,  # Save individual results folder
            na_results_folder,
            None,  # Barriers
            True  # Precalculate network locations
        )
        self.check_tool_output(out_csv, na_results_folder)

    def test_same_origins_destinations(self):
        """Test when the origins and destinations are the same. No chunking of inputs"""
        out_csv = os.path.join(self.scratch_folder, "CTTS_Same.csv")
        arcpy.TransitNetworkAnalysisTools.CalculateTravelTimeStatisticsOD(  # pylint: disable=no-member
            self.origins,
            self.origins,
            out_csv,
            self.local_nd,
            self.local_tm_time,
            "Wednesday",
            "08:00",
            "Wednesday",
            "08:03",
            1,
            1000,  # Chunk size,
            4,  # Parallel processes
            False,  # Save individual results folder
            None,
            None,  # Barriers
            True  # Precalculate network locations
        )
        self.check_tool_output(out_csv)

    def test_polygon_inputs(self):
        """Test using polygon feature classes as inputs."""
        out_csv = os.path.join(self.scratch_folder, "CTTS_Polygons.csv")
        arcpy.TransitNetworkAnalysisTools.CalculateTravelTimeStatisticsOD(  # pylint: disable=no-member
            self.origins + "_Polygons",
            self.destinations + "_Polygons",
            out_csv,
            self.local_nd,
            self.local_tm_time,
            "Wednesday",
            "08:00",
            "Wednesday",
            "08:03",
            1,
            10,  # Chunk size,
            4,  # Parallel processes
            False,  # Save individual results folder
            None,
            None,  # Barriers
            True  # Precalculate network locations
        )
        self.check_tool_output(out_csv)

    def test_selection_and_oid_mapping(self):
        """Test that the original OIDs are preserved and mapped correctly. Input with selection set."""
        origins_lyr_name = "OriginsLayer"
        arcpy.management.MakeFeatureLayer(self.origins, origins_lyr_name, "ObjectID > 5")
        dests_lyr_name = "DestsLayer"
        arcpy.management.MakeFeatureLayer(self.destinations, dests_lyr_name, "ObjectID > 5")
        out_csv = os.path.join(self.scratch_folder, "CTTS_OIDs.csv")
        arcpy.TransitNetworkAnalysisTools.CalculateTravelTimeStatisticsOD(  # pylint: disable=no-member
            origins_lyr_name,
            dests_lyr_name,
            out_csv,
            self.local_nd,
            self.local_tm_time,
            "Wednesday",
            "08:00",
            "Wednesday",
            "08:03",
            1,
            10,  # Chunk size,
            4,  # Parallel processes
            False,  # Save individual results folder
            None,
            None,  # Barriers
            True  # Precalculate network locations
        )
        df = self.check_tool_output(out_csv)
        self.assertFalse((df["OriginOID"] <= 5).any(), f"OriginOID values are incorrect. {df['OriginOID']}")
        self.assertFalse(
            (df["DestinationOID"] <= 5).any(), f"DestinationOID values are incorrect. {df['DestinationOID']}")


if __name__ == '__main__':
    unittest.main()
