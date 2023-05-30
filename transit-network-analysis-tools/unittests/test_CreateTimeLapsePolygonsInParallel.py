"""Unit tests for the CreateTimeLapsePolygonsInParallel.py module.

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
import CreateTimeLapsePolygonsInParallel  # noqa: E402, pylint: disable=wrong-import-position
from AnalysisHelpers import MAX_ALLOWED_MAX_PROCESSES, arcgis_version  # noqa: E402, pylint: disable=wrong-import-position
import input_data_helper  # noqa: E402, pylint: disable=wrong-import-position


class TestCreateTimeLapsePolygonsInParallel(unittest.TestCase):
    """Test cases for the CreateTimeLapsePolygonsInParallel module."""

    @classmethod
    def setUpClass(self):  # pylint: disable=bad-classmethod-argument
        self.maxDiff = None

        self.input_data_folder = os.path.join(CWD, "TestInput")
        input_data_helper.make_feature_classes_from_json(self.input_data_folder)
        self.in_gdb = os.path.join(self.input_data_folder, "CincinnatiTransitNetwork.gdb")
        self.facilities = os.path.join(self.in_gdb, "TestOrigins_Subset")
        self.num_facilities = int(arcpy.management.GetCount(self.facilities).getOutput(0))
        self.local_nd = os.path.join(self.in_gdb, "TransitNetwork", "TransitNetwork_ND")
        self.local_tm_time = "Public transit time"

        # Create a unique output directory and gdb for this test
        self.scratch_folder = os.path.join(
            CWD, "TestOutput", "Output_ParallelSA_" + datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S"))
        os.makedirs(self.scratch_folder)
        self.output_gdb = os.path.join(self.scratch_folder, "outputs.gdb")
        arcpy.management.CreateFileGDB(os.path.dirname(self.output_gdb), os.path.basename(self.output_gdb))

        self.sa_args = {
            "facilities": self.facilities,
            "cutoffs": [30, 45],
            "time_units": "Minutes",
            "output_polygons": os.path.join(self.output_gdb, "TestPolys"),
            "time_window_start_day": "Wednesday",
            "time_window_start_time": "08:00",
            "time_window_end_day": "Wednesday",
            "time_window_end_time": "08:02",
            "time_increment": 1,
            "network_data_source": self.local_nd,
            "travel_mode": self.local_tm_time,
            "travel_direction": "Toward Facilities",
            "geometry_at_cutoff": "Rings",
            "geometry_at_overlap": "Overlap",
            "max_processes": 4,
            "precalculate_network_locations": True,
            "barriers": None
        }

    def test_validate_inputs(self):
        """Test the validate_inputs function."""
        does_not_exist = os.path.join(self.in_gdb, "DoesNotExist")
        invalid_inputs = [
            ("max_processes", 0, ValueError, "Maximum allowed parallel processes must be greater than 0."),
            ("max_processes", 5000, ValueError, (
                f"The maximum allowed parallel processes cannot exceed {MAX_ALLOWED_MAX_PROCESSES:} due "
                "to limitations imposed by Python's concurrent.futures module."
            )),
            ("cutoffs", [30, -45], ValueError, "Impedance cutoff must be greater than 0."),
            ("time_increment", 0, ValueError, "The time increment must be greater than 0."),
            ("time_units", "BadUnits", ValueError, "Invalid time units: BadUnits"),
            ("travel_direction", "BadValue", ValueError, "Invalid travel direction: BadValue"),
            ("geometry_at_cutoff", "BadValue", ValueError, "Invalid geometry at cutoff: BadValue"),
            ("geometry_at_overlap", "BadValue", ValueError, "Invalid geometry at overlap: BadValue"),
            ("facilities", does_not_exist, ValueError, f"Input dataset {does_not_exist} does not exist."),
            ("barriers", [does_not_exist], ValueError, f"Input dataset {does_not_exist} does not exist."),
            ("network_data_source", does_not_exist, ValueError,
             f"Input network dataset {does_not_exist} does not exist."),
            ("travel_mode", "BadTM", ValueError if arcgis_version >= "3.1" else RuntimeError, ""),
        ]
        for invalid_input in invalid_inputs:
            property_name, value, error_type, expected_message = invalid_input
            with self.subTest(
                property_name=property_name, value=value, error_type=error_type, expected_message=expected_message
            ):
                inputs = deepcopy(self.sa_args)
                inputs[property_name] = value
                sa_solver = CreateTimeLapsePolygonsInParallel.ServiceAreaSolver(**inputs)
                with self.assertRaises(error_type) as ex:
                    sa_solver._validate_inputs()
                if expected_message:
                    self.assertEqual(expected_message, str(ex.exception))

    def test_solve_service_areas_in_parallel(self):
        """Test the full solve Service Area workflow."""
        out_fc = os.path.join(self.output_gdb, "TestSolve")
        sa_inputs = deepcopy(self.sa_args)
        sa_inputs["output_polygons"] = out_fc
        sa_solver = CreateTimeLapsePolygonsInParallel.ServiceAreaSolver(**sa_inputs)
        sa_solver.solve_service_areas_in_parallel()
        self.assertTrue(arcpy.Exists(out_fc))
        # 4 facilities, 2 cutoffs, 3 time slices = 24 total output polygons
        expected_num_polygons = 24
        self.assertEqual(expected_num_polygons, int(arcpy.management.GetCount(out_fc).getOutput(0)))


if __name__ == '__main__':
    unittest.main()
