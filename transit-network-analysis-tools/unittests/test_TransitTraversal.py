"""Unit tests for the TransitTraversal.py module.

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
import arcpy
import input_data_helper

CWD = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(CWD))
import TransitTraversal  # noqa: E402, pylint: disable=wrong-import-position


class TestTransitTraversal(unittest.TestCase):
    """Test cases for the TransitTraversal module."""

    @classmethod
    def setUpClass(self):  # pylint: disable=bad-classmethod-argument
        """Set up shared test properties."""
        self.maxDiff = None

        self.input_data_folder = os.path.join(CWD, "TestInput")
        # input_data_helper.make_feature_classes_from_json(self.input_data_folder)
        self.toy_gdb = os.path.join(self.input_data_folder, "TransitToyNetwork.gdb")
        self.toy_fd = os.path.join(self.toy_gdb, "TransitNetwork")
        self.toy_nd = os.path.join(self.toy_fd, "Transit_Network_ND")
        self.toy_tm_transit = arcpy.nax.GetTravelModes(self.toy_nd)["Transit"]
        self.toy_tm_with_bike = arcpy.nax.GetTravelModes(self.toy_nd)["Transit with bicycle"]
        self.toy_tm_with_wheelchair = arcpy.nax.GetTravelModes(self.toy_nd)["Transit with wheelchair"]

        # Create a unique output directory and gdb for this test
        self.scratch_folder = os.path.join(
            CWD, "TestOutput", "Output_Traversal_" + datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S"))
        os.makedirs(self.scratch_folder)
        self.output_gdb = os.path.join(self.scratch_folder, "outputs.gdb")
        arcpy.management.CreateFileGDB(os.path.dirname(self.output_gdb), os.path.basename(self.output_gdb))

        self.expected_fields = ["WalkTime", "RideTime", "WaitTime", "RunID", "RunDepTime", "RunArrTime"]

    def calculate_traversal_and_check_results(
            self, expected_output, traversed_edges_fc, transit_fd, travel_mode, analysis_datetime,
            analysis_time_type=TransitTraversal.AnalysisTimeType.StartTime, route_id_field="RouteID",
            use_impedance_in_field_names=False
         ):
        """Add transit to the traversal result feature class and check results."""
        # Copy the traversed edges feature class to the output gdb to avoid altering the input
        out_fc = os.path.join(self.output_gdb, os.path.basename(traversed_edges_fc))
        arcpy.management.Copy(traversed_edges_fc, out_fc)
        # Run the transit traversal result calculator
        traversal_calculator = TransitTraversal.TransitTraversalResultCalculator(
            out_fc,
            analysis_datetime,
            analysis_time_type,
            transit_fd,
            travel_mode,
            route_id_field,
            use_impedance_in_field_names
        )
        traversal_calculator.add_transit_to_traversal_result()
        # Check the results
        self.assertTrue(
            set(self.expected_fields).issubset({f.name for f in arcpy.ListFields(out_fc)}),
            "Expected fields weren't added to traversal result."
        )
        actual_output = []
        attr_field = "Attr_Minutes"
        if use_impedance_in_field_names:
            attr_field = "Attr_" + travel_mode.impedance
        for row in arcpy.da.SearchCursor(out_fc, ["OID@", "SourceName", attr_field] + [self.expected_fields]):
            actual_output.append(row)
            print(row)
        self.assertEqual(expected_output, actual_output)

    # def test_early_morning_today(self):
    #     """Test a route in the early morning hours using transit scheduled for today."""
    #     time_of_day = datetime.datetime(1900, 1, 6, 0, 59, 0)
    #     traversed_edges = os.path.join(self.toy_gdb, "EarlyMorningToday")
    #     # Expect to use RunID 12.
    #     expected_rows = [
    #         (1, 'Streets', 0.03318819500087722, 0.03318819500087722, None, None, None, None, None),
    #         (2, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (3, 'LineVariantElements', 2.9668117908295244, 0.0, 2.0, 0.97,
    #          12, datetime.datetime(1900, 1, 6, 1, 0), datetime.datetime(1900, 1, 6, 1, 2)),
    #         (4, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (5, 'Streets', 0.038736364262887554, 0.038736364262887554, None, None, None, None, None)
    #     ]
    #     self.calculate_traversal_and_check_results(
    #         expected_rows,
    #         traversed_edges,
    #         self.toy_fd,
    #         self.toy_tm_transit,
    #         time_of_day,
    #     )

    # def test_early_morning_yesterday(self):
    #     """Test a route in the early morning hours using transit still running from yesterday."""
    #     time_of_day = datetime.datetime(1900, 1, 6, 0, 29, 0)
    #     traversed_edges = os.path.join(self.toy_gdb, "EarlyMorningYesterday")
    #     # Expect to use RunID 15.
    #     expected_rows = [
    #         (1, 'Streets', 0.03318819500087722, 0.03318819500087722, None, None, None, None, None),
    #         (2, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (3, 'LineVariantElements', 2.9668118013069034, 0.0, 2.0, 0.97,
    #          15, datetime.datetime(1900, 1, 6, 0, 30), datetime.datetime(1900, 1, 6, 0, 32)),
    #         (4, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (5, 'Streets', 0.038736364262887554, 0.038736364262887554, None, None, None, None, None)
    #     ]
    #     self.calculate_traversal_and_check_results(
    #         expected_rows,
    #         traversed_edges,
    #         self.toy_fd,
    #         self.toy_tm_transit,
    #         time_of_day,
    #     )

    # def test_late_night_tomorrow(self):
    #     """Test a route in the late night that uses transit from tomorrow's schedule."""
    #     time_of_day = datetime.datetime(1900, 1, 5, 23, 59, 0)
    #     traversed_edges = os.path.join(self.toy_gdb, "LateNightTomorrow")
    #     # Expect to use RunID 16.
    #     expected_rows = [
    #         (1, 'Streets', 0.03318819500087722, 0.03318819500087722, None, None, None, None, None),
    #         (2, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (3, 'LineVariantElements', 2.9668118013069034, 0.0, 2.0, 0.97,
    #          16, datetime.datetime(1900, 1, 6, 0, 0), datetime.datetime(1900, 1, 6, 0, 2)),
    #         (4, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (5, 'Streets', 0.038736364262887554, 0.038736364262887554, None, None, None, None, None)
    #     ]
    #     self.calculate_traversal_and_check_results(
    #         expected_rows,
    #         traversed_edges,
    #         self.toy_fd,
    #         self.toy_tm_transit,
    #         time_of_day,
    #     )

    # def test_exact_date_service_added(self):
    #     """Test a route using added service in CalendarExceptions on an exact date."""
    #     time_of_day = datetime.datetime(2019, 7, 4, 6, 59, 0)
    #     traversed_edges = os.path.join(self.toy_gdb, "ExactDateServiceAdded")
    #     # Expect to use RunID 21.
    #     expected_rows = [
    #         (1, 'Streets', 0.03318819500087722, 0.03318819500087722, None, None, None, None, None),
    #         (2, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (3, 'LineVariantElements', 2.9668117908295244, 0.0, 2.0, 0.97,
    #          21, datetime.datetime(2019, 7, 4, 7, 0), datetime.datetime(2019, 7, 4, 7, 2)),
    #         (4, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (5, 'Streets', 0.038736364262887554, 0.038736364262887554, None, None, None, None, None)
    #     ]
    #     self.calculate_traversal_and_check_results(
    #         expected_rows,
    #         traversed_edges,
    #         self.toy_fd,
    #         self.toy_tm_transit,
    #         time_of_day,
    #     )

    # def test_bikes(self):
    #     """Test a route when traveling with a bicycle."""
    #     time_of_day = datetime.datetime(1900, 1, 2, 8, 27, 0)
    #     traversed_edges = os.path.join(self.toy_gdb, "TravelingWithBike")
    #     # RunID 19 is the fastest but doesn't allow bikes. Expect RunID 22 instead.
    #     # RunID 23 also runs at exactly the same time as RunID 22 but also doesn't allow bikes, so this test ensures
    #     # that the correct run has been chosen as the one actually used.
    #     expected_rows = [
    #         (1, 'Streets', 2.179174228126206, 2.179174228126206, None, None, None, None, None),
    #         (2, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (3, 'LineVariantElements', 5.820825775153935, 0.0, 3.0, 2.82,
    #          22, datetime.datetime(1900, 1, 2, 8, 32), datetime.datetime(1900, 1, 2, 8, 35)),
    #         (4, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (5, 'Streets', 1.3810111935733977, 1.3810111935733977, None, None, None, None, None)
    #     ]
    #     self.calculate_traversal_and_check_results(
    #         expected_rows,
    #         traversed_edges,
    #         self.toy_fd,
    #         self.toy_tm_with_bike,
    #         time_of_day,
    #     )

    # def test_wheelchair(self):
    #     """Test a route when traveling with a wheelchair."""
    #     time_of_day = datetime.datetime(1900, 1, 2, 8, 27, 0)
    #     traversed_edges = os.path.join(self.toy_gdb, "TravelingWithWhlchr")
    #     # RunID 19 is the fastest but doesn't allow wheelchairs. Expect RunID 23 instead.
    #     # RunID 22 also runs at exactly the same time as RunID 23 but also doesn't allow wheelchairs, so this test
    #     # ensures that the correct run has been chosen as the one actually used.
    #     expected_rows = [
    #         (1, 'Streets', 2.179174228126206, 2.179174228126206, None, None, None, None, None),
    #         (2, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (3, 'LineVariantElements', 5.820825775153935, 0.0, 3.0, 2.82,
    #          23, datetime.datetime(1900, 1, 2, 8, 32), datetime.datetime(1900, 1, 2, 8, 35)),
    #         (4, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (5, 'Streets', 1.3810111935733977, 1.3810111935733977, None, None, None, None, None)
    #     ]
    #     self.calculate_traversal_and_check_results(
    #         expected_rows,
    #         traversed_edges,
    #         self.toy_fd,
    #         self.toy_tm_with_wheelchair,
    #         time_of_day,
    #     )

    # def test_exclude_runs(self):
    #     """Test a route an excluded run in the travel mode."""
    #     time_of_day = datetime.datetime(1900, 1, 2, 8, 29, 0)
    #     traversed_edges = os.path.join(self.toy_gdb, "ExcludeRuns")
    #     tm = arcpy.nax.TravelMode(self.toy_tm_transit)
    #     attr_params = tm.attributeParameters
    #     attr_params[('Transit_TravelTime', 'Exclude runs')] = "22"  # Exclude run 22
    #     tm.attributeParameters = attr_params
    #     # RunIDs 22 and 23 run at exactly the same time, but one is excluded. This test ensures that the correct run has
    #     # been chosen as the one actually used.
    #     expected_rows = [
    #         (1, 'Streets', 2.179174228126206, 2.179174228126206, None, None, None, None, None),
    #         (2, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (3, 'LineVariantElements', 3.820825768634677, 0.0, 3.0, 0.82,
    #          23, datetime.datetime(1900, 1, 2, 8, 32), datetime.datetime(1900, 1, 2, 8, 35)),
    #         (4, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (5, 'Streets', 1.3810111935733977, 1.3810111935733977, None, None, None, None, None)
    #     ]
    #     self.calculate_traversal_and_check_results(
    #         expected_rows,
    #         traversed_edges,
    #         self.toy_fd,
    #         tm,
    #         time_of_day,
    #     )

    # def test_exclude_modes(self):
    #     """Test a route an excluded mode in the travel mode.

    #     This situation is virtually impossible to verify even with toy data. This test just exercises the code paths to
    #     make sure nothing terrible happens.
    #     """
    #     time_of_day = datetime.datetime(1900, 1, 6, 0, 59, 0)
    #     traversed_edges = os.path.join(self.toy_gdb, "ExcludeModes")
    #     tm = arcpy.nax.TravelMode(self.toy_tm_transit)
    #     attr_params = tm.attributeParameters
    #     attr_params[('Transit_TravelTime', 'Exclude modes')] = "0"  # Exclude mode 0
    #     tm.attributeParameters = attr_params
    #     # Expect to use RunID 12.
    #     expected_rows = [
    #         (1, 'Streets', 0.03318819500087722, 0.03318819500087722, None, None, None, None, None),
    #         (2, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (3, 'LineVariantElements', 2.9668117908295244, 0.0, 2.0, 0.97,
    #          12, datetime.datetime(1900, 1, 6, 1, 0), datetime.datetime(1900, 1, 6, 1, 2)),
    #         (4, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (5, 'Streets', 0.038736364262887554, 0.038736364262887554, None, None, None, None, None)
    #     ]
    #     self.calculate_traversal_and_check_results(
    #         expected_rows,
    #         traversed_edges,
    #         self.toy_fd,
    #         tm,
    #         time_of_day,
    #     )

    # def test_exclude_line(self):
    #     """Test a route an excluded line in the travel mode.

    #     This situation is virtually impossible to verify even with toy data. This test just exercises the code paths to
    #     make sure nothing terrible happens.
    #     """
    #     time_of_day = datetime.datetime(1900, 1, 6, 0, 59, 0)
    #     traversed_edges = os.path.join(self.toy_gdb, "ExcludeLines")
    #     tm = arcpy.nax.TravelMode(self.toy_tm_transit)
    #     attr_params = tm.attributeParameters
    #     attr_params[('Transit_TravelTime', 'Exclude lines')] = "2"  # Exclude line 2
    #     tm.attributeParameters = attr_params
    #     # Expect to use RunID 12.
    #     expected_rows = [
    #         (1, 'Streets', 0.03318819500087722, 0.03318819500087722, None, None, None, None, None),
    #         (2, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (3, 'LineVariantElements', 2.9668117908295244, 0.0, 2.0, 0.97,
    #          12, datetime.datetime(1900, 1, 6, 1, 0), datetime.datetime(1900, 1, 6, 1, 2)),
    #         (4, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (5, 'Streets', 0.038736364262887554, 0.038736364262887554, None, None, None, None, None)
    #     ]
    #     self.calculate_traversal_and_check_results(
    #         expected_rows,
    #         traversed_edges,
    #         self.toy_fd,
    #         tm,
    #         time_of_day,
    #     )

    # def test_cf_end_time(self):
    #     """Test when the route is from a Closest Facility analysis using end time instead of start time."""
    #     time_of_day = datetime.datetime(1900, 1, 3, 8, 3, 0)
    #     traversed_edges = os.path.join(self.toy_gdb, "CFEndTime")
    #     # Expect to use RunID 1.
    #     expected_rows = [
    #         (1, 'Streets', 0.038736364262887554, 0.038736364262887554, None, None, None, None, None),
    #         (2, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (3, 'LineVariantElements', 2.96126363100484, 0.0, 2.5, 0.46,
    #          1, datetime.datetime(1900, 1, 3, 8, 0), datetime.datetime(1900, 1, 3, 8, 2, 30)),
    #         (4, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (5, 'Streets', 0.03318819500087722, 0.03318819500087722, None, None, None, None, None)
    #     ]
    #     self.calculate_traversal_and_check_results(
    #         expected_rows,
    #         traversed_edges,
    #         self.toy_fd,
    #         self.toy_tm_transit,
    #         time_of_day,
    #         analysis_time_type=TransitTraversal.AnalysisTimeType.CFLayerEndTime,
    #         use_impedance_in_field_names=True
    #     )

    # def test_sa_end_time(self):
    #     """Test when the route is from a Service Area analysis using end time instead of start time."""
    #     time_of_day = datetime.datetime(1900, 1, 3, 8, 3, 0)
    #     traversed_edges = os.path.join(self.toy_gdb, "SAEndTime")
    #     # Expect to use RunID 1.
    #     expected_rows = [
    #         (1, 'Streets', 0.038736364262887554, 0.038736364262887554, None, None, None, None, None),
    #         (2, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (3, 'LineVariantElements', 2.96126363100484, 0.0, 2.5, 0.46,
    #          1, datetime.datetime(1900, 1, 3, 8, 0), datetime.datetime(1900, 1, 3, 8, 2, 30)),
    #         (4, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (5, 'Streets', 2.000000004732272, 2.000000004732272, None, None, None, None, None),
    #         (6, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
    #         (7, 'Streets', 2.000000004732272, 2.000000004732272, None, None, None, None, None),
    #         (8, 'Streets', 4.961263635737112, 4.961263635737112, None, None, None, None, None),
    #         (9, 'Streets', 5.0, 5.0, None, None, None, None, None)
    #     ]
    #     self.calculate_traversal_and_check_results(
    #         expected_rows,
    #         traversed_edges,
    #         self.toy_fd,
    #         self.toy_tm_transit,
    #         time_of_day,
    #         analysis_time_type=TransitTraversal.AnalysisTimeType.SALayerEndTime,
    #         route_id_field="FacilityID",
    #         use_impedance_in_field_names=True
    #     )

    # def test_no_transit(self):
    #     """Test a route where no transit lines are used."""
    #     time_of_day = datetime.datetime(1900, 1, 6, 4, 0, 0)
    #     traversed_edges = os.path.join(self.toy_gdb, "NoTransit")
    #     expected_rows = [
    #         (1, 'Streets', 0.03318819500087722, 0.03318819500087722, None, None, None, None, None),
    #         (2, 'Streets', 10.0, 10.0, None, None, None, None, None),
    #         (3, 'Streets', 10.0, 10.0, None, None, None, None, None),
    #         (4, 'Streets', 0.0431375329990017, 0.0431375329990017, None, None, None, None, None)
    #     ]
    #     self.calculate_traversal_and_check_results(
    #         expected_rows,
    #         traversed_edges,
    #         self.toy_fd,
    #         self.toy_tm_transit,
    #         time_of_day,
    #         use_impedance_in_field_names=True
    #     )

    def test_mismatching_time(self):
        """Test behavior when no matching transit route can be found."""
        time_of_day = datetime.datetime(1900, 1, 6, 0, 40, 0)  # Not the time of day this route was actually solved
        traversed_edges = os.path.join(self.toy_gdb, "MismatchingTime")
        expected_rows = [
            (1, 'Streets', 0.03318819500087722, 0.03318819500087722, None, None, None, None, None),
            (2, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
            (3, 'LineVariantElements', 2.9668117908295244, 0.0, None, None, None, None, None),
            (4, 'StopConnectors', 0.0, 0.0, None, None, None, None, None),
            (5, 'Streets', 0.038736364262887554, 0.038736364262887554, None, None, None, None, None)
        ]
        self.calculate_traversal_and_check_results(
            expected_rows,
            traversed_edges,
            self.toy_fd,
            self.toy_tm_transit,
            time_of_day,
        )


if __name__ == '__main__':
    unittest.main()
