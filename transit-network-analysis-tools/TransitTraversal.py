############################################################################
## Tool name: Transit Network Analysis Tools
## Created by: Melinda Morang, Esri
## Last updated: 31 May 2023
############################################################################
"""
This is a shared module with classes for adding transit information, such
as wait time, ride time, and run information, to a feature class of traversed
edges, or traversal result.  The TransitTraversalResultCalculator class can
be used with a traversal result generated from a network analysis layer or
a Route solver object.

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
import os
import datetime
import enum
import pandas as pd
import arcpy
from AnalysisHelpers import TransitNetworkAnalysisToolsError


WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class DayType(enum.Enum):
    """Defines a day type representing today, yesterday, or tomorrow."""

    Today = 1
    Yesterday = 2
    Tomorrow = 3


class AnalysisTimeType(enum.Enum):
    """Defines how to interpret the analysis datetime.

    The way to calculate the time of day associated with each row in the traversal result varies depending on travel
    direction and solver.
    """

    # The analysis datetime represents a departure time.  The behavior is the same for all solvers.
    StartTime = 1

    # The analysis datetime represents an end time, or arrival time.  This option is specific to Closest Facility
    # layers with a time of day usage of End Time.
    CFLayerEndTime = 2

    # The analysis datetime is interpreted as an end time, or arrival time, because the direction of travel for the
    # Service Area layer is toward the facility.
    SALayerEndTime = 3


class TransitDataModel:  # pylint: disable=too-many-instance-attributes
    """Defines and validates the public transit data model as relevant to this tool."""

    def __init__(self, transit_fd: str):
        """Define the public transit data model as relevant to this tool."""
        # For details on the public transit data model, see
        # https://pro.arcgis.com/en/pro-app/latest/help/analysis/networks/transit-data-model.htm
        gdb = os.path.dirname(transit_fd)
        self.line_variant_elements = os.path.join(transit_fd, "LineVariantElements")
        self.line_variants = os.path.join(gdb, "LineVariants")
        self.lines = os.path.join(gdb, "Lines")
        self.calendars = os.path.join(gdb, "Calendars")
        self.calendar_exceptions = os.path.join(gdb, "CalendarExceptions")
        self.runs = os.path.join(gdb, "Runs")
        self.schedules = os.path.join(gdb, "Schedules")
        self.schedule_elements = os.path.join(gdb, "ScheduleElements")
        self.required_tables = [self.line_variant_elements, self.line_variants, self.lines, self.runs, self.schedules,
                                self.schedule_elements]
        self.has_calendars = arcpy.Exists(self.calendars)
        self.has_calendar_exceptions = arcpy.Exists(self.calendar_exceptions)
        self.required_fields = {
            self.line_variant_elements: ["LineVarID", "SqIdx"],
            self.line_variants: ["ID", "LineID"],
            self.lines: ["ID"],
            self.calendars: ["ID", "StartDate", "EndDate"] + list(WEEKDAYS),
            self.calendar_exceptions: ["CalendarID", "ExceptionDate", "GExceptionType"],
            self.runs: ["ID", "ScheduleID", "StartRun"],
            self.schedules: ["LineVarID", "ID"],
            self.schedule_elements: ["ScheduleID", "SqIdx", "Arrival", "Departure"]
        }

    def validate_tables_exist(self):
        """Validate that the required public transit data model feature classes and tables exist.

        Raises:
            TransitNetworkAnalysisToolsError: If not all required fields are present.
        """
        # Check for required feature classes and tables
        tables_exist = True
        for table in self.required_tables:
            if not arcpy.Exists(table):
                tables_exist = False
        # Check that at least one of the calendar tables is present
        if not (self.has_calendars or self.has_calendar_exceptions):
            tables_exist = False
        if not tables_exist:
            # One or more public transit data model tables does not exist.
            raise TransitNetworkAnalysisToolsError(arcpy.GetIDMessage(2922))

    def validate_required_fields(self):
        """Validate that the transit data model feature classes and tables have the required fields for this tool.

        Raises:
            TransitNetworkAnalysisToolsError: If not all required fields are present.
        """
        for table in self.required_fields:
            if table == self.calendars and not self.has_calendars:
                continue
            if table == self.calendar_exceptions and not self.has_calendar_exceptions:
                continue
            # Compare in lower case because SDE switches the case around. Oracle is all upper. Postgres is all lower.
            required_fields_lower = [f.lower() for f in self.required_fields[table]]
            actual_fields = [f.name.lower() for f in arcpy.ListFields(table)]
            if not set(required_fields_lower).issubset(set(actual_fields)):
                # Public transit data model table %1 is missing one or more required fields. Required fields: %2
                msg = arcpy.GetIDMessage(2925) % (table, ", ".join(self.required_fields[table]))
                raise TransitNetworkAnalysisToolsError(msg)


class TransitTraversalResultCalculator:
    """Enrich an ordinary traversal result with public transit info."""

    def __init__(
        self, traversed_edges_fc, analysis_datetime, analysis_time_type, transit_fd, travel_mode,
        route_id_field="RouteID", use_impedance_in_field_names=True
    ):
        """Initialize the calculator for the given analysis.

        Args:
            traversed_edges_fc (str or layer): Feature class layer or catalog path containing the Edges portion of a
                traversal result. Typically obtained from the Copy Traversed Source Features tool or the RouteEdges
                output from a solver result object.
            analysis_datetime (datetime): The date and time of the network analysis, typically obtained from the layer
                or solver object analysis properties.
            analysis_time_type (AnalysisTimeType): Defines how to interpret the analysis_datetime.
            transit_fd (str): Catalog path to the feature dataset containing the transit-enabled network dataset used
                for the analysis and its associated Public Transit Data Model feature classes.
            travel_mode (arcpy.nax.TravelMode): Travel mode used for the analysis. Should be passed as a travel mode
                object and not a string name.
            route_id_field (str): Field name separating routes in the traversed edges feature class.  RouteID for Route
                and Closest Facility analysis; FacilityID for Service Area.
            use_impedance_in_field_names (bool): Whether to use field names of the form Attr_[impedance] and
                Cumul_[impedance] (as for NA layers) (True) or use the standard Attr_Minutes and Cumul_Minutes
                (as for solver objects) (False)
        """
        self.traversed_edges_fc = traversed_edges_fc
        self.analysis_datetime = analysis_datetime
        self.analysis_time_type = analysis_time_type
        self.travel_mode = travel_mode
        self.route_id_field = route_id_field

        # Validate basic inputs
        if not isinstance(self.analysis_time_type, AnalysisTimeType):
            raise TransitNetworkAnalysisToolsError(
                "The analysis time type must be a member of the AnalysisTimeType enum.")
        if not isinstance(self.analysis_datetime, datetime.datetime):
            raise TransitNetworkAnalysisToolsError(
                f"Analysis datetime must be a datetime.datetime object. Actual type: {type(self.analysis_datetime)}")
        if not isinstance(transit_fd, str):
            raise TransitNetworkAnalysisToolsError("Invalid Public Transit Data Model feature dataset.")
        self._validate_travel_mode()

        # Initialize the Public Transit Data Model tables
        self.transit_dm = TransitDataModel(transit_fd)
        # Validate Public Transit Data Model
        self.transit_dm.validate_tables_exist()
        self.transit_dm.validate_required_fields()

        # Parse the analysis travel mode to retrieve parameter values relevant to filtering lines, modes, and runs
        # and to determine the impedance attribute (needed for field names)
        self.impedance, self.exclude_lines, self.exclude_modes, self.exclude_runs, self.use_bicycle, \
            self.use_wheelchair = self._parse_travel_mode_attr_params()
        self.cumul_field = f"Cumul_{self.impedance}" if use_impedance_in_field_names else "Cumul_Minutes"
        self.attr_field = f"Attr_{self.impedance}" if use_impedance_in_field_names else "Attr_Minutes"

        # Validate traversal result
        if not arcpy.Exists(self.traversed_edges_fc):
            raise TransitNetworkAnalysisToolsError(
                f"The input traversed edges feature class {self.traversed_edges_fc} does not exist.")
        desc = arcpy.Describe(self.traversed_edges_fc)
        required_fields = ["SourceName", "SourceOID", self.attr_field, self.cumul_field, self.route_id_field]
        if not set(required_fields).issubset(set([f.name for f in desc.fields])):
            raise TransitNetworkAnalysisToolsError((
                f"The input traversed edges feature class {self.traversed_edges_fc} is missing one or more required "
                f"fields. Required fields: {required_fields}"
            ))
        self.te_oid_field_name = desc.oidFieldName

        # Determine if the analysis date is a specific date or a generic weekday, and construct a date-only version
        # for later use
        self.date_is_specific = self._is_date_specific()
        self.analysis_date_only = datetime.datetime(  # Midnight on the morning of the analysis datetime
            self.analysis_datetime.year, self.analysis_datetime.month, self.analysis_datetime.day)

        # Shared dataframes (initialized later)
        self.df_traversal = None
        self.df_lve = None

        # Initialize instance variables
        self.traversal_departure_time_field = "RunDepTime"
        self.traversal_arrival_time_field = "RunArrTime"
        self.segment_start_time_field = "SegmentStartTime"
        self.segment_end_time_field = "SegmentEndTime"
        self.output_field_defs = [
            ["WalkTime", "DOUBLE"],
            ["RideTime", "DOUBLE"],
            ["WaitTime", "DOUBLE"],
            ["RunID", "LONG"],
            [self.traversal_departure_time_field, "DATE"],
            [self.traversal_arrival_time_field, "DATE"]
        ]

    def add_transit_to_traversal_result(self) -> bool:
        """Populate transit run information in the traversed edges feature class.

        Add a set of additional output fields to the traversed edges feature class.  Read the Public Transit Data Model
        tables and perform some joins and calculations so we can match up the runs with each row in the traversed
        edges feature class representing travel along a transit line.  Populate the transit-related fields with the
        calculated information.

        Returns:
            bool: True if transit information was successfully added to the traversed edges feature class. False
                otherwise. The code should print a warning in these cases. The fields should be added to the table but
                will not be populated.
        """
        self._add_output_fields()
        self._parse_traversed_edges()
        if self.df_traversal.empty:
            return False
        successfully_cached = self._cache_transit_dm()
        if not successfully_cached:
            return False
        self._add_run_id_to_traversal()
        if self.df_traversal.empty:
            return False
        self._append_transit_info_to_traversal_fc()
        return True

    def _add_output_fields(self):
        """Add the transit info fields in the edge traversal feature class."""
        # Check if output fields already exist and get rid of them if needed
        te_fields = [f.name for f in arcpy.ListFields(self.traversed_edges_fc)]
        existing_fields = [f for f in te_fields if f in [g[0] for g in self.output_field_defs]]
        if existing_fields:
            arcpy.management.DeleteField(self.traversed_edges_fc, existing_fields)

        # Add output fields
        arcpy.management.AddFields(self.traversed_edges_fc, self.output_field_defs)

        # Calculate the WalkTime field, since this doesn't require any transit information. It will equal the
        # Cumul_[impedance] field value for non-transit edges and 0 for transit edges.
        calc_function = (
            "def get_value(source_name, attr_time):\n"
            '    if source_name == "LineVariantElements":\n'
            "        return 0\n"
            "    return attr_time"
        )
        arcpy.management.CalculateField(
            self.traversed_edges_fc,
            "WalkTime",
            f"get_value(!SourceName!, !{self.attr_field}!)",
            "PYTHON3",
            calc_function
        )

    def _parse_traversed_edges(self):
        """Parse the input traversed edges into a dataframe and calculate arrival time."""
        # Read traversed edges
        where = "SourceName = 'LineVariantElements'"
        fields = [self.te_oid_field_name, "SourceOID", self.attr_field, self.cumul_field, self.route_id_field]
        with arcpy.da.SearchCursor(self.traversed_edges_fc, fields, where) as cur:  # pylint: disable=no-member
            self.df_traversal = pd.DataFrame(cur, columns=fields)
        if self.df_traversal.empty:
            arcpy.AddWarning((
                "Warning: The input traversed edges feature class does not contain any rows that used a public transit "
                "line. Transit fields will be added to the output but not populated."))
            return
        # Check for incorrect Attr_ and Cumul_ fields
        null_msg = ((
                "The input traversed edges feature class contains null values in the %s field. Either "
                "the feature class contains invalid rows, or the input travel mode is not the same travel mode that "
                "was used in the analysis that generated this traversed edges feature class."
            ))
        if self.df_traversal[self.attr_field].isnull().values.any():
            raise TransitNetworkAnalysisToolsError(null_msg % self.attr_field)
        if self.df_traversal[self.cumul_field].isnull().values.any():
            raise TransitNetworkAnalysisToolsError(null_msg % self.cumul_field)
        # self.df_traversal status:
        # Columns: ObjectID, SourceOID, Attr_[impedance], Cumul_Impedance, RouteID/FacilityID

        if self.analysis_time_type is AnalysisTimeType.StartTime:
            # Straightforward case. The transit run's arrive time is the analysis datetime plus the accumulated
            # travel time.  Any wait time is incurred at the beginning of the edge, which is why we look at the arrive
            # time of the transit run instead of the depart time.
            self.df_traversal[self.traversal_arrival_time_field] = self.analysis_datetime + \
                pd.to_timedelta(self.df_traversal[self.cumul_field], unit="minute")
            # Remove stray microseconds that the solver sometimes injects by rounding to the nearest second
            self.df_traversal[self.traversal_arrival_time_field] = \
                self.df_traversal[self.traversal_arrival_time_field].dt.round("s")

        elif self.analysis_time_type is AnalysisTimeType.CFLayerEndTime:
            # We have to do some extra work figure out the total length of each route.
            fields = [self.route_id_field, self.cumul_field]
            with arcpy.da.SearchCursor(self.traversed_edges_fc, fields) as cur:  # pylint: disable=no-member
                df_route_lengths = pd.DataFrame(cur, columns=fields)
            route_lengths = df_route_lengths.groupby(self.route_id_field)[self.cumul_field].max()
            route_lengths.rename("RouteMin", inplace=True)
            self.df_traversal = self.df_traversal.join(route_lengths, self.route_id_field)
            del route_lengths
            # For a Closest Facility interpreting the time of day as end time, the "wait time" is incurred at the end of
            # the transit edge and should be interpreted more like the buffer time or how early you arrive.  For this
            # reason, we need to use the depart time of the transit run.
            self.df_traversal[self.traversal_departure_time_field] = self.analysis_datetime - \
                pd.to_timedelta(self.df_traversal["RouteMin"], unit="minute") + \
                pd.to_timedelta(self.df_traversal[self.cumul_field], unit="minute") - \
                pd.to_timedelta(self.df_traversal[self.attr_field], unit="minute")
            # Remove stray microseconds that the solver sometimes injects by rounding to the nearest second
            self.df_traversal[self.traversal_departure_time_field] = \
                self.df_traversal[self.traversal_departure_time_field].dt.round("s")
            self.df_traversal.drop(["RouteMin"], axis="columns", inplace=True)

        elif self.analysis_time_type is AnalysisTimeType.SALayerEndTime:
            # For a Service Area layer with a travel direction of toward the facility, the time of day is interpreted
            # as an end time.  For whatever reason, the traversal result for this situation is reported a little
            # differently from the Closest Facility End Time case (essentially already as total time - value), and the
            # departure time can be calculated using a simple subtraction.
            self.df_traversal[self.traversal_departure_time_field] = self.analysis_datetime - \
                pd.to_timedelta(self.df_traversal[self.cumul_field], unit="minute")
            # Remove stray microseconds that the solver sometimes injects by rounding to the nearest second
            self.df_traversal[self.traversal_departure_time_field] = \
                self.df_traversal[self.traversal_departure_time_field].dt.round("s")

        else:
            # This should never happen.
            raise TransitNetworkAnalysisToolsError(
                "The analysis time type must be a member of the AnalysisTimeType enum.")

        # self.df_traversal status:
        # Columns: ObjectID, SourceOID, Attr_[impedance], Cumul_[impedance], RouteID/FacilityID, RunDepartureTime,
        #          RunArrivalTime
        # print(self.df_traversal)

    def _cache_transit_dm(self):
        """Cache the relevant transit data model tables."""
        # Cache the transit info for the analysis date
        df_lve_today = self._cache_transit_dm_for_day(DayType.Today)

        # Cache the transit info for the day before the analysis date in case runs from yesterday are carrying over
        # into the early hours of the morning
        df_lve_yesterday = self._cache_transit_dm_for_day(DayType.Yesterday)

        # Cache the transit info for the day after the analysis date if any of the traversed edges end up finishing
        # in the early hours of the following day
        df_lve_tomorrow = None
        tomorrow = self.analysis_date_only + datetime.timedelta(days=1)
        tomorrow = tomorrow.date()
        field_to_check = self.traversal_arrival_time_field if self.analysis_time_type is AnalysisTimeType.StartTime \
            else self.traversal_departure_time_field
        arr_dep_times_tomorrow = self.df_traversal[self.df_traversal[field_to_check].dt.date == tomorrow]
        if not arr_dep_times_tomorrow.empty:
            df_lve_tomorrow = self._cache_transit_dm_for_day(DayType.Tomorrow)

        empty_msg = (
                "No public transit service was found matching the analysis parameters. "
                "Fields will be added to the traversed edges feature class, but transit information will not be "
                "populated."
            )

        df_lves = [df for df in [df_lve_today, df_lve_yesterday, df_lve_tomorrow] if df is not None]
        if not df_lves:
            arcpy.AddWarning(empty_msg)
            return False

        # Combine all the cached schedules into one dataframe
        self.df_lve = pd.concat(df_lves)

        if self.df_lve.empty:
            arcpy.AddWarning(empty_msg)
            return False

        return True

    def _cache_transit_dm_for_day(self, day_type: DayType):
        """Cache the relevant transit data model tables for today, yesterday, or tomorrow."""
        # Read ScheduleElements into a dataframe
        columns = ["ScheduleID", "SqIdx", "Arrival", "Departure"]
        with arcpy.da.SearchCursor(self.transit_dm.schedule_elements, columns) as cur_se:  # pylint: disable=no-member
            se_df = pd.DataFrame(cur_se, columns=columns)
        # se_df status:
        # Columns: ScheduleID, SqIdx, Arrival, Departure
        # print(se_df)

        # Read Schedules into a dataframe in order to join the LineVarID into our Schedule Elements dataframe
        with arcpy.da.SearchCursor(  # pylint: disable=no-member
            self.transit_dm.schedules, ["LineVarID", "ID"]
        ) as cur_s:
            s_df = pd.DataFrame(cur_s, columns=["LineVarID", "ScheduleID"])
        s_df.set_index("ScheduleID", inplace=True)
        se_df = se_df.join(s_df, "ScheduleID")
        del s_df
        # se_df status:
        # Columns: ScheduleID, SqIdx, Arrival, Departure, LineVarID
        # print(se_df)

        # If the travel mode excludes modes, read the Lines table to map modes to Line ID values and update
        # self.exclude_lines
        if self.exclude_modes:
            # Read Lines table and eliminate rows with excluded modes
            where = f"GRouteType IN ({', '.join([str(lid) for lid in self.exclude_modes])})"
            for row in arcpy.da.SearchCursor(  # pylint: disable=no-member
                self.transit_dm.lines, ["ID"], where
            ):
                self.exclude_lines.append(row[0])
            self.exclude_lines = list(set(self.exclude_lines))

        # Remove records associated with excluded lines if necessary
        if self.exclude_lines:
            # Read LineVariants table to get a list of invalid LineVarID values
            excluded_line_var_ids = []
            where = f"LineID IN ({', '.join([str(lid) for lid in self.exclude_lines])})"
            for row in arcpy.da.SearchCursor(  # pylint: disable=no-member
                self.transit_dm.line_variants, ["ID"], where
            ):
                excluded_line_var_ids.append(row[0])
            # Eliminate schedule elements with the excluded LineVarID values
            se_df = se_df[~se_df["LineVarID"].isin(excluded_line_var_ids)]
            # print(se_df)

        if day_type is DayType.Today:
            date_to_use = self.analysis_date_only
        elif day_type is DayType.Tomorrow:
            date_to_use = self.analysis_date_only + datetime.timedelta(days=1)
        elif day_type is DayType.Yesterday:
            date_to_use = self.analysis_date_only - datetime.timedelta(days=1)
        else:
            # This should never happen.
            raise TransitNetworkAnalysisToolsError("Invalid DayType.")

        valid_calendar_ids = self._get_valid_calendar_ids(date_to_use)
        if not valid_calendar_ids:
            # No CalendarIDs were found matching the analysis datetime
            return None
        # print(valid_calendar_ids)

        # Read runs into a dataframe.
        # The StartRun field in the Runs table represents the number of minutes since midnight that the run starts.
        # Only read in the run if StartRun is before the end of our time window.
        # Only read in runs that have CalendarID values in our list of valid ones for the time window day/date.
        where = f"CalendarID IN ({', '.join([str(cid) for cid in valid_calendar_ids])})"
        # Exclude runs if requested by the travel mode
        if self.exclude_runs:
            where += f" AND ID NOT IN ({', '.join([str(rid) for rid in self.exclude_runs])})"
        # Exclude wheelchairs and bikes if requested by the travel mode
        if self.use_wheelchair:
            where += " AND (GWheelchairAccessible <> 2 OR GWheelchairAccessible IS NULL)"
        if self.use_bicycle:
            where += " AND (GBikesAllowed <> 2 OR GBikesAllowed IS NULL)"
        columns = ["ID", "ScheduleID", "StartRun"]
        with arcpy.da.SearchCursor(self.transit_dm.runs, columns, where) as cur_r:  # pylint: disable=no-member
            r_df = pd.DataFrame(cur_r, columns=columns)
        r_df.rename(columns={"ID": "RunID"}, inplace=True)
        if r_df.empty:
            # No Runs were found matching the analysis parameters
            return None
        # r_df status:
        # Columns: RunID, ScheduleID, StartRun
        # print(r_df)

        # Join the Runs table into Schedule Elements.
        # Do an inner join so that each ScheduleElement is duplicated for each run, but any ScheduleElement that has
        # no runs is dropped.
        r_df.set_index("ScheduleID", inplace=True)
        se_df = se_df.join(r_df, "ScheduleID", "inner")
        del r_df
        if se_df.empty:
            # No ScheduleElements have runs matching the analysis parameters
            return None
        # se_df status:
        # Columns: ScheduleID, SqIdx, Arrival, Departure, LineVarID, RunID, StartRun
        # Rows have been dropped if they had no runs associated with them.
        # print(se_df)

        # Calculate the actual times of day when transit service arrives at the end of the segment. This is a sum of
        # the time of day when the run starts (StartRun) plus the number of minutes since the beginning of the run that
        # the vehicle arrives at the end of the segment.
        se_df["SegmentEndMin"] = se_df["StartRun"] + se_df["Arrival"]
        # Convert to a time of day
        se_df[self.segment_end_time_field] = date_to_use + \
            pd.to_timedelta(se_df["SegmentEndMin"], unit="minute")
        # Remove stray microseconds that the solver sometimes injects by rounding to the nearest second
        se_df[self.segment_end_time_field] = se_df[self.segment_end_time_field].dt.round("s")

        # Calculate the actual times of day when transit service starts at the beginning of the segment. This is a sum
        # the time of day when the run starts (StartRun) plus the number of minutes since the beginning of the run that
        # the vehicle departs.
        se_df["SegmentStartMin"] = se_df["StartRun"] + se_df["Departure"]
        # Convert to a time of day
        se_df[self.segment_start_time_field] = date_to_use + \
            pd.to_timedelta(se_df["SegmentStartMin"], unit="minute")
        # Remove stray microseconds that the solver sometimes injects by rounding to the nearest second
        se_df[self.segment_start_time_field] = se_df[self.segment_start_time_field].dt.round("s")

        # Clean up fields that are no longer needed.
        se_df.drop(
            ["ScheduleID", "StartRun", "SegmentEndMin", "SegmentStartMin"], axis="columns", inplace=True)
        # se_df status:
        # Columns: SqIdx, Arrival, Departure, LineVarID, RunID, SegmentEndTime, SegmentStartTime
        # print(se_df)

        # Get the list of relevant LineVariantElements from the input traversal result
        line_variant_element_oids = self.df_traversal["SourceOID"].unique().tolist()
        # We should have checked before this point whether we had any LVEs, but check again just in case.
        if not line_variant_element_oids:
            return None
        # print(line_variant_element_oids)

        # Read relevant LineVariantElements into a dataframe
        lve_oid_field_name = arcpy.Describe(self.transit_dm.line_variant_elements).oidFieldName
        where = f"{lve_oid_field_name} IN ({', '.join([str(oid) for oid in line_variant_element_oids])})"
        with arcpy.da.SearchCursor(  # pylint: disable=no-member
            self.transit_dm.line_variant_elements, [lve_oid_field_name, "LineVarID", "SqIdx"], where
        ) as cur:
            df_lve = pd.DataFrame(cur, columns=["LVE_OID", "LineVarID", "SqIdx"])
        # df_lve status:
        # Columns: LVE_OID, LineVarID, SqIdx
        # print(df_lve)

        # Join the schedule elements with arrival time info to the LineVariantElements table
        # Do an inner join so that records in the schedule elements are eliminated if they don't match one of the
        # relevant LineVariantElements from the traversal result.
        se_df.set_index(["LineVarID", "SqIdx"], inplace=True)
        df_lve = df_lve.join(se_df, ["LineVarID", "SqIdx"], "inner")
        del se_df
        # Clean up fields that are no longer needed.
        df_lve.drop(["LineVarID", "SqIdx"], axis="columns", inplace=True)
        # df_lve status:
        # Columns: LVE_OID, Arrival, Departure, RunID, SegmentEndTime, SegmentStartTime
        # print(df_lve)
        if df_lve.empty:
            # Could not match up LineVariantElements with schedules
            return None

        return df_lve

    def _get_valid_calendar_ids(self, date_to_use):
        """Return a list of transit data model Calendar IDs valid for the time window and day.

        Returns:
            List[int]: List of Calendar ID values
        """
        # Get a list of Calendar IDs valid for the time window date or day
        valid_calendar_ids = []
        if self.transit_dm.has_calendars:
            weekday = WEEKDAYS[date_to_use.weekday()]
            where = f"{weekday} = 1"
            for row in arcpy.da.SearchCursor(  # pylint: disable=no-member
                self.transit_dm.calendars, ["ID", "StartDate", "EndDate"], where
            ):
                if self.date_is_specific and (
                    date_to_use < row[1] or date_to_use > row[2]
                ):
                    # The analysis datetime not fall within the row's valid date range
                    continue
                valid_calendar_ids.append(row[0])

        # For specific dates, we need to add and remove service according to CalendarExceptions
        if self.date_is_specific and arcpy.Exists(self.transit_dm.calendar_exceptions):
            remove_service = []
            for row in arcpy.da.SearchCursor(  # pylint: disable=no-member
                self.transit_dm.calendar_exceptions, ["CalendarID", "ExceptionDate", "GExceptionType"]
            ):
                if row[1] != date_to_use:
                    # Date does not apply
                    continue
                if row[2] == 1:
                    # Service is added
                    valid_calendar_ids.append(row[0])
                elif row[2] == 2:
                    # Service is removed
                    remove_service.append(row[0])
            if remove_service:
                valid_calendar_ids = [id for id in valid_calendar_ids if id not in remove_service]

        return valid_calendar_ids

    def _add_run_id_to_traversal(self):
        """For each route segment in the traversal, add the RunID from the matching records."""
        if self.analysis_time_type is AnalysisTimeType.StartTime:
            # First drop duplicates. The Public Transit evaluator has more complex tie-breaking logic that we can't
            # really reproduce here.  Just keep whichever entry is first in the table.  It should be very rare that we
            # get any duplicates, so the chance of incorrect guesses is very low.
            self.df_lve.drop_duplicates(["LVE_OID", self.segment_end_time_field], inplace=True)
            # Match by ObjectID and the transit run's arrival time
            self.df_lve.set_index(["LVE_OID", self.segment_end_time_field], inplace=True)
            self.df_traversal = self.df_traversal.join(
                self.df_lve, ["SourceOID", self.traversal_arrival_time_field], "inner")
            self.df_traversal.rename(
                columns={self.segment_start_time_field: self.traversal_departure_time_field}, inplace=True)
        else:
            # First drop duplicates. The Public Transit evaluator has more complex tie-breaking logic that we can't
            # really reproduce here.  Just keep whichever entry is first in the table.  It should be very rare that we
            # get any duplicates, so the chance of incorrect guesses is very low.
            self.df_lve.drop_duplicates(["LVE_OID", self.segment_start_time_field])
            # Match by ObjectID and the transit run's departure time
            self.df_lve.set_index(["LVE_OID", self.segment_start_time_field], inplace=True)
            self.df_traversal = self.df_traversal.join(
                self.df_lve, ["SourceOID", self.traversal_departure_time_field], "inner")
            self.df_traversal.rename(
                columns={self.segment_end_time_field: self.traversal_arrival_time_field}, inplace=True)
        del self.df_lve
        if self.df_traversal.empty:
            arcpy.AddWarning((
                "Warning: Could not match any runs to the traversed edges. "
                "Transit information cannot be populated."))
            return
        # self.df_traversal status:
        # Columns: ObjectID, SourceOID, Attr_[impedance], Cumul_[impedance], RouteID/FacilityID, RunDepartureTime,
        #          RunArrivalTime, Arrival, Departure, RunID

        # Calculate other useful fields
        self.df_traversal["RideTime"] = self.df_traversal["Arrival"] - self.df_traversal["Departure"]
        self.df_traversal["WaitTime"] = self.df_traversal[self.attr_field] - self.df_traversal["RideTime"]
        self.df_traversal["WaitTime"] = self.df_traversal["WaitTime"].round(2)
        ##TODO: For an analysis datetime that is an end time, the "wait time" is incurred on the end of the transit line
        # and actually represents an early arrival margin.  Rename this field?
        # Clean up fields that are no longer needed.
        self.df_traversal.drop(
            ["SourceOID", "Arrival", "Departure", self.route_id_field, self.attr_field, self.cumul_field],
            axis="columns", inplace=True)
        self.df_traversal.set_index(self.te_oid_field_name, inplace=True)
        # self.df_traversal status:
        # Columns: ObjectID, RunDepartureTime, RunArrivalTime, RunID, RideTime, WaitTime
        # print(self.df_traversal)

    def _append_transit_info_to_traversal_fc(self):
        """Populate transit info fields in the edge traversal feature class."""
        where = "SourceName = 'LineVariantElements'"
        # WalkTime already handled
        fields = [self.te_oid_field_name] + [f[0] for f in self.output_field_defs if f[0] != "WalkTime"]
        with arcpy.da.UpdateCursor(self.traversed_edges_fc, fields, where) as cur:
            for row in cur:
                updated_row = list(row)
                # Set the transit fields by retrieving their values from the traversal dataframe
                oid = row[0]
                try:
                    transit_info = self.df_traversal.loc[oid]
                    for i, field_name in enumerate(fields[1:]):
                        updated_row[i+1] = transit_info[field_name]
                except KeyError:
                    # This means that the transit info wasn't found for this row. No need to fail.
                    arcpy.AddWarning(
                        f"Warning: Could not find public transit traversal information for ObjectID {oid}.")
                cur.updateRow(updated_row)

    def _is_date_specific(self):
        """Determine if the analysis datetime is a specific date or a generic weekday.

        Returns:
            bool: True if the analysis datetime is a specific date.  False if it's a generic weekday.
        """
        if datetime.datetime(1899, 12, 31, 0, 0, 0) <= self.analysis_datetime < datetime.datetime(1900, 1, 7, 0, 0, 0):
            # Special reserved dates for generic weekdays
            return False
        if datetime.datetime(1990, 1, 7, 0, 0, 0) <= self.analysis_datetime < datetime.datetime(1990, 1, 14, 0, 0, 0):
            # Special reserved dates used exclusively for transit solves (sometimes shown in the output results)
            return False
        return True

    @staticmethod
    def _parse_exclude_attr_param_string(exclude_str):
        """Parse the string value from 'Exclude lines', 'Exclude modes', and 'Exclude runs' attribute parameters."""
        if not exclude_str:
            return []
        exclude_str = exclude_str.strip()
        if not exclude_str:
            return []
        exclude_list = []
        for val in exclude_str.split(" "):
            try:
                exclude_list.append(int(val))
            except ValueError:
                # Invalid parameter value. Just skip it.
                continue
        return list(set(exclude_list))

    def _parse_travel_mode_attr_params(self):
        """Read the travel mode's impedance attribute and relevant attribute parameters."""
        impedance = self.travel_mode.impedance
        attr_params = self.travel_mode.attributeParameters
        exclude_lines = self._parse_exclude_attr_param_string(
            attr_params.get((impedance, "Exclude lines"), ""))
        exclude_modes = self._parse_exclude_attr_param_string(
            attr_params.get((impedance, "Exclude modes"), ""))
        if exclude_modes and "groutetype" not in [f.name.lower() for f in arcpy.ListFields(self.transit_dm.lines)]:
            # No point in trying to exclude modes if modes aren't defined
            exclude_modes = []
        exclude_runs = self._parse_exclude_attr_param_string(
            attr_params.get((impedance, "Exclude runs"), ""))
        use_bicycle = attr_params.get((impedance, "Traveling with a bicycle"), False)
        use_wheelchair = attr_params.get((impedance, "Traveling with a wheelchair"), False)
        if use_bicycle or use_wheelchair:
            # Don't bother checking for wheelchair or bike restrictions if the Runs table doesn't have the fields
            # Compare in lower case because SDE switches the case around. Oracle is all upper. Postgres is all lower.
            runs_fields = [f.name.lower() for f in arcpy.ListFields(self.transit_dm.runs)]
            if "gwheelchairaccessible" not in runs_fields:
                use_wheelchair = False
            if "gbikesallowed" not in runs_fields:
                use_bicycle = False

        return impedance, exclude_lines, exclude_modes, exclude_runs, use_bicycle, use_wheelchair

    def _validate_travel_mode(self):
        """Validate the input travel mode.

        Raises:
            TransitNetworkAnalysisToolsError: The travel mode is not an arcpy.nax.TravelMode object
            TransitNetworkAnalysisToolsError: The travel mode does not have a time-based impedance
        """
        if str(type(self.travel_mode)) != "<class 'Network Travel Mode object'>":
            raise TransitNetworkAnalysisToolsError(
                f"Travel mode must be an arcpy.nax.TravelMode object. Actual type: {type(self.travel_mode)}")

        if self.travel_mode.impedance != self.travel_mode.timeAttributeName:
            raise TransitNetworkAnalysisToolsError((
                "The Travel Mode does not use a time-based impedance attribute, so public transit lines were not used "
                "in the analysis."))


if __name__ == "__main__":
    pass
