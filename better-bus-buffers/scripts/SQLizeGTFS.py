############################################################################
## Tool name: BetterBusBuffers
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 4 February 2016
############################################################################
''' BetterBusBuffers: Preprocess GTFS

BetterBusBuffers provides a quantitative measure of access to public transit
in your city.  This tool takes a set of input points, finds the transit stops
reachable within a user-selected buffer distance, and counts the number of
transit trips that pass those stops during the time window selected.
Output can be shown as the total number of trips or the average number of trips
per hour during the time window.  Note that the tool tells you nothing about
the destination of the buses/trains that pass by the stops, only how many of
them there are.
BetterBusBuffers uses GTFS public transit data and ArcGIS Network Analyst.

This tool preprocess the GTFS data, converting it into a SQL database that is
used as input by all the BetterBusBuffers tools.
'''

''' This tool uses code written by Luitien Pan for GTFS_NATools.'''
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
import sqlize_csv
import BBB_SharedFunctions

class CustomError(Exception):
    pass

try:
    
    # Figure out what version of ArcGIS they're running
    BBB_SharedFunctions.DetermineArcVersion()
    if BBB_SharedFunctions.ProductName == "ArcGISPro" and BBB_SharedFunctions.ArcVersion in ["1.0", "1.1", "1.1.1"]:
        arcpy.AddError("The BetterBusBuffers toolbox does not work in versions of ArcGIS Pro prior to 1.2.\
You have ArcGIS Pro version %s." % BBB_SharedFunctions.ArcVersion)
        raise CustomError

    #----- SQLize the GTFS data-----
    arcpy.AddMessage("SQLizing the GTFS data...")
    arcpy.AddMessage("(This will take a while for large datasets.)")

    # GTFS files
    inGTFSdir = arcpy.GetParameterAsText(0)
    SQLDbase = arcpy.GetParameterAsText(1)
    if not SQLDbase.lower().endswith(".sql"):
        SQLDbase = SQLDbase + ".sql"

    # Fix up list of GTFS datasets
    inGTFSdirList = inGTFSdir.split(";")
    # Remove single quotes ArcGIS puts in if there are spaces in the filename.
    for d in inGTFSdirList:
        if d[0] == "'" and d[-1] == "'":
            loc = inGTFSdirList.index(d)
            inGTFSdirList[loc] = d[1:-1]

    # The main SQLizing work is done in the sqlize_csv module
    # written by Luitien Pan.
    # Connect to or create the SQL file.
    sqlize_csv.connect(SQLDbase)
    # Create tables.
    for tblname in sqlize_csv.sql_schema:
        sqlize_csv.create_table(tblname)
    # SQLize all the GTFS files, for each separate GTFS dataset.
    for gtfs_dir in inGTFSdirList:
        # handle_agency checks for blank values in arrival_time and departure_time
        GTFSErrors = sqlize_csv.handle_agency(gtfs_dir)
        if GTFSErrors:
            for error in GTFSErrors:
                arcpy.AddError(error)
            raise CustomError

    # Create indices to make queries faster.
    sqlize_csv.create_indices()

    # Check for non-overlapping date ranges to prevent double-counting.
    overlapwarning = sqlize_csv.check_nonoverlapping_dateranges()
    if overlapwarning:
        arcpy.AddWarning(overlapwarning)

    arcpy.AddMessage("Successfully created SQL database of GTFS data:")
    arcpy.AddMessage("- " + SQLDbase)

except CustomError:
    arcpy.AddMessage("Failed to create SQL database of GTFS data.")
    pass

except:
    arcpy.AddMessage("Failed to create SQL database of GTFS data.")
    raise
