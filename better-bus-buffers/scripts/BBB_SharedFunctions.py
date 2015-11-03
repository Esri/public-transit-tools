############################################################################
## Tool name: BetterBusBuffers
## Shared Functions
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 3 November 2015
############################################################################
''' This file contains shared functions used by various BetterBusBuffers tools.'''
################################################################################
'''Copyright 2015 Esri
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

import sqlite3, os, operator
import arcpy

# sqlite cursor - must be set from the script calling the functions explicitly
# or using the ConnectToSQLDatabase() function
c = None

# Version of ArcGIS they are running
ArcVersion = None
ProductName = None

# Whether or not to consider trips from yesterday or tomorrow
ConsiderYesterday = None
ConsiderTomorrow = None

# If the dataset uses a frequencies table, store the info in a global dictionary
frequencies_dict_initialized = False
frequencies_dict = {}

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


def MakeServiceIDList(day):
    '''Find the service ids for the selected day of the week and check for
    non-overlapping date ranges.'''

    # Find the service_ids that describe trips on our selected days of the week.
    serviceidlist = []
    startdatedict = {}
    enddatedict = {}
    serviceidfetch = '''
        SELECT service_id, start_date, end_date FROM calendar
        WHERE %s == "1"
        ;''' % day.lower()
    c.execute(serviceidfetch)
    ids = c.fetchall()
    for id in ids:
        # Add to the list of service_ids
        serviceidlist.append(id[0])
        startdatedict[id[0]] = id[1]
        enddatedict[id[0]] = id[2]

    # Check for non-overlapping date ranges to prevent double-counting.
    nonoverlappingsids = []
    for sid in serviceidlist:
        for eid in serviceidlist:
            if startdatedict[sid] > enddatedict[eid]:
                nonoverlappingsids.append((sid, eid))

    return serviceidlist, nonoverlappingsids


def GetServiceIDListsAndNonOverlaps(DayOfWeek, start_sec, end_sec, DepOrArr):
    ''' Get the lists of service ids for today, yesterday, and tomorrow, and
    combine non-overlapping date range list for all days'''

    # Determine if it's early enough in the day that we need to consider trips
    # still running from yesterday - these set global variables
    if not ConsiderYesterday:
        ShouldConsiderYesterday(start_sec, DepOrArr)
    # If our time window spans midnight, we need to check tomorrow's trips, too.
    if not ConsiderTomorrow:
        ShouldConsiderTomorrow(end_sec)
    # And what weekdays are yesterday and tomorrow?
    Yesterday = days[(days.index(DayOfWeek) - 1)%7] # %7 wraps it around
    Tomorrow = days[(days.index(DayOfWeek) + 1)%7] # %7 wraps it around

    try:
        # Get the service ids applicable for the current day of the week
        # Furthermore, get list of service ids with non-overlapping date ranges.
        serviceidlist, nonoverlappingsids = MakeServiceIDList(DayOfWeek)

        # If we need to consider yesterday's trips, get the service ids.
        serviceidlist_yest = []
        nonoverlappingsids_yest = []
        if ConsiderYesterday:
            serviceidlist_yest, nonoverlappingsids_yest = MakeServiceIDList(Yesterday)

        # If we need to consider tomorrow's trips, get the service ids.
        serviceidlist_tom = []
        nonoverlappingsids_tom = []
        if ConsiderTomorrow:
            serviceidlist_tom, nonoverlappingsids_tom = MakeServiceIDList(Tomorrow)
    except:
        arcpy.AddError("Error getting list of service_ids for time window.")
        raise

    # Make sure there is service on the day we're analyzing.
    if not serviceidlist and not serviceidlist_yest and not serviceidlist_tom:
        arcpy.AddWarning("There is no transit service during this time window. \
No service_ids cover the weekday you have selected.")

    # Combine lists of non-overlapping date range pairs of service ids
    nonoverlappingsids += nonoverlappingsids_yest
    nonoverlappingsids += nonoverlappingsids_tom
    nonoverlappingsids = list(set(nonoverlappingsids))

    return serviceidlist, serviceidlist_yest, serviceidlist_tom, nonoverlappingsids


def MakeTripList(serviceidlist):
    '''Select the trips with the service_ids of interest'''

    triplist = []
    for service_id in serviceidlist:
        tripsfetch = '''
            SELECT DISTINCT trip_id FROM trips
            WHERE service_id == ?
            ;'''
        c.execute(tripsfetch, (service_id,))
        selectedtrips = c.fetchall()
        for tr in selectedtrips:
            triplist.append(tr[0])
    # There shouldn't be any duplicates, but check anyway.
    triplist = list(set(triplist))

    return triplist


def MakeFrequenciesDict():
    '''Put the frequencies.txt information into a dictionary'''
    global frequencies_dict_initialized, frequencies_dict

    # Check if the dataset uses frequency. If not, no need to do more.
    tblnamelist = GetGTFSTableNames()
    if not "frequencies" in tblnamelist:
        frequencies_dict_initialized = True
        return

    # Fill the dictionary
    frequencies_dict = {}
    freqfetch = '''
        SELECT trip_id, start_time, end_time, headway_secs
        FROM frequencies
        ;'''
    c.execute(freqfetch)
    freqlist = c.fetchall()
    for freq in freqlist:
        trip_id = freq[0]
        trip_data = [freq[1], freq[2], freq[3]]
        # {trip_id: [start_time, end_time, headway_secs]}
        frequencies_dict.setdefault(trip_id, []).append(trip_data)
    frequencies_dict_initialized = True
    return


def GetStopTimesForStopsInTimeWindow(start, end, DepOrArr, triplist, day):
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

    # If we haven't already, initialize the frequencies dictionary so we can
    # find trips that use the frequencies table instead of stop_times and
    # treat them accordingly.
    if not frequencies_dict_initialized:
        MakeFrequenciesDict()

    stoptimedict = {} # {stop_id: [[trip_id, stop_time]]}
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
            c.execute(stopsfetch, (trip,))
            StopTimes = c.fetchall()
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
            c.execute(stopsfetch, (trip, start, end,))
            StopTimes = c.fetchall()

            for stoptime in StopTimes:
                stop_id = stoptime[0]
                stop_time = int(stoptime[1])
                if day == "yesterday":
                    stop_time = stop_time - SecsInDay
                elif day == "tomorrow":
                    stop_time += SecsInDay
                stoptimedict.setdefault(stop_id, []).append([trip, stop_time])

    return stoptimedict


def ShouldConsiderYesterday(start_sec, DepOrArr):
    '''Determine if it's early enough in the day that we need to consider trips
    still running from the day before. Do this by finding the largest stop_time
    in the GTFS file and comparing it to the user's start time.'''
    global ConsiderYesterday
    ConsiderYesterday = 0
    # Select the largest stop time
    MaxTimeFetch = '''
        SELECT MAX(%s) FROM stop_times
        ;''' % (DepOrArr)
    c.execute(MaxTimeFetch)
    MaxTime = c.fetchone()[0]
    if start_sec < MaxTime - SecsInDay:
        ConsiderYesterday = 1


def ShouldConsiderTomorrow(end_sec):
    '''Return whether a time is greater than midnight.'''
    global ConsiderTomorrow
    ConsiderTomorrow = 0
    if end_sec > SecsInDay:
        ConsiderTomorrow = 1


def CountTripsAtStops(DayOfWeek, start_sec, end_sec, DepOrArr):
    '''Given a time window, return a dictionary of
    {stop_id: [[trip_id, stop_time]]}'''

    serviceidlist, serviceidlist_yest, serviceidlist_tom, nonoverlappingsids = \
        GetServiceIDListsAndNonOverlaps(DayOfWeek, start_sec, end_sec, DepOrArr)

    # If there are nonoverlapping date ranges in our data, raise a warning.
    if nonoverlappingsids:
        overlapwarning = "Warning! Your calendar.txt file(s) contain(s) \
non-overlapping date ranges. Your output might be double counting the number \
of trips available. Please check the date ranges in your calendar.txt file(s). \
See the User's Guide for further assistance.  Date ranges do not overlap in the \
following pairs of service_ids used in \
this analysis: " + str(nonoverlappingsids)
        arcpy.AddWarning(overlapwarning)

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
        raise

    # Make sure there is service on the day we're analyzing.
    if not triplist and not triplist_yest and not triplist_tom:
        arcpy.AddWarning("There is no transit service during this time window. \
No trips are running.")

    try:
        # Get the stop_times that occur during this time window
        stoptimedict = GetStopTimesForStopsInTimeWindow(start_sec, end_sec, DepOrArr, triplist, "today")
        stoptimedict_yest = GetStopTimesForStopsInTimeWindow(start_sec, end_sec, DepOrArr, triplist, "yesterday")
        stoptimedict_tom = GetStopTimesForStopsInTimeWindow(start_sec, end_sec, DepOrArr, triplist, "tomorrow")

        # Combine the three dictionaries into one master
        for stop in stoptimedict_yest:
            stoptimedict[stop] = stoptimedict.setdefault(stop, []) + stoptimedict_yest[stop]
        for stop in stoptimedict_tom:
            stoptimedict[stop] = stoptimedict.setdefault(stop, []) + stoptimedict_tom[stop]

    except:
        arcpy.AddError("Error creating dictionary of stops and trips in time window.")
        raise

    return stoptimedict


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
    if CalcWaitTime == "true":
        MaxWaitTime = CalculateMaxWaitTime(StopTimesAtThisPoint, start_sec, end_sec)

    return NumTrips, NumTripsPerHr, NumStopsInRange, MaxWaitTime


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


def MakeStopsFeatureClass(stopsfc, stoplist=None):
    '''Make a feature class of GTFS stops from the SQL table. Returns the path
    to the feature class and a list of stop IDs.'''

    stopsfc_path = os.path.dirname(stopsfc)
    stopsfc_name = os.path.basename(stopsfc)

    # Create a points feature class for the point pairs.
    StopsLayer = arcpy.management.CreateFeatureclass(stopsfc_path, stopsfc_name, "POINT", spatial_reference=WGSCoords)
    arcpy.management.AddField(StopsLayer, "stop_id", "TEXT")
    arcpy.management.AddField(StopsLayer, "stop_code", "TEXT")
    arcpy.management.AddField(StopsLayer, "stop_name", "TEXT")
    arcpy.management.AddField(StopsLayer, "stop_desc", "TEXT")
    arcpy.management.AddField(StopsLayer, "zone_id", "TEXT")
    arcpy.management.AddField(StopsLayer, "stop_url", "TEXT")
    if ".shp" in stopsfc_name:
        arcpy.management.AddField(StopsLayer, "loc_type", "TEXT")
        arcpy.management.AddField(StopsLayer, "parent_sta", "TEXT")
    else:
        arcpy.management.AddField(StopsLayer, "location_type", "TEXT")
        arcpy.management.AddField(StopsLayer, "parent_station", "TEXT")

    # Get the stop info from the GTFS SQL file
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
    possiblenulls = [1, 3, 4, 6, 9, 10]

    # Make a list of stop_ids for use later.
    StopIDList = []
    for stop in StopTable:
        StopIDList.append(stop[0])

    if not ArcVersion:
        DetermineArcVersion()

    # Add the stops table to a feature class.
    if ArcVersion == "10.0":
        cur3 = arcpy.InsertCursor(StopsLayer)
        for stopitem in StopTable:
            stop = list(stopitem)
            # Shapefile output can't handle null values, so make them empty strings.
            if ".shp" in stopsfc_name:
                for idx in possiblenulls:
                    if not stop[idx]:
                        stop[idx] = ""
            row = cur3.newRow()
            pt = arcpy.Point()
            pt.X = float(stop[7])
            pt.Y = float(stop[2])
            row.shape = pt
            row.setValue("stop_id", stop[5])
            row.setValue("stop_code", stop[4])
            row.setValue("stop_name", stop[8])
            row.setValue("stop_desc", stop[6])
            row.setValue("zone_id", stop[10])
            row.setValue("stop_url", stop[9])
            if ".shp" in stopsfc_name:
                row.setValue("loc_type", stop[3])
                row.setValue("parent_sta", stop[1])
            else:
                row.setValue("location_type", stop[3])
                row.setValue("parent_station", stop[1])
            cur3.insertRow(row)
        del row

    else:
        # For everything 10.1 and forward
        if ".shp" in stopsfc_name:
            cur3 = arcpy.da.InsertCursor(StopsLayer, ["SHAPE@X", "SHAPE@Y", "stop_id",
                                                     "stop_code", "stop_name", "stop_desc",
                                                     "zone_id", "stop_url", "loc_type",
                                                     "parent_sta"])
        else:
            cur3 = arcpy.da.InsertCursor(StopsLayer, ["SHAPE@X", "SHAPE@Y", "stop_id",
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
            # Shapefile output can't handle null values, so make them empty strings.
            if ".shp" in stopsfc_name:
                for idx in possiblenulls:
                    if not stop[idx]:
                        stop[idx] = ""
            cur3.insertRow((float(stop[5]), float(stop[4]), stop[0], stop[1],
                             stop[2], stop[3], stop[6], stop[7], stop[8], stop[9]))
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
    if ArcVersion == "10.0":
        # Make the service area layer
        # Can't use the hierarchy attribute in 10.0.
        SALayer = arcpy.na.MakeServiceAreaLayer(inNetworkDataset, outNALayer_SA,
                                    impedanceAttribute, TravelFromTo,
                                    BufferSize, PolyType, merge,
                                    NestingType, LineType, overlap,
                                    split, exclude, accumulate, uturns,
                                    restrictions, TrimPolys, TrimPolysValue).getOutput(0)
    else:
        # For everything 10.1 and forward
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
                print(CurrentGPWorkspaceError)
            raise

    # To refer to the SA sublayers, get the sublayer names.  This is essential for localization.
    if ArcVersion == "10.0":
        naSubLayerNames = dict((sublayer.datasetName, sublayer.name) for sublayer in  arcpy.mapping.ListLayers(SALayer)[1:])
    else:
        naSubLayerNames = arcpy.na.GetNAClassNames(SALayer)
    facilities = naSubLayerNames["Facilities"]

    # Add a field for stop_id as a unique identifier for service areas.
    arcpy.na.AddFieldToAnalysisLayer(SALayer, facilities,
                                    "stop_id", "TEXT")

    # Specify the field mappings for the stop_id field.
    if ArcVersion == "10.0":
        fieldMappingSA = "Name stop_id #; stop_id stop_id #"
    else:
        fieldMappingSA = arcpy.na.NAClassFieldMappings(SALayer, facilities)
        fieldMappingSA["Name"].mappedFieldName = "stop_id"
        fieldMappingSA["stop_id"].mappedFieldName = "stop_id"

    # Add the GTFS stops as locations for the analysis.
    arcpy.na.AddLocations(SALayer, facilities, StopsLayer,
                            fieldMappingSA, "50 meters", "", "", "", "", "", "",
                            ExcludeRestricted)

    # Solve the service area.
    arcpy.na.Solve(SALayer)

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


def ConnectToSQLDatabase(SQLDbase):
    '''Connect to a SQL database'''
    conn = sqlite3.connect(SQLDbase)
    global c
    c = conn.cursor()


def GetGTFSTableNames():
    '''Return a list of SQL database table names'''
    GetTblNamesStmt = "SELECT name FROM sqlite_master WHERE type='table';"
    c.execute(GetTblNamesStmt)
    tblnames = c.fetchall()
    tblnamelist = []
    for name in tblnames:
        tblnamelist.append(name[0])
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

def CheckAndSetWorkspace(workspace):
    '''Set arcpy.env.workspace if it's not already set to a file geodatabase. This is essential for Pro when creating NA layers.'''
    currentworkspace = arcpy.env.workspace
    if currentworkspace:
        desc = arcpy.Describe(currentworkspace)
        if desc.workspaceFactoryProgID != "esriDataSourcesGDB.FileGDBWorkspaceFactory.1": #File gdb
            arcpy.env.workspace = workspace


class CustomError(Exception):
    pass