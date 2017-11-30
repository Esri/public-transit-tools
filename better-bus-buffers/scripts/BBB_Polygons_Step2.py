####################################################
## Tool name: BetterBusBuffers - Count Trips in Polygon Buffers Around Stops
## Step 2: Count Trips in Buffers
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 25 September 2017
####################################################
'''BetterBusBuffers - Count Trips in Polygon Buffers Around Stops - Step 2: Count Trips in Buffers

BetterBusBuffers provides a quantitative measure of access to public transit
in your city by counting the transit trip frequency at various locations.

The Count Trips in Polygon Buffers Around Stops tool creates service area
buffers around all transit stops in the transit system.  For each resulting
area, the tool counts the number of transit trips available during a time window
The tool also calculates the number of trips per hour, the maximum time between
subsequent trips, and the number of stops within range of the area.

Step 2: Count Trips in Buffers uses the template feature class created in Step
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

class CustomError(Exception):
    pass

OverwriteOutput = None


def runTool(inStep1GDB, outFile, day, start_time, end_time, TravelFromTo):
    try:

        # ----- Set up the run -----
        try:
            BBB_SharedFunctions.CheckArcVersion(min_version_pro="1.2")
            
            # Get the files from Step 1 to work with.
            # Step1_GTFS.sql and Step1_FlatPolys must exist in order for the tool to run.
            # Their existence is checked in the GUI validation logic.
            FlatPolys = os.path.join(inStep1GDB, "Step1_FlatPolys")
            SQLDbase = os.path.join(inStep1GDB, "Step1_GTFS.sql")
            # Connect to the SQL database
            conn = BBB_SharedFunctions.conn = sqlite3.connect(SQLDbase)
            c = BBB_SharedFunctions.c = conn.cursor()

            # Output file designated by user
            outDir = os.path.dirname(outFile)
            outFilename = os.path.basename(outFile)

            Specific, day = BBB_SharedFunctions.CheckSpecificDate(day)
            start_sec, end_sec = BBB_SharedFunctions.ConvertTimeWindowToSeconds(start_time, end_time)

            # Will we calculate the max wait time? This slows down the calculation, so leave it optional.
            CalcWaitTime = True

            # It's okay to overwrite stuff.
            OverwriteOutput = arcpy.env.overwriteOutput # Get the orignal value so we can reset it.
            arcpy.env.overwriteOutput = True

        except:
            arcpy.AddError("Error setting up run.")
            raise


        #----- Query the GTFS data to count the trips at each stop -----
        try:
            arcpy.AddMessage("Counting transit trips during the time window...")

            # Get a dictionary of stop times in our time window {stop_id: [[trip_id, stop_time]]}
            stoptimedict = BBB_SharedFunctions.CountTripsAtStops(day, start_sec, end_sec, BBB_SharedFunctions.CleanUpDepOrArr(DepOrArrChoice), Specific)

        except:
            arcpy.AddError("Failed to count transit trips during the time window.")
            raise


        #----- Find which stops serve each polygon -----
        try:
            arcpy.AddMessage("Retrieving list of stops associated with each polygon...")
            # Find the stop_ids associated with each flattened polygon and put them in
            # a dictionary. {ORIG_FID: [stop_id, stop_id,...]}
            stackedpointdict = {}
            GetStackedPtsStmt = "SELECT * FROM StackedPoints"
            c.execute(GetStackedPtsStmt)
            for PolyFID in c:
                stackedpointdict.setdefault(PolyFID[0], []).append(str(PolyFID[1]))
        except:
            arcpy.AddError("Error retrieving list of stops associated with each polygon.")
            raise


        # ----- Generate output data -----
        try:
            arcpy.AddMessage("Writing output data...")

            # Create the output file from FlatPolys.  We don't want to overwrite the
            # original Step 1 template file.
            arcpy.management.CopyFeatures(FlatPolys, outFile)
            badpolys = []

            if ".shp" in outFilename:
                ucursor = arcpy.da.UpdateCursor(outFile,
                                                ["PolyID", "NumTrips",
                                                "NumTripsPe", "NumStopsIn",
                                                "MaxWaitTim"])
            else:
                ucursor = arcpy.da.UpdateCursor(outFile,
                                            ["PolyID", "NumTrips",
                                            "NumTripsPerHr", "NumStopsInRange",
                                            "MaxWaitTime"])
            for row in ucursor:
                try:
                    ImportantStops = stackedpointdict[int(row[0])]
                except KeyError:
                    # If we got a KeyError here, then an output polygon never
                    # got a point associated with it, probably the result of a
                    # geometry problem because of the large cluster tolerance
                    # used to generate the polygons in Step 1. Just skip this
                    # polygon and alert the user.
                    badpolys.append(row[0])
                    continue
                NumTrips, NumTripsPerHr, NumStopsInRange, MaxWaitTime = \
                                BBB_SharedFunctions.RetrieveStatsForSetOfStops(
                                    ImportantStops, stoptimedict, CalcWaitTime,
                                    start_sec, end_sec)
                row[1] = NumTrips
                row[2] = NumTripsPerHr
                row[3] = NumStopsInRange
                if ".shp" in outFilename and MaxWaitTime == None:
                    row[4] = -1
                else:
                    row[4] = MaxWaitTime
                ucursor.updateRow(row)

            if badpolys:
                arcpy.AddWarning("Warning! BetterBusBuffers could not calculate trip \
statistics for one or more polygons due to a geometry issue. These polygons will \
appear in your output data, but all output values will be null. Bad polygon \
PolyID values: " + str(badpolys))

        except:
            arcpy.AddMessage("Error writing output.")
            raise

        arcpy.AddMessage("Finished!")
        arcpy.AddMessage("Your output is located at " + outFile)

    except CustomError:
        arcpy.AddError("Error counting transit trips in polygons.")
        pass

    except:
        arcpy.AddError("Error counting transit trips in polygons.")
        raise

    finally:
        # Reset overwriteOutput to what it was originally.
        arcpy.env.overwriteOutput = OverwriteOutput
