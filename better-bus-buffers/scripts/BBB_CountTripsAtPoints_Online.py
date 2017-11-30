############################################################################
## Tool name: BetterBusBuffers
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 27 July 2016
############################################################################
''' BetterBusBuffers - Count Trips at Points

BetterBusBuffers provides a quantitative measure of access to public transit
in your city by counting the transit trip frequency at various locations.

The Count Trips at Points tool takes a set of input points, finds the transit stops
reachable within a user-selected buffer distance, and counts the number of
transit trips that pass those stops during the time window selected. The tool
also calculates the number of trips per hour, the maximum time between
subsequent trips, and the number of stops within range of the input point.

This version of the tool uses the ArcGIS Online Origin Destionation cost matrix
service.
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

import os, time, math, json, math
import arcpy
import BBB_SharedFunctions


def runOD(Points, Stops):
    # Call the OD Cost Matrix service for this set of chunks
    result = ODservice.GenerateOriginDestinationCostMatrix(Points, Stops, TravelMode, Distance_Units=BufferUnits, Cutoff=BufferSize,
                                                    Origin_Destination_Line_Shape=PathShape)

    # Check the status of the result object every 0.5 seconds 
    # until it has a value of 4(succeeded) or greater 
    while result.status < 4:
        time.sleep(0.5)
    
    # Print any warning or error messages returned from the tool
    result_severity = result.maxSeverity
    if result_severity == 2:
        errors = result.getMessages(2)
        if "No solution found." in errors:
            # No destinations were found for the origins, which probably just means they were too far away.
            pass
        else:
            arcpy.AddError("An error occured when running the tool")
            arcpy.AddError(result.getMessages(2))
            raise BBB_SharedFunctions.CustomError
    elif result_severity == 1:
        arcpy.AddWarning("Warnings were returned when running the tool")
        arcpy.AddWarning(result.getMessages(1))
        
    # Get the resulting OD Lines and store the stops that are reachable from points.
    if result_severity != 2:
        linesSubLayer = result.getOutput(1)
        if ArcVersion == "10.0":
            with arcpy.SearchCursor(linesSubLayer, "", "", "OriginOID; DestinationOID") as ODCursor:
                for row in ODCursor:
                    UID = pointsOIDdict[row.getValue("OriginOID")]
                    SID = stopOIDdict[row.getValue("DestinationOID")]
                    PointsAndStops.setdefault(str(UID), []).append(str(SID))
        else:
            with arcpy.da.SearchCursor(linesSubLayer, ["OriginOID", "DestinationOID"]) as ODCursor:
                for row in ODCursor:
                    UID = pointsOIDdict[row[0]]
                    SID = stopOIDdict[row[1]]
                    PointsAndStops.setdefault(str(UID), []).append(str(SID))


def runTool(outFile, SQLDbase, inPointsLayer, inLocUniqueID, day, start_time, end_time, 
            BufferSize, BufferUnits, DepOrArrChoice, username, password):
    try:
        # Source FC names are not prepended to field names.
        arcpy.env.qualifiedFieldNames = False
        # It's okay to overwrite in-memory stuff.
        OverwriteOutput = arcpy.env.overwriteOutput # Get the orignal value so we can reset it.
        arcpy.env.overwriteOutput = True
        
        BBB_SharedFunctions.CheckArcVersion(min_version_pro="1.2")

        #----- Get input parameters -----

        # GTFS SQL dbase - must be created ahead of time.
        BBB_SharedFunctions.ConnectToSQLDatabase(SQLDbase)

        Specific, day = BBB_SharedFunctions.CheckSpecificDate(day)

        # Lower end of time window (HH:MM in 24-hour time)
        # Default start time is midnight if they leave it blank.
        if start_time == "":
            start_time = "00:00"
        # Convert to seconds
        start_sec = BBB_SharedFunctions.parse_time(start_time + ":00")
        # Upper end of time window (HH:MM in 24-hour time)
        # Default end time is 11:59pm if they leave it blank.
        if end_time == "":
            end_time = "23:59"
        # Convert to seconds
        end_sec = BBB_SharedFunctions.parse_time(end_time + ":00")

        # Distance between stops and points
        BufferSize_padded = BufferSize + (.2 * BufferSize)
        BufferLinearUnit = str(BufferSize_padded) + " " + BufferUnits

        # Will we calculate the max wait time?
        CalcWaitTime = "true"

        if DepOrArrChoice == "Arrivals":
            DepOrArr = "arrival_time"
        elif DepOrArrChoice == "Departures":
            DepOrArr = "departure_time"

        # Output file designated by user
        outDir = os.path.dirname(outFile)
        outFilename = os.path.basename(outFile)
        ispgdb = "esriDataSourcesGDB.AccessWorkspaceFactory" in arcpy.Describe(outDir).workspaceFactoryProgID
        isshp = ".shp" in outFilename

        # If ObjectID was selected as the unique ID, copy the values to a new field
        # so they don't get messed up when copying the table.
        pointsOID = arcpy.Describe(inPointsLayer).OIDFieldName
        if inLocUniqueID == pointsOID:
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
                raise


        # ----- Prepare OD service -----
        try:
            arcpy.AddMessage("Obtaining credentials for and information about OD Cost Matrix service...")
        
            # Hard-wired OD variables
            TravelMode = "Walking Distance"
            PathShape = "None"
        
            OD_service_name = "World/OriginDestinationCostMatrix"
            Utility_service_name = "World/Utilities"
            # Get the credentials from the signed in user and import the service
            if username and password:
                ODservice = BBB_SharedFunctions.import_AGOLservice(OD_service_name, username=username, password=password)
                Utilityservice = BBB_SharedFunctions.import_AGOLservice(Utility_service_name, username=username, password=password)
            else:
                credentials = arcpy.GetSigninToken()
                if not credentials:
                    arcpy.AddError("Please sign into ArcGIS Online or pass a username and password to the tool.")
                    raise BBB_SharedFunctions.CustomError
                token = credentials["token"]
                referer = credentials["referer"]
                ODservice = BBB_SharedFunctions.import_AGOLservice(OD_service_name, token=token, referer=referer)
                Utilityservice = BBB_SharedFunctions.import_AGOLservice(Utility_service_name, token=token, referer=referer)
        
            # Get the service limits from the OD service (how many origins and destinations allowed)
            utilresult = Utilityservice.GetToolInfo("asyncODCostMatrix", "GenerateOriginDestinationCostMatrix")
            utilresultstring = utilresult.getOutput(0)
            utilresultjson = json.loads(utilresultstring)
            origin_limit = int(utilresultjson['serviceLimits']['maximumDestinations'])
            destination_limit = int(utilresultjson['serviceLimits']['maximumOrigins'])

        except:
            arcpy.AddError("Failed to obtain credentials for and information about OD Cost Matrix service.")
            raise


        # ----- Create a feature class of stops ------
        try:
            arcpy.AddMessage("Getting GTFS stops...")
            tempstopsname = "Temp_Stops"
            if isshp:
                tempstopsname += ".shp"
            StopsLayer, StopList = BBB_SharedFunctions.MakeStopsFeatureClass(os.path.join(outDir, tempstopsname))
            
            # Select only the stops within a reasonable distance of points to reduce problem size
            arcpy.management.MakeFeatureLayer(StopsLayer, "StopsToRemove")
            arcpy.management.SelectLayerByLocation("StopsToRemove", "WITHIN_A_DISTANCE_GEODESIC", inPointsLayer, BufferLinearUnit, invert_spatial_relationship="INVERT")
            arcpy.management.DeleteRows("StopsToRemove")
            arcpy.management.Delete("StopsToRemove")
            
            # Make Feature Layer of stops to use later
            arcpy.management.MakeFeatureLayer(StopsLayer, "StopsLayer")
            stopsOID = arcpy.Describe("StopsLayer").OIDFieldName

        except:
            arcpy.AddError("Error creating feature class of GTFS stops.")
            raise


        # ----- Prepare input data -----
        try:
            arcpy.AddMessage("Preparing input points...")
            
            # Select only the points within a reasonable distance of stops to reduce problem size
            if isshp:
                temppointsname = outFilename.split(".shp")[0] + "_Temp.shp"
            else:
                temppointsname = outFilename + "_Temp"
            relevantPoints = os.path.join(outDir, temppointsname)
            arcpy.management.MakeFeatureLayer(inPointsLayer, "PointsToKeep")
            arcpy.management.SelectLayerByLocation("PointsToKeep", "WITHIN_A_DISTANCE_GEODESIC", StopsLayer, BufferLinearUnit)
            num_points = int(arcpy.management.GetCount("PointsToKeep").getOutput(0))
            
            # If the number of points is large, sort them spatially for smart chunking
            if num_points > origin_limit:
                shapeFieldName = arcpy.Describe("PointsToKeep").shapeFieldName
                arcpy.management.Sort("PointsToKeep", relevantPoints, shapeFieldName, "PEANO")
            # Otherwise, just copy them.
            else:
                arcpy.management.CopyFeatures("PointsToKeep", relevantPoints)
            arcpy.management.Delete("PointsToKeep")
            
            # Store OIDs in a dictionary for later joining
            pointsOIDdict = {} # {OID: inLocUniqueID}
            with arcpy.da.SearchCursor(relevantPoints, ["OID@", inLocUniqueID]) as cur:
                for row in cur:
                    pointsOIDdict[row[0]] = row[1]
            relevantpointsOID = arcpy.Describe(relevantPoints).OIDFieldName

        except:
            arcpy.AddError("Error preparing input points for analysis.")
            raise


        #----- Create OD Matrix between stops and user's points -----
        try:
            arcpy.AddMessage("Creating OD matrix between points and stops...")
            arcpy.AddMessage("(This step could take a while for large datasets or buffer sizes.)")

            global PointsAndStops
            # PointsAndStops = {LocID: [stop_1, stop_2, ...]}
            PointsAndStops = {}

            # Chunk the points to fit the service limits and loop through chunks
            points_numchunks = int(math.ceil(float(num_points)/origin_limit))
            points_chunkstart = 0
            points_chunkend = origin_limit
            current_chunk = 0
            for x in range(0, points_numchunks):
                current_chunk += 1
                arcpy.AddMessage("Handling input points chunk %i of %i" % (current_chunk, points_numchunks))
            
                # Select only the points belonging to this chunk
                points_chunk = sorted(pointsOIDdict.keys())[points_chunkstart:points_chunkend]
                points_chunkstart = points_chunkend
                points_chunkend = points_chunkstart + origin_limit
                if ispgdb:
                    points_selection_query = '[{0}] IN ({1})'.format(relevantpointsOID, ','.join(map(str, points_chunk)))
                else:
                    points_selection_query = '"{0}" IN ({1})'.format(relevantpointsOID, ','.join(map(str, points_chunk)))
                arcpy.MakeFeatureLayer_management(relevantPoints, "PointsLayer", points_selection_query)
                
                # Select only the stops within the safe buffer of these points
                arcpy.management.SelectLayerByLocation("StopsLayer", "WITHIN_A_DISTANCE_GEODESIC", "PointsLayer", BufferLinearUnit)
                num_stops = int(arcpy.GetCount_management("StopsLayer").getOutput(0))
                stopOIDdict = {} # {OID: stop_id}
                with arcpy.da.SearchCursor("StopsLayer", ["OID@", "stop_id"]) as cur:
                    for row in cur:
                        stopOIDdict[row[0]] = row[1]

                # If the number of stops in range exceeds the destination limit, we have to chunk these as well.
                if num_stops > destination_limit:
                    stops_numchunks = int(math.ceil(float(num_stops)/destination_limit))
                    stops_chunkstart = 0
                    stops_chunkend = destination_limit
                    for x in range(0, stops_numchunks):
                        stops_chunk = sorted(stopOIDdict.keys())[stops_chunkstart:stops_chunkend]
                        stops_chunkstart = stops_chunkend
                        stops_chunkend = stops_chunkstart + destination_limit
                        if ispgdb:
                            stops_selection_query = '[{0}] IN ({1})'.format(stopsOID, ','.join(map(str, stops_chunk)))
                        else:
                            stops_selection_query = '"{0}" IN ({1})'.format(stopsOID, ','.join(map(str, stops_chunk)))
                        arcpy.MakeFeatureLayer_management("StopsLayer", "StopsLayer_Chunk", stops_selection_query)
                        runOD("PointsLayer", "StopsLayer_Chunk")
                    arcpy.management.Delete("StopsLayer_Chunk")
                # Otherwise, just run them all.
                else:
                    runOD("PointsLayer", "StopsLayer")

            # Clean up
            arcpy.management.Delete("StopsLayer")
            arcpy.management.Delete("PointsLayer")
            arcpy.management.Delete(StopsLayer)
            arcpy.management.Delete(relevantPoints)

        except:
            arcpy.AddError("Error creating OD matrix between stops and input points.")
            raise


        #----- Query the GTFS data to count the trips at each stop -----
        try:
            arcpy.AddMessage("Calculating the number of transit trips available during the time window...")

            # Get a dictionary of stop times in our time window {stop_id: [[trip_id, stop_time]]}
            stoptimedict = BBB_SharedFunctions.CountTripsAtStops(day, start_sec, end_sec, DepOrArr, Specific)

        except:
            arcpy.AddError("Error calculating the number of transit trips available during the time window.")
            raise


        # ----- Generate output data -----
        try:
            arcpy.AddMessage("Writing output data...")

            arcpy.management.CopyFeatures(inPointsLayer, outFile)
            # Add a field to the output file for number of trips and num trips / hour.
            if isshp:
                arcpy.management.AddField(outFile, "NumTrips", "SHORT")
                arcpy.management.AddField(outFile, "TripsPerHr", "DOUBLE")
                arcpy.management.AddField(outFile, "NumStops", "SHORT")
                arcpy.management.AddField(outFile, "MaxWaitTm", "SHORT")
            else:
                arcpy.management.AddField(outFile, "NumTrips", "SHORT")
                arcpy.management.AddField(outFile, "NumTripsPerHr", "DOUBLE")
                arcpy.management.AddField(outFile, "NumStopsInRange", "SHORT")
                arcpy.management.AddField(outFile, "MaxWaitTime", "SHORT")

            if ArcVersion == "10.0":
                if isshp:
                    ucursor = arcpy.UpdateCursor(outFile, "", "",
                                            inLocUniqueID[0:10] + "; NumTrips; TripsPerHr; NumStops; MaxWaitTm")
                    for row in ucursor:
                        try:
                            ImportantStops = PointsAndStops[str(row.getValue(inLocUniqueID))]
                        except KeyError:
                            # This point had no stops in range
                            ImportantStops = []
                        NumTrips, NumTripsPerHr, NumStopsInRange, MaxWaitTime = \
                                    BBB_SharedFunctions.RetrieveStatsForSetOfStops(
                                        ImportantStops, stoptimedict, CalcWaitTime,
                                        start_sec, end_sec)
                        row.NumTrips = NumTrips
                        row.TripsPerHr = NumTripsPerHr
                        row.NumStops = NumStopsInRange
                        if MaxWaitTime == None:
                            row.MaxWaitTm = -1
                        else:
                            row.MaxWaitTm = MaxWaitTime
                        ucursor.updateRow(row)
                else:
                    ucursor = arcpy.UpdateCursor(outFile, "", "",
                                            inLocUniqueID + "; NumTrips; NumTripsPerHr; NumStopsInRange; MaxWaitTime")
                    for row in ucursor:
                        try:
                            ImportantStops = PointsAndStops[str(row.getValue(inLocUniqueID))]
                        except KeyError:
                            # This point had no stops in range
                            ImportantStops = []
                        NumTrips, NumTripsPerHr, NumStopsInRange, MaxWaitTime = \
                                    BBB_SharedFunctions.RetrieveStatsForSetOfStops(
                                        ImportantStops, stoptimedict, CalcWaitTime,
                                        start_sec, end_sec)
                        row.NumTrips = NumTrips
                        row.NumTripsPerHr = NumTripsPerHr
                        row.NumStopsInRange = NumStopsInRange
                        row.MaxWaitTime = MaxWaitTime
                        ucursor.updateRow(row)

            else:
                # For everything 10.1 and forward
                if isshp:
                    ucursor = arcpy.da.UpdateCursor(outFile,
                                                    [inLocUniqueID[0:10], "NumTrips",
                                                    "TripsPerHr", "NumStops",
                                                    "MaxWaitTm"])
                else:
                    ucursor = arcpy.da.UpdateCursor(outFile,
                                                [inLocUniqueID, "NumTrips",
                                                "NumTripsPerHr", "NumStopsInRange",
                                                "MaxWaitTime"])
                for row in ucursor:
                    try:
                        ImportantStops = PointsAndStops[str(row[0])]
                    except KeyError:
                        # This point had no stops in range
                        ImportantStops = []
                    NumTrips, NumTripsPerHr, NumStopsInRange, MaxWaitTime =\
                                    BBB_SharedFunctions.RetrieveStatsForSetOfStops(
                                        ImportantStops, stoptimedict, CalcWaitTime,
                                        start_sec, end_sec)
                    row[1] = NumTrips
                    row[2] = NumTripsPerHr
                    row[3] = NumStopsInRange
                    if isshp and MaxWaitTime == None:
                        row[4] = -1
                    else:
                        row[4] = MaxWaitTime
                    ucursor.updateRow(row)
            del ucursor
                    
        except:
            arcpy.AddError("Error writing output.")
            raise

        arcpy.AddMessage("Done!")
        arcpy.AddMessage("Output files written:")
        arcpy.AddMessage("- " + outFile)

    except BBB_SharedFunctions.CustomError:
        arcpy.AddError("Error counting transit trips at input locations.")
        pass

    except:
        arcpy.AddError("Error counting transit trips at input locations.")
        raise

    finally:
        # Reset overwriteOutput to what it was originally.
        arcpy.env.overwriteOutput = OverwriteOutput