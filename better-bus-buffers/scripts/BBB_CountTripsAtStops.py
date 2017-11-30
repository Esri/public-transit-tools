############################################################################
## Tool name: BetterBusBuffers - Count Trips at Stops
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 8 February 2016
############################################################################
''' BetterBusBuffers - Count Trips at Stops

BetterBusBuffers provides a quantitative measure of access to public transit
in your city by counting the transit trip frequency at various locations.

The Count Trips at Stops tool creates a feature class of your GTFS stops and
counts the number of trips that visit each one during a time window as well as
the number of trips per hour and the maximum time between subsequent trips
during that time window.
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

import arcpy
import BBB_SharedFunctions


def runTool(outStops, SQLDbase, day, start_time, end_time, DepOrArrChoice):
    try:
        # ------ Get input parameters and set things up. -----
        try:
            
            BBB_SharedFunctions.CheckArcVersion(min_version_pro="1.2")

            # GTFS SQL dbase - must be created ahead of time.
            BBB_SharedFunctions.ConnectToSQLDatabase(SQLDbase)

            Specific, day = BBB_SharedFunctions.CheckSpecificDate(day)
                
            # Lower end of time window (HH:MM in 24-hour time)
            start_time = arcpy.GetParameterAsText(3)
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

            # Will we calculate the max wait time?
            CalcWaitTime = "true"

            # Does the user want to count arrivals or departures at the stops?
            if DepOrArrChoice == "Arrivals":
                DepOrArr = "arrival_time"
            elif DepOrArrChoice == "Departures":
                DepOrArr = "departure_time"

        except:
            arcpy.AddError("Error getting user inputs.")
            raise


        # ----- Create a feature class of stops and add fields for transit trip counts ------
        try:
            arcpy.AddMessage("Creating feature class of GTFS stops...")

            # Create a feature class of transit stops
            outStops, StopIDList = BBB_SharedFunctions.MakeStopsFeatureClass(outStops)

            # Add a field to the output file for number of trips, num trips / hour, and max wait time
            if ".shp" in outStops:
                # Shapefiles can't have long field names
                arcpy.management.AddField(outStops, "NumTrips", "SHORT")
                arcpy.management.AddField(outStops, "TripsPerHr", "DOUBLE")
                arcpy.management.AddField(outStops, "MaxWaitTm", "SHORT")
            else:
                arcpy.management.AddField(outStops, "NumTrips", "SHORT")
                arcpy.management.AddField(outStops, "NumTripsPerHr", "DOUBLE")
                arcpy.management.AddField(outStops, "MaxWaitTime", "SHORT")

        except:
            arcpy.AddError("Error creating feature class of GTFS stops.")
            raise


        #----- Query the GTFS data to count the trips at each stop -----
        try:
            arcpy.AddMessage("Calculating the number of transit trips available during the time window...")

            # Get a dictionary of {stop_id: [[trip_id, stop_time]]} for our time window
            stoptimedict = BBB_SharedFunctions.CountTripsAtStops(day, start_sec, end_sec, DepOrArr, Specific)

        except:
            arcpy.AddError("Error counting arrivals or departures at stop during time window.")
            raise


        # ----- Write to output -----
        try:
            arcpy.AddMessage("Writing output data...")

            # Create an update cursor to add numtrips, trips/hr, and maxwaittime to stops
            if BBB_SharedFunctions.ArcVersion == "10.0":
                if ".shp" in outStops:
                    ucursor = arcpy.UpdateCursor(outStops, "", "", "stop_id; NumTrips; TripsPerHr; MaxWaitTm")
                    for row in ucursor:
                        NumTrips, NumTripsPerHr, NumStopsInRange, MaxWaitTime = \
                                BBB_SharedFunctions.RetrieveStatsForSetOfStops(
                                    [str(row.getValue("stop_id"))], stoptimedict,
                                    CalcWaitTime, start_sec, end_sec)
                        row.NumTrips = NumTrips
                        row.TripsPerHr = NumTripsPerHr
                        if MaxWaitTime == None:
                            row.MaxWaitTm = -1
                        else:
                            row.MaxWaitTm = MaxWaitTime
                        ucursor.updateRow(row)
                else:
                    ucursor = arcpy.UpdateCursor(outStops, "", "", "stop_id; NumTrips; NumTripsPerHr; MaxWaitTime")
                    for row in ucursor:
                        NumTrips, NumTripsPerHr, NumStopsInRange, MaxWaitTime = \
                                BBB_SharedFunctions.RetrieveStatsForSetOfStops(
                                    [str(row.getValue("stop_id"))], stoptimedict,
                                    CalcWaitTime, start_sec, end_sec)
                        row.NumTrips = NumTrips
                        row.NumTripsPerHr = NumTripsPerHr
                        row.MaxWaitTime = MaxWaitTime
                        ucursor.updateRow(row)

            else:
                # For everything 10.1 and forward
                if ".shp" in outStops:
                    ucursor = arcpy.da.UpdateCursor(outStops,
                                                ["stop_id", "NumTrips",
                                                "TripsPerHr",
                                                "MaxWaitTm"])
                else:
                    ucursor = arcpy.da.UpdateCursor(outStops,
                                                ["stop_id", "NumTrips",
                                                "NumTripsPerHr",
                                                "MaxWaitTime"])
                for row in ucursor:
                    NumTrips, NumTripsPerHr, NumStopsInRange, MaxWaitTime = \
                                BBB_SharedFunctions.RetrieveStatsForSetOfStops(
                                    [str(row[0])], stoptimedict, CalcWaitTime,
                                    start_sec, end_sec)
                    row[1] = NumTrips
                    row[2] = NumTripsPerHr
                    if ".shp" in outStops and MaxWaitTime == None:
                        row[3] = -1
                    else:
                        row[3] = MaxWaitTime
                    ucursor.updateRow(row)

        except:
            arcpy.AddError("Error writing to output.")
            raise

        arcpy.AddMessage("Finished!")
        arcpy.AddMessage("Your output is located at " + outStops)

    except BBB_SharedFunctions.CustomError:
        arcpy.AddError("Failed to count trips at stops.")
        pass

    except:
        arcpy.AddError("Failed to count trips at stops.")
        raise