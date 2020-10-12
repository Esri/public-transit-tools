############################################################################
## Tool name: BetterBusBuffers
## Shared Functions
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 14 December 2017
############################################################################
''' This file contains shared functions used by various BetterBusBuffers tools.'''
################################################################################
'''Copyright 2017 Esri
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

import sqlite3, os, operator, datetime
import arcpy

# sqlite cursor - must be set from the script calling the functions explicitly
# or using the ConnectToSQLDatabase() function
c = None
conn = None

# Version of ArcGIS they are running
ArcVersion = None
ProductName = None

# The GTFS spec uses WGS 1984 coordinates
WGSCoords = "GEOGCS['GCS_WGS_1984',DATUM['D_WGS_1984', \
SPHEROID['WGS_1984',6378137.0,298.257223563]], \
PRIMEM['Greenwich',0.0],UNIT['Degree',0.0174532925199433]]; \
-400 -400 1000000000;-100000 10000;-100000 10000; \
8.98315284119522E-09;0.001;0.001;IsHighPrecision"

# World Cylindrical Equal Area (WKID 54034) preserves area in meters
WorldCylindrical = "PROJCS['World_Cylindrical_Equal_Area', \
GEOGCS['GCS_WGS_1984',DATUM['D_WGS_1984',SPHEROID['WGS_1984', \
6378137.0,298.257223563]],PRIMEM['Greenwich',0.0], \
UNIT['Degree',0.0174532925199433]],PROJECTION['Cylindrical_Equal_Area'], \
PARAMETER['False_Easting',0.0],PARAMETER['False_Northing',0.0], \
PARAMETER['Central_Meridian',0.0],PARAMETER['Standard_Parallel_1',0.0], \
UNIT['Meter',1.0]];-20037700 -6364000 10000;-100000 10000;-100000 10000; \
5;0.001;0.001;IsHighPrecision"

# Number of seconds in a day.
SecsInDay = 86400

# Days of the week
days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

CurrentGPWorkspaceError = "This tool creates one or more Network Analysis layers. \
In ArcGIS Pro, Network Analysis layers make use of on-disk feature classes.  These \
feature classes are created in the Geoprocessing Current Workspace that you specify. \
In order to use this tool, you must explicitly specify a file geodatabase as the \
Geoprocessing Current workspace.  You can do this in your python script by setting \
arcpy.env.workspace = [path to desired file geodatabase]."

MaxTextFieldLength = 255


def MakeServiceIDList(day, Specific=False):
    '''Find the service ids for the specific date using both calendar and calendar_dates.'''

    if Specific == True:
        # The weekday of the specific date, as an integer with 0 being Monday
        dayString = days[day.weekday()]
    else:
        dayString = day

    serviceidlist = []
    noservice = []
    nonoverlappingsids = []
    startdatedict = {}
    enddatedict = {}

    tables = GetGTFSTableNames()
    
    # Find added and subtracted service_ids from calendar_dates.
    cs = conn.cursor()
    if Specific == True and "calendar_dates" in tables:
        serviceidfetch = '''
            SELECT service_id, exception_type FROM calendar_dates
            WHERE date == "%s"
            ;''' % datetime.datetime.strftime(day, '%Y%m%d')
        cs.execute(serviceidfetch)
        for id in cs:
            # If service is added that day, add it to the list of valid service_ids
            if id[1] == 1:
                serviceidlist.append(id[0])
            # If service is subtracted that day, add it to a list of service_ids to exclude
            elif id[1] == 2:
                noservice.append(id[0])

    # Find the service_ids that describe trips on our selected day from calendar.
    if "calendar" in tables:
        serviceidfetch = '''
            SELECT service_id, start_date, end_date FROM calendar
            WHERE %s == "1"
            ;''' % dayString.lower()
        cs.execute(serviceidfetch)
        for id in cs:
            if Specific == False:
                startdatedict[id[0]] = id[1]
                enddatedict[id[0]] = id[2]
                serviceidlist.append(id[0])
            else:
                # If the service_id is in our list of exceptions, skip it
                if id[0] in noservice:
                    continue
                # Add to the list of service_ids if it falls within the valid date range
                startdatetime = datetime.datetime.strptime(id[1], '%Y%m%d')
                enddatetime = datetime.datetime.strptime(id[2], '%Y%m%d')
                if day >= startdatetime and day <= enddatetime:
                    serviceidlist.append(id[0])

    if Specific == False:
        # Check for non-overlapping date ranges to prevent double-counting.
        for sid in serviceidlist:
            for eid in serviceidlist:
                if startdatedict[sid] > enddatedict[eid]:
                    nonoverlappingsids.append((sid, eid))
                if len(nonoverlappingsids) >= 10:
                    break

    return serviceidlist, nonoverlappingsids


def GetServiceIDListsAndNonOverlaps(day, start_sec, end_sec, DepOrArr, Specific=False, ConsiderYesterday=None, ConsiderTomorrow=None):
    ''' Get the lists of service ids for today, yesterday, and tomorrow, and
    combine non-overlapping date range list for all days'''

    # Determine if it's early enough in the day that we need to consider trips
    # still running from yesterday
    if ConsiderYesterday is None:
        ConsiderYesterday = ShouldConsiderYesterday(start_sec, DepOrArr)
    # If our time window spans midnight, we need to check tomorrow's trips, too.
    if ConsiderTomorrow is None:
        ConsiderTomorrow = ShouldConsiderTomorrow(end_sec)
    # And what weekdays are yesterday and tomorrow?
    if Specific == False:
        Yesterday = days[(days.index(day) - 1)%7] # %7 wraps it around
        Tomorrow = days[(days.index(day) + 1)%7] # %7 wraps it around
    else:
        Yesterday = day - datetime.timedelta(days=1)
        Tomorrow = day + datetime.timedelta(days=1)

    try:
        # Get the service ids applicable for the current day of the week
        # Furthermore, get list of service ids with non-overlapping date ranges.
        serviceidlist, nonoverlappingsids = MakeServiceIDList(day, Specific)

        # If we need to consider yesterday's trips, get the service ids.
        serviceidlist_yest = []
        nonoverlappingsids_yest = []
        if ConsiderYesterday:
            serviceidlist_yest, nonoverlappingsids_yest = MakeServiceIDList(Yesterday, Specific)

        # If we need to consider tomorrow's trips, get the service ids.
        serviceidlist_tom = []
        nonoverlappingsids_tom = []
        if ConsiderTomorrow:
            serviceidlist_tom, nonoverlappingsids_tom = MakeServiceIDList(Tomorrow, Specific)
    except:
        arcpy.AddError("Error getting list of service_ids for time window.")
        raise CustomError

    # Make sure there is service on the day we're analyzing.
    if not serviceidlist and not serviceidlist_yest and not serviceidlist_tom:
        arcpy.AddWarning("There is no transit service during this time window. \
No service_ids cover the weekday or specific date you have selected.")

    # Combine lists of non-overlapping date range pairs of service ids
    nonoverlappingsids += nonoverlappingsids_yest
    nonoverlappingsids += nonoverlappingsids_tom
    nonoverlappingsids = list(set(nonoverlappingsids))
    nonoverlappingsids = nonoverlappingsids[:10] # Truncate to 10 records
    
    if nonoverlappingsids:
        overlapwarning = u"Warning! The trips being counted in this analysis \
have service_ids with non-overlapping date ranges in your GTFS dataset's \
calendar.txt file(s). As a result, your analysis might double count the number \
of trips available if you are analyzing a generic weekday instead of a specific \
date.  This is especially likely if the non-overlapping pairs are in the same \
GTFS dataset.  Please check the date ranges in your calendar.txt file(s), and \
consider running this analysis for a specific date instead of a generic weekday. \
See the User's Guide for further assistance.  Date ranges do not overlap in the \
following pairs of service_ids: "
        if len(nonoverlappingsids) == 10:
            overlapwarning += "(Showing the first 10 non-overlaps) "
        overlapwarning += str(nonoverlappingsids)
        arcpy.AddWarning(overlapwarning)   
    
    return serviceidlist, serviceidlist_yest, serviceidlist_tom


def MakeTripList(serviceidlist):
    '''Select the trips with the service_ids of interest'''

    triplist = []
    ct = conn.cursor()
    for service_id in serviceidlist:
        tripsfetch = '''
            SELECT DISTINCT trip_id FROM trips
            WHERE service_id == ?
            ;'''
        ct.execute(tripsfetch, (service_id,))
        for tr in ct:
            triplist.append(tr[0])
    # There shouldn't be any duplicates, but check anyway.
    triplist = list(set(triplist))

    return triplist


def MakeTripRouteDict():
    '''Make global dictionary of {trip_id: route_id}'''

    triproute_dict = {}
    ctr = conn.cursor()

    # First, make sure there are no duplicate trip_id values, as this will mess things up later.
    tripDuplicateFetch = "SELECT trip_id, count(*) from trips group by trip_id having count(*) > 1"
    ctr.execute(tripDuplicateFetch)
    tripdups = ctr.fetchall()
    tripdupslist = [tripdup for tripdup in tripdups]
    if tripdupslist:
        arcpy.AddError("Your GTFS trips table is invalid.  It contains multiple trips with the same trip_id.")
        for tripdup in tripdupslist:
            arcpy.AddError("There are %s instances of the trip_id value '%s'." % (str(tripdup[1]), unicode(tripdup[0])))
        raise CustomError
 
    tripsfetch = '''
        SELECT trip_id, route_id
        FROM trips
        ;'''
    ctr.execute(tripsfetch)
    for trip in ctr:
        triproute_dict[trip[0]] = trip[1]
    
    return triproute_dict


def MakeFrequenciesDict():
    '''Put the frequencies.txt information into a dictionary'''

    # Check if the dataset uses frequency. If not, no need to do more.
    tblnamelist = GetGTFSTableNames()
    if not "frequencies" in tblnamelist:
        return {}

    # Fill the dictionary
    frequencies_dict = {}
    cf = conn.cursor()
    freqfetch = '''
        SELECT trip_id, start_time, end_time, headway_secs
        FROM frequencies
        ;'''
    cf.execute(freqfetch)
    for freq in cf:
        trip_id = freq[0]
        trip_data = [freq[1], freq[2], freq[3]]
        # {trip_id: [start_time, end_time, headway_secs]}
        frequencies_dict.setdefault(trip_id, []).append(trip_data)

    return frequencies_dict


def GetStopTimesForStopsInTimeWindow(start, end, DepOrArr, triplist, day, frequencies_dict):
    '''Return a dictionary of {stop_id: [[trip_id, stop_time]]} for trips and
    stop_times in the time window. Adjust the stop_time value to today's time of
    day if it is a trip from yesterday or tomorrow.'''

    # Adjust times for trips from yesterday or tomorrow
    if day == "yesterday":
        start += SecsInDay
        end += SecsInDay
    if day == "tomorrow":
        start = start - SecsInDay
        end = end - SecsInDay

    stoptimedict = {} # {stop_id: [[trip_id, stop_time]]}
    cst = conn.cursor()
    for trip in triplist:

        # If the trip uses the frequencies.txt file, extrapolate the stop_times
        # throughout the day using the relative time between the stops given in
        # stop_times and the headways listed in frequencies.
        if trip in frequencies_dict:

            # Grab the stops stop_times for this trip
            stopsfetch = '''
                SELECT stop_id, %s FROM stop_times
                WHERE trip_id == ?
                ;''' % DepOrArr
            cst.execute(stopsfetch, (trip,))
            StopTimes = cst.fetchall()
            # Sort by time
            StopTimes.sort(key=operator.itemgetter(1))
            # time 0 for this trip
            initial_stop_time = int(StopTimes[0][1])

            # Extrapolate using the headway and time windows from frequencies to
            # find the stop visits. Add them to the dictionary if they fall within
            # our analysis time window.
            for window in frequencies_dict[trip]:
                start_timeofday = window[0]
                end_timeofday = window[1]
                headway = window[2]
                # Increment by by headway to create new stop visits
                for i in range(int(round(start_timeofday, 0)), int(round(end_timeofday, 0)), headway):
                    for stop in StopTimes:
                        time_along_trip = int(stop[1]) - initial_stop_time
                        stop_time = i + time_along_trip
                        if start < stop_time < end:
                            if day == "yesterday":
                                stop_time = stop_time - SecsInDay
                            elif day == "tomorrow":
                                stop_time += SecsInDay
                            # To distinguish between stop visits, since all frequency-based
                            # trips have the same id, create a special id based on the day
                            # and time of day: trip_id_DayStartTime. This ensures that the
                            # number of trips will be counted correctly later and not eliminated
                            # as being the same trip
                            special_trip_name = trip + "_%s%s" % (day, str(i))
                            stoptimedict.setdefault(stop[0], []).append([special_trip_name, stop_time])

        # If the trip doesn't use frequencies, get the stop times directly
        else:
            # Grab the stop_times within the time window
            stopsfetch = '''
                SELECT stop_id, %s FROM stop_times
                WHERE trip_id == ?
                AND %s BETWEEN ? AND ?
                ;''' % (DepOrArr, DepOrArr)
            cst.execute(stopsfetch, (trip, start, end,))
            for stoptime in cst:
                stop_id = stoptime[0]
                stop_time = int(stoptime[1])
                if day == "yesterday":
                    stop_time = stop_time - SecsInDay
                elif day == "tomorrow":
                    stop_time += SecsInDay
                stoptimedict.setdefault(stop_id, []).append([trip, stop_time])

    return stoptimedict


def GetLineTimesInTimeWindow(start, end, DepOrArr, triplist, day, frequencies_dict):
    '''Return a dictionary of {line_key: [[trip_id, start_time, end_time]]} for trips and
    stop_times in the time window. Adjust the stop_time value to today's time of
    day if it is a trip from yesterday or tomorrow.'''

    # Adjust times for trips from yesterday or tomorrow
    if day == "yesterday":
        start += SecsInDay
        end += SecsInDay
    if day == "tomorrow":
        start = start - SecsInDay
        end = end - SecsInDay

    linetimedict = {} # {line_key: [[trip_id, start_time, end_time]]}
    for trip in triplist:

        # If the trip uses the frequencies.txt file, extrapolate the stop_times
        # throughout the day using the relative time between the stops given in
        # stop_times and the headways listed in frequencies.
        if trip in frequencies_dict:

            # Grab the stops stop_times for this trip
            linesfetch = '''
                SELECT key, start_time, end_time FROM schedules
                WHERE trip_id == ?
                ;'''
            c.execute(linesfetch, (trip,))
            LineTimes = c.fetchall()
            # Sort by time
            LineTimes.sort(key=operator.itemgetter(1))
            # time 0 for this trip
            initial_stop_time1 = int(LineTimes[0][1]) # Beginning stop of segment
            initial_stop_time2 = int(LineTimes[0][2]) # Ending stop of segment

            # Extrapolate using the headway and time windows from frequencies to
            # find the times lines are traveled on. Add them to the dictionary if they fall within
            # our analysis time window.
            for window in frequencies_dict[trip]:
                start_timeofday = window[0]
                end_timeofday = window[1]
                headway = window[2]
                # Increment by by headway to create new stop visits
                for i in range(int(round(start_timeofday, 0)), int(round(end_timeofday, 0)), headway):
                    for line in LineTimes:
                        time_along_trip1 = int(line[1]) - initial_stop_time1 # Time into trip when it reaches first stop of line segment
                        time_along_trip2 = int(line[2]) - initial_stop_time2 # Time into trip when it reaches second stop of line segment
                        stop_time1 = i + time_along_trip1
                        stop_time2 = i + time_along_trip2
                        if start < stop_time1 < stop_time2 < end: # Segment is fully within time window
                            if day == "yesterday":
                                stop_time1 = stop_time1 - SecsInDay
                                stop_time2 = stop_time2 - SecsInDay
                            elif day == "tomorrow":
                                stop_time1 += SecsInDay
                                stop_time2 += SecsInDay
                            # To distinguish between stop visits, since all frequency-based
                            # trips have the same id, create a special id based on the day
                            # and time of day: trip_id_DayStartTime. This ensures that the
                            # number of trips will be counted correctly later and not eliminated
                            # as being the same trip
                            special_trip_name = trip + "_%s%s" % (day, str(i))
                            linetimedict.setdefault(line[0], []).append([special_trip_name, stop_time1, stop_time2])

        # If the trip doesn't use frequencies, get the stop times directly
        else:
            # Grab the line schedules fully within the time window
            linesfetch = '''
                SELECT key, start_time, end_time FROM schedules
                WHERE trip_id == ?
                AND start_time BETWEEN ? AND ?
                AND end_time BETWEEN ? AND ?
                ;'''
            c.execute(linesfetch, (trip, start, end, start, end,))
            LineTimes = c.fetchall()

            for linetime in LineTimes:
                line_id = linetime[0]
                start_time = int(linetime[1])
                end_time = int(linetime[2])
                if day == "yesterday":
                    start_time = start_time - SecsInDay
                    end_time = end_time - SecsInDay
                elif day == "tomorrow":
                    start_time += SecsInDay
                    end_time += SecsInDay
                linetimedict.setdefault(line_id, []).append([trip, start_time, end_time])

    return linetimedict


def ShouldConsiderYesterday(start_sec, DepOrArr):
    '''Determine if it's early enough in the day that we need to consider trips
    still running from the day before. Do this by finding the largest stop_time
    in the GTFS file and comparing it to the user's start time.'''
    ConsiderYesterday = False
    # Select the largest stop time
    MaxTimeFetch = '''
        SELECT MAX(%s) FROM stop_times
        ;''' % (DepOrArr)
    c.execute(MaxTimeFetch)
    MaxTime = c.fetchone()[0]
    if start_sec < MaxTime - SecsInDay:
        ConsiderYesterday = True
    return ConsiderYesterday


def ShouldConsiderTomorrow(end_sec):
    '''Return whether a time is greater than midnight.'''
    ConsiderTomorrow = False
    if end_sec > SecsInDay:
        ConsiderTomorrow = True
    return ConsiderTomorrow

def GetTripLists(day, start_sec, end_sec, DepOrArr, Specific=False):
    '''Returns separate lists of trips running today, yesterday, and tomorrow'''

    # Determine if it's early enough in the day that we need to consider trips
    # still running from yesterday
    ConsiderYesterday = ShouldConsiderYesterday(start_sec, DepOrArr)
    ConsiderTomorrow = ShouldConsiderTomorrow(end_sec)

    # Find the service_ids that serve the relevant day
    serviceidlist, serviceidlist_yest, serviceidlist_tom, = \
        GetServiceIDListsAndNonOverlaps(day, start_sec, end_sec, DepOrArr, Specific, ConsiderYesterday, ConsiderTomorrow)

    try:
        # Get the list of trips with these service ids.
        triplist = MakeTripList(serviceidlist)

        triplist_yest = []
        if ConsiderYesterday:
            # To save time, only get yesterday's trips if yesterday's service ids
            # are different than today's.
            if serviceidlist_yest != serviceidlist:
                triplist_yest = MakeTripList(serviceidlist_yest)
            else:
                triplist_yest = triplist

        triplist_tom = []
        if ConsiderTomorrow:
            # To save time, only get tomorrow's trips if tomorrow's service ids
            # are different than today's.
            if serviceidlist_tom == serviceidlist:
                triplist_tom = triplist
            elif serviceidlist_tom == serviceidlist_yest:
                triplist_tom = triplist_yest
            else:
                triplist_tom = MakeTripList(serviceidlist_tom)
    except:
        arcpy.AddError("Error creating list of trips for time window.")
        raise CustomError

    # Make sure there is service on the day we're analyzing.
    if not triplist and not triplist_yest and not triplist_tom:
        arcpy.AddWarning("There is no transit service during this time window. \
No trips are running.")

    return triplist, triplist_yest, triplist_tom


def CountTripsAtStops(day, start_sec, end_sec, DepOrArr, Specific=False):
    '''Given a time window, return a dictionary of
    {stop_id: [[trip_id, stop_time]]}'''

    triplist, triplist_yest, triplist_tom = GetTripLists(day, start_sec, end_sec, DepOrArr, Specific)

    try:
        frequencies_dict = MakeFrequenciesDict()

        # Get the stop_times that occur during this time window
        stoptimedict = GetStopTimesForStopsInTimeWindow(start_sec, end_sec, DepOrArr, triplist, "today", frequencies_dict)
        stoptimedict_yest = GetStopTimesForStopsInTimeWindow(start_sec, end_sec, DepOrArr, triplist_yest, "yesterday", frequencies_dict)
        stoptimedict_tom = GetStopTimesForStopsInTimeWindow(start_sec, end_sec, DepOrArr, triplist_tom, "tomorrow", frequencies_dict)

        # Combine the three dictionaries into one master
        for stop in stoptimedict_yest:
            stoptimedict[stop] = stoptimedict.setdefault(stop, []) + stoptimedict_yest[stop]
        for stop in stoptimedict_tom:
            stoptimedict[stop] = stoptimedict.setdefault(stop, []) + stoptimedict_tom[stop]

    except:
        arcpy.AddError("Error creating dictionary of stops and trips in time window.")
        raise CustomError

    return stoptimedict


def CountTripsOnLines(day, start_sec, end_sec, DepOrArr, Specific=False):
    '''Given a time window, return a dictionary of {line_key: [[trip_id, start_time, end_time]]}'''

    triplist, triplist_yest, triplist_tom = GetTripLists(day, start_sec, end_sec, DepOrArr, Specific)

    try:
        frequencies_dict = MakeFrequenciesDict()

        # Get the stop_times that occur during this time window
        linetimedict = GetLineTimesInTimeWindow(start_sec, end_sec, DepOrArr, triplist, "today", frequencies_dict)
        linetimedict_yest = GetLineTimesInTimeWindow(start_sec, end_sec, DepOrArr, triplist_yest, "yesterday", frequencies_dict)
        linetimedict_tom = GetLineTimesInTimeWindow(start_sec, end_sec, DepOrArr, triplist_tom, "tomorrow", frequencies_dict)

        # Combine the three dictionaries into one master
        for line in linetimedict_yest:
            linetimedict[line] = linetimedict.setdefault(line, []) + linetimedict_yest[line]
        for line in linetimedict_tom:
            linetimedict[line] = linetimedict.setdefault(line, []) + linetimedict_tom[line]

    except:
        arcpy.AddError("Error creating dictionary of lines and trips in time window.")
        raise CustomError

    return linetimedict


def RetrieveStatsForSetOfStops(stoplist, stoptimedict, CalcWaitTime, start_sec, end_sec):
    '''For a set of stops, query the stoptimedict {stop_id: [[trip_id, stop_time]]}
    and return the NumTrips, NumTripsPerHr, NumStopsInRange, and MaxWaitTime for
    that set of stops.'''

    # Number of stops (in range of the given point or polygon being studied)
    NumStopsInRange = len(stoplist)

    # Find the list of unique trips
    triplist = []
    StopTimesAtThisPoint = []
    for stop in stoplist:
        try:
            stoptimelist = stoptimedict[stop]
            for stoptime in stoptimelist:
                trip = stoptime[0]
                triplist.append(trip)
                StopTimesAtThisPoint.append(stoptime[1])
        except KeyError:
            pass
    triplist = list(set(triplist))
    NumTrips = len(triplist)
    NumTripsPerHr = round(float(NumTrips) / ((end_sec - start_sec) / 3600), 2)

    MaxWaitTime = None
    if CalcWaitTime:
        MaxWaitTime = CalculateMaxWaitTime(StopTimesAtThisPoint, start_sec, end_sec)

    return NumTrips, NumTripsPerHr, NumStopsInRange, MaxWaitTime


def RetrieveStatsForLines(linekey, linetimedict, start_sec, end_sec, combine_corridors, triproute_dict=None):
    '''For a set of lines, query the linetimedict {line_key: [[trip_id, start_time, end_time]]}
    and return the NumTrips, NumTripsPerHr, MaxWaitTime, and AvgHeadway for
    that set of lines.'''

    # Find the list of unique trips
    triplist = []
    StartTimesOnThisLine = []
    route_id = None
    if not combine_corridors:
        linekeyparts = linekey.split(" , ")
        linekey = linekeyparts[0] + " , " + linekeyparts[1]
        route_id = linekeyparts[2]
    try:
        linetimelist = linetimedict[linekey]
        for linetime in linetimelist:
            trip = linetime[0]
            if combine_corridors or triproute_dict[trip] == route_id:
                triplist.append(trip)
                StartTimesOnThisLine.append(linetime[1])
    except KeyError:
        pass
    triplist = list(set(triplist))
    NumTrips = len(triplist)
    NumTripsPerHr = round(float(NumTrips) / ((end_sec - start_sec) / 3600), 2)

    MaxWaitTime = CalculateMaxWaitTime(StartTimesOnThisLine, start_sec, end_sec)
    AvgHeadway = CalculateAvgHeadway(StartTimesOnThisLine)

    return NumTrips, NumTripsPerHr, MaxWaitTime, AvgHeadway


def CalculateMaxWaitTime(stoptimelist, start_sec, end_sec):
    '''Calculate the max time in minutes between adjacent stop visits. Set value
    to None if it can't be calculated.'''

    maxWaitTime_toReturn = None

    # Calculate max time between adjacent stop times.
    if len(stoptimelist) > 1:
        # Sort the list of stoptimes
        stoptimelist.sort()
        # Find time from time window start to earliest stop visit
        TimeFromStart = stoptimelist[0] - start_sec
        # and time from latest stop visit to end of time window
        TimeToEnd = end_sec - stoptimelist[-1]
        # and which is largest.
        MaxEdge = max(TimeFromStart, TimeToEnd)
        # Find the maximum difference between adjacent visits
        MaxWaitTime = max(abs(x - y) for (x, y) in zip(stoptimelist[1:], stoptimelist[:-1]))
        # Compare with distance to edge of time window
        if (MaxEdge < MaxWaitTime):
            # Exclude cases where the time to the time window boundaries is
            # > MaxWaitTime because we can't properly determine MaxWaitTime.
           maxWaitTime_toReturn = int(round(float(MaxWaitTime) / 60, 0)) # In minutes

    return maxWaitTime_toReturn


def CalculateAvgHeadway(TimeList, round_to=None):
    '''Find the average amount of time between all trips in a list. Cannot be calculated if there are fewer than 2 trips.'''
    if len(TimeList) > 1:
        headway = int(round(float(sum(abs(x - y) for (x, y) in zip(TimeList[1:], TimeList[:-1]))/(len(TimeList)-1))/60, 0)) # minutes
        if round_to:
            headway = int(round(float(headway) / float(round_to)) * round_to)
        return headway
    else:
        return None


def CreateStopsFeatureClass(stopsfc):
    '''Make an empty feature class for stops and add fields. Returns the output coordinate system used.'''
    stopsfc_path = os.path.dirname(stopsfc)
    stopsfc_name = os.path.basename(stopsfc)

    # If the output location is a feature dataset, we have to match the coordinate system
    desc = arcpy.Describe(stopsfc_path)
    if hasattr(desc, "spatialReference"):
        output_coords = desc.spatialReference
    else:
        output_coords = WGSCoords

    # Create a points feature class for the point pairs.
    StopsLayer = arcpy.management.CreateFeatureclass(stopsfc_path, stopsfc_name, "POINT", spatial_reference=output_coords)
    arcpy.management.AddField(StopsLayer, "stop_id", "TEXT")
    arcpy.management.AddField(StopsLayer, "stop_code", "TEXT", field_length=MaxTextFieldLength)
    arcpy.management.AddField(StopsLayer, "stop_name", "TEXT", field_length=MaxTextFieldLength)
    arcpy.management.AddField(StopsLayer, "stop_desc", "TEXT", field_length=MaxTextFieldLength)
    arcpy.management.AddField(StopsLayer, "zone_id", "TEXT", field_length=MaxTextFieldLength)
    arcpy.management.AddField(StopsLayer, "stop_url", "TEXT", field_length=MaxTextFieldLength)
    if ".shp" in stopsfc_name:
        arcpy.management.AddField(StopsLayer, "loc_type", "TEXT")
        arcpy.management.AddField(StopsLayer, "parent_sta", "TEXT")
    else:
        arcpy.management.AddField(StopsLayer, "location_type", "TEXT")
        arcpy.management.AddField(StopsLayer, "parent_station", "TEXT")

    return output_coords

def GetStopsData(stoplist=None):
    '''Retrieve the data from the stops table for use in populating a feature class.'''
    if stoplist:
        StopTable = []
        for stop_id in stoplist:
            selectstoptablestmt = "SELECT stop_id, stop_code, stop_name, stop_desc, stop_lat, stop_lon, zone_id, stop_url, location_type, parent_station FROM stops WHERE stop_id='%s';" % stop_id
            c.execute(selectstoptablestmt)
            StopInfo = c.fetchall()
            StopTable.append(StopInfo[0])
    else:
        selectstoptablestmt = "SELECT stop_id, stop_code, stop_name, stop_desc, stop_lat, stop_lon, zone_id, stop_url, location_type, parent_station FROM stops;"
        c.execute(selectstoptablestmt)
        StopTable = c.fetchall()
    return StopTable

def MakeStopGeometry(stop_lat, stop_lon, output_coords):
    '''Return a PointGeometry for a stop.'''
    pt = arcpy.Point()
    pt.X = float(stop_lon)
    pt.Y = float(stop_lat)
    # GTFS stop lat/lon is written in WGS1984
    ptGeometry = arcpy.PointGeometry(pt, WGSCoords)
    if output_coords != WGSCoords:  # Change projection to match output location
        ptGeometry = ptGeometry.projectAs(output_coords)
    return ptGeometry

def MakeStopsFeatureClass(stopsfc, stoplist=None):
    '''Make a feature class of GTFS stops from the SQL table. Returns the path
    to the feature class and a list of stop IDs.'''
    # Create the feature class with desired schema
    output_coords = CreateStopsFeatureClass(stopsfc)

    # Get the stop info from the GTFS SQL file
    StopTable = GetStopsData(stoplist)
    possiblenulls = [1, 3, 6, 7, 8, 9]

    # Make a list of stop_ids for use later.
    StopIDList = []
    for stop in StopTable:
        StopIDList.append(stop[0])

    if not ArcVersion:
        DetermineArcVersion()

    # Add the stops table to a feature class.
    stopsfc_path = os.path.dirname(stopsfc)
    stopsfc_name = os.path.basename(stopsfc)
    if ".shp" in stopsfc_name:
        cur3 = arcpy.da.InsertCursor(stopsfc, ["SHAPE@", "stop_id",
                                                    "stop_code", "stop_name", "stop_desc",
                                                    "zone_id", "stop_url", "loc_type",
                                                    "parent_sta"])
    else:
        cur3 = arcpy.da.InsertCursor(stopsfc, ["SHAPE@", "stop_id",
                                                    "stop_code", "stop_name", "stop_desc",
                                                    "zone_id", "stop_url", "location_type",
                                                    "parent_station"])
    # Schema of stops table
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
    for stopitem in StopTable:
        stop = list(stopitem)
        # Truncate text fields to the field length if needed.
        truncate_idx = [1, 2, 3, 6, 7]
        for idx in truncate_idx:
            if stop[idx]:
                stop[idx] = stop[idx][:MaxTextFieldLength]
        ptGeometry = MakeStopGeometry(stop[4], stop[5], output_coords)
        # Shapefile output can't handle null values, so make them empty strings.
        if ".shp" in stopsfc_name:
            for idx in possiblenulls:
                if not stop[idx]:
                    stop[idx] = ""
        cur3.insertRow((ptGeometry, stop[0], stop[1],
                            stop[2], stop[3], stop[6],
                            stop[7], stop[8], stop[9]))
    del cur3

    return stopsfc, StopIDList


def MakeServiceAreasAroundStops(StopsLayer, inNetworkDataset, impedanceAttribute, BufferSize, restrictions, TrimPolys, TrimPolysValue):
    '''Make Service Area polygons around transit stops and join the stop_id
    field to the output polygons. Note: Assume NA license is checked out.'''

    # Name to refer to Service Area layer
    outNALayer_SA = "ServiceAreas"
    # Hard-wired Service Area settings
    ExcludeRestricted = "EXCLUDE"
    TravelFromTo = "TRAVEL_TO"
    PolyType = "DETAILED_POLYS"
    merge = "NO_MERGE"
    NestingType = ""
    LineType = "NO_LINES"
    overlap = ""
    split = ""
    exclude = ""
    accumulate = ""
    uturns = "ALLOW_UTURNS"
    hierarchy = "NO_HIERARCHY"

    if not ArcVersion or not ProductName:
        DetermineArcVersion()

    # SALayer is the NA Layer object returned by getOutput(0)
    # Make the service area layer
    # The "hierarcy" attribute for SA is only available in 10.1.
    # Default is that hierarchy is on, but we don't want it on for
    # pedestrian travel (probably makes little difference).
    try:
        SALayer = arcpy.na.MakeServiceAreaLayer(inNetworkDataset, outNALayer_SA,
                                    impedanceAttribute, TravelFromTo,
                                    BufferSize, PolyType, merge,
                                    NestingType, LineType, overlap,
                                    split, exclude, accumulate, uturns,
                                    restrictions, TrimPolys, TrimPolysValue, "", hierarchy).getOutput(0)
    except:
        errors = arcpy.GetMessages(2).split("\n")
        if errors[0] == "ERROR 030152: Geoprocessing Current Workspace not found.":
            arcpy.AddMessage(CurrentGPWorkspaceError)
        raise CustomError

    # To refer to the SA sublayers, get the sublayer names.  This is essential for localization.
    naSubLayerNames = arcpy.na.GetNAClassNames(SALayer)
    facilities = naSubLayerNames["Facilities"]

    # Add a field for stop_id as a unique identifier for service areas.
    if ProductName == "ArcGISPro":
        arcpy.na.AddFieldToAnalysisLayer(SALayer, facilities, "stop_id", "TEXT", field_length=255)
    else:
        arcpy.na.AddFieldToAnalysisLayer(outNALayer_SA, facilities, "stop_id", "TEXT", field_length=255)

    # Specify the field mappings for the stop_id field.
    fieldMappingSA = arcpy.na.NAClassFieldMappings(SALayer, facilities)
    fieldMappingSA["Name"].mappedFieldName = "stop_id"
    fieldMappingSA["stop_id"].mappedFieldName = "stop_id"

    # Add the GTFS stops as locations for the analysis.
    if ProductName == "ArcGISPro":
        arcpy.na.AddLocations(SALayer, facilities, StopsLayer,
                            fieldMappingSA, "500 meters", "", "", "", "", "", "",
                            ExcludeRestricted)
    else:
        arcpy.na.AddLocations(outNALayer_SA, facilities, StopsLayer,
                            fieldMappingSA, "500 meters", "", "", "", "", "", "",
                            ExcludeRestricted)

    # Solve the service area.
    if ProductName == "ArcGISPro":
        arcpy.na.Solve(SALayer)
    else:
        arcpy.na.Solve(outNALayer_SA)

    # Make layer objects for each sublayer we care about.
    if ProductName == 'ArcGISPro':
        subLayerDict = dict((lyr.name, lyr) for lyr in SALayer.listLayers())
        subLayers = {}
        for subL in naSubLayerNames:
            subLayers[subL] = subLayerDict[naSubLayerNames[subL]]
    else:
        subLayers = dict((lyr.datasetName, lyr) for lyr in arcpy.mapping.ListLayers(SALayer)[1:])
    facilitiesSubLayer = subLayers["Facilities"]
    polygonsSubLayer = subLayers["SAPolygons"]

    # Get the OID fields, just to be thorough
    desc1 = arcpy.Describe(facilitiesSubLayer)
    facilities_OID = desc1.OIDFieldName

    # Source FC names are not prepended to field names.
    arcpy.env.qualifiedFieldNames = False

    # Join polygons layer with input facilities to port over the stop_id
    arcpy.management.JoinField(polygonsSubLayer, "FacilityID", facilitiesSubLayer,
                            facilities_OID, ["stop_id"])

    return polygonsSubLayer


def import_AGOLservice(service_name, username="", password="", ags_connection_file="", token="", referer=""):
    '''Imports the AGOL service toolbox based on the specified credentials and returns the toolbox object'''

    #Construct the connection string to import the service toolbox
    if username and password:
        tbx = "http://logistics.arcgis.com/arcgis/services;{0};{1};{2}".format(service_name, username, password)
    elif ags_connection_file:
        tbx = "{0};{1}".format(ags_connection_file, service_name)
    elif token and referer:
        tbx = "http://logistics.arcgis.com/arcgis/services;{0};token={1};{2}".format(service_name, token, referer)
    else:
        arcpy.AddError("No valid option specified to connect to the {0} service".format(service_name))
        raise CustomError

    #Import the service toolbox
    tbx_alias = "agol"
    arcpy.ImportToolbox(tbx, tbx_alias)

    return getattr(arcpy, tbx_alias)


def ConnectToSQLDatabase(SQLDbase):
    '''Connect to a SQL database'''
    global c, conn
    conn = sqlite3.connect(SQLDbase)
    c = conn.cursor()


def GetGTFSTableNames():
    '''Return a list of SQL database table names'''
    ctn = conn.cursor()
    GetTblNamesStmt = "SELECT name FROM sqlite_master WHERE type='table';"
    ctn.execute(GetTblNamesStmt)
    tblnamelist = [name[0] for name in ctn]
    return tblnamelist


def parse_time(HMS):
    '''Convert HH:MM:SS to seconds since midnight, for comparison purposes.'''
    H, M, S = HMS.split(':')
    seconds = (float(H) * 3600) + (float(M) * 60) + float(S)
    return seconds


def DetermineArcVersion():
    '''Figure out what version of ArcGIS the user is running'''
    ArcVersionInfo = arcpy.GetInstallInfo("desktop")
    global ArcVersion, ProductName
    ProductName = ArcVersionInfo['ProductName']
    ArcVersion = ArcVersionInfo['Version']

def CheckArcVersion(min_version_pro=None, min_version_10x=None):
    DetermineArcVersion()
    # Lists must stay in product release order
    # They do not need to have new product numbers added unless a tool requires a higher version
    versions_pro = ["1.0", "1.1", "1.1.1", "1.2"]
    versions_10x = ["10.1", "10.2", "10.2.1", "10.2.2", "10.3", "10.3.1", "10.4"]

    def check_version(min_version, all_versions):
        if min_version not in all_versions:
            arcpy.AddError("Invalid minimum software version number: %s" % str(min_version))
            raise CustomError
        version_idx = all_versions.index(min_version)
        if ArcVersion in all_versions[:version_idx]:
            # Fail out if the current software version is in the list somewhere earlier than the minimum version
            arcpy.AddError("The BetterBusBuffers toolbox does not work in versions of %s prior to %s.  \
You have version %s.  Please check the user's guide for more information on software version compatibility." % (ProductName, min_version, ArcVersion))
            raise CustomError

    if ProductName == "ArcGISPro" and min_version_pro:
        check_version(min_version_pro, versions_pro)
    else:
        if min_version_10x:
            check_version(min_version_10x, versions_10x)

def CheckArcInfoLicense():
    ArcLicense = arcpy.ProductInfo()
    if ArcLicense != "ArcInfo":
        arcpy.AddError("To run this tool, you must have the Desktop \
Advanced (ArcInfo) license.  Your license type is: %s." % ArcLicense)
        raise CustomError


def CheckOutNALicense():
    if arcpy.CheckExtension("Network") == "Available":
        arcpy.CheckOutExtension("Network")
    else:
        arcpy.AddError("You must have a Network Analyst license to use this tool.")
        raise CustomError


def CheckWorkspace():
    '''Check if arcpy.env.workspace is set to a file geodatabase. This is essential for Pro when creating NA layers.'''
    if ProductName == "ArcGISPro":
        currentworkspace = arcpy.env.workspace
        if not currentworkspace:
            arcpy.AddError(CurrentGPWorkspaceError)
            raise CustomError
        else:
            workspacedesc = arcpy.Describe(arcpy.env.workspace)
            if not workspacedesc.workspaceFactoryProgID.startswith('esriDataSourcesGDB.FileGDBWorkspaceFactory'): # file gdb
                arcpy.AddError(CurrentGPWorkspaceError)
                raise CustomError


def CleanUpTrimSettings(TrimSettings):
    if TrimSettings and TrimSettings != -1.0:
        TrimPolys = "TRIM_POLYS"
        TrimPolysValue = str(TrimSettings) + " meters"
    else:
        TrimPolys = "NO_TRIM_POLYS"
        TrimPolysValue = ""
    return TrimPolys, TrimPolysValue

def CleanUpImpedance(imp):
    '''Extract impedance attribute and units from text string'''
    # The input is formatted as "[Impedance] (Units: [Units])"
    return imp.split(" (")[0]

def CleanUpDepOrArr(DepOrArrChoice):
    if DepOrArrChoice == "Arrivals":
        return "arrival_time"
    elif DepOrArrChoice == "Departures":
        return "departure_time"
    return None

def CheckSpecificDate(day):
    '''Is the chosen day a specific date or a generic weekday?'''
    # Note: Datetime format check is in tool validation code
    if day in days: #Generic weekday
        return False, day
    else: #Specific date
        return True, datetime.datetime.strptime(day, '%Y%m%d')

def ConvertTimeWindowToSeconds(start_time, end_time):
    # Lower end of time window (HH:MM in 24-hour time)
    # Default start time is midnight if they leave it blank.
    if start_time == "":
        start_time = "00:00"
    # Convert to seconds
    start_sec = parse_time(start_time + ":00")
    # Upper end of time window (HH:MM in 24-hour time)
    # Default end time is 11:59pm if they leave it blank.
    if end_time == "":
        end_time = "23:59"
    # Convert to seconds
    end_sec = parse_time(end_time + ":00")
    return start_sec, end_sec

def HandleOIDUniqueID(inPointsLayer, inLocUniqueID):
    '''If ObjectID was selected as the unique ID, copy the values to a new field
    so they don't get messed up when copying the table.'''
    pointsOID = arcpy.Describe(inPointsLayer).OIDFieldName
    if inLocUniqueID.lower() == pointsOID.lower():
        try:
            inLocUniqueID = "BBBUID"
            arcpy.AddMessage("You have selected your input features' ObjectID field as the unique ID to use for this analysis. \
In order to use this field, we have to transfer the ObjectID values to a new field in your input data called '%s' because ObjectID values \
may change when the input data is copied to the output. Adding the '%s' field now, and calculating the values to be the same as the current \
ObjectID values..." % (inLocUniqueID, inLocUniqueID))
            arcpy.management.AddField(inPointsLayer, inLocUniqueID, "LONG")
            arcpy.management.CalculateField(inPointsLayer, inLocUniqueID, "!" + pointsOID + "!", "PYTHON_9.3")
        except:
            arcpy.AddError("Unable to add or calculate new unique ID field. Please fix your data or choose a different unique ID field.")
            raise CustomError
    return inLocUniqueID


class CustomError(Exception):
    pass