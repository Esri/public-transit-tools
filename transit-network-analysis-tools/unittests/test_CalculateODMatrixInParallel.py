"""Unit tests for the CalculateODMatrixInParallel.py module.

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
from copy import deepcopy
import arcpy

CWD = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(CWD))
import CalculateODMatrixInParallel  # noqa: E402, pylint: disable=wrong-import-position
from AnalysisHelpers import MAX_ALLOWED_MAX_PROCESSES, arcgis_version  # noqa: E402, pylint: disable=wrong-import-position
import input_data_helper  # noqa: E402, pylint: disable=wrong-import-position


class TestCalculateODMatrixInParallel(unittest.TestCase):
    """Test cases for the CalculateODMatrixInParallel module."""

    @classmethod
    def setUpClass(self):  # pylint: disable=bad-classmethod-argument
        self.maxDiff = None

        self.input_data_folder = os.path.join(CWD, "TestInput")
        input_data_helper.make_feature_classes_from_json(self.input_data_folder)
        self.in_gdb = os.path.join(self.input_data_folder, "CincinnatiTransitNetwork.gdb")
        self.origins = os.path.join(self.in_gdb, "TestOrigins")
        self.destinations = os.path.join(self.in_gdb, "TestDestinations")
        self.local_nd = os.path.join(self.in_gdb, "TransitNetwork", "TransitNetwork_ND")
        self.local_tm_time = "Public transit time"

        # Create a unique output directory and gdb for this test
        self.scratch_folder = os.path.join(
            CWD, "TestOutput", "Output_ParallelSA_" + datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S"))
        os.makedirs(self.scratch_folder)
        self.output_gdb = os.path.join(self.scratch_folder, "outputs.gdb")
        arcpy.management.CreateFileGDB(os.path.dirname(self.output_gdb), os.path.basename(self.output_gdb))

        self.od_args = {
            "origins": self.origins,
            "destinations": self.destinations,
            "time_window_start_day": "Wednesday",
            "time_window_start_time": "08:00",
            "time_window_end_day": "Wednesday",
            "time_window_end_time": "08:02",
            "time_increment": 1,
            "network_data_source": self.local_nd,
            "travel_mode": self.local_tm_time,
            "chunk_size": 10,
            "max_processes": 4,
            "precalculate_network_locations": True,
            "barriers": None
        }
        self.cam_inputs = deepcopy(self.od_args)
        self.cam_inputs["output_origins"] = os.path.join(self.output_gdb, "TestCAM")
        self.cam_inputs["time_units"] = "Minutes"
        self.cam_inputs["cutoff"] = 30
        self.cam_inputs["weight_field"] = "NumJobs"
        self.ctts_inputs = deepcopy(self.od_args)
        self.ctts_inputs["out_csv_file"] = os.path.join(self.scratch_folder, "TestCSV")
        self.ctts_inputs["out_na_folder"] = os.path.join(self.scratch_folder, "TestOutNAFolder")

        # Invalid inputs for the base class
        does_not_exist = os.path.join(self.in_gdb, "DoesNotExist")
        self.invalid_inputs = [
            ("chunk_size", -5, ValueError, "Chunk size must be greater than 0."),
            ("max_processes", 0, ValueError, "Maximum allowed parallel processes must be greater than 0."),
            ("max_processes", 5000, ValueError, (
                f"The maximum allowed parallel processes cannot exceed {MAX_ALLOWED_MAX_PROCESSES:} due "
                "to limitations imposed by Python's concurrent.futures module."
            )),
            ("time_increment", 0, ValueError, "The time increment must be greater than 0."),
            ("origins", does_not_exist, ValueError, f"Input dataset {does_not_exist} does not exist."),
            ("destinations", does_not_exist, ValueError, f"Input dataset {does_not_exist} does not exist."),
            ("barriers", [does_not_exist], ValueError, f"Input dataset {does_not_exist} does not exist."),
            ("network_data_source", does_not_exist, ValueError,
             f"Input network dataset {does_not_exist} does not exist."),
            ("travel_mode", "BadTM", ValueError if arcgis_version >= "3.1" else RuntimeError, ""),
        ]

    def test_validate_inputs_cam(self):
        """Test the validate_inputs function of the CalculateAccessibilityMatrix child class."""
        # Check base class invalid inputs and additional validation of child class
        invalid_inputs = self.invalid_inputs + [
            ("cutoff", 0, ValueError, "Impedance cutoff must be greater than 0."),
            ("cutoff", -5, ValueError, "Impedance cutoff must be greater than 0."),
            ("weight_field", "BadField", ValueError,
             (f"The destinations feature class {self.cam_inputs['destinations']} is missing the designated weight "
              "field BadField.")),
            ("weight_field", "Shape", TypeError,
             (f"The weight field Shape in the destinations feature class {self.cam_inputs['destinations']} is not "
              "numerical."))
        ]
        for invalid_input in invalid_inputs:
            property_name, value, error_type, expected_message = invalid_input
            with self.subTest(
                property_name=property_name, value=value, error_type=error_type, expected_message=expected_message
            ):
                inputs = deepcopy(self.cam_inputs)
                inputs[property_name] = value
                sa_solver = CalculateODMatrixInParallel.CalculateAccessibilityMatrix(**inputs)
                with self.assertRaises(error_type) as ex:
                    sa_solver._validate_inputs()
                if expected_message:
                    self.assertEqual(expected_message, str(ex.exception))

    def test_validate_inputs_ctts(self):
        """Test the validate_inputs function of the CalculateTravelTimeStatistics child class."""
        # No additional validation of child class. Just check base class bad inputs.
        for invalid_input in self.invalid_inputs:
            property_name, value, error_type, expected_message = invalid_input
            with self.subTest(
                property_name=property_name, value=value, error_type=error_type, expected_message=expected_message
            ):
                inputs = deepcopy(self.ctts_inputs)
                inputs[property_name] = value
                sa_solver = CalculateODMatrixInParallel.CalculateTravelTimeStatistics(**inputs)
                with self.assertRaises(error_type) as ex:
                    sa_solver._validate_inputs()
                if expected_message:
                    self.assertEqual(expected_message, str(ex.exception))

    def test_CalculateAccessibilityMatrix(self):
        """Test the full CalculateAccessibilityMatrix workflow."""
        od_calculator = CalculateODMatrixInParallel.CalculateAccessibilityMatrix(**self.cam_inputs)
        od_calculator.solve_large_od_cost_matrix()
        self.assertTrue(arcpy.Exists(self.cam_inputs["output_origins"]), "Output origins does not exist.")
        expected_cam_fields = ["TotalDests", "PercDests"] + \
                              [f"DsAL{p}Perc" for p in range(10, 100, 10)] + \
                              [f"PsAL{p}Perc" for p in range(10, 100, 10)]
        self.assertTrue(
            set(expected_cam_fields).issubset({f.name for f in arcpy.ListFields(self.cam_inputs["output_origins"])}),
            "Incorrect fields in origins after CalculateAccessibilityMatrix"
        )

    def test_CalculateTravelTimeStatistics(self):
        """Test the full CalculateTravelTimeStatistics workflow."""
        od_calculator = CalculateODMatrixInParallel.CalculateTravelTimeStatistics(**self.ctts_inputs)
        od_calculator.solve_large_od_cost_matrix()
        self.assertTrue(os.path.exists(self.ctts_inputs["out_csv_file"]))
        self.assertTrue(os.path.exists(self.ctts_inputs["out_na_folder"]))

if __name__ == '__main__':
    unittest.main()
