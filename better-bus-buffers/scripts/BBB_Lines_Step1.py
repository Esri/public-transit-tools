############################################################################
## Tool name: BetterBusBuffers - Count Trips on Lines
## Step 1 - Preprocess Lines
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 4 October 2017
############################################################################
''' BetterBusBuffers - Count Trips on Lines

BetterBusBuffers provides a quantitative measure of access to public transit
in your city by counting the transit trip frequency at various locations.

The Count Trips on Lines tool counts the number of transit trips that travel 
along corridors between stops during a time window. This pre-processing step
generates a feature class of transit lines and updates a SQL database of 
transit schedules so that the frequency of transit service along the lines 
can be calculated. The counts are done in Step 2 for specific time windows.
Step 1 need only be run once for a given transit system.
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

import sqlite3, os, uuid
import arcpy
import BBB_SharedFunctions

class CustomError(Exception):
    pass

# ----- Collect user inputs -----

outLinesFC = arcpy.GetParameterAsText(0)
SQLDbase = arcpy.GetParameterAsText(1)
combine_corridors = arcpy.GetParameter(2)

# Derived inputs
outGDB = os.path.dirname(outLinesFC) # Must be in fgdb. Validated in tool validation.
# Create a guid to make sure temporary outputs have unique names. They should be deleted
# when the tool completes, but this ensures they don't conflict with any existing feature
# classes in the gdb and makes it easier to know what they are and delete them if they
# don't automatically get deleted.
guid = uuid.uuid4().hex
outStopPairsFCName = "StopPairs_" + guid
outStopPairsFC = os.path.join(outGDB, outStopPairsFCName)
outStopsFCName = "Stops_" + guid
outStopsFC = os.path.join(outGDB, outStopsFCName)

# Get the original overwrite output setting so we can reset it at the end.
OverwriteOutput = arcpy.env.overwriteOutput
# It's okay to overwrite stuff in this tool
arcpy.env.overwriteOutput = True


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


# ----- Connect to SQL locally for further queries and entries -----

    # Connect to the SQL database
    conn = sqlite3.connect(SQLDbase)
    c = conn.cursor()


# ----- Make dictionary of {trip_id: route_id} -----

    # First, make sure there are no duplicate trip_id values, as this will mess things up later.
    tripDuplicateFetch = "SELECT trip_id, count(*) from trips group by trip_id having count(*) > 1"
    c.execute(tripDuplicateFetch)
    tripdups = c.fetchall()
    tripdupslist = [tripdup for tripdup in tripdups]
    if tripdupslist:
        arcpy.AddError("Your GTFS trips table is invalid.  It contains multiple trips with the same trip_id.")
        for tripdup in tripdupslist:
            arcpy.AddError("There are %s instances of the trip_id value '%s'." % (str(tripdup[1]), unicode(tripdup[0])))
        raise CustomError

    # Now make the dictionary
    trip_routeid_dict = {}
    if not combine_corridors:
        tripsfetch = '''
            SELECT trip_id, route_id
            FROM trips
            ;'''
        c.execute(tripsfetch)
        for trip in c:
            trip_routeid_dict[trip[0]] = trip[1]


# ----- Generate transit stops feature class (for the final ND) -----

    arcpy.AddMessage("Generating transit stops feature class.")

    # Get the stops table (exclude parent stations and station entrances)
    selectstoptablestmt = "SELECT stop_id, stop_lat, stop_lon, stop_code, \
                        stop_name, stop_desc, zone_id, stop_url, location_type, \
                        parent_station FROM stops;"
    c.execute(selectstoptablestmt)

    # Initialize a dictionary of stop lat/lon (filled below)
    # {stop_id: <stop geometry object>} in the output coordinate system
    stoplatlon_dict = {}

    # Create a points feature class for the point pairs.
    arcpy.management.CreateFeatureclass(outGDB, outStopsFCName, "POINT", "", "", "", BBB_SharedFunctions.WGSCoords)
    arcpy.management.AddField(outStopsFC, "stop_id", "TEXT")
    arcpy.management.AddField(outStopsFC, "stop_code", "TEXT")
    arcpy.management.AddField(outStopsFC, "stop_name", "TEXT")
    arcpy.management.AddField(outStopsFC, "stop_desc", "TEXT")
    arcpy.management.AddField(outStopsFC, "zone_id", "TEXT")
    arcpy.management.AddField(outStopsFC, "stop_url", "TEXT")
    arcpy.management.AddField(outStopsFC, "location_type", "TEXT")
    arcpy.management.AddField(outStopsFC, "parent_station", "TEXT")

    # Add the stops table to a feature class.
    with arcpy.da.InsertCursor(outStopsFC, ["SHAPE@", "stop_id",
                                                 "stop_code", "stop_name", "stop_desc",
                                                 "zone_id", "stop_url", "location_type",
                                                 "parent_station"]) as cur3:
        for stop in c:
            stop_id = stop[0]
            stop_lat = stop[1]
            stop_lon = stop[2]
            stop_code = stop[3]
            stop_name = stop[4]
            stop_desc = stop[5]
            zone_id = stop[6]
            stop_url = stop[7]
            location_type = stop[8]
            parent_station = stop[9]
            if location_type not in [0, '0', None, ""]:
                # Skip parent stations and station entrances
                continue
            pt = arcpy.Point()
            pt.X = float(stop_lon)
            pt.Y = float(stop_lat)
            # GTFS stop lat/lon is written in WGS1984
            ptGeometry = arcpy.PointGeometry(pt, BBB_SharedFunctions.WGSCoords)
            stoplatlon_dict[stop_id] = ptGeometry
            cur3.insertRow((ptGeometry, stop_id, stop_code, stop_name,
                            stop_desc, zone_id, stop_url, location_type,
                            parent_station))


# ----- Obtain schedule info from the stop_times.txt file and convert it to a line-based model -----

    arcpy.AddMessage("Obtaining and processing transit schedule and line information...")
    arcpy.AddMessage("(This will take a few minutes for large datasets.)")

    # Create a line-based schedule table
    c2 = conn.cursor()
    c2.execute("DROP TABLE IF EXISTS schedules;")
    c2.execute("CREATE TABLE schedules (key TEXT, start_time REAL, end_time REAL, trip_id TEXT);")

    # Find pairs of directly-connected stops
    linefeature_dict = {}
    stoptimefetch = '''
    SELECT trip_id, stop_id, arrival_time, departure_time
    FROM stop_times
    ORDER BY trip_id, stop_sequence
    ;'''
    c.execute(stoptimefetch)
    current_trip = None
    previous_stop = None
    start_time = None
    end_time = None
    for st in c:
        trip_id = st[0]
        stop_id = st[1]
        arrival_time = st[2]
        departure_time = st[3]
        if trip_id != current_trip:
            current_trip = trip_id
            previous_stop = stop_id
            start_time = departure_time # Start time of segment is the departure time from the stop
            continue
        start_stop = previous_stop
        end_stop = stop_id
        end_time = arrival_time
        if combine_corridors:
            # All trips between each pair of stops will be combined, regardless of route_id
            SourceOIDkey = "%s , %s" % (start_stop, end_stop)
        else:
            # Include the route_id as a part of the key so a separate line will be created for each separate route between the same two stops
            SourceOIDkey = "%s , %s , %s" % (start_stop, end_stop, trip_routeid_dict[trip_id])
        # This stop pair needs a line feature
        linefeature_dict[SourceOIDkey] = True
        stmt = """INSERT INTO schedules (key, start_time, end_time, trip_id) VALUES ('%s', %s, %s, '%s');""" % (SourceOIDkey, start_time, end_time, trip_id)
        c2.execute(stmt)
        previous_stop = stop_id
        start_time = departure_time
    conn.commit()
    c2.execute("CREATE INDEX schedules_index_tripsstend ON schedules (trip_id, start_time, end_time);")
    conn.commit()


    # ----- Write pairs to a points feature class (this is intermediate and will NOT go into the final output) -----

    # Create a points feature class for the point pairs.
    arcpy.management.CreateFeatureclass(outGDB, outStopPairsFCName, "POINT", "", "", "", BBB_SharedFunctions.WGSCoords)
    arcpy.management.AddField(outStopPairsFC, "stop_id", "TEXT")
    arcpy.management.AddField(outStopPairsFC, "pair_id", "TEXT")
    arcpy.management.AddField(outStopPairsFC, "sequence", "SHORT")

    # Add pairs of stops to the feature class in preparation for generating line features
    badStops = []
    badkeys = []
    with arcpy.da.InsertCursor(outStopPairsFC, ["SHAPE@", "stop_id", "pair_id", "sequence"]) as cur:
        # linefeature_dict = {"start_stop , end_stop , route_type": True}
        for SourceOIDkey in linefeature_dict:
            stopPair = SourceOIDkey.split(" , ")
            # {stop_id: [stop_lat, stop_lon]}
            try:
                stop1 = stopPair[0]
                stop1_geom = stoplatlon_dict[stop1]
            except KeyError:
                badStops.append(stop1)
                badkeys.append(SourceOIDkey)
                continue
            try:
                stop2 = stopPair[1]
                stop2_geom = stoplatlon_dict[stop2]
            except KeyError:
                badStops.append(stop2)
                badkeys.append(SourceOIDkey)
                continue
            cur.insertRow((stop1_geom, stop1, SourceOIDkey, 1))
            cur.insertRow((stop2_geom, stop2, SourceOIDkey, 2))

    if badStops:
        badStops = list(set(badStops))
        arcpy.AddWarning("Your stop_times.txt lists times for the following \
stops which are not included in your stops.txt file. Schedule information for \
these stops will be ignored. " + unicode(badStops))

    # Remove these entries from the linefeatures dictionary so it doesn't cause false records later
    if badkeys:
        badkeys = list(set(badkeys))
        for key in badkeys:
            del linefeature_dict[key]

# ----- Generate lines between all stops (for the final output) -----

    arcpy.management.PointsToLine(outStopPairsFC, outLinesFC, "pair_id", "sequence")
    if not combine_corridors:
        arcpy.management.AddField(outLinesFC, "route_id", "TEXT")

    # We don't need the points for anything anymore, so delete them.
    arcpy.management.Delete(outStopPairsFC)
    arcpy.management.Delete(outStopsFC)

    # Clean up lines with 0 length.  They will just produce build errors and
    # are not valuable for the network dataset in any other way.
    expression = """"Shape_Length" = 0"""
    with arcpy.da.UpdateCursor(outLinesFC, ["pair_id"], expression) as cur2:
        for row in cur2:
            del linefeature_dict[row[0]]
            cur2.deleteRow()

    if not combine_corridors:
        with arcpy.da.UpdateCursor(outLinesFC, ["pair_id", "route_id"]) as cur4:
            for row in cur4:
                row[1] = row[0].split(" , ")[2]
                cur4.updateRow(row)


# ----- Finish up. -----

    conn.close()

    arcpy.AddMessage("Finished!")
    arcpy.AddMessage("Your transit lines template feature class is:")
    arcpy.AddMessage("- " + outLinesFC)

except CustomError:
    arcpy.AddError("Failed to generate transit lines.")
    pass

except:
    arcpy.AddError("Failed to generate transit lines.")
    raise

finally:
    # Reset the overwrite output to the user's original setting..
    arcpy.env.overwriteOutput = OverwriteOutput