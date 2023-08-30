"""Unit tests for the AnalysisAnalysisHelpers.py module.

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
import sys
import os
import datetime
import logging
import unittest
import arcpy
import portal_credentials  # Contains log-in for an ArcGIS Online account to use as a test portal
import input_data_helper

CWD = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(CWD))
import AnalysisHelpers  # noqa: E402, pylint: disable=wrong-import-position


class TestHelpers(unittest.TestCase):
    """Test cases for the helpers module."""

    @classmethod
    def setUpClass(self):  # pylint: disable=bad-classmethod-argument
        """Set up shared test properties."""
        self.maxDiff = None

        self.input_data_folder = os.path.join(CWD, "TestInput")
        input_data_helper.make_feature_classes_from_json(self.input_data_folder)
        self.in_gdb = os.path.join(self.input_data_folder, "CincinnatiTransitNetwork.gdb")
        self.local_nd = os.path.join(self.in_gdb, "TransitNetwork", "TransitNetwork_ND")
        self.local_tm_time = "Public transit time"
        self.portal_nd = portal_credentials.PORTAL_URL

        arcpy.SignInToPortal(self.portal_nd, portal_credentials.PORTAL_USERNAME, portal_credentials.PORTAL_PASSWORD)

        self.scratch_folder = os.path.join(
            CWD, "TestOutput", "Output_Helpers_" + datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S"))
        os.makedirs(self.scratch_folder)
        self.output_gdb = os.path.join(self.scratch_folder, "outputs.gdb")
        arcpy.management.CreateFileGDB(os.path.dirname(self.output_gdb), os.path.basename(self.output_gdb))

    def test_validate_input_feature_class(self):
        """Test the validate_input_feature_class function."""
        # Test when the input feature class does note exist.
        input_fc = os.path.join(self.in_gdb, "DoesNotExist")
        with self.subTest(feature_class=input_fc):
            with self.assertRaises(ValueError) as ex:
                AnalysisHelpers.validate_input_feature_class(input_fc)
            self.assertEqual(f"Input dataset {input_fc} does not exist.", str(ex.exception))

        # Test when the input feature class is empty
        input_fc = os.path.join(self.output_gdb, "EmptyFC")
        with self.subTest(feature_class=input_fc):
            arcpy.management.CreateFeatureclass(self.output_gdb, os.path.basename(input_fc))
            with self.assertRaises(ValueError) as ex:
                AnalysisHelpers.validate_input_feature_class(input_fc)
            self.assertEqual(f"Input dataset {input_fc} has no rows.", str(ex.exception))

    def test_is_nds_service(self):
        """Test the is_nds_service function."""
        self.assertTrue(AnalysisHelpers.is_nds_service(self.portal_nd))
        self.assertFalse(AnalysisHelpers.is_nds_service(self.local_nd))

    def test_get_tool_limits_and_is_agol(self):
        """Test the _get_tool_limits_and_is_agol function for a portal network data source."""
        services = [
            ("asyncODCostMatrix", "GenerateOriginDestinationCostMatrix"),
            ("asyncServiceArea", "GenerateServiceAreas")
        ]
        for service in services:
            with self.subTest(service=service):
                service_limits, is_agol = AnalysisHelpers.get_tool_limits_and_is_agol(
                    self.portal_nd, service[0], service[1])
                self.assertIsInstance(service_limits, dict)
                self.assertIsInstance(is_agol, bool)
                if service[0] == "asyncODCostMatrix":
                    self.assertIn("maximumDestinations", service_limits)
                    self.assertIn("maximumOrigins", service_limits)
                if "arcgis.com" in self.portal_nd:
                    # Note: If testing with some other portal, this test would need to be updated.
                    self.assertTrue(is_agol)

    def test_does_travel_mode_use_transit_evaluator(self):
        """Test the does_travel_mode_use_transit_evaluator function."""
        tm = arcpy.nax.GetTravelModes(self.local_nd)[self.local_tm_time]
        self.assertTrue(AnalysisHelpers.does_travel_mode_use_transit_evaluator(self.local_nd, tm))
        tm2 = arcpy.nax.TravelMode(tm)
        tm2.impedance = "WalkTime"
        self.assertFalse(AnalysisHelpers.does_travel_mode_use_transit_evaluator(self.local_nd, tm2))

    def test_convert_time_units_str_to_enum(self):
        """Test the convert_time_units_str_to_enum function."""
        # Test all valid units
        valid_units = AnalysisHelpers.TIME_UNITS
        for unit in valid_units:
            enum_unit = AnalysisHelpers.convert_time_units_str_to_enum(unit)
            self.assertIsInstance(enum_unit, arcpy.nax.TimeUnits)
            self.assertEqual(unit.lower(), enum_unit.name.lower())
        # Test for correct error with invalid units
        bad_unit = "BadUnit"
        with self.assertRaises(ValueError) as ex:
            AnalysisHelpers.convert_time_units_str_to_enum(bad_unit)
        self.assertEqual(f"Invalid time units: {bad_unit}", str(ex.exception))

    def test_convert_travel_direction_str_to_enum(self):
        """Test the convert_travel_direction_str_to_enum function."""
        # Test all valid travel directions
        for direction in ["Away From Facilities", "Toward Facilities"]:
            enum_dir = AnalysisHelpers.convert_travel_direction_str_to_enum(direction)
            self.assertIsInstance(enum_dir, arcpy.nax.TravelDirection)
            if direction == "Away From Facilities":
                self.assertEqual(enum_dir, arcpy.nax.TravelDirection.FromFacility)
            else:
                self.assertEqual(enum_dir, arcpy.nax.TravelDirection.ToFacility)
        # Test for correct error with invalid travel direction
        bad_direction = "BadDirection"
        with self.assertRaises(ValueError) as ex:
            AnalysisHelpers.convert_travel_direction_str_to_enum(bad_direction)
        self.assertEqual(f"Invalid travel direction: {bad_direction}", str(ex.exception))

    def test_convert_geometry_at_cutoff_str_to_enum(self):
        """Test the convert_geometry_at_cutoff_str_to_enum function."""
        # Test all valid cutoff types
        for cutoff_type in ["Rings", "Disks"]:
            enum_ct = AnalysisHelpers.convert_geometry_at_cutoff_str_to_enum(cutoff_type)
            self.assertIsInstance(enum_ct, arcpy.nax.ServiceAreaPolygonCutoffGeometry)
            self.assertEqual(cutoff_type.lower(), enum_ct.name.lower())
        # Test for correct error with invalid units
        bad_ct = "BadCutoff"
        with self.assertRaises(ValueError) as ex:
            AnalysisHelpers.convert_geometry_at_cutoff_str_to_enum(bad_ct)
        self.assertEqual(f"Invalid geometry at cutoff: {bad_ct}", str(ex.exception))

    def test_convert_geometry_at_overlap_str_to_enum(self):
        """Test the convert_geometry_at_overlap_str_to_enum function."""
        # Test all valid overlap types
        for overlap_type in ["Overlap", "Dissolve", "Split"]:
            enum_ct = AnalysisHelpers.convert_geometry_at_overlap_str_to_enum(overlap_type)
            self.assertIsInstance(enum_ct, arcpy.nax.ServiceAreaOverlapGeometry)
            self.assertEqual(overlap_type.lower(), enum_ct.name.lower())
        # Test for correct error with invalid units
        bad_overlap = "BadOverlap"
        with self.assertRaises(ValueError) as ex:
            AnalysisHelpers.convert_geometry_at_overlap_str_to_enum(bad_overlap)
        self.assertEqual(f"Invalid geometry at overlap: {bad_overlap}", str(ex.exception))

    def test_parse_std_and_write_to_gp_ui(self):
        """Test the parse_std_and_write_to_gp_ui function."""
        # There is nothing much to test here except that nothing terrible happens.
        msgs = [
            f"CRITICAL{AnalysisHelpers.MSG_STR_SPLITTER}Critical message",
            f"ERROR{AnalysisHelpers.MSG_STR_SPLITTER}Error message",
            f"WARNING{AnalysisHelpers.MSG_STR_SPLITTER}Warning message",
            f"INFO{AnalysisHelpers.MSG_STR_SPLITTER}Info message",
            f"DEBUG{AnalysisHelpers.MSG_STR_SPLITTER}Debug message",
            "Poorly-formatted message 1",
            f"Poorly-formatted{AnalysisHelpers.MSG_STR_SPLITTER}message 2"
        ]
        for msg in msgs:
            with self.subTest(msg=msg):
                AnalysisHelpers.parse_std_and_write_to_gp_ui(msg)

    def test_are_input_layers_the_same(self):
        """Test the are_input_layers_the_same function."""
        fc1 = os.path.join(self.in_gdb, "TestOrigins")
        fc2 = os.path.join(self.in_gdb, "TestDestinations")
        lyr1_name = "Layer1"
        lyr2_name = "Layer2"
        lyr1_obj = arcpy.management.MakeFeatureLayer(fc1, lyr1_name)
        lyr1_obj_again = arcpy.management.MakeFeatureLayer(fc1, "Layer1 again")
        lyr2_obj = arcpy.management.MakeFeatureLayer(fc2, lyr2_name)
        lyr1_file = os.path.join(self.scratch_folder, "lyr1.lyrx")
        lyr2_file = os.path.join(self.scratch_folder, "lyr2.lyrx")
        arcpy.management.SaveToLayerFile(lyr1_obj, lyr1_file)
        arcpy.management.SaveToLayerFile(lyr2_obj, lyr2_file)
        fset_1 = arcpy.FeatureSet(fc1)
        fset_2 = arcpy.FeatureSet(fc2)

        # Feature class catalog path inputs
        self.assertFalse(AnalysisHelpers.are_input_layers_the_same(fc1, fc2))
        self.assertTrue(AnalysisHelpers.are_input_layers_the_same(fc1, fc1))
        # Layer inputs
        self.assertFalse(AnalysisHelpers.are_input_layers_the_same(lyr1_name, lyr2_name))
        self.assertTrue(AnalysisHelpers.are_input_layers_the_same(lyr1_name, lyr1_name))
        self.assertFalse(AnalysisHelpers.are_input_layers_the_same(lyr1_obj, lyr2_obj))
        self.assertTrue(AnalysisHelpers.are_input_layers_the_same(lyr1_obj, lyr1_obj))
        self.assertFalse(AnalysisHelpers.are_input_layers_the_same(lyr1_obj, lyr1_obj_again))
        self.assertFalse(AnalysisHelpers.are_input_layers_the_same(lyr1_file, lyr2_file))
        self.assertTrue(AnalysisHelpers.are_input_layers_the_same(lyr1_file, lyr1_file))
        # Feature set inputs
        self.assertFalse(AnalysisHelpers.are_input_layers_the_same(fset_1, fset_2))
        self.assertTrue(AnalysisHelpers.are_input_layers_the_same(fset_1, fset_1))

    def test_make_analysis_time_of_day_list(self):
        """Test the make_analysis_time_of_day_list function."""
        # Test a generic weekday
        tod_list = AnalysisHelpers.make_analysis_time_of_day_list("Monday", "Monday", "08:00", "08:03", 1)
        self.assertEqual(
            [
                datetime.datetime(1900, 1, 1, 8, 0),
                datetime.datetime(1900, 1, 1, 8, 1),
                datetime.datetime(1900, 1, 1, 8, 2),
                datetime.datetime(1900, 1, 1, 8, 3)
            ],
            tod_list
        )
        # Test a specific date
        tod_list = AnalysisHelpers.make_analysis_time_of_day_list("20230829", "20230829", "08:00", "08:04", 2)
        self.assertEqual(
            [
                datetime.datetime(2023, 8, 29, 8, 0),
                datetime.datetime(2023, 8, 29, 8, 2),
                datetime.datetime(2023, 8, 29, 8, 4)
            ],
            tod_list
        )

    def test_convert_inputs_to_datetimes(self):
        """Test the convert_inputs_to_datetimes function."""
        # Test a generic weekday
        start_time, end_time = AnalysisHelpers.convert_inputs_to_datetimes("Monday", "Monday", "08:00", "08:03")
        self.assertEqual(start_time, datetime.datetime(1900, 1, 1, 8, 0))
        self.assertEqual(end_time, datetime.datetime(1900, 1, 1, 8, 3))
        # Test a specific date
        start_time, end_time = AnalysisHelpers.convert_inputs_to_datetimes("20230829", "20230829", "17:00", "17:03")
        self.assertEqual(start_time, datetime.datetime(2023, 8, 29, 17, 0))
        self.assertEqual(end_time, datetime.datetime(2023, 8, 29, 17, 3))
        # Test mismatching generic and specific start and end dates
        with self.assertRaises(ValueError) as ex:
            AnalysisHelpers.convert_inputs_to_datetimes("Monday", "20230829", "17:00", "17:03")
        self.assertEqual(
            ("Your Start Day is a generic weekday, but your End Day is a specific date. Please use either a "
             "specific date or a generic weekday for both Start Date and End Date."),
            str(ex.exception))
        with self.assertRaises(ValueError) as ex:
            AnalysisHelpers.convert_inputs_to_datetimes("20230829", "Monday", "17:00", "17:03")
        self.assertEqual(
            ("Your Start Day is a specific date, but your End Day is a generic weekday. Please use either a "
             "specific date or a generic weekday for both Start Date and End Date."),
            str(ex.exception))
        # Test mismatching generic weekdays
        with self.assertRaises(ValueError) as ex:
            AnalysisHelpers.convert_inputs_to_datetimes("Sunday", "Monday", "17:00", "17:03")
        self.assertEqual("If using a generic weekday, the Start Day and End Day must be the same.", str(ex.exception))
        # Test same start and end times
        with self.assertRaises(ValueError) as ex:
            AnalysisHelpers.convert_inputs_to_datetimes("Monday", "Monday", "17:00", "17:00")
        self.assertEqual("Start and end date and time are the same.", str(ex.exception))
        # Test start time earlier than end time
        with self.assertRaises(ValueError) as ex:
            AnalysisHelpers.convert_inputs_to_datetimes("Monday", "Monday", "17:03", "17:00")
        self.assertEqual("End time is earlier than start time.", str(ex.exception))

    def test_cell_size_to_meters(self):
        """Test the cell_size_to_meters function."""
        self.assertEqual(3.5, AnalysisHelpers.cell_size_to_meters("3.5 Meters"))
        self.assertEqual(3500, AnalysisHelpers.cell_size_to_meters("3,5 Kilometers"))
        self.assertAlmostEqual(0.9144, AnalysisHelpers.cell_size_to_meters("3 Feet"), 1)
        self.assertAlmostEqual(2.7432, AnalysisHelpers.cell_size_to_meters("3 Yards"), 1)
        self.assertAlmostEqual(4828.03, AnalysisHelpers.cell_size_to_meters("3 Miles"), 1)
        bad_units = "3 BadUnits"
        with self.assertRaises(ValueError) as ex:
            AnalysisHelpers.cell_size_to_meters(bad_units)
        self.assertEqual("Invalid cell size units: BadUnits", str(ex.exception))

    def test_get_oid_ranges_for_input(self):
        """Test the get_oid_ranges_for_input function."""
        ranges = AnalysisHelpers.get_oid_ranges_for_input(os.path.join(self.in_gdb, "TestOrigins"), 5)
        self.assertEqual([[1, 5], [6, 10], [11, 13]], ranges)

    def test_run_gp_tool(self):
        """Test the run_gp_tool function."""
        # Set up a logger to use with the function
        logger = logging.getLogger(__name__)  # pylint:disable=invalid-name
        # Test for handled tool execute error (create fgdb in invalid folder)
        with self.assertRaises(arcpy.ExecuteError):
            AnalysisHelpers.run_gp_tool(
                logger,
                arcpy.management.CreateFileGDB,
                [self.scratch_folder + "DoesNotExist"],
                {"out_name": "outputs.gdb"}
            )
        # Test for handled non-arcpy error when calling function
        with self.assertRaises(TypeError):
            AnalysisHelpers.run_gp_tool(logger, "BadTool", [self.scratch_folder])
        # Valid call to tool with simple function
        AnalysisHelpers.run_gp_tool(
            logger, arcpy.management.CreateFileGDB, [self.scratch_folder], {"out_name": "testRunTool.gdb"})

    def test_get_locatable_network_source_names(self):
        """Test the get_locatable_network_source_names function."""
        self.assertEqual(
            ["StopConnectors", "Stops", "StopsOnStreets", "Streets", "TransitNetwork_ND_Junctions"],
            AnalysisHelpers.get_locatable_network_source_names(self.local_nd)
        )

    def test_get_locate_settings_from_config_file(self):
        """Test the get_locate_settings_from_config_file function."""
        # Test searchTolerance and searchQuery without searchSources
        config_props = {
            "searchQuery": [["Streets", "ObjectID <> 1"], ["TransitNetwork_ND_Junctions", ""]],
            "searchTolerance": 1000,
            "searchToleranceUnits": arcpy.nax.DistanceUnits.Feet
        }
        search_tolerance, search_criteria, search_query = AnalysisHelpers.get_locate_settings_from_config_file(
            config_props, self.local_nd)
        self.assertEqual("1000 Feet", search_tolerance, "Incorrect search tolerance.")
        self.assertEqual(
            "", search_criteria,
            "Search criteria should be an empty string when searchSources is not used.")
        self.assertEqual(
            "Streets 'ObjectID <> 1';TransitNetwork_ND_Junctions #",
            search_query,
            "Incorrect search query."
        )

        # Test searchSources
        config_props = {
            "searchSources": [["Streets", "ObjectID <> 1"]],
            "searchTolerance": 1000,
        }
        search_tolerance, search_criteria, search_query = AnalysisHelpers.get_locate_settings_from_config_file(
            config_props, self.local_nd)
        self.assertEqual(
            "", search_tolerance,
            "Search tolerance should be an empty string when both searchTolerance and searchToleranceUnits are not set."
        )
        self.assertEqual(
            "Streets SHAPE;StopConnectors NONE;Stops NONE;StopsOnStreets NONE;TransitNetwork_ND_Junctions NONE",
            search_criteria,
            "Incorrect search criteria.")
        self.assertEqual("Streets 'ObjectID <> 1'", search_query, "Incorrect search query.")


if __name__ == '__main__':
    unittest.main()
