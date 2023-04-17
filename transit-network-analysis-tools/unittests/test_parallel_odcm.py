"""Unit tests for the parallel_odcm.py module.

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
import unittest
import pandas as pd
from copy import deepcopy
from glob import glob
import arcpy
import input_data_helper

CWD = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(CWD))
import parallel_odcm  # noqa: E402, pylint: disable=wrong-import-position
import AnalysisHelpers  # noqa: E402, pylint: disable=wrong-import-position


class TestParallelODCM(unittest.TestCase):
    """Test cases for the parallel_odcm module."""

    @classmethod
    def setUpClass(self):  # pylint: disable=bad-classmethod-argument
        """Set up shared test properties."""
        self.maxDiff = None

        self.input_data_folder = os.path.join(CWD, "TestInput")
        input_data_helper.make_feature_classes_from_json(self.input_data_folder)
        in_gdb = os.path.join(self.input_data_folder, "CincinnatiTransitNetwork.gdb")
        self.origins = os.path.join(in_gdb, "TestOrigins")
        self.origins_subset = os.path.join(in_gdb, "TestOrigins_Subset")
        self.destinations = os.path.join(in_gdb, "TestDestinations")
        self.destinations_subset = os.path.join(in_gdb, "TestDestinations_Subset")
        self.num_origins = int(arcpy.management.GetCount(self.origins).getOutput(0))
        self.num_dests = int(arcpy.management.GetCount(self.destinations).getOutput(0))
        self.local_nd = os.path.join(in_gdb, "TransitNetwork", "TransitNetwork_ND")
        self.local_tm_time = "Public transit time"

        # Create a unique output directory and gdb for this test
        self.scratch_folder = os.path.join(
            CWD, "TestOutput", "Output_ParallelODCM_" + datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S"))
        os.makedirs(self.scratch_folder)
        self.output_gdb = os.path.join(self.scratch_folder, "outputs.gdb")
        arcpy.management.CreateFileGDB(os.path.dirname(self.output_gdb), os.path.basename(self.output_gdb))

        self.expected_cam_fields = ["TotalDests", "PercDests"] + \
                                   [f"DsAL{p}Perc" for p in range(10, 100, 10)] + \
                                   [f"PsAL{p}Perc" for p in range(10, 100, 10)]
        self.expected_ctts_columns = ["OriginOID", "DestinationOID", "count", "min", "max", "mean"]

        self.od_args = {
            "tool": AnalysisHelpers.ODTool.CalculateAccessibilityMatrix,
            "origins": self.origins,
            "destinations": self.destinations,
            "destination_where_clause": "NumJobs <= 10",
            "network_data_source": self.local_nd,
            "travel_mode": self.local_tm_time,
            "time_units": arcpy.nax.TimeUnits.Minutes,
            "cutoff": 120,
            "scratch_folder": self.scratch_folder,
            "od_output_location": self.scratch_folder,
            "barriers": []
        }

        self.parallel_od_class_args = {
            "tool": AnalysisHelpers.ODTool.CalculateAccessibilityMatrix.name,
            "origins": self.origins,
            "destinations": self.destinations,
            "network_data_source": self.local_nd,
            "travel_mode": self.local_tm_time,
            "max_origins": 10,
            "max_destinations": 10,
            "time_window_start_day": "Wednesday",
            "time_window_start_time": "08:00",
            "time_window_end_day": "Wednesday",
            "time_window_end_time": "08:03",
            "time_increment": 1,
            "max_processes": 4,
            "time_units": "Minutes",
            "cutoff": 30,
            "weight_field": "NumJobs",
            "barriers": [],
            "out_csv_file": "",
            "out_na_folder": ""
        }

    def test_ODCostMatrix_select_inputs(self):
        """Test the _select_inputs method of the ODCostMatrix class."""
        od = parallel_odcm.ODCostMatrix(**self.od_args)
        origin_criteria = [1, 2]  # Encompasses two origins
        dest_criteria = [5, 9]  # Encompasses five destinations, two of which have > 10 jobs
        od._select_inputs(origin_criteria, dest_criteria)
        self.assertEqual(2, int(arcpy.management.GetCount(od.input_origins_layer_obj).getOutput(0)))
        self.assertEqual(3, int(arcpy.management.GetCount(od.input_destinations_layer_obj).getOutput(0)))

    def test_ODCostMatrix_solve(self):
        """Test the solve method of the ODCostMatrix class."""
        # Initialize an ODCostMatrix analysis object
        out_folder = os.path.join(self.scratch_folder, "ODCostMatrix")
        os.makedirs(out_folder)
        od_inputs = deepcopy(self.od_args)
        od_inputs["od_output_location"] = out_folder
        od = parallel_odcm.ODCostMatrix(**od_inputs)
        # Solve a chunk
        origin_criteria = [1, 3]  # Encompasses 3 rows
        dest_criteria = [11, 15]  # Encompasses five destinations, one of which has > 10 jobs
        time_of_day = datetime.datetime(1900, 1, 3, 10, 0, 0)
        od.solve(origin_criteria, dest_criteria, time_of_day)
        # Check results
        self.assertIsInstance(od.job_result, dict)
        self.assertTrue(od.job_result["solveSucceeded"], "OD solve failed")
        time_string = time_of_day.strftime("%Y%m%d_%H%M%S")
        expected_out_file = os.path.join(
            out_folder,
            (
                f"ODLines_O_{origin_criteria[0]}_{origin_criteria[1]}_"
                f"D_{dest_criteria[0]}_{dest_criteria[1]}_"
                f"T_{time_string}.csv"
            )
        )
        self.assertTrue(os.path.exists(od.job_result["outputLines"]), "OD line CSV file output does not exist.")
        self.assertEqual(expected_out_file, od.job_result["outputLines"], "OD line CSV file has the wrong filepath.")
        row_count = pd.read_csv(expected_out_file).shape[0]
        self.assertEqual(12, row_count, "OD line CSV file has an incorrect number of rows.")

    def test_solve_od_cost_matrix(self):
        """Test the solve_od_cost_matrix function."""
        result = parallel_odcm.solve_od_cost_matrix(
            self.od_args, [[1, 3], [11, 15], datetime.datetime(1900, 1, 3, 10, 0, 0)])
        # Check results
        self.assertIsInstance(result, dict)
        self.assertTrue(os.path.exists(result["logFile"]), "Log file does not exist.")
        self.assertTrue(result["solveSucceeded"], "OD solve failed")
        self.assertTrue(arcpy.Exists(result["outputLines"]), "OD line output does not exist.")
        self.assertEqual(12, int(arcpy.management.GetCount(result["outputLines"]).getOutput(0)))

    def test_ParallelODCalculator_validate_od_settings(self):
        """Test the _validate_od_settings function."""
        # Test that with good inputs, nothing should happen
        od_calculator = parallel_odcm.ParallelODCalculator(**self.parallel_od_class_args)
        od_calculator._validate_od_settings()
        # Test completely invalid travel mode
        od_inputs = deepcopy(self.parallel_od_class_args)
        od_inputs["travel_mode"] = "InvalidTM"
        od_calculator = parallel_odcm.ParallelODCalculator(**od_inputs)
        error_type = ValueError if AnalysisHelpers.arcgis_version >= "3.1" else RuntimeError
        with self.assertRaises(error_type):
            od_calculator._validate_od_settings()

    def test_ParallelODCalculator_solve_od_in_parallel_cam_weight(self):
        """Test Calculate Accessibility Matrix tool solving and post-processing using a weight field."""
        # Run parallel process. This calculates the OD and also post-processes the results
        test_origins = os.path.join(self.output_gdb, "Origins_CAM_weighted")
        arcpy.management.Copy(self.origins, test_origins)
        od_inputs = deepcopy(self.parallel_od_class_args)
        od_inputs["origins"] = test_origins
        od_calculator = parallel_odcm.ParallelODCalculator(**od_inputs)
        od_calculator.solve_od_in_parallel()

        # Check results
        self.assertEqual(13, int(arcpy.management.GetCount(test_origins).getOutput(0)))
        self.assertTrue(
            set(self.expected_cam_fields).issubset({f.name for f in arcpy.ListFields(test_origins)}),
            "Incorrect fields in origins after Calculate Accessibility Matrix"
        )
        # Because this calculation used a weight field, the number of destinations found for some origins should exceed
        # the number of destination records in the input feature class.  Don't check specific results, but at least
        # verify that the weight field was used and that results are generally correct.  This is not a comprehensive
        # test for the accuracy of the results and the specific post-processing behavior.
        max_dests = 0
        for row in arcpy.da.SearchCursor(test_origins, self.expected_cam_fields):
            for val in row:
                self.assertIsNotNone(val, "Unexpected null record")
            max_dests = max(row[0], max_dests)
        self.assertGreater(max_dests, self.num_dests)

    def test_ParallelODCalculator_solve_od_in_parallel_cam_no_weight(self):
        """Test Calculate Accessibility Matrix tool solving and post-processing without using a weight field."""
        # Run parallel process. This calculates the OD and also post-processes the results
        test_origins = os.path.join(self.output_gdb, "Origins_CAM_unweighted")
        arcpy.management.Copy(self.origins, test_origins)
        od_inputs = deepcopy(self.parallel_od_class_args)
        od_inputs["origins"] = test_origins
        od_inputs["weight_field"] = None
        od_calculator = parallel_odcm.ParallelODCalculator(**od_inputs)
        od_calculator.solve_od_in_parallel()

        # Check results
        self.assertEqual(13, int(arcpy.management.GetCount(test_origins).getOutput(0)))
        self.assertTrue(
            set(self.expected_cam_fields).issubset({f.name for f in arcpy.ListFields(test_origins)}),
            "Incorrect fields in origins after Calculate Accessibility Matrix"
        )
        # Because this calculation did not use a weight field, the number of destinations found for any origins should
        # not exceed the number of destination records in the input feature class.  Don't check specific results, but at
        # least verify that the number of destinations found is generally correct.  This is not a comprehensive
        # test for the accuracy of the results and the specific post-processing behavior.
        max_dests = 0
        for row in arcpy.da.SearchCursor(test_origins, self.expected_cam_fields):
            for val in row:
                self.assertIsNotNone(val, "Unexpected null record")
            max_dests = max(row[0], max_dests)
        self.assertGreater(max_dests, 0)
        self.assertLessEqual(max_dests, self.num_dests)

    def test_ParallelODCalculator_solve_od_in_parallel_ctts(self):
        """Test Calculate Accessibility Matrix tool solving and post-processing without using a weight field."""
        # Run parallel process. This calculates the OD and also post-processes the results
        out_csv = os.path.join(self.scratch_folder, "out_ctts.csv")
        od_inputs = deepcopy(self.parallel_od_class_args)
        od_inputs["tool"] = AnalysisHelpers.ODTool.CalculateTravelTimeStatistics.name
        od_inputs["out_csv_file"] = out_csv
        od_calculator = parallel_odcm.ParallelODCalculator(**od_inputs)
        od_calculator.solve_od_in_parallel()

        # Check results.  Check for generally correct-looking results.  This is not a comprehensive test for the
        # accuracy of the results and the specific post-processing behavior.
        os.path.exists(out_csv)
        df = pd.read_csv(out_csv)
        self.assertEqual(self.num_origins * self.num_dests, df.shape[0], "Incorrect number of rows in CSV.")
        self.assertEqual(self.expected_ctts_columns, df.columns.tolist(), "Incorrect columns in CSV")

    def test_calculate_accessibility_matrix_outputs_unweighted(self):
        """Test the Calculate Accessibility Matrix tool post-processing (unweighted)."""
        test_origins = os.path.join(self.output_gdb, "Origins_CAM_unweighted_pp")
        arcpy.management.Copy(self.origins_subset, test_origins)
        od_inputs = deepcopy(self.parallel_od_class_args)
        od_inputs["origins"] = test_origins
        od_inputs["destinations"] = self.destinations_subset
        od_inputs["weight_field"] = None
        od_calculator = parallel_odcm.ParallelODCalculator(**od_inputs)
        # Do not solve.  Use pre-cooked test data with a known solution.
        od_calculator.od_line_files = glob(
            os.path.join(self.input_data_folder, "CAM_PostProcessing", "*.csv"))
        od_calculator._calculate_accessibility_matrix_outputs()

        # Check results
        self.assertTrue(
            set(self.expected_cam_fields).issubset({f.name for f in arcpy.ListFields(test_origins)}),
            "Incorrect fields in origins after Calculate Accessibility Matrix"
        )
        expected_values = [
            (1, 4, 100.0, 4, 4, 4, 4, 4, 4, 4, 4, 4, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0),
            (2, 0, 0.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            (3, 4, 100.0, 4, 4, 4, 4, 4, 0, 0, 0, 0, 100.0, 100.0, 100.0, 100.0, 100.0, 0.0, 0.0, 0.0, 0.0),
            (4, 3, 75.0, 3, 3, 2, 2, 2, 1, 1, 0, 0, 75.0, 75.0, 50.0, 50.0, 50.0, 25.0, 25.0, 0.0, 0.0)
        ]
        actual_values = []
        for row in arcpy.da.SearchCursor(test_origins, ["OID@"] + self.expected_cam_fields):
            actual_values.append(row)
        self.assertEqual(expected_values, actual_values)

    def test_calculate_accessibility_matrix_outputs_weighted(self):
        """Test the Calculate Accessibility Matrix tool post-processing (weighted)."""
        test_origins = os.path.join(self.output_gdb, "Origins_CAM_weighted_pp")
        arcpy.management.Copy(self.origins_subset, test_origins)
        od_inputs = deepcopy(self.parallel_od_class_args)
        od_inputs["origins"] = test_origins
        od_inputs["destinations"] = self.destinations_subset
        od_calculator = parallel_odcm.ParallelODCalculator(**od_inputs)
        # Do not solve.  Use pre-cooked test data with a known solution.
        od_calculator.od_line_files = glob(
            os.path.join(self.input_data_folder, "CAM_PostProcessing", "*.csv"))
        od_calculator._calculate_accessibility_matrix_outputs()

        # Check results
        self.assertTrue(
            set(self.expected_cam_fields).issubset({f.name for f in arcpy.ListFields(test_origins)}),
            "Incorrect fields in origins after Calculate Accessibility Matrix"
        )
        expected_values = [  # Note: Rounded
            (1, 35, 100.0, 35, 35, 35, 35, 35, 35, 35, 35, 35, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0),
            (2, 0, 0.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            (3, 35, 100.0, 35, 35, 35, 35, 35, 0, 0, 0, 0, 100.0, 100.0, 100.0, 100.0, 100.0, 0.0, 0.0, 0.0, 0.0),
            (4, 35, 100.0, 35, 35, 25, 25, 25, 20, 20, 0, 0, 100.0, 100.0, 71.4, 71.4, 71.4, 57.1, 57.1, 0.0, 0.0)
        ]
        actual_values = []
        for row in arcpy.da.SearchCursor(test_origins, ["OID@"] + self.expected_cam_fields):
            actual_values.append(row)
        for i, e_row in enumerate(expected_values):
            for j, e_val in enumerate(e_row):
                self.assertAlmostEqual(
                    e_val, actual_values[i][j], 1,
                    f"Wrong value in row {i} for field {self.expected_cam_fields[j - 1]}"
                )

    def test_calculate_travel_time_statistics_outputs(self):
        """Test the Calculate Travel Time Statistics tool post-processing."""
        test_origins = os.path.join(self.output_gdb, "Origins_CTTS_pp")
        arcpy.management.Copy(self.origins_subset, test_origins)
        out_csv = os.path.join(self.scratch_folder, "out_ctts_pp.csv")
        od_inputs = deepcopy(self.parallel_od_class_args)
        od_inputs["origins"] = test_origins
        od_inputs["destinations"] = self.destinations_subset
        od_inputs["max_origins"] = 2
        od_inputs["max_destinations"] = 2
        od_inputs["tool"] = AnalysisHelpers.ODTool.CalculateTravelTimeStatistics.name
        od_inputs["out_csv_file"] = out_csv
        od_calculator = parallel_odcm.ParallelODCalculator(**od_inputs)
        # Do not solve.  Use pre-cooked test data with a known solution.
        od_calculator.od_line_files = glob(
            os.path.join(self.input_data_folder, "CTTS_PostProcessing", "*.csv"))
        od_calculator._calculate_travel_time_statistics_outputs()

        # Check results
        df = pd.read_csv(out_csv)
        self.assertEqual(16, df.shape[0], "Incorrect number of rows in CSV.")
        self.assertEqual(self.expected_ctts_columns, df.columns.tolist(), "Incorrect columns in CSV")
        # Don't check every row.  The first row should be sufficient to determine if the statistics were calculated
        # correctly.  We can trust that pandas is doing the rest.
        expected_values = [1, 1, 4, 9.8, 10.2, 10.0]
        self.assertEqual(expected_values, df.iloc[0].to_list())


if __name__ == '__main__':
    unittest.main()
