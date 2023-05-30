"""Unit tests for the parallel_sa.py module.

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
import input_data_helper

CWD = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(CWD))
import parallel_sa  # noqa: E402, pylint: disable=wrong-import-position
import AnalysisHelpers  # noqa: E402, pylint: disable=wrong-import-position


class TestParallelSA(unittest.TestCase):
    """Test cases for the parallel_sa module."""

    @classmethod
    def setUpClass(self):  # pylint: disable=bad-classmethod-argument
        """Set up shared test properties."""
        self.maxDiff = None

        self.input_data_folder = os.path.join(CWD, "TestInput")
        input_data_helper.make_feature_classes_from_json(self.input_data_folder)
        in_gdb = os.path.join(self.input_data_folder, "CincinnatiTransitNetwork.gdb")
        self.facilities = os.path.join(in_gdb, "TestOrigins_Subset")
        self.num_facilities = int(arcpy.management.GetCount(self.facilities).getOutput(0))
        self.local_nd = os.path.join(in_gdb, "TransitNetwork", "TransitNetwork_ND")
        self.local_tm_time = "Public transit time"

        # Create a unique output directory and gdb for this test
        self.scratch_folder = os.path.join(
            CWD, "TestOutput", "Output_ParallelSA_" + datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S"))
        os.makedirs(self.scratch_folder)
        self.output_gdb = os.path.join(self.scratch_folder, "outputs.gdb")
        arcpy.management.CreateFileGDB(os.path.dirname(self.output_gdb), os.path.basename(self.output_gdb))

        self.parallel_sa_class_args = {
            "facilities": self.facilities,
            "output_polygons": os.path.join(self.output_gdb, "TestPolys"),
            "network_data_source": self.local_nd,
            "travel_mode": self.local_tm_time,
            "cutoffs": [30, 45],
            "time_units": "Minutes",
            "time_window_start_day": "Wednesday",
            "time_window_start_time": "08:00",
            "time_window_end_day": "Wednesday",
            "time_window_end_time": "08:02",
            "time_increment": 1,
            "travel_direction": "Toward Facilities",
            "geometry_at_cutoff": "Rings",
            "geometry_at_overlap": "Overlap",
            "max_processes": 4
        }

    def check_ServiceArea_solve(self, sa_inputs, expected_num_polygons):
        """Test the solve method of the ServiceArea class."""
        out_folder = sa_inputs["output_folder"]
        os.makedirs(out_folder)
        sa = parallel_sa.ServiceArea(**sa_inputs)
        time_of_day = datetime.datetime(1900, 1, 3, 10, 0, 0)
        sa.solve(time_of_day)
        # Check results
        self.assertIsInstance(sa.job_result, dict)
        self.assertTrue(sa.job_result["solveSucceeded"], "SA solve failed")
        out_polygons = sa.job_result["outputPolygons"]
        self.assertEqual(
            out_folder, os.path.commonprefix([out_folder, out_polygons]),
            "Output SA polygons feature class has the wrong filepath.")
        self.assertTrue(
            arcpy.Exists(out_polygons),
            "Output SA polygons feature class does not exist.")
        self.assertEqual(
            expected_num_polygons, int(arcpy.management.GetCount(out_polygons).getOutput(0)),
            "Output SA polygons feature class has an incorrect number of rows.")
        self.assertIn(
            AnalysisHelpers.TIME_FIELD, [f.name for f in arcpy.ListFields(out_polygons)],
            "Output SA polygons feature class is missing time of day field.")
        for row in arcpy.da.SearchCursor(out_polygons, [AnalysisHelpers.TIME_FIELD]):
            self.assertEqual(time_of_day, row[0], "Incorrect time field value.")

    def test_ServiceArea_solve_overlap(self):
        """Test the solve method of the ServiceArea class using overlapping polygons."""
        out_folder = os.path.join(self.scratch_folder, "ServiceAreaOverlap")
        sa_inputs = {
            "facilities": self.facilities,
            "cutoffs": [30, 45],
            "time_units": arcpy.nax.TimeUnits.Minutes,
            "travel_direction": arcpy.nax.TravelDirection.FromFacility,
            "geometry_at_cutoff": arcpy.nax.ServiceAreaPolygonCutoffGeometry.Rings,
            "geometry_at_overlap": arcpy.nax.ServiceAreaOverlapGeometry.Overlap,
            "network_data_source": self.local_nd,
            "travel_mode": self.local_tm_time,
            "output_folder": out_folder
        }
        # 4 facilities, 2 cutoffs, 1 time slice = 8 total output polygons
        self.check_ServiceArea_solve(sa_inputs, 8)

    def test_ServiceArea_solve_dissolve(self):
        """Test the solve method of the ServiceArea class using dissolved polygons.

        The time of day field in the output in this case has some special handling.
        """
        out_folder = os.path.join(self.scratch_folder, "ServiceAreaDissolve")
        sa_inputs = {
            "facilities": self.facilities,
            "cutoffs": [30, 45],
            "time_units": arcpy.nax.TimeUnits.Minutes,
            "travel_direction": arcpy.nax.TravelDirection.FromFacility,
            "geometry_at_cutoff": arcpy.nax.ServiceAreaPolygonCutoffGeometry.Rings,
            "geometry_at_overlap": arcpy.nax.ServiceAreaOverlapGeometry.Dissolve,
            "network_data_source": self.local_nd,
            "travel_mode": self.local_tm_time,
            "output_folder": out_folder
        }
        # 4 facilities (dissolved), 2 cutoffs, 1 time slice = 2 total output polygons
        self.check_ServiceArea_solve(sa_inputs, 2)

    def test_ParallelSACalculator_validate_sa_settings(self):
        """Test the _validate_sa_settings function."""
        # Test that with good inputs, nothing should happen
        sa_calculator = parallel_sa.ParallelSACalculator(**self.parallel_sa_class_args)
        sa_calculator._validate_sa_settings()
        # Test completely invalid travel mode
        sa_inputs = deepcopy(self.parallel_sa_class_args)
        sa_inputs["travel_mode"] = "InvalidTM"
        sa_calculator = parallel_sa.ParallelSACalculator(**sa_inputs)
        error_type = ValueError if AnalysisHelpers.arcgis_version >= "3.1" else RuntimeError
        with self.assertRaises(error_type):
            sa_calculator._validate_sa_settings()

    def test_ParallelSACalculator_solve_sa_in_parallel(self):
        """Test calculating parallel service areas and post-processing."""
        # Run parallel process. This calculates the SAs and also post-processes the results
        out_fc = os.path.join(self.output_gdb, "TestSolveInParallel")
        sa_inputs = deepcopy(self.parallel_sa_class_args)
        sa_inputs["output_polygons"] = out_fc
        sa_calculator = parallel_sa.ParallelSACalculator(**sa_inputs)
        sa_calculator.solve_sa_in_parallel()
        self.assertTrue(arcpy.Exists(out_fc))
        # 4 facilities, 2 cutoffs, 3 time slices = 24 total output polygons
        expected_num_polygons = 24
        self.assertEqual(expected_num_polygons, int(arcpy.management.GetCount(out_fc).getOutput(0)))


if __name__ == '__main__':
    unittest.main()
