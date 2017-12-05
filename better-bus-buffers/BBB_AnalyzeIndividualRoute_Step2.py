############################################################################
## Tool name: BetterBusBuffers - Count Trips for Individual Route
## Step 2: Count Trips for Route
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 4 December 2017
############################################################################
'''BetterBusBuffers - Count Trips for Individual Route - Step 2: Count Trips for Route

BetterBusBuffers provides a quantitative measure of access to public transit
in your city by counting the transit trip frequency at various locations.

The Count Trips for Individual Route tool creates service area
buffers around all transit stops used by a particular route in the transit
system.  For each resulting area, the tool counts the number of transit trips
available during a time window.  The tool also calculates the number of trips
per hour, the maximum time between subsequent trips, and the average headway.

Step 2: Count Trips for Route uses the template feature class created in Step
1 and counts the trips in a specific time window.
'''
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

import os, sqlite3
import arcpy
import BBB_SharedFunctions


#===== Main code =====
def runTool(FCs, SQLDbase, dayString, start_time, end_time, DepOrArrChoice):

    def RetrieveStatsForStop(stop_id, rtdirtuple):
        '''For a given stop, query the stoptimedict {stop_id: [[trip_id, stop_time]]}
        and return the NumTrips, NumTripsPerHr, MaxWaitTime, and AvgHeadway given a
        specific route_id and direction'''

        try:
            stoptimedict = stoptimedict_rtdirpair[rtdirtuple]
        except KeyError:
            # We will get a KeyError if there were no trips found for the route/direction
            # pair, which usually happens if the wrong SQL database was selected.
            stoptimedict = {}

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
        NumTripsPerHr = float(NumTrips) / TimeWindowLength

        # Get the max wait time and the average headway
        MaxWaitTime = BBB_SharedFunctions.CalculateMaxWaitTime(StopTimesAtThisPoint, start_sec, end_sec)
        AvgHeadway = BBB_SharedFunctions.CalculateAvgHeadway(StopTimesAtThisPoint)

        return NumTrips, NumTripsPerHr, MaxWaitTime, AvgHeadway

    try:
        # ------ Get input parameters and set things up. -----
        try:
            OverwriteOutput = arcpy.env.overwriteOutput # Get the orignal value so we can reset it.
            arcpy.env.overwriteOutput = True

            BBB_SharedFunctions.CheckArcVersion(min_version_pro="1.2")

            # Stops and Polygons from Step 1 (any number and route combo)
            FCList = FCs.split(";")
            # Remove single quotes ArcGIS puts in if there are spaces in the filename.
            for d in FCList:
                if d[0] == "'" and d[-1] == "'":
                    loc = FCList.index(d)
                    FCList[loc] = d[1:-1]

            # Get list of field names from the input data and check that the required ones are there
            FieldNames = {}
            RequiredFields = ["stop_id", "route_id", "direction_id"]
            for FC in FCList:
                Fields = arcpy.ListFields(FC)
                FieldNames[FC] = [f.name for f in Fields]
                for field in RequiredFields:
                    if not field in FieldNames[FC]:
                        arcpy.AddError("Feature class %s does not have the required \
fields %s. Please choose a valid feature class." % (FC, str(RequiredFields)))
                        raise BBB_SharedFunctions.CustomError

            # SQL database of preprocessed GTFS from Step 1
            conn = BBB_SharedFunctions.conn = sqlite3.connect(SQLDbase)
            c = BBB_SharedFunctions.c = conn.cursor()

            Specific, day = BBB_SharedFunctions.CheckSpecificDate(dayString)
            # For field names in the output file
            if Specific:
                dayshort = BBB_SharedFunctions.days[day.weekday()][0:3] 
            else:
                dayshort = dayString[0:3]
            
            if start_time == "":
                start_time = "00:00"
            start_time_pretty = start_time.replace(":", "") # For field names in the output file
            if end_time == "":
                end_time = "23:59"
            end_time_pretty = end_time.replace(":", "") # For field names in the output file
            start_sec, end_sec = BBB_SharedFunctions.ConvertTimeWindowToSeconds(start_time, end_time)
            TimeWindowLength = (end_sec - start_sec) / 3600

            # Does the user want to count arrivals or departures at the stops?
            DepOrArr = BBB_SharedFunctions.CleanUpDepOrArr(DepOrArrChoice)

        except:
            arcpy.AddError("Error getting inputs.")
            raise


        # ----- Get list of route_ids and direction_ids to analyze from input files -----
        try:
            # We just check the first line in each file for this information.
            FC_route_dir_dict = {} # {FC: [route_id, direction_id]}
            route_dir_list = [] # [[route_id, direction_id], ...]
            for FC in FCList:
                with arcpy.da.SearchCursor(FC, ["route_id", "direction_id"]) as cur:
                    rt_dir = cur.next()
                route_dir_pair = [rt_dir[0], rt_dir[1]]
                FC_route_dir_dict[FC] = route_dir_pair
                if not route_dir_pair in route_dir_list:
                    route_dir_list.append(route_dir_pair)

        except:
            arcpy.AddError("Error getting route_id and direction_id values from input feature classes.")
            raise


        # ----- Get trips associated with route and direction -----

        try:
            arcpy.AddMessage("Getting list of trips...")

            # Get the service_ids serving the correct days
            serviceidlist, serviceidlist_yest, serviceidlist_tom = \
                BBB_SharedFunctions.GetServiceIDListsAndNonOverlaps(day, start_sec, end_sec, DepOrArr, Specific)

            trip_route_dict = {} #{(route_id, direction_id): [trip_id, trip_id,..]}
            trip_route_dict_yest = {}
            trip_route_dict_tom = {}
            for rtpair in route_dir_list:
                key = tuple(rtpair)
                route_id = rtpair[0]
                direction_id = rtpair[1]

                # Get list of trips
                # Ignore direction if this route doesn't have a direction
                if direction_id:
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
                    if triproute[1] in serviceidlist:
                        trip_route_dict.setdefault(key, []).append(triproute[0])
                    if triproute[1] in serviceidlist_tom:
                        trip_route_dict_tom.setdefault(key, []).append(triproute[0])
                    if triproute[1] in serviceidlist_yest:
                        trip_route_dict_yest.setdefault(key, []).append(triproute[0])

                if not trip_route_dict and not trip_route_dict_tom and not trip_route_dict_yest:
                    arcpy.AddWarning("There is no service for route %s in direction %s \
on %s during the time window you selected. Output fields will be generated, but \
the values will be 0 or <Null>." % (route_id, str(direction_id), str(day)))

        except:
            arcpy.AddError("Error getting trips associated with route.")
            raise


        #----- Query the GTFS data to count the trips at each stop -----
        try:
            arcpy.AddMessage("Calculating the number of transit trips available during the time window...")

            frequencies_dict = BBB_SharedFunctions.MakeFrequenciesDict()

            stoptimedict_rtdirpair = {}
            for rtdirpair in list(set([rt for rt in list(trip_route_dict.keys()) + list(trip_route_dict_yest.keys()) + list(trip_route_dict_tom.keys())])):

                # Get the stop_times that occur during this time window
                stoptimedict = {}
                stoptimedict_yest = {}
                stoptimedict_tom = {}
                try:
                    triplist = trip_route_dict[rtdirpair]
                    stoptimedict = BBB_SharedFunctions.GetStopTimesForStopsInTimeWindow(start_sec, end_sec, DepOrArr, triplist, "today", frequencies_dict)
                except KeyError: # No trips
                    pass
                try:
                    triplist_yest = trip_route_dict_yest[rtdirpair]
                    stoptimedict_yest = BBB_SharedFunctions.GetStopTimesForStopsInTimeWindow(start_sec, end_sec, DepOrArr, triplist_yest, "yesterday", frequencies_dict)
                except KeyError: # No trips
                    pass
                try:
                    triplist_tom = trip_route_dict_tom[rtdirpair]
                    stoptimedict_tom = BBB_SharedFunctions.GetStopTimesForStopsInTimeWindow(start_sec, end_sec, DepOrArr, triplist_tom, "tomorrow", frequencies_dict)
                except KeyError: # No trips
                    pass

                # Combine the three dictionaries into one master
                for stop in stoptimedict_yest:
                    stoptimedict[stop] = stoptimedict.setdefault(stop, []) + stoptimedict_yest[stop]
                for stop in stoptimedict_tom:
                    stoptimedict[stop] = stoptimedict.setdefault(stop, []) + stoptimedict_tom[stop]

                stoptimedict_rtdirpair[rtdirpair] = stoptimedict

                # Add a warning if there is no service.
                if not stoptimedict:
                    arcpy.AddWarning("There is no service for route %s in direction %s \
on %s during the time window you selected. Output fields will be generated, but \
the values will be 0 or <Null>." % (rtdirpair[0], str(rtdirpair[1]), dayString))

        except:
            arcpy.AddError("Error counting arrivals or departures at stop during time window.")
            raise


        #----- Write to output -----

        arcpy.AddMessage("Writing output...")

        try:
            # Prepare the fields we're going to add to the feature classes
            ending = "_" + dayshort + "_" + start_time_pretty + "_" + end_time_pretty
            fields_to_fill = ["NumTrips" + ending, "NumTripsPerHr" + ending, "MaxWaitTime" + ending, "AvgHeadway" + ending]
            fields_to_read = ["stop_id", "route_id", "direction_id"] + fields_to_fill
            field_type_dict = {"NumTrips" + ending: "Short", "NumTripsPerHr" + ending: "Double", "MaxWaitTime" + ending: "Short", "AvgHeadway" + ending: "Short"}

            for FC in FCList:
                # We probably need to add new fields for our calculations, but if the field
                # is already there, don't add it because we'll overwrite it.
                for field in fields_to_fill:
                    if field not in FieldNames[FC]:
                        arcpy.management.AddField(FC, field, field_type_dict[field])
                with arcpy.da.UpdateCursor(FC, fields_to_read) as cur2:
                    for row in cur2:
                        rtpairtuple = (row[1], row[2]) # (route_id, direction_id)
                        stop = row[0]
                        NumTrips, NumTripsPerHr, MaxWaitTime, AvgHeadway = RetrieveStatsForStop(stop, rtpairtuple)
                        row[3] = NumTrips
                        row[4] = NumTripsPerHr
                        row[5] = MaxWaitTime
                        row[6] = AvgHeadway
                        cur2.updateRow(row)

        except:
            arcpy.AddError("Error writing output to feature class(es).")
            raise

        arcpy.AddMessage("Finished!")
        arcpy.AddMessage("Calculated trip counts, frequency, max wait time, and \
headway were written to the following fields in your input feature class(es):")
        for field in fields_to_fill:
            arcpy.AddMessage("- " + field)

        # Tell the tool that this is output. This will add the output to the map.
        arcpy.SetParameterAsText(6, FCs)

    except BBB_SharedFunctions.CustomError:
        arcpy.AddError("Failed to calculate transit statistics for this route and time window.")
        pass

    except:
        arcpy.AddError("Failed to calculate transit statistics for this route and time window.")
        raise

    finally:
        arcpy.env.overwriteOutput = OverwriteOutput
