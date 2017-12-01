############################################################################
## Tool name: BetterBusBuffers - Count Trips on Lines
## Step 2 - Count Trips on Lines
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 6 October 2017
############################################################################
''' BetterBusBuffers - Count Trips on Lines

BetterBusBuffers provides a quantitative measure of access to public transit
in your city by counting the transit trip frequency at various locations.

The Count Trips on Lines tool counts the number of transit trips that travel 
along corridors between stops during a time window. This step uses the output
of Step 1 and counts the frequency of service during specific time windows.
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

import arcpy
import BBB_SharedFunctions


def runTool(step1LinesFC, SQLDbase, linesFC, day, start_time, end_time):
    try:
        # ------ Get input parameters and set things up. -----

        BBB_SharedFunctions.CheckArcVersion(min_version_pro="1.2")

        try:
            # If it was a feature layer, it will have a data source property
            step1LinesFC = step1LinesFC.dataSource
        except:
            # Otherwise, assume it was a catalog path and use as is
            pass

        # GTFS SQL dbase - must be created ahead of time.
        BBB_SharedFunctions.ConnectToSQLDatabase(SQLDbase)

        Specific, day = BBB_SharedFunctions.CheckSpecificDate(day)
        start_sec, end_sec = BBB_SharedFunctions.ConvertTimeWindowToSeconds(start_time, end_time)

        # Does the user want to count arrivals or departures at the stops?
        DepOrArr = "departure_time"


        # ----- Prepare output file -----

        try:
            arcpy.management.Copy(step1LinesFC, linesFC)
        except:
            arcpy.AddError("Error copying template lines feature class to output %s," % linesFC)
            raise


        # ----- Query the GTFS data to count the trips on each line segment -----
        try:
            arcpy.AddMessage("Calculating the number of transit trips available during the time window...")

            # Get a dictionary of {line_key: [[trip_id, start_time, end_time]]} for our time window
            linetimedict = BBB_SharedFunctions.CountTripsOnLines(day, start_sec, end_sec, DepOrArr, Specific)

        except:
            arcpy.AddError("Error counting arrivals or departures at during time window.")
            raise


        # ----- Write to output -----
        try:
            arcpy.AddMessage("Writing output data...")

            combine_corridors = "route_id" not in [f.name for f in arcpy.ListFields(linesFC)]

            triproute_dict = None
            if not combine_corridors:
                triproute_dict = BBB_SharedFunctions.MakeTripRouteDict()

            arcpy.management.AddField(linesFC, "NumTrips", "SHORT")
            arcpy.management.AddField(linesFC, "NumTripsPerHr", "DOUBLE")
            arcpy.management.AddField(linesFC, "MaxWaitTime", "SHORT")
            arcpy.management.AddField(linesFC, "AvgHeadway", "SHORT")

            with arcpy.da.UpdateCursor(linesFC, ["pair_id", "NumTrips",
                                                "NumTripsPerHr",
                                                "MaxWaitTime", "AvgHeadway"]) as ucursor:
                for row in ucursor:
                    NumTrips, NumTripsPerHr, MaxWaitTime, AvgHeadway = \
                                BBB_SharedFunctions.RetrieveStatsForLines(
                                    str(row[0]), linetimedict,
                                    start_sec, end_sec, combine_corridors, triproute_dict)
                    row[1] = NumTrips
                    row[2] = NumTripsPerHr
                    row[3] = MaxWaitTime
                    row[4] = AvgHeadway
                    ucursor.updateRow(row)

        except:
            arcpy.AddError("Error writing to output.")
            raise

        arcpy.AddMessage("Finished!")
        arcpy.AddMessage("Your output is located at " + linesFC)

    except BBB_SharedFunctions.CustomError:
        arcpy.AddError("Failed to count trips on lines.")
        pass

    except:
        arcpy.AddError("Failed to count trips on lines.")
        raise