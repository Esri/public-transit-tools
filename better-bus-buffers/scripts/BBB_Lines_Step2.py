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

class CustomError(Exception):
    pass


try:
    # ------ Get input parameters and set things up. -----
    try:

        # Figure out what version of ArcGIS they're running
        BBB_SharedFunctions.DetermineArcVersion()
        if BBB_SharedFunctions.ProductName == "ArcGISPro" and BBB_SharedFunctions.ArcVersion in ["1.0", "1.1", "1.1.1"]:
            arcpy.AddError("The BetterBusBuffers toolbox does not work in versions of ArcGIS Pro prior to 1.2.\
You have ArcGIS Pro version %s." % BBB_SharedFunctions.ArcVersion)
            raise CustomError
        if BBB_SharedFunctions.ArcVersion == "10.0":
            arcpy.AddError("You must have ArcGIS 10.1 or higher (or ArcGIS Pro) to run this \
tool. You have ArcGIS version %s." % BBB_SharedFunctions.ArcVersion)
            raise CustomError

        # Get the files from Step 1 to work with.
        step1LinesFC = arcpy.GetParameter(0)
        SQLDbase = arcpy.GetParameterAsText(1)
        linesFC = arcpy.GetParameterAsText(2)

        try:
            # If it was a feature layer, it will have a data source property
            step1LinesFC = step1LinesFC.dataSource
        except:
            # Otherwise, assume it was a catalog path and use as is
            pass

        # GTFS SQL dbase - must be created ahead of time.
        BBB_SharedFunctions.ConnectToSQLDatabase(SQLDbase)

        # Weekday or specific date to analyze.
        # Note: Datetime format check is in tool validation code
        # day = "20160812"
        day = arcpy.GetParameterAsText(3)
        if day in BBB_SharedFunctions.days: #Generic weekday
            Specific = False
        else: #Specific date
            Specific = True
            day = datetime.datetime.strptime(day, '%Y%m%d')
            
        # Lower end of time window (HH:MM in 24-hour time)
        start_time = arcpy.GetParameterAsText(4)
        # Default start time is midnight if they leave it blank.
        if start_time == "":
            start_time = "00:00"
        # Convert to seconds
        start_sec = BBB_SharedFunctions.parse_time(start_time + ":00")
        # Upper end of time window (HH:MM in 24-hour time)
        end_time = arcpy.GetParameterAsText(5)
        # Default end time is 11:59pm if they leave it blank.
        if end_time == "":
            end_time = "23:59"
        # Convert to seconds
        end_sec = BBB_SharedFunctions.parse_time(end_time + ":00")

        # Will we calculate the max wait time?
        CalcWaitTime = "true"

        # Does the user want to count arrivals or departures at the stops?
        DepOrArr = "departure_time"

    except:
        arcpy.AddError("Error getting user inputs.")
        raise


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
                                [str(row[0])], linetimedict, CalcWaitTime,
                                start_sec, end_sec)
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

except CustomError:
    arcpy.AddError("Failed to count trips on lines.")
    pass

except:
    arcpy.AddError("Failed to count trips on lines.")
    raise