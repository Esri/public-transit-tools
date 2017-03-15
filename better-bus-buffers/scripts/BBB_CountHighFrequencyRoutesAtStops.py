############################################################################
## Tool name: BetterBusBuffers - Count High Frequency Routes At Stops
## Created by: David Wasserman, david.wasserman.plan@gmail.com
## Based on work by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 14 March 2017
############################################################################
''' BetterBusBuffers - Count High Frequency Routes At Stops

BetterBusBuffers provides a quantitative measure of access to public transit
in your city by counting the transit trip frequency at various locations.

The Count High Frequency Routes At Stops tool creates a feature class of your GTFS stops
and counts the number of routes that by pass that stop that meet a specified headway threshold.
In addition, the tool counts the number of trips that visit each one during a time window
as well as the number of trips per hour, the maximum time between subsequent trips
during that time window, the average, minimum, and maximum headways of all routes visit that stop.
'''
################################################################################
'''Copyright 2016 Esri
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
# --------------------------------
# Copyright 2016 David J. Wasserman
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# --------------------------------
################################################################################

import arcpy
import BBB_SharedFunctions
import numpy as np
import collections
import sqlite3, os, operator, datetime
try:
    import pandas as pd
except:
    arcpy.AddError("This BetterBusBuffers tool requires the python library pandas. Please install the library or use"
                   "ArcGIS Pro or ArcMap 10.4 and above.")

class CustomError(Exception):
    pass


def RetrieveFrequencyStatsForStop(stop_id, rtdirtuple, trip_per_hr_threshold=.5, snap_to_nearest_5_minutes=False):
    '''For a given stop, query the stop_time_dictionaries {stop_id: [[trip_id, stop_time]]}
    and return the NumTrips, NumTripsPerHr, MaxWaitTime, and AvgHeadway given a
    specific route_id and direction. If snap to nearest five minutes is true, then
    this function will return headways snapped to the closest 5 minute interval. If
    the number of trips per hour is below the trip frequency interval, headways are
    changed to 180 minutes.'''
    try:
        stop_time_dictionaries = stoptimedict_rtedirpair[rtdirtuple]
    except KeyError:
        # We will get a KeyError if there were no trips found for the route/direction
        # pair, which usually happens if the wrong SQL database was selected.
        print("Could not retrieve Key.")
        stop_time_dictionaries = {}

    # Make a list of stop_times
    StopTimesAtThisPoint = []
    try:
        for trip in stop_time_dictionaries[stop_id]:
            StopTimesAtThisPoint.append(trip[1])
    except KeyError:
        print("Could not retrieve Key.")  # Issue is here
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
    if NumTripsPerHr <= trip_per_hr_threshold:  # If Number of Trips Per Hour is less than .5, set to 180.
        AvgHeadway = 180
    return NumTrips, NumTripsPerHr, MaxWaitTime, AvgHeadway


try:
    # ------ Get input parameters and set things up. -----
    try:
        arcpy.env.overwriteOutput = True  # Comment out
        # Figure out what version of ArcGIS they're running
        BBB_SharedFunctions.DetermineArcVersion()
        if BBB_SharedFunctions.ProductName == "ArcGISPro" and BBB_SharedFunctions.ArcVersion in ["1.0", "1.1", "1.1.1"]:
            arcpy.AddError("The BetterBusBuffers toolbox does not work in versions of ArcGIS Pro prior to 1.2.\
You have ArcGIS Pro version %s." % BBB_SharedFunctions.ArcVersion)
            raise CustomError
        # Path for output feature class of GTFS stops.
        # Must be a file geodatabase feature class, not a shapefile.
        outStops =  arcpy.GetParameterAsText(7)

        # GTFS SQL dbase - must be created ahead of time.
        SQLDbase = arcpy.GetParameterAsText(0)
        conn = sqlite3.connect(SQLDbase)
        c = BBB_SharedFunctions.c = conn.cursor()

        # Weekday or specific date to analyze.
        # Note: Datetime format check is in tool validation code
        day = arcpy.GetParameterAsText(1)
        if day in BBB_SharedFunctions.days:  # Generic weekday
            Specific = False
        else:  # Specific date
            Specific = True
            day = datetime.datetime.strptime(day, '%Y%m%d')

        # Lower end of time window (HH:MM in 24-hour time)
        start_time =  arcpy.GetParameterAsText(2)
        # Default start time is midnight if they leave it blank.
        if start_time == "":
            start_time = "00:00"
        # Convert to seconds
        start_sec = BBB_SharedFunctions.parse_time(start_time + ":00")
        # Upper end of time window (HH:MM in 24-hour time)
        end_time =  arcpy.GetParameterAsText(3)
        # Default end time is 11:59pm if they leave it blank.
        if end_time == "":
            end_time = "23:59"
        # Convert to seconds
        end_sec = BBB_SharedFunctions.parse_time(end_time + ":00")
        # Window of Time In Hours
        TimeWindowLength = (end_sec - start_sec) / 3600

        # threshold for headways to be counted
        FrequencyThreshold = float(arcpy.GetParameterAsText(5))
        # boolean will snap headways to nearest 5 minute increment (ie 11.5 minutes snaps to 10, but 13 snaps to 15)
        SnapToNearest5MinuteBool = bool(arcpy.GetParameterAsText(6))
        # Does the user want to count arrivals or departures at the stops?
        DepOrArrChoice = arcpy.GetParameterAsText(4)
        if DepOrArrChoice == "Arrivals":
            DepOrArr = "arrival_time"
        elif DepOrArrChoice == "Departures":
            DepOrArr = "departure_time"
        time_period = start_time + ":" + end_time

    except:
        arcpy.AddError("Error getting user inputs.")
        raise

    # ----- Create a feature class of stops and add fields for transit trip counts ------
    try:
        arcpy.AddMessage("Creating feature class of GTFS stops...")
        # Create a feature class of transit stops
        outStops, StopIDList = BBB_SharedFunctions.MakeStopsFeatureClass(outStops)
    except:
        arcpy.AddError("Error creating feature class of GTFS stops.")
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
            BBB_SharedFunctions.GetServiceIDListsAndNonOverlaps(day, start_sec, end_sec, DepOrArr, Specific)
        # Some GTFS datasets use the same route_id to identify trips traveling in
        # either direction along a route. Others identify it as a different route.
        # We will consider each direction separately if there is more than one.

        trip_route_warning_counter = 0
        trip_route_dict = {}  # {(route_id, direction_id): [trip_id, trip_id,..]}
        triproutelist = []
        for rtpair in route_dir_list:
            key = tuple(rtpair)
            route_id = rtpair[0]
            direction_id = rtpair[1]
            # Get list of trips
            # Ignore direction if this route doesn't have a direction
            if not direction_id is None:  # GTFS can have direction IDs of zero
                triproutefetch = '''
                        SELECT trip_id, service_id FROM trips
                        WHERE route_id='%s'
                        AND direction_id=%s
                        ;''' % (route_id, direction_id)
            else:
                triproutefetch = '''
                        SELECT trip_id, service_id FROM trips
                        WHERE route_id='%s'
                        ;''' % route_id
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
    # ----- Query the GTFS data to count the trips at each stop for this time period -----
    try:
        arcpy.AddMessage(
            "Calculating the number of transit trips available during the time window of time period ID"
            " {0}...".format(str(time_period)))
        stoptimedict_rtedirpair = {}  # #{rtdir tuple:stoptimedict}}
        ###################################stoptimedict={stop_id: [[trip_id, stop_time]]} Get length of stop_id
        for rtedirpair in trip_route_dict:
            triplist = trip_route_dict[rtedirpair]

            # Get the stop_times that occur during this time window- Not Causing Issues
            stoptimedict = BBB_SharedFunctions.GetStopTimesForStopsInTimeWindow(start_sec, end_sec, DepOrArr,
                                                                                triplist, "today")
            stoptimedict_yest = BBB_SharedFunctions.GetStopTimesForStopsInTimeWindow(start_sec, end_sec, DepOrArr,
                                                                                     triplist, "yesterday")
            stoptimedict_tom = BBB_SharedFunctions.GetStopTimesForStopsInTimeWindow(start_sec, end_sec, DepOrArr,
                                                                                    triplist, "tomorrow")

            # Combine the three dictionaries into one master
            for stop in stoptimedict_yest:  # Update Dictionaries based on setdefault returns values.
                stoptimedict[stop] = stoptimedict.setdefault(stop, []) + stoptimedict_yest[stop]
            for stop in stoptimedict_tom:
                stoptimedict[stop] = stoptimedict.setdefault(stop, []) + stoptimedict_tom[stop]
            # PD here
            stoptimedict_rtedirpair[rtedirpair] = stoptimedict  # {rtdir tuple:{stoptimedict}}
            # Add a warning if there is no service.
            if not stoptimedict:
                arcpy.AddWarning("There is no service for route %s in direction %s \
       on %s during the time window you selected. Output fields will be generated, but \
       the values will be 0 or <Null>." % (rtedirpair[0], str(rtedirpair[1]), str(day)))

        print(datetime.datetime.now())
    except:
        arcpy.AddError("Error counting arrivals or departures at stop during time window.")
        raise

    # ----- Write to output -----

    try:
        arcpy.AddMessage("Calculating frequency statistics from route direction pairs...")

        frequency_record_table=[] #[(rtedirpair_id,route_id,direction_id,stop_id,NumTripsPerHr,MaxWaitTime,AvgHeadway)]
        labels=["rtedirpair_id","rte_count","direction_id","stop_id","NumTrips","NumTripsPerHr","MaxWaitTime","AvgHeadway"]
        for rtedirpair in stoptimedict_rtedirpair:
            route_id=rtedirpair[0]
            stops = stoptimedict_rtedirpair[rtedirpair].keys()
            for stop_id in stops:
                NumTrips,NumTripsPerHr,MaxWaitTime,AvgHeadway=RetrieveFrequencyStatsForStop(stop_id,rtedirpair,
                                                                   snap_to_nearest_5_minutes=SnapToNearest5MinuteBool)
                frequency_record_table.append((rtedirpair,route_id,direction_id,stop_id,NumTrips,NumTripsPerHr,
                                               MaxWaitTime,AvgHeadway))
        frequency_dataframe=pd.DataFrame.from_records(frequency_record_table,columns=labels)
        #Count the number of routes that meet threshold
        frequency_dataframe["MetHdWyLim"]=1
        frequency_dataframe["MetHdWyLim"].where(frequency_dataframe["AvgHeadway"]<=FrequencyThreshold,np.nan,inplace=True)
        #Add Fields for frequency aggregation
        frequency_dataframe["MinHeadway"]=frequency_dataframe["AvgHeadway"]
        frequency_dataframe["MaxHeadway"]=frequency_dataframe["AvgHeadway"]
        output_stats=collections.OrderedDict([("NumTrips",("sum")),("NumTripsPerHr", ("sum")),("MaxWaitTime",("max")),
                                 ("rte_count",("count")),("AvgHeadway", ("mean")),("MinHeadway",
                                    ("min")),("MaxHeadway", ("max")), ("MetHdWyLim", ("sum"))])
        stop_groups=frequency_dataframe.groupby("stop_id")
        stop_frequency_statistics=stop_groups.agg(output_stats)
    except:
        arcpy.AddError("Error calculating frequency statistics...")
        raise
    try:
        arcpy.AddMessage("Writing output data...")
        # Create an update cursor to add numtrips, trips/hr, maxwaittime, and headway stats to stops
        frequency_records=stop_frequency_statistics.to_records()
        arcpy.da.ExtendTable(outStops,"stop_id", frequency_records, "stop_id", append_only=False)
        arcpy.AddMessage("Script complete!")
    except:
        arcpy.AddError("Error writing to output.")
        raise

    arcpy.AddMessage("Finished!")
    arcpy.AddMessage("Your output is located at " + outStops)

except CustomError:
    arcpy.AddError("Failed to count trips at stops.")
    pass

except:
    arcpy.AddError("Failed to count trips at stops.")
    raise
