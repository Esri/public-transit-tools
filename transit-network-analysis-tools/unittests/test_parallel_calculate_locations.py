"""Unit tests for the parallel_calculate_locations.py module.

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
# pylint: disable=import-error, protected-access, invalid-name

import sys
import os
import datetime
import subprocess
import unittest
import arcpy

CWD = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(CWD))
import parallel_calculate_locations  # noqa: E402, pylint: disable=wrong-import-position
from AnalysisHelpers import configure_global_logger, teardown_logger


class TestParallelCalculateLocations(unittest.TestCase):
    """Test cases for the parallel_calculate_locations module."""

    @classmethod
    def setUpClass(self):  # pylint: disable=bad-classmethod-argument
        """Set up shared test properties."""
        self.maxDiff = None
        self.input_data_folder = os.path.join(CWD, "TestInput")
        in_gdb = os.path.join(self.input_data_folder, "CincinnatiTransitNetwork.gdb")
        self.input_fc = os.path.join(in_gdb, "TestOrigins")
        self.local_nd = os.path.join(in_gdb, "TransitNetwork", "TransitNetwork_ND")
        self.local_tm_time = "Public transit time"
        self.search_criteria = [
            ["StopConnectors", "NONE"],
            ["Stops", "NONE"],
            ["StopsOnStreets", "NONE"],
            ["Streets", "SHAPE"],
            ["TransitNetwork_ND_Junctions", "NONE"]
        ]
        self.search_query = [
            ["StopConnectors", ""],
            ["Stops", ""],
            ["StopsOnStreets", ""],
            ["Streets", "ObjectID <> 1"],
            ["TransitNetwork_ND_Junctions", ""]
        ]

        # Create a unique output directory and gdb for this test
        self.output_folder = os.path.join(
            CWD, "TestOutput", "Output_ParallelCalcLocs_" + datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S"))
        os.makedirs(self.output_folder)
        self.output_gdb = os.path.join(self.output_folder, "outputs.gdb")
        arcpy.management.CreateFileGDB(os.path.dirname(self.output_gdb), os.path.basename(self.output_gdb))

    def check_precalculated_locations(self, fc, check_has_values):
        """Check precalculated locations."""
        loc_fields = {"SourceID", "SourceOID", "PosAlong", "SideOfEdge"}
        actual_fields = set([f.name for f in arcpy.ListFields(fc)])
        self.assertTrue(loc_fields.issubset(actual_fields), "Network location fields not added")
        if check_has_values:
            for row in arcpy.da.SearchCursor(fc, list(loc_fields)):  # pylint: disable=no-member
                for val in row:
                    self.assertIsNotNone(val)

    def test_LocationCalculator_subset_inputs(self):
        """Test the _subset_inputs method of the LocationCalculator class."""
        inputs = {
            "input_fc": self.input_fc,
            "network_data_source": self.local_nd,
            "travel_mode": self.local_tm_time,
            "scratch_folder": self.output_folder
        }
        location_calculator = parallel_calculate_locations.LocationCalculator(**inputs)
        location_calculator._subset_inputs([6, 11])
        self.assertTrue(arcpy.Exists(location_calculator.out_fc), "Subset fc does not exist.")
        self.assertEqual(
            6, int(arcpy.management.GetCount(location_calculator.out_fc).getOutput(0)),
            "Subset feature class has the wrong number of rows."
        )

    def test_LocationCalculator_calculate_locations(self):
        """Test the calculate_locations method of the LocationCalculator class.

        Use all optional Calculate Locations tool settings.
        """
        fc_to_precalculate = os.path.join(self.output_gdb, "PrecalcFC_LocationCalculator")
        arcpy.management.Copy(self.input_fc, fc_to_precalculate)
        inputs = {
            "input_fc": fc_to_precalculate,
            "network_data_source": self.local_nd,
            "travel_mode": self.local_tm_time,
            "scratch_folder": self.output_folder,
            "search_tolerance": "1000 Feet",
            "search_criteria": self.search_criteria,
            "search_query": self.search_query
        }
        location_calculator = parallel_calculate_locations.LocationCalculator(**inputs)
        oid_range = [6, 11]
        location_calculator.calculate_locations(oid_range)
        self.assertTrue(arcpy.Exists(location_calculator.out_fc), "Subset fc does not exist.")
        self.assertEqual(
            6, int(arcpy.management.GetCount(location_calculator.out_fc).getOutput(0)),
            "Subset feature class has the wrong number of rows."
        )
        self.check_precalculated_locations(location_calculator.out_fc, check_has_values=False)
        self.assertEqual(
            location_calculator.out_fc, location_calculator.job_result["outputFC"],
            "outputFC property of job_result was not set correctly."
        )
        self.assertEqual(
            tuple(oid_range), location_calculator.job_result["oidRange"],
            "oidRange property of job_result was not set correctly."
        )

    def test_ParallelLocationCalculator(self):
        """Test the ParallelLocationCalculator class."""
        # The input feature class should not be overwritten by this tool, but copy it first just in case.
        fc_to_precalculate = os.path.join(self.output_gdb, "PrecalcFC_Parallel")
        arcpy.management.Copy(self.input_fc, fc_to_precalculate)
        out_fc = os.path.join(self.output_gdb, "PrecalcFC_Parallel_out")
        logger = configure_global_logger(parallel_calculate_locations.LOG_LEVEL)
        inputs = {
            "logger": logger,
            "input_features": fc_to_precalculate,
            "output_features": out_fc,
            "chunk_size": 6,
            "max_processes": 4,
            "network_data_source": self.local_nd,
            "travel_mode": self.local_tm_time,
            "search_tolerance": "1000 Feet",
            "search_criteria": self.search_criteria,
            "search_query": self.search_query
        }
        try:
            parallel_calculator = parallel_calculate_locations.ParallelLocationCalculator(**inputs)
            parallel_calculator.calc_locs_in_parallel()
            self.assertTrue(arcpy.Exists(out_fc), "Output fc does not exist.")
            self.assertEqual(
                int(arcpy.management.GetCount(self.input_fc).getOutput(0)),
                int(arcpy.management.GetCount(out_fc).getOutput(0)),
                "Output feature class doesn't have the same number of rows as the original input."
            )
            self.check_precalculated_locations(out_fc, check_has_values=True)
        finally:
            teardown_logger(logger)

    def test_cli(self):
        """Test the command line interface."""
        # The input feature class should not be overwritten by this tool, but copy it first just in case.
        fc_to_precalculate = os.path.join(self.output_gdb, "PrecalcFC_CLI")
        arcpy.management.Copy(self.input_fc, fc_to_precalculate)
        out_fc = os.path.join(self.output_gdb, "PrecalcFC_CLI_out")
        inputs = [
            os.path.join(sys.exec_prefix, "python.exe"),
            os.path.join(os.path.dirname(CWD), "parallel_calculate_locations.py"),
            "--input-features", fc_to_precalculate,
            "--output-features", out_fc,
            "--network-data-source", self.local_nd,
            "--chunk-size", "6",
            "--max-processes", "4",
            "--travel-mode", self.local_tm_time,
            "--search-tolerance", "1000 Feet",
            "--search-criteria",
            "StopConnectors NONE;Stops NONE;StopsOnStreets NONE;Streets SHAPE;TransitNetwork_ND_Junctions NONE",
            "--search-query", "Streets 'OBJECTID <> 1'"
        ]
        result = subprocess.run(inputs, check=True)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(arcpy.Exists(out_fc))


if __name__ == '__main__':
    unittest.main()
