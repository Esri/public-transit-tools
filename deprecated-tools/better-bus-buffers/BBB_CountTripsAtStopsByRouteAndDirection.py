############################################################################
## Tool name: BetterBusBuffers - Count Trips at Stops by Route and Direction
## Created by: David Wasserman, https://github.com/d-wasserman and Melinda Morang, Esri
## This tool was developed as part of Transit R&D Efforts from Fehr & Peers.
## Fehr & Peers contributes this tool to the BBB Toolset to further more
## informed planning. 
## Last updated: 8 October 2020
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

def runTool(output_stop_file, SQLDbase, time_window_value_table, snap_to_nearest_5_minutes):
    def RetrieveFrequencyStatsForStop(stop_id, stoptimedict, start_sec, end_sec):
        '''For a given stop, query the dictionary
        and return the NumTrips, NumTripsPerHr, MaxWaitTime, and AvgHeadway given a
        specific route_id and direction. If snap to nearest five minutes is true, then
        this function will return headways snapped to the closest 5 minute interval.'''
        # Make a list of stop_times
        StopTimesAtThisPoint = []
        try:
            for trip in stoptimedict[stop_id]:
                StopTimesAtThisPoint.append(trip[1])
        except KeyError:
            pass
        StopTimesAtThisPoint.sort()

        # Calculate the number of trips
        NumTrips = len(StopTimesAtThisPoint)
        NumTripsPerHr = round(float(NumTrips) / ((end_sec - start_sec) / 3600), 2)
        # Get the max wait time and the average headway
        MaxWaitTime = BBB_SharedFunctions.CalculateMaxWaitTime(StopTimesAtThisPoint, start_sec, end_sec)
        if snap_to_nearest_5_minutes:
            round_to = 5
        else:
            round_to = None
        AvgHeadway = BBB_SharedFunctions.CalculateAvgHeadway(StopTimesAtThisPoint, round_to)
        return NumTrips, NumTripsPerHr, MaxWaitTime, AvgHeadway

    # ----- Get input parameters and set things up. -----
    # Check software version and fail out quickly if it's not sufficient.
    BBB_SharedFunctions.CheckArcVersion(min_version_pro="1.2")

    arcpy.AddMessage("Reading data...")

    # Connect to SQL database of preprocessed GTFS from Step 1
    conn = BBB_SharedFunctions.conn = sqlite3.connect(SQLDbase)
    c = BBB_SharedFunctions.c = conn.cursor()

    # Store frequencies if relevant
    frequencies_dict = BBB_SharedFunctions.MakeFrequenciesDict()

    # Get unique route_id/direction_id pairs and calculate the trips used in each
    # Some GTFS datasets use the same route_id to identify trips traveling in
    # either direction along a route. Others identify it as a different route.
    # We will consider each direction separately if there is more than one.
    trip_route_dict = {}  # {(route_id, direction_id): [(trip_id, service_id),..]}
    triproutefetch = '''SELECT DISTINCT route_id,direction_id FROM trips;'''
    c.execute(triproutefetch)
    for rtpair in c.fetchall():
        key = tuple(rtpair)
        route_id = rtpair[0]
        direction_id = rtpair[1]
        # Get list of trips
        # Ignore direction if this route doesn't have a direction
        if direction_id is not None and str(direction_id).strip():
            triproutefetch = '''
                    SELECT trip_id, service_id FROM trips
                    WHERE route_id = '{0}' AND direction_id = {1};'''.format(route_id, direction_id)
        else:
            triproutefetch = '''
                    SELECT trip_id, service_id FROM trips
                    WHERE route_id = '{0}';'''.format(route_id)
        c.execute(triproutefetch)
        triproutelist = c.fetchall()
        trip_route_dict[key] = triproutelist

    # ----- For each time window, calculate the stop frequency -----
    final_stop_freq_dict = {}  # {(stop_id, route_id, direction_id): {prefix: (NumTrips, NumTripsPerHour, MaxWaitTimeSec, AvgHeadwayMin)}}
    # The time_window_value_table will be a list of nested lists of strings like:
    # [[Weekday name or YYYYMMDD date, HH: MM, HH: MM, Departures / Arrivals, Prefix], [], ...]
    for time_window in time_window_value_table:
        # Prefix/identifier associated with this time window
        prefix = time_window[4]
        arcpy.AddMessage("Calculating statistics for time window %s..." % prefix)
        # Clean up date and determine whether it's a date or a weekday
        Specific, day = BBB_SharedFunctions.CheckSpecificDate(time_window[0])
        # Convert times to seconds
        start_time = time_window[1]
        end_time = time_window[2]
        if not start_time:
            start_time = "00:00"
        if not end_time:
            end_time = "23:59"
        start_sec, end_sec = BBB_SharedFunctions.ConvertTimeWindowToSeconds(start_time, end_time)
        # Clean up arrival/departure time choice
        DepOrArr = BBB_SharedFunctions.CleanUpDepOrArr(time_window[3])

        # Get the trips running in this time window for each route/direction pair
        # Get the service_ids serving the correct days
        serviceidlist, serviceidlist_yest, serviceidlist_tom = \
            BBB_SharedFunctions.GetServiceIDListsAndNonOverlaps(day, start_sec, end_sec, DepOrArr, Specific)

        # Retrieve the stop_times for the time window broken out by route/direction
        stoproutedir_dict = {}  # {(stop_id, route_id, direction_id): [NumTrips, NumTripsPerHour, MaxWaitTimeSec, AvgHeadwayMin]}
        for rtdirpair in trip_route_dict:
            # Get trips running with these service_ids
            trip_serv_list = trip_route_dict[rtdirpair]
            triplist = []
            for tripserv in trip_serv_list:
                # Only keep trips running on the correct day
                if tripserv[1] in serviceidlist or tripserv[1] in serviceidlist_tom or \
                    tripserv[1] in serviceidlist_yest:
                    triplist.append(tripserv[0])

            # Get the stop_times that occur during this time window for these trips
            try:
                stoptimedict = BBB_SharedFunctions.GetStopTimesForStopsInTimeWindow(
                    start_sec, end_sec, DepOrArr, triplist, "today", frequencies_dict)
            except KeyError:  # No trips
                pass
            try:
                stoptimedict_yest = BBB_SharedFunctions.GetStopTimesForStopsInTimeWindow(
                    start_sec, end_sec, DepOrArr, triplist, "yesterday", frequencies_dict)
            except KeyError:  # No trips
                pass
            try:
                stoptimedict_tom = BBB_SharedFunctions.GetStopTimesForStopsInTimeWindow(
                    start_sec, end_sec, DepOrArr, triplist, "tomorrow", frequencies_dict)
            except KeyError:  # No trips
                pass

            # Combine the three dictionaries into one master
            for stop in stoptimedict_yest:
                stoptimedict[stop] = stoptimedict.setdefault(stop, []) + stoptimedict_yest[stop]
            for stop in stoptimedict_tom:
                stoptimedict[stop] = stoptimedict.setdefault(stop, []) + stoptimedict_tom[stop]

            for stop in stoptimedict.keys():
                # Get Stop-Route-Dir Frequencies by time period
                vals = RetrieveFrequencyStatsForStop(stop, stoptimedict, start_sec, end_sec)
                key = (stop, rtdirpair[0], rtdirpair[1],)
                if key not in final_stop_freq_dict:
                    final_stop_freq_dict[key] = {prefix: vals}
                else:
                    final_stop_freq_dict[key][prefix] = vals

    # ----- Write the stops and stats to the output feature class -----
    arcpy.AddMessage("Writing outputs...")
    # Make the basic feature class for stops with correct gtfs fields
    with arcpy.EnvManager(overwriteOutput=True):
        output_coords = BBB_SharedFunctions.CreateStopsFeatureClass(output_stop_file)

    # Add fields specific to this tool's outputs
    arcpy.management.AddField(output_stop_file, 'route_id', "TEXT")
    arcpy.management.AddField(output_stop_file, 'direction_id', "SHORT")
    # Create fields for stats for each time window using prefix
    base_field_names = ['_NumTrips', '_NumTripsPerHr', '_MaxWaitTime', '_AvgHeadway']
    new_fields = []
    for time_window in time_window_value_table:
        for base_field in base_field_names:
            new_field = time_window[4] + base_field
            new_fields.append(new_field)
            arcpy.management.AddField(output_stop_file, new_field, "DOUBLE")

    # Get the stop info from the GTFS SQL file
    StopTable = BBB_SharedFunctions.GetStopsData()
    stop_dict = {stop[0]: stop for stop in StopTable}

    # Make a dictionary to track whether we have inserted all stops at least once into the output
    used_stops = {stop[0]: False for stop in StopTable}
    # Store stop geometries in dictionary so they can be inserted multiple times without recalculating
    stop_geoms = {stop[0]: BBB_SharedFunctions.MakeStopGeometry(stop[4], stop[5], output_coords) for stop in StopTable}

    # Add the stops with stats to the feature class
    fields = [
        "SHAPE@", "stop_id", "stop_code", "stop_name", "stop_desc", "zone_id", "stop_url", "location_type",
        "parent_station", "route_id", "direction_id"
    ] + new_fields
    with arcpy.da.InsertCursor(output_stop_file, fields) as cur3:
        # Iterate over all unique stop, route_id, direction_id groups and insert values
        for key in sorted(final_stop_freq_dict.keys()):
            stop_id = key[0]
            used_stops[stop_id] = True
            route_id = key[1]
            direction_id = key[2]
            stop_data = stop_dict[stop_id]
            # Schema of StopTable
            ##   0 - stop_id
            ##   1 - stop_code
            ##   2 - stop_name
            ##   3 - stop_desc
            ##   4 - stop_lat
            ##   5 - stop_lon
            ##   6 - zone_id
            ##   7 - stop_url
            ##   8 - location_type
            ##   9 - parent_station
            row = [
                stop_geoms[stop_id],  # Geometry
                stop_data[0], stop_data[1], stop_data[2], stop_data[3], stop_data[6], stop_data[7], stop_data[8], stop_data[9],  # GTFS data
                route_id, direction_id  # route and direction IDs
            ]
            # Populate stats fields for each prefix
            for time_window in time_window_value_table:
                prefix = time_window[4]
                try:
                    vals = final_stop_freq_dict[key][prefix]
                except KeyError:
                    # This stop/route/direction group had no service for this time window
                    vals = [0, 0, None, None]
                row += vals

            # Insert the row
            cur3.insertRow(row)

        # Insert row for any remaining stops that were not used at all
        for stop_id in used_stops:
            if used_stops[stop_id]:
                # This one was already inserted
                continue
            stop_data = stop_dict[stop_id]
            row = [
                stop_geoms[stop_id],  # Geometry
                stop_data[0], stop_data[1], stop_data[2], stop_data[3], stop_data[6], stop_data[7], stop_data[8], stop_data[9],  # GTFS data
                None, None  # route and direction IDs - None because not used
            ]
            # Populate stats fields for each prefix
            for time_window in time_window_value_table:
                row += [0, 0, None, None]
            # Insert the row
            cur3.insertRow(row)

    # Close Connection
    conn.close()
    arcpy.AddMessage("Finished!")
    arcpy.AddMessage("Calculated trip counts, frequency, max wait time, and \
headway were written to an output stops file by route-direction pairs.")
