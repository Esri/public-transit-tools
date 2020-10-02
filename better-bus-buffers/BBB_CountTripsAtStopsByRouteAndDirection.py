############################################################################
## Tool name: BetterBusBuffers - Count Trips at Stops by Route and Direction
## Created by: David Wasserman, https://github.com/d-wasserman and Melinda Morang, Esri
## This Tool deve developed as part of Transit R&D Efforts from Fehr & Peers.
## Fehr & Peers contributes this tool to the BBB Toolset to further more
## informed planning. 
## Last updated: 7 August 2020
############################################################################
''' BetterBusBuffers - Count Trips at Stops by Route and Direction

BetterBusBuffers provides a quantitative measure of access to public transit
in your city by counting the transit trip frequency at various locations.

The Count Trips at Stops by Route and Direction outputs a feature class where
every GTFS stop is duplicated for every route-direction combination that uses
that stop during the analysis time windows. Each point will represent a unique
combination of stop id, route id, and direction id, and the frequency statistics
that relate to each of them for the analyzed time window.
'''
################################################################################
'''Copyright 2020 Esri
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at
       http://www.apache.org/licenses/LICENSE-2.0
   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.'''

################################################################################
"""Copyright 2020 Fehr & Peers

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
################################################################################
"""Copyright 2020 David Wasserman

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
################################################################################
import arcpy
import BBB_SharedFunctions
import sqlite3, os, datetime


def GenerateTimePeriodExtent(start_time_stamp_list, end_time_stamp_list):
    """Takes a list of start and end time stamps and returns the minimum valued start time and the maximum valued
    end time to determine the global temporal extent."""
    temporal_extent = None
    start_seconds_list = []
    end_seconds_list = []
    for start_time, end_time in zip(start_time_stamp_list, end_time_stamp_list):
        # Convert to seconds from midnight
        start_sec = BBB_SharedFunctions.parse_time(start_time + ":00")
        # Convert to seconds from midnight
        end_sec = BBB_SharedFunctions.parse_time(end_time + ":00")
        start_seconds_list.append(start_sec)
        end_seconds_list.append(end_sec)
    min_start_time, max_end_time = min(start_seconds_list), max(end_seconds_list)
    return min_start_time, max_end_time


def GenerateTimePeriodList(start_time_stamp_list, end_time_stamp_list, alias_list, start_default="00:00",
                           end_default="23:59"):
    """This function will take alist of string time stamps of start and end times, and return a nested list of the structure.
    [(Time_period_iD,start_seconds,end_seconds,time_window),...]
    :param - start_time_stamp_list - list of start times in HH:MM
    :param - end_time_stamp_list - list of end times in HH:MM
    :param - alias_list- list of names to name time period summaries
    :param - start_default - default start time
    :param - end_default -default end time"""
    time_period_list = []
    cached_hours = (None, None)
    for start_time, end_time, alias in zip(start_time_stamp_list, end_time_stamp_list, alias_list):
        # Declare Defaults
        if start_time == "":
            start_time = start_default
        # Convert to seconds
        start_sec = BBB_SharedFunctions.parse_time(start_time + ":00")
        # Upper end of time window (HH:MM in 24-hour time)
        # Default end time is 11:59pm if they leave it blank.
        if end_time == "":
            end_time = end_default
        # Generate Unique Time Period ID
        start_time_id = str(start_time).split(":")[0]
        end_time_id = str(end_time).split(":")[0]
        if start_time_id == cached_hours[0] and end_time_id == cached_hours[1]:
            start_time_id = str(start_time).replace(":", "")
            end_time_id = str(end_time).replace(":", "")
        finalID = alias
        cached_hours = (start_time_id, end_time_id)
        # Determine Temporal Values
        # Convert to seconds
        end_sec = BBB_SharedFunctions.parse_time(end_time + ":00")
        # Length of time window in hours - used to calculate num trips / hour
        # TimeWindowLength = (end_sec - start_sec) / 3600
        TimeWindowLength = (end_sec - start_sec) / 3600
        time_period_list.append((finalID, start_sec, end_sec, TimeWindowLength))
    return time_period_list

def runTool(outStops, SQLDbase, time_window_value_table):
    def RetrieveFrequencyStatsForStop(stop_id, rtdirtuple, snap_to_nearest_5_minutes=False):
        '''For a given stop, query the stop_time_dictionaries {stop_id: [[trip_id, stop_time]]}
        and return the NumTrips, NumTripsPerHr, MaxWaitTime, and AvgHeadway given a
        specific route_id and direction. If snap to nearest five minutes is true, then
        this function will return headways snapped to the closest 5 minute interval.'''
        # Figure out what version of ArcGIS they're running
        BBB_SharedFunctions.DetermineArcVersion()
        if BBB_SharedFunctions.ProductName == "ArcGISPro" and BBB_SharedFunctions.ArcVersion in ["1.0", "1.1", "1.1.1"]:
            arcpy.AddError("The BetterBusBuffers toolbox does not work in versions of ArcGIS Pro prior to 1.2.\
        You have ArcGIS Pro version %s." % BBB_SharedFunctions.ArcVersion)
            raise BBB_SharedFunctions.CustomError
        try:
            stop_time_dictionaries = stoptimedict_rtedirpair[rtdirtuple]
        except KeyError:
            # We will get a KeyError if there were no trips found for the route/direction
            # pair, which usually happens if the wrong SQL database was selected.
            stop_time_dictionaries = {}

        # Make a list of stop_times
        StopTimesAtThisPoint = []
        try:
            for trip in stop_time_dictionaries[stop_id]:
                StopTimesAtThisPoint.append(trip[1])
        except KeyError:
            pass
        StopTimesAtThisPoint.sort()

        # Calculate the number of trips
        NumTrips = len(StopTimesAtThisPoint)
        NumTripsPerHr = float(NumTrips) / TimeWindowLength
        # Get the max wait time and the average headway
        MaxWaitTime = BBB_SharedFunctions.CalculateMaxWaitTime(StopTimesAtThisPoint, start_sec, end_sec)
        AvgHeadway = None
        if NumTrips > 1:
            AvgHeadway = max(1, int(round(float(
                sum(abs(x - y) for (x, y) in zip(StopTimesAtThisPoint[1:], StopTimesAtThisPoint[:-1])) / (
                        len(StopTimesAtThisPoint) - 1)) / 60, 0)))  # minutes
            if snap_to_nearest_5_minutes:
                AvgHeadway = round(AvgHeadway / 5.0) * 5
        return NumTrips, NumTripsPerHr, MaxWaitTime, AvgHeadway

    try:
        # The time_window_value_table will be a list of nested lists of strings like:
        # ------ Get input parameters and set things up. -----
        analysis_groups = {}
        arcpy.AddMessage("Establishing analysis parameters...")
        for row in time_window_value_table:
            # [[Weekday name or YYYYMMDD date, HH: MM, HH: MM, Departures / Arrivals, Prefix], [], ...]
            ag_key = (row[0], row[3])
            ag_value = analysis_groups.setdefault(ag_key, [])
            ag_addition = {row[4]: [row[1], row[2]]}
            ag_value.append(ag_addition)
            analysis_groups.update({ag_key: ag_value})
        # SQL database of preprocessed GTFS from Step 1
        conn = BBB_SharedFunctions.conn = sqlite3.connect(SQLDbase)
        c = BBB_SharedFunctions.c = conn.cursor()
        for period_group_key in analysis_groups:
            dayString = period_group_key[0]  # "Monday"  # "20160307" #20
            DepOrArrChoice = period_group_key[1]  # Departure/Arrival
            arcpy.AddMessage("Evaluting {0} on Date/Day {1}...".format(dayString, DepOrArrChoice))
            # Weekday or specific date to analyze.
            # Note: Datetime format check is in tool validation code
            alias_hour_pairs = analysis_groups[period_group_key]  # [{alias:[hfrom,hto],...}]
            if dayString in BBB_SharedFunctions.days:  # Generic weekday
                Specific = False
                day = dayString
            else:  # Specific date
                Specific = True
                day = datetime.datetime.strptime(dayString, "%Y%m%d")

            # Lower end of time window (HH:MM in 24-hour time)
            start_time_list = [list(i.values())[0][0] for i in alias_hour_pairs]
            # Default start time is midnight if they leave it blank.
            if not start_time_list:
                start_time_list = ["00:00"]
            # Convert to seconds
            # start_sec = BBB_SharedFunctions.parse_time(start_time + ":00")
            # Upper end of time window (HH:MM in 24-hour time)\

            end_time_list = [list(i.values())[0][1] for i in alias_hour_pairs]
            # Default end time is 11:59pm if they leave it blank.
            if not end_time_list:
                end_time_list = ["23:59"]
            # Convert to seconds
            alias_list = [list(i.keys())[0] for i in alias_hour_pairs]  # Will not work reliably in python 2
            TimePeriodTuples = GenerateTimePeriodList(start_time_list, end_time_list, alias_list)
            Min_Start_Sec, Max_End_Sec = GenerateTimePeriodExtent(start_time_list, end_time_list)
            total_frequency_fields = 4 * len(TimePeriodTuples)
            arcpy.AddMessage("Time Period IDs and Tuples created. The inputs provided will lead to the creation of {0} "
                             "frequency fields for {1} time periods.".format(total_frequency_fields,
                                                                             len(TimePeriodTuples)))
            # Does the user want to count arrivals or departures at the stops?
            if DepOrArrChoice == "Arrivals":
                DepOrArr = "arrival_time"
            elif DepOrArrChoice == "Departures":
                DepOrArr = "departure_time"
            # Output File Paths
            output_stop_file = outStops
            # Output Settings
            OverwriteOutput = arcpy.env.overwriteOutput  # Get the orignal value so we can reset it.
            arcpy.env.overwriteOutput = True

    except:
        arcpy.AddError("Error getting inputs.")
        raise
        # ----- Query the GTFS data to count the trips at each stop -----
    try:
        arcpy.AddMessage("Calculating the determining trips for route-direction pairs...")
        # Assemble Route and Direction IDS
        triproutefetch = '''
                            SELECT DISTINCT route_id,direction_id FROM trips;'''
        c.execute(triproutefetch)
        route_dir_list = c.fetchall()
        # Get the service_ids serving the correct days
        serviceidlist, serviceidlist_yest, serviceidlist_tom = \
            BBB_SharedFunctions.GetServiceIDListsAndNonOverlaps(day, Min_Start_Sec, Max_End_Sec, DepOrArr, Specific)
        # Some GTFS datasets use the same route_id to identify trips traveling in
        # either direction along a route. Others identify it as a different route.
        # We will consider each direction separately if there is more than one.

        trip_route_warning_counter = 0
        trip_route_dict = {}  # {(route_id, direction_id): [trip_id, trip_id,..]}
        for rtpair in route_dir_list:
            key = tuple(rtpair)
            route_id = rtpair[0]
            direction_id = rtpair[1]
            # Get list of trips
            # Ignore direction if this route doesn't have a direction
            if not direction_id is None and str(direction_id).strip():  # GTFS direction IDs of zero or empty text
                triproutefetch = '''
                        SELECT trip_id, service_id FROM trips
                        WHERE route_id = '{0}' AND direction_id = {1};'''.format(route_id, direction_id)
                # arcpy.AddMessage(triproutefetch)
            else:
                triproutefetch = '''
                        SELECT trip_id, service_id FROM trips
                        WHERE route_id = '{0}';'''.format(route_id)
            c.execute(triproutefetch)
            triproutelist = c.fetchall()
            if not triproutelist:
                arcpy.AddWarning("Your GTFS dataset does not contain any trips \
    corresponding to Route %s and Direction %s. Please ensure that \
    you have selected the correct GTFS SQL file for this input file or that your \
    GTFS data is good. Output fields will be generated, but \
    the values will be 0 or <Null>." % (route_id, str(direction_id)))

            for triproute in triproutelist:
                # Only keep trips running on the correct day

                if triproute[1] in serviceidlist or triproute[1] in serviceidlist_tom or triproute[
                    1] in serviceidlist_yest:  # Where FILTERING SHOULD BE happening.
                    trip_route_dict.setdefault(key, []).append(triproute[0])  # {(rtdirpair): [trip_id, trip_id,..]}

            if not trip_route_dict:
                arcpy.AddWarning("There is no service for route %s in direction %s \
    on %s during the time window you selected. Output fields will be generated, but \
    the values will be 0 or <Null>." % (route_id, str(direction_id), str(day)))

    except:
        arcpy.AddError("Error getting trips associated with route.")
        raise
    time_period_id_list = []  # List of Time Period IDs used to generate final fields in FC.
    stop_frequency_route_dir_dict = {}  # Stop ID to nested list{stop_id:{rtdirpair:[route-dir-pair-string,route_id,route_id_num,dir_id,
    # repeated for n time periods->[Period*]NumTrips,[Period*]NumTripsPerHour,[Period*]MaxWaitTime,[Period*]Headway],{...}
    for temporal_idx, time_tuple in enumerate(TimePeriodTuples):
        time_period = time_tuple[0]
        time_period_id_list.append(time_period)
        start_sec = time_tuple[1]
        end_sec = time_tuple[2]
        TimeWindowLength = time_tuple[3]
        # ----- Query the GTFS data to count the trips at each stop for this time period -----
        try:
            arcpy.AddMessage(
                "Calculating the number of transit trips available during the time window of time period ID"
                " {0}...".format(str(time_period)))
            frequencies_dict = BBB_SharedFunctions.MakeFrequenciesDict()
            stoptimedict_rtedirpair = {}  # #{rtdir tuple:stoptimedict}}
            ###################################stoptimedict={stop_id: [[trip_id, stop_time]]} Get length of stop_id
            for rtdirpair in trip_route_dict:
                triplist = trip_route_dict[rtdirpair]  # TODO - Melinda can, you review how this compares to updates?
                # Get the stop_times that occur during this time window- Not Causing Issues
                try:
                    stoptimedict = BBB_SharedFunctions.GetStopTimesForStopsInTimeWindow(start_sec, end_sec, DepOrArr,
                                                                                        triplist, "today",
                                                                                        frequencies_dict)
                except KeyError:  # No trips
                    pass
                try:
                    stoptimedict_yest = BBB_SharedFunctions.GetStopTimesForStopsInTimeWindow(start_sec, end_sec,
                                                                                             DepOrArr,
                                                                                             triplist, "yesterday",
                                                                                             frequencies_dict)
                except KeyError:  # No trips
                    pass
                try:
                    stoptimedict_tom = BBB_SharedFunctions.GetStopTimesForStopsInTimeWindow(start_sec, end_sec,
                                                                                            DepOrArr,
                                                                                            triplist, "tomorrow",
                                                                                            frequencies_dict)
                except KeyError:  # No trips
                    pass

                # Combine the three dictionaries into one master
                for stop in stoptimedict_yest:  # Update Dictionaries based on setdefault returns values.
                    stoptimedict[stop] = stoptimedict.setdefault(stop, []) + stoptimedict_yest[stop]
                for stop in stoptimedict_tom:
                    stoptimedict[stop] = stoptimedict.setdefault(stop, []) + stoptimedict_tom[stop]

                stoptimedict_rtedirpair[rtdirpair] = stoptimedict  # {rtdir tuple:{stoptimedict}}
                # Add a warning if there is no service.
                if not stoptimedict:
                    arcpy.AddWarning("There is no service for route %s in direction %s \
        on %s during the time window you selected. Output fields will be generated, but \
        the values will be 0 or <Null>." % (rtdirpair[0], str(rtdirpair[1]), dayString))

        except:
            arcpy.AddError("Error counting arrivals or departures at stop during time window.")
            raise
        try:
            arcpy.AddMessage("Developing Frequency and Trip Statistics for Stop-Route-Direction combinations.")
            for rtdirpair in stoptimedict_rtedirpair:
                stops = stoptimedict_rtedirpair[rtdirpair].keys()
                for stop in stops:
                    # Declare Unique ID Fields
                    routedir_id_str, route_id, dir_id = str(rtdirpair), str(rtdirpair[0]), str(rtdirpair[1])
                    try:
                        route_id_num = int(''.join(list(
                            filter(str.isdigit, route_id.split(":")[-1]))))  # Works in Python 3 too-gets all numbers
                    except:  # not a number
                        route_id_num = 999
                    # Get Stop-Route-Dir Frequencies by time period
                    NumTrips, NumTripsPerHour, MaxWaitTimeSec, AvgHeadwayMin = RetrieveFrequencyStatsForStop(stop,
                                                                                                             rtdirpair)
                    # Nested Dictionary Starts with Stop Level Keys
                    stop_frequency_record_rtdir_pair_dict = stop_frequency_route_dir_dict.setdefault(stop, {})
                    # The Dictionary that is keyed to the stop is a dictionary that is keyed to the current rtdirpair,
                    # the value is the list of values that are having frequencies extended on to based on the analysis
                    # analysis parameters.
                    # Declare empty default Record with IDs and None values as starting values of record.
                    empty_default_record = [routedir_id_str, route_id, route_id_num, dir_id]
                    frequency_field_start_index = int(
                        len(empty_default_record))  # No Minus because it is the start index
                    empty_default_record.extend([None] * total_frequency_fields)
                    stop_frequency_record = stop_frequency_record_rtdir_pair_dict.setdefault(rtdirpair,
                                                                                             empty_default_record)
                    new_frequency_fields = [NumTrips, NumTripsPerHour, MaxWaitTimeSec, AvgHeadwayMin]
                    number_of_frequency_fields = int(len(new_frequency_fields))
                    # Update Values with the appropriate index values.
                    time_period_start_index = temporal_idx * number_of_frequency_fields
                    for idx, value in enumerate(new_frequency_fields):
                        # Allocate values based on enumerate index, time period placement, and start of frequency fields
                        frequency_value_index = idx + time_period_start_index + frequency_field_start_index
                        stop_frequency_record[frequency_value_index] = new_frequency_fields[idx]
        except:
            arcpy.AddError("Error calculating statistics arrivals or departures at stop during time window.")
            raise
            # ----- Write to output -----

    try:
        arcpy.AddMessage("Writing output...")
        BBB_SharedFunctions.MakeTemporalRouteDirStopsFeatureClass(output_stop_file, stop_frequency_route_dir_dict,
                                                                  time_period_id_list)
    except:
        arcpy.AddError("Error writing output to feature class(es).")
        raise
    # Close Connection
    conn.close()
    arcpy.AddMessage("Finished!")
    arcpy.AddMessage("Calculated trip counts, frequency, max wait time, and \
headway were written to an output stops file by route-direction pairs.")
