###############################################################################
## Tool name: Generate GTFS Route Shapes
## Step 1: Generate Shapes on Map
## Creator: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 11 January 2018
###############################################################################
''' This tool generates a feature class of route shapes for GTFS data.
The route shapes show the geographic paths taken by the transit vehicles along
the streets or tracks. Each unique sequence of stop visits in the GTFS data will
get its own shape in the output feature class.  Alternatively, the user can 
select existing shapes from shapes.txt to draw in the map. The user can edit the output
feature class shapes as desired.  Then, the user should use this feature class
and the other associated files in the output GDB as input to Step 2 in order
to create updated .txt files for use in the GTFS dataset.'''
################################################################################
'''Copyright 2018 Esri
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

import sqlite3, operator, os, re, csv, itertools, sys
import numpy as np
import AGOLRouteHelper
import arcpy

class CustomError(Exception):
    pass


# User input variables, set in the scripts that get input from the GUI
inGTFSdir = None
outDir = None
outGDBName = None
in_route_type_Street = None
in_route_type_Straight = None
inNetworkDataset = None
impedanceAttribute = None
driveSide = None
UTurn_input = None
restrictions = None
useJunctions = None
useBearing = None
BearingTol = None
CurbApproach = None
MaxAngle = None
useNA = None
useAGOL = None
badStops = []

# Global derived variables
ProductName = None
outGDB = None
SQLDbase = None
outSequencePoints = None
outRoutesfc = None
NoRouteGenerated = None

# Other global variables
# Use WGS coordinates because that's what the GTFS spec uses
WGSCoords = "GEOGCS['GCS_WGS_1984',DATUM['D_WGS_1984', \
SPHEROID['WGS_1984',6378137.0,298.257223563]], \
PRIMEM['Greenwich',0.0],UNIT['Degree',0.0174532925199433]]; \
-400 -400 1000000000;-100000 10000;-100000 10000; \
8.98315284119522E-09;0.001;0.001;IsHighPrecision"
WGSCoords_WKID = 4326

# Explicitly set max allowed length for route_desc. Some agencies are wordy.
max_route_desc_length = 250


def RunStep1_existing_shapestxt(shapelist):
    '''Create feature classes of shapes and relevant stop sequences using an existing shapes.txt file
so the user can edit existing shapes.'''

    try:
        
        # It's okay to overwrite stuff.
        orig_overwrite = arcpy.env.overwriteOutput
        arcpy.env.overwriteOutput = True
        
        # Check that the user's software version can support this tool
        check_Arc_version()

        # Set up the outputs
        global outGDBName
        if not outGDBName.lower().endswith(".gdb"):
            outGDBName += ".gdb"
        outGDB = os.path.join(outDir, outGDBName)
        outSequencePointsName = "Stops_wShapeIDs"
        outSequencePoints = os.path.join(outGDB, outSequencePointsName)
        outShapesFCName = "Shapes"
        outShapesFC = os.path.join(outGDB, outShapesFCName)
        SQLDbase = os.path.join(outGDB, "SQLDbase.sql")

        # Create output geodatabase
        arcpy.management.CreateFileGDB(outDir, outGDBName)


    # ----- SQLize the GTFS data -----

        try:
            # These are the GTFS files we need to use in this tool, so we will add them to a SQL database.
            files_to_sqlize = ["stops", "stop_times", "trips", "routes", "shapes"]
            connect_to_sql(SQLDbase)
            SQLize_GTFS(files_to_sqlize)
        except:
            arcpy.AddError("Error SQLizing the GTFS data.")
            raise


    # ----- Add shapes to feature class -----
        
        # Find all the route_ids and associated info
        get_route_info()
        
        # Make a feature class for shapes
        arcpy.management.CreateFeatureclass(outGDB, outShapesFCName, "POLYLINE", '', '', '', WGSCoords)
        arcpy.management.AddField(outShapesFC, "shape_id", "TEXT")
        arcpy.management.AddField(outShapesFC, "route_id", "TEXT")
        arcpy.management.AddField(outShapesFC, "route_short_name", "TEXT")
        arcpy.management.AddField(outShapesFC, "route_long_name", "TEXT")
        arcpy.management.AddField(outShapesFC, "route_desc", "TEXT", "", "", max_route_desc_length)
        arcpy.management.AddField(outShapesFC, "route_type", "SHORT")
        arcpy.management.AddField(outShapesFC, "route_type_text", "TEXT")

        # Populate shapes feature class with user's selected shapes from shapes.txt
        with arcpy.da.InsertCursor(outShapesFC, ["SHAPE@", "shape_id", "route_id",
                      "route_short_name", "route_long_name", "route_desc",
                      "route_type", "route_type_text"]) as cur:
            for shape in shapelist:
                # Get the route ids that have this shape.
                # There should probably be a 1-1 relationship, but not sure.
                # We're just adding route info to the shapes feature class for readability
                shapesroutesfetch = '''
                    SELECT DISTINCT route_id FROM trips WHERE shape_id='%s'
                    ;''' % shape
                c.execute(shapesroutesfetch)
                weresome = False
                for route in c:
                    weresome = True
                    append_existing_shape_to_fc(shape, cur, route[0])
                if not weresome:
                    # No trips actually use this shape, so skip adding route info
                    arcpy.AddWarning("shape_id %s is not used by any \
trips in your trips.txt file.  You can still update this shape, but this might be an indication of problems in your GTFS dataset." % shape)
                    append_existing_shape_to_fc(shape, cur)

            
    # ----- Find the sequences of stops associated with these shapes -----
        
        # Find the lat/lon coordinates of all stops
        get_stop_lat_lon()
        
        # Create a feature class for stops associated with the selected shapes - for reference and for input to Step 2
        arcpy.management.CreateFeatureclass(outGDB, outSequencePointsName, "POINT", "", "", "", WGSCoords)
        arcpy.management.AddField(outSequencePoints, "stop_id", "TEXT")
        arcpy.management.AddField(outSequencePoints, "shape_id", "TEXT")
        arcpy.management.AddField(outSequencePoints, "sequence", "LONG")
        
        # Populate the feature class with stops in the correct sequence
        badStops = []
        with arcpy.da.InsertCursor(outSequencePoints, ["SHAPE@X", "SHAPE@Y", "shape_id", "sequence", "stop_id"]) as cur:
            for shape_id in shapelist:
                # Trips designated with this shape_id
                trips_for_shape = get_trips_with_shape_id(shape_id)
                # The sequence of stops visited by each of these trips.  There should probably be only one unique sequence associated with each shape_id, but not sure.
                stop_sequences_for_shape = []
                for trip in trips_for_shape:
                    stop_sequences_for_shape.append(get_trip_stop_sequence(trip))
                stop_sequences_for_shape = list(set(stop_sequences_for_shape))
                # Add each stop in the sequence to the feature class
                for sequence in stop_sequences_for_shape: 
                    sequence_num = 1
                    for stop in sequence:
                        try:
                            stop_lat = stoplatlon_dict[stop][0]
                            stop_lon = stoplatlon_dict[stop][1]
                        except KeyError:
                            badStops.append(stop)
                            sequence_num += 1
                            continue
                        cur.insertRow((float(stop_lon), float(stop_lat), shape_id, sequence_num, stop))
                        sequence_num += 1
               
        if badStops:
            badStops = sorted(list(set(badStops)))
            messageText = "Your stop_times.txt file lists times for the following stops which are not included in your stops.txt file. These stops have been ignored. "
            if ProductName == "ArcGISPro":
                messageText += str(badStops)
            else:
                messageText += unicode(badStops)
            arcpy.AddWarning(messageText)


        # Set output
        arcpy.SetParameterAsText(4, outShapesFC)
        arcpy.SetParameterAsText(5, outSequencePoints)

        arcpy.AddMessage("Done!")
        arcpy.AddMessage("Output generated in " + outGDB + ":")
        arcpy.AddMessage("- Shapes")
        arcpy.AddMessage("- Stops_wShapeIDs")

    except CustomError:
        arcpy.AddError("Error generating shapes feature class from existing shapes.txt file.")
        pass
    except:
        raise

    finally:
        arcpy.env.overwriteOutput = orig_overwrite


# ----- Main part of script -----
def RunStep1():
    '''Run Step 1 - Generate feature class of shapes for input to Step 2, which
    generates the actual GTFS shapes.txt file.'''

    try:
        
        # It's okay to overwrite stuff.
        orig_overwrite = arcpy.env.overwriteOutput
        arcpy.env.overwriteOutput = True
        
        # Check that the user's software version can support this tool
        check_Arc_version(useAGOL, useNA)

        # Check out the Network Analyst extension license
        if useNA:
            if arcpy.CheckExtension("Network") == "Available":
                arcpy.CheckOutExtension("Network")
            else:
                arcpy.AddError("The Network Analyst license is unavailable.")
                raise CustomError
        
        if useAGOL:
            # Get the user's ArcGIS Online token. They must already be signed in to use this tool.
            # That way we don't need to collect a username and password.
            # But, you can't run this script in standalone python.
            AGOLRouteHelper.get_token()
            if AGOLRouteHelper.token == None:
                arcpy.AddError("Unable to retrieve token for ArcGIS Online. To use this tool, \
you must be signed in to ArcGIS Online with an account that has routing privileges and credits. \
Talk to your organization's ArcGIS Online administrator for assistance.")
                raise CustomError
            arcpy.AddMessage("Successfully retrieved ArcGIS Online token.")


    # ----- Set up the run, fix some inputs -----

        # Input format is a string separated by a ; ("0 - Tram, Streetcar, Light rail;3 - Bus;5 - Cable car")
        global route_type_Straight_textlist, route_type_Street_textlist, route_types_Straight, route_types_Street
        if in_route_type_Street:
            route_type_Street_textlist = in_route_type_Street.split(";")
        else:
            route_type_Street_textlist = []
        if in_route_type_Straight:
            route_type_Straight_textlist = in_route_type_Straight.split(";")
        else:
            route_type_Straight_textlist = []
        route_types_Street = []
        route_types_Straight = []
        for rtype in route_type_Street_textlist:
            route_types_Street.append(int(rtype.split(" - ")[0].strip('\'')))
        for rtype in route_type_Straight_textlist:
            route_types_Straight.append(int(rtype.split(" - ")[0].strip('\'')))

        # Set curb approach based on side of road vehicles drive on
        global CurbApproach
        driveSide = "Right"
        if driveSide == "Right":
            CurbApproach = 1 #"Right side of vehicle"
        else:
            CurbApproach = 2 #"Left side of vehcle"

        # Uturn policy is explained here: http://resources.arcgis.com/en/help/main/10.1/index.html#//00480000000n000000
        global UTurns
        if UTurn_input == "Allowed anywhere":
            UTurns = "ALLOW_UTURNS"
        elif UTurn_input == "Allowed only at intersections and dead ends":
            UTurns = "ALLOW_DEAD_ENDS_AND_INTERSECTIONS_ONLY"
        elif UTurn_input == "Allowed only at dead ends":
            UTurns = "ALLOW_DEAD_ENDS_ONLY"
        elif UTurn_input == "Not allowed anywhere":
            UTurns = "NO_UTURNS"

        # Sometimes, when locating stops, they snap to the closest street, which is
        # actually a side street instead of the main road where the stop is really
        # located. The Route results consequently have a lot of little loops or
        # spikes sticking out the side.  Sometimes we can improve results by
        # locating stops on network junctions instead of streets. Sometimes this
        # messes up the results, however, but we allow the users to try.
        # Note: As of January 2017, I have removed the useJunctions option from 
        # the tool because it never really worked that great, and the useBearing
        # method is a dramatic improvement.  I'm leaving this code here in case
        # someone wants it again.
        global search_criteria
        if useJunctions:
            search_criteria = []
            NAdesc = arcpy.Describe(inNetworkDataset)
            for source in NAdesc.sources:
                if source.sourceType in ["JunctionFeature", "SystemJunction"]:
                    search_criteria.append([source.name, "SHAPE"])
                else:
                    search_criteria.append([source.name, "NONE"])
        else:
            search_criteria = "#"

        # Initialize a list for shapes that couldn't be generated from the route solver
        global NoRouteGenerated
        NoRouteGenerated = []

        # Set up the outputs
        global outGDB, outSequencePoints, outRoutesfc, outRoutesfcName, SQLDbase, outGDBName
        if not outGDBName.lower().endswith(".gdb"):
            outGDBName += ".gdb"
        outGDB = os.path.join(outDir, outGDBName)
        outSequencePointsName = "Stops_wShapeIDs"
        outSequencePoints = os.path.join(outGDB, outSequencePointsName)
        outRoutesfcName = "Shapes"
        outRoutesfc = os.path.join(outGDB, outRoutesfcName)
        SQLDbase = os.path.join(outGDB, "SQLDbase.sql")

        # Create output geodatabase
        arcpy.management.CreateFileGDB(outDir, outGDBName)


    # ----- SQLize the GTFS data -----

        try:
            # These are the GTFS files we need to use in this tool, so we will add them to a SQL database.
            files_to_sqlize = ["stops", "stop_times", "trips", "routes"]
            connect_to_sql(SQLDbase)
            SQLize_GTFS(files_to_sqlize)
        except:
            arcpy.AddError("Error SQLizing the GTFS data.")
            raise


    # ----- Get lat/long for all stops and add to dictionary. Calculate location fields if necessary. -----

        get_stop_lat_lon()
        
        # Grab the pointGeometry objects for each stop
        if useBearing:
            get_stop_geom()

        # Calculate location fields for the stops and save them to a dictionary.
        if useNA and not useBearing:
            calculate_stop_location_fields()


    # ----- Make dictionary of route info -----

        get_route_info()


    # ----- Match trip_ids with route_ids -----

        arcpy.AddMessage("Collecting GTFS trip information...")

        get_trip_route_info()


    # ----- Create ordered stop sequences -----

        get_unique_stop_sequences()


    # ----- Figure out which routes go with which shapes and update trips table -----

        global shape_route_dict
        shape_route_dict = {}
        for shape in shape_trip_dict:
            shaperoutes = []
            for trip in shape_trip_dict[shape]:
                shaperoutes.append(trip_route_dict[trip])
                # Update the trips table with the shape assigned to the trip
                updatetripstablestmt = "UPDATE trips SET shape_id='%s' WHERE trip_id='%s'" % (shape, trip)
                c.execute(updatetripstablestmt)
            conn.commit()
            shaperoutesset = set(shaperoutes)
            for route in shaperoutesset:
                shape_route_dict.setdefault(shape, []).append(route)
        conn.close()


    # ----- Generate street and straight routes -----

        # Create a points feature class for the stops to input for Routes
        # We'll save this so users can see the stop sequences with the shape_ids.
        arcpy.management.CreateFeatureclass(outGDB, outSequencePointsName, "POINT", "", "", "", WGSCoords)
        arcpy.management.AddField(outSequencePoints, "stop_id", "TEXT")
        arcpy.management.AddField(outSequencePoints, "shape_id", "TEXT")
        arcpy.management.AddField(outSequencePoints, "sequence", "LONG")
        if useNA and not useBearing:
            # We will pre-calculate location fields for faster loading if we're not using Bearing
            arcpy.management.AddField(outSequencePoints, "CurbApproach", "SHORT")
            arcpy.management.AddField(outSequencePoints, "SourceID", "LONG")
            arcpy.management.AddField(outSequencePoints, "SourceOID", "LONG")
            arcpy.management.AddField(outSequencePoints, "PosAlong", "DOUBLE")
            arcpy.management.AddField(outSequencePoints, "SideOfEdge", "LONG")
        if useBearing:
            # If we're using Bearing, add the relevant fields
            arcpy.management.AddField(outSequencePoints, "CurbApproach", "SHORT")
            arcpy.management.AddField(outSequencePoints, "Bearing", "DOUBLE")
            arcpy.management.AddField(outSequencePoints, "BearingTol", "DOUBLE")

        # Flag for whether we created the output fc in from Routes or if we need
        # to create it in the straight-line part
        Created_Street_Output = False

        # Generate shapes following the streets
        if route_types_Street:
            if useNA:
                Generate_Shapes_Street()
                Created_Street_Output = True
            elif useAGOL:
                Generate_Shapes_AGOL()
                Created_Street_Output = True

        # Generate routes as straight lines between stops
        if route_types_Straight or NoRouteGenerated:
            Generate_Shapes_Straight(Created_Street_Output)
            
        global badStops
        if badStops:
            badStops = sorted(list(set(badStops)))
            messageText = "Your stop_times.txt file lists times for the following stops which are not included in your stops.txt file. These stops have been ignored. "
            if ProductName == "ArcGISPro":
                messageText += str(badStops)
            else:
                messageText += unicode(badStops)
            arcpy.AddWarning(messageText)


    # ----- Add route information to output feature class -----

        arcpy.AddMessage("Adding GTFS route information to output shapes feature class")

        # Explicitly set max allowed length for route_desc. Some agencies are wordy.
        max_route_desc_length = 250

        arcpy.management.AddField(outRoutesfc, "shape_id", "TEXT")
        arcpy.management.AddField(outRoutesfc, "route_id", "TEXT")
        arcpy.management.AddField(outRoutesfc, "route_short_name", "TEXT")
        arcpy.management.AddField(outRoutesfc, "route_long_name", "TEXT")
        arcpy.management.AddField(outRoutesfc, "route_desc", "TEXT", "", "", max_route_desc_length)
        arcpy.management.AddField(outRoutesfc, "route_type", "SHORT")
        arcpy.management.AddField(outRoutesfc, "route_type_text", "TEXT")

        with arcpy.da.UpdateCursor(outRoutesfc, ["Name", "shape_id", "route_id",
                      "route_short_name", "route_long_name", "route_desc",
                      "route_type", "route_type_text"]) as ucursor:
            for row in ucursor:
                shape_id = row[0]
                route_id = shape_route_dict[shape_id][0]
                route_short_name = RouteDict[route_id][1]
                route_long_name = RouteDict[route_id][2]
                route_desc = RouteDict[route_id][3]
                route_type = RouteDict[route_id][4]
                route_type_text = RouteDict[route_id][8]
                row[0] = row[0]
                row[1] = shape_id
                row[2] = route_id
                row[3] = route_short_name
                row[4] = route_long_name
                row[5] = route_desc[0:max_route_desc_length] if route_desc else route_desc #logic handles the case where it's empty
                row[6] = route_type
                row[7] = route_type_text
                ucursor.updateRow(row)


    # ----- Finish things up -----

        # Add output to map.
        if useNA:
            arcpy.SetParameterAsText(12, outRoutesfc)
            arcpy.SetParameterAsText(13, outSequencePoints)
        elif useAGOL:
            arcpy.SetParameterAsText(8, outRoutesfc)
            arcpy.SetParameterAsText(9, outSequencePoints)
        else:
            arcpy.SetParameterAsText(4, outRoutesfc)
            arcpy.SetParameterAsText(5, outSequencePoints)

        arcpy.AddMessage("Done!")
        arcpy.AddMessage("Output generated in " + outGDB + ":")
        arcpy.AddMessage("- Shapes")
        arcpy.AddMessage("- Stops_wShapeIDs")

    except CustomError:
        arcpy.AddError("Error generating shapes feature class from GTFS data.")
        pass

    except:
        raise

    finally:
        arcpy.env.overwriteOutput = orig_overwrite


def SQLize_GTFS(files_to_sqlize):
    ''' SQLize the GTFS data'''
    arcpy.AddMessage("SQLizing the GTFS data...")
    arcpy.AddMessage("(This step might take a while for large datasets.)")

    # Schema of standard GTFS, with a 1 or 0 to indicate if the field is required
    sql_schema = {
            "stops" : {
                    "stop_id" :     ("TEXT", 1),
                    "stop_code" :   ("TEXT", 0),
                    "stop_name" :   ("TEXT", 1),
                    "stop_desc" :   ("TEXT", 0),
                    "stop_lat" :    ("REAL", 1),
                    "stop_lon" :    ("REAL", 1),
                    "zone_id" :     ("TEXT", 0),
                    "stop_url" :    ("TEXT", 0),
                    "location_type" : ("INTEGER", 0),
                    "parent_station" : ("TEXT", 0),
                    "stop_timezone" :   ("TEXT", 0),
                    "wheelchair_boarding": ("INTEGER", 0)
                } ,
            "stop_times" : {
                    "trip_id" :     ("TEXT", 1),
                    "arrival_time" :    ("TEXT", 1),
                    "departure_time" :  ("TEXT", 1),
                    "stop_id" :         ("TEXT", 1),
                    "stop_sequence" :   ("INTEGER", 1),
                    "stop_headsign" :   ("TEXT", 0),
                    "pickup_type" :     ("INTEGER", 0),
                    "drop_off_type" :   ("INTEGER", 0),
                    "shape_dist_traveled" : ("REAL", 0)
                } ,
            "trips" : {
                    "route_id" :    ("TEXT", 1),
                    "service_id" :  ("TEXT", 1),
                    "trip_id" :     ("TEXT", 1),
                    "trip_headsign" :   ("TEXT", 0),
                    "trip_short_name" :     ("TEXT", 0),
                    "direction_id" : ("INTEGER", 0),
                    "block_id" :    ("TEXT", 0),
                    "shape_id" :    ("TEXT", 0),
                    "wheelchair_accessible" : ("INTEGER", 0)
                } ,
            "routes" : {
                    "route_id" :    ("TEXT", 1),
                    "agency_id" :  ("TEXT", 0),
                    "route_short_name": ("TEXT", 0),
                    "route_long_name":  ("TEXT", 0),
                    "route_desc":   ("TEXT", 0),
                    "route_type":   ("INTEGER", 1),
                    "route_url":    ("TEXT", 0),
                    "route_color":  ("TEXT", 0),
                    "route_text_color": ("TEXT", 0),
                } ,
            "shapes" : {
                "shape_id":     ("TEXT", 1),
                "shape_pt_lat": ("REAL", 1),
                "shape_pt_lon": ("REAL", 1),
                "shape_pt_sequence":    ("INTEGER", 1),
                "shape_dist_traveled":  ("REAL", "NULL")
            }
        }


    # SQLize each file we care about, using its own schema and ordering
    for GTFSfile in files_to_sqlize:
        # Note: a check for existance of each required file is in tool validation

        # Open the file for reading
        fname = os.path.join(inGTFSdir, GTFSfile) + ".txt"
        if ProductName == "ArcGISPro":
            f = open(fname, encoding="utf-8-sig")
        else:
            f = open(fname)
        reader = csv.reader(f)

        # Put everything in utf-8 to handle BOMs and weird characters.
        # Eliminate blank rows (extra newlines) while we're at it.
        if ProductName == "ArcGISPro":
            reader = ([x.strip() for x in r] for r in reader if len(r) > 0)
        else:
            reader = ([x.decode('utf-8-sig').strip() for x in r] for r in reader if len(r) > 0)

        # First row is column names:
        columns = [name.strip() for name in next(reader)]

        # Set up the table schema
        schema = ""
        for col in columns:
            try:
                # Read the data type from the GTFS schema dictionary
                schema = schema + col + " " + sql_schema[GTFSfile][col][0] + ", "
            except KeyError:
                # If they're using a custom field, preserve it and assume it's text.
                schema = schema + col + " TEXT, "
        schema = schema[:-2]

        # Make sure file has all the required fields
        for col in sql_schema[GTFSfile]:
            if sql_schema[GTFSfile][col][1] == 1:
                if not col in columns:
                    arcpy.AddError("GTFS file " + GTFSfile + ".txt is missing required field '" + col + "'.")
                    raise CustomError

        # Make sure lat/lon values are valid
        if GTFSfile == "stops":
            rows = check_latlon_fields(reader, columns, "stop_lat", "stop_lon", "stop_id", fname)
        elif GTFSfile == "shapes":
            rows = check_latlon_fields(reader, columns, "shape_pt_lat", "shape_pt_lon", "shape_id", fname)
        # Otherwise just leave them as they are
        else:
            rows = reader

        # Create the SQL table
        c.execute("DROP TABLE IF EXISTS %s;" % GTFSfile)
        create_stmt = "CREATE TABLE %s (%s);" % (GTFSfile, schema)
        c.execute(create_stmt)
        conn.commit()

        # Add the data to the table
        values_placeholders = ["?"] * len(columns)
        c.executemany("INSERT INTO %s (%s) VALUES (%s);" %
                            (GTFSfile,
                            ",".join(columns),
                            ",".join(values_placeholders))
                        , rows)
        conn.commit()

        # If optional columns in routes weren't included in the original data, add them so we don't encounter errors later.
        if GTFSfile == "routes":
            for col in sql_schema["routes"]:
                if not col in columns:
                    c.execute("ALTER TABLE routes ADD COLUMN %s %s" % (col, sql_schema[GTFSfile][col][0]))
                    conn.commit()

        # If our original data did not have a shape-related fields, add them.
        if GTFSfile == "trips":
            if 'shape_id' not in columns:
                if "shapes" in files_to_sqlize:
                    arcpy.AddError("Your trips.txt file does not contain a shape_id field. In order to update your shapes.txt file, \
you must first assign each trip_id in trips.txt a valid shape_id.  If you do not have this information, it is recommended that you \
create a new shapes.txt file from scratch rather than attempting to update your existing one.")
                    raise CustomError
                c.execute("ALTER TABLE trips ADD COLUMN shape_id TEXT")
                conn.commit()
        if GTFSfile == "stop_times":
            if 'shape_dist_traveled' not in columns:
                if "shapes" in files_to_sqlize:
                    arcpy.AddWarning("Your stop_times.txt file does not contain a shape_dist_traveled field. When you run Step 2 of this tool, \
a shape_dist_traveled field will be added, and it will be populated with valid values for the shape(s) you have chosen to update.  However, the \
field will remain blank for all other shapes.")
                c.execute("ALTER TABLE stop_times ADD COLUMN shape_dist_traveled REAL")
                conn.commit()
        if GTFSfile == "shapes":
            if 'shape_dist_traveled' not in columns:
                arcpy.AddWarning("Your shapes.txt file does not contain a shape_dist_traveled field. When you run Step 2 of this tool, \
a shape_dist_traveled field will be added, and it will be populated with valid values for the shape(s) you have chosen to update.  However, the \
field will remain blank for all other shapes.")
                c.execute("ALTER TABLE shapes ADD COLUMN shape_dist_traveled REAL")
                conn.commit()

        f.close ()

    #  Generate indices
    c.execute("CREATE INDEX stoptimes_index_tripIDs ON stop_times (trip_id);")
    c.execute("CREATE INDEX trips_index_tripIDs ON trips (trip_id);")
    if "shapes" in files_to_sqlize:
        c.execute("CREATE INDEX trips_index_shapeIDs ON trips (shape_id);")
        c.execute("CREATE INDEX shapes_index_shapeIDs ON shapes (shape_id, shape_pt_sequence);")


def check_latlon_fields(rows, col_names, lat_col_name, lon_col_name, id_col_name, fname):
    '''Ensure lat/lon fields are valid'''
    
    def check_latlon_cols(row):
        id_val = row[col_names.index(id_col_name)]
        lat = row[col_names.index(lat_col_name)]
        lon = row[col_names.index(lon_col_name)]
        try:
            lat_float = float(lat)
        except ValueError:
            msg = '%s "%s" in %s contains an invalid non-numerical value \
for the %s field: "%s". Please double-check all lat/lon values in your \
%s file.' % (id_col_name, id_val, fname, lat_col_name, lat, fname)
            arcpy.AddError(msg)
            raise CustomError
        try:
            stop_lon_float = float(lon)
        except ValueError:
            msg = '%s "%s" in %s contains an invalid non-numerical value \
for the %s field: "%s". Please double-check all lat/lon values in your \
%s file.' % (id_col_name, id_val, fname, lon_col_name, lon, fname)
            arcpy.AddError(msg)
            raise CustomError
        if not (-90.0 <= lat_float <= 90.0):
            msg = '%s "%s" in %s contains an invalid value outside the \
range (-90, 90) the %s field: "%s". %s values must be in valid WGS 84 \
coordinates.  Please double-check all lat/lon values in your %s file.\
' % (id_col_name, id_val, fname, lat_col_name, lat, lat_col_name, fname)
            arcpy.AddError(msg)
            raise CustomError
        if not (-180.0 <= stop_lon_float <= 180.0):
            msg = '%s "%s" in %s contains an invalid value outside the \
range (-180, 180) the %s field: "%s". %s values must be in valid WGS 84 \
coordinates.  Please double-check all lat/lon values in your %s file.\
' % (id_col_name, id_val, fname, lon_col_name, lon, lon_col_name, fname)
            arcpy.AddError(msg)
            raise CustomError
        return row
    if ProductName == "ArcGISPro":
        return map(check_latlon_cols, rows)
    else:
        return itertools.imap(check_latlon_cols, rows)


def Generate_Shapes_Street():
    '''Generate preliminary shapes for each route by calculating the optimal
    route along the network with the Network Analyst Route solver.'''

    arcpy.AddMessage("Generating on-street route shapes for routes of the following types, if they exist in your data:")
    for rtype in route_type_Street_textlist:
        arcpy.AddMessage(rtype)
    arcpy.AddMessage("(This step may take a while for large GTFS datasets.)")


    # ----- Writing stops in sequence to feature class for Route input -----

    arcpy.AddMessage("- Preparing stops")

    # Extract only the sequences we want to make street-based shapes for.
    sequences_Streets = []
    for sequence in sequence_shape_dict:
        shape_id = sequence_shape_dict[sequence]
        route_id = sequence[0]
        route_type = RouteDict[route_id][4]
        if route_type in route_types_Street:
            sequences_Streets.append(sequence)

    # Chunk the sequences so we don't run out of memory in the Route solver.
    ChunkSize = 100
    sequences_Streets_chunked = []
    for i in range(0, len(sequences_Streets), ChunkSize):
        sequences_Streets_chunked.append(sequences_Streets[i:i+ChunkSize])

    # Huge loop over each chunk.
    totchunks = len(sequences_Streets_chunked)
    chunkidx = 1
    global NoRouteGenerated
    global badStops
    unlocated_stops = []
    for chunk in sequences_Streets_chunked:

        arcpy.AddMessage("- Calculating Routes part %s of %s." % (str(chunkidx), str(totchunks)))
        chunkidx += 1

        InputRoutePoints = arcpy.management.CreateFeatureclass(outGDB, "TempInputRoutePoints", "POINT", outSequencePoints, "", "", WGSCoords)

        # Add the StopPairs table to the feature class.
        shapes_in_chunk = []
        
        if useBearing:
            # Calculate the bearing value for each stop and insert
            with arcpy.da.InsertCursor(InputRoutePoints, ["SHAPE@", "shape_id", "sequence", "CurbApproach", "stop_id", "Bearing", "BearingTol"]) as cur:
                for sequence in chunk:
                    bearingdict = getBearingsForSequence(sequence[1])
                    shape_id = sequence_shape_dict[sequence]
                    shapes_in_chunk.append(shape_id)
                    sequence_num = 1
                    for stop in sequence[1]:
                        try:
                            stopGeom = stopgeom_dict[stop]
                            try:
                                Bearing = bearingdict[stop]
                            except KeyError:
                                # If we couldn't calculate the bearing for some reason, just leave it as null, and Add Locations will locate it normally.
                                Bearing = None
                        except KeyError:
                            badStops.append(stop)
                            sequence_num += 1
                            continue
                        cur.insertRow((stopGeom, shape_id, sequence_num, CurbApproach, stop, Bearing, BearingTol))
                        sequence_num += 1

        else:
            # Insert shapes and location fields
            with arcpy.da.InsertCursor(InputRoutePoints, ["SHAPE@X", "SHAPE@Y", "shape_id", "sequence", "CurbApproach", "stop_id", "SourceID", "SourceOID", "PosAlong", "SideOfEdge"]) as cur:
                for sequence in chunk:
                    shape_id = sequence_shape_dict[sequence]
                    shapes_in_chunk.append(shape_id)
                    sequence_num = 1
                    for stop in sequence[1]:
                        try:
                            stop_lat = stoplatlon_dict[stop][0]
                            stop_lon = stoplatlon_dict[stop][1]
                            SourceID = stoplocfielddict[stop][0]
                            SourceOID = stoplocfielddict[stop][1]
                            PosAlong = stoplocfielddict[stop][2]
                            SideOfEdge = stoplocfielddict[stop][3]
                        except KeyError:
                            badStops.append(stop)
                            sequence_num += 1
                            continue
                        cur.insertRow((float(stop_lon), float(stop_lat), shape_id, sequence_num, CurbApproach, stop, SourceID, SourceOID, PosAlong, SideOfEdge))
                        sequence_num += 1


        # ----- Generate routes ------

        # Note: The reason we use hierarchy is to ensure that the entire network doesn't gets searched
        # if a route can't be found between two points
        RLayer = arcpy.na.MakeRouteLayer(inNetworkDataset, "TransitShapes", impedanceAttribute,
                    find_best_order="USE_INPUT_ORDER",
                    UTurn_policy=UTurns,
                    restriction_attribute_name=restrictions,
                    hierarchy="USE_HIERARCHY",
                    output_path_shape="TRUE_LINES_WITH_MEASURES").getOutput(0)

        # To refer to the Route sublayers, get the sublayer names.  This is essential for localization.
        naSubLayerNames = arcpy.na.GetNAClassNames(RLayer)
        stopsSubLayer = naSubLayerNames["Stops"]

        # Map fields to ensure that each shape gets its own route.
        fieldMappings = arcpy.na.NAClassFieldMappings(RLayer, stopsSubLayer, True)
        fieldMappings["RouteName"].mappedFieldName = "shape_id"
        fieldMappings["CurbApproach"].mappedFieldName = "CurbApproach"
        if not useBearing:
            fieldMappings["SourceID"].mappedFieldName = "SourceID"
            fieldMappings["SourceOID"].mappedFieldName = "SourceOID"
            fieldMappings["PosAlong"].mappedFieldName = "PosAlong"
            fieldMappings["SideOfEdge"].mappedFieldName = "SideOfEdge"
        # Note: Bearing and BearingTol fields are magically used without explicit field mapping
        # See http://desktop.arcgis.com/en/arcmap/latest/extensions/network-analyst/bearing-and-bearingtol-what-are.htm

        arcpy.na.AddLocations(RLayer, stopsSubLayer, InputRoutePoints, fieldMappings,
                    sort_field="sequence",
                    append="CLEAR")

        # Use a simplification tolerance on Solve to reduce the number of vertices
        # in the output lines (to make shapes.txt files smaller and to make the
        # linear referencing quicker.
        simpTol = "2 Meters"
        try:
            SolvedLayer = arcpy.na.Solve(RLayer, ignore_invalids=True, simplification_tolerance=simpTol)
        except:
            arcpy.AddWarning("Unable to create on-street Routes because the Solve failed.")
            arcpy.AddWarning("Solve warning messages:")
            arcpy.AddWarning(arcpy.GetMessages(1))
            arcpy.AddWarning("Solve error messages:")
            arcpy.AddWarning(arcpy.GetMessages(2))
            NoRouteGenerated += shapes_in_chunk
            continue

        # If any of the routes couldn't be solved, they will leave a warning.
        # Save the shape_ids so we can generate straight-line routes for them.
        # Similarly, if any stops were skipped because they were unlocated, they will leave a warning.
        warnings = arcpy.GetMessages(1)
        warninglist = warnings.split("\n")
        for w in warninglist:
            if re.match('No route for ', w):
                thingsInQuotes = re.findall('"(.+?)"', w)
                NoRouteGenerated.append(thingsInQuotes[0])
            elif re.search(' is unlocated.', w):
                thingsInQuotes = re.findall('"(.+?)"', w)
                unlocated_stops.append(thingsInQuotes[0])

        # Make layer objects for each sublayer we care about.
        if ProductName == "ArcGISPro":
            RoutesLayer = RLayer.listLayers(naSubLayerNames["Routes"])[0]
        else:
            RoutesLayer = arcpy.mapping.ListLayers(RLayer, naSubLayerNames["Routes"])[0]


    # ----- Save routes to feature class -----

        # Uncomment this if you want to save the Stops layer from Route.
        ##StopsLayer = arcpy.mapping.ListLayers(RLayer, stopsSubLayer)[0]
        ##arcpy.CopyFeatures_management(StopsLayer, os.path.join(outGDB, "TestOutStops"))

        # Save the output routes.
        if not arcpy.Exists(outRoutesfc):
            arcpy.management.CopyFeatures(RoutesLayer, outRoutesfc)
        else:
            arcpy.management.Append(RoutesLayer, outRoutesfc)

        arcpy.management.Delete(SolvedLayer)

        # Add the stop sequences to the final output FC and delete the temporary one.
        arcpy.management.Append(InputRoutePoints, outSequencePoints)
        arcpy.management.Delete(InputRoutePoints)

    if NoRouteGenerated:
        arcpy.AddWarning("On-street route shapes for the following shape_ids could \
not be generated.  Straight-line route shapes will be generated for these \
shape_ids instead:")
        arcpy.AddWarning(sorted(NoRouteGenerated))
        arcpy.AddWarning("If you are unhappy with this result, try re-running your \
analysis with a different u-turn policy and/or network restrictions, and check your \
network dataset for connectivity problems.")

    if unlocated_stops:
        unlocated_stops = sorted(list(set(unlocated_stops)))
        arcpy.AddWarning("The following stop_ids could not be located on your network dataset and were skipped when route shapes were generated.  \
If you are unhappy with this result, please double-check your stop_lat and stop_lon values in stops.txt and your network dataset geometry \
to make sure everything is correct.")


def Generate_Shapes_AGOL():
    '''Generate preliminary shapes for each route by calculating the optimal
    route along the network using the ArcGIS Online route services.'''

    arcpy.AddMessage("Generating on-street route shapes via ArcGIS Online for routes of the following types, if they exist in your data:")
    for rtype in route_type_Street_textlist:
        arcpy.AddMessage(rtype)
    arcpy.AddMessage("(This step may take a while for large GTFS datasets.)")

    global NoRouteGenerated
    NoRouteGenerated = []
    Too_Many_Stops = []
    global badStops

    # ----- Generate a route for each sequence -----

    arcpy.AddMessage("- Generating routes using ArcGIS Online")

    # Set up input parameters for route request
    service_params = {}
    service_params["travelMode"] = AGOLRouteHelper.travel_mode
    service_params["returnRoutes"] = True
    service_params["outputLines"] = "esriNAOutputLineTrueShapeWithMeasure"
    service_params["returnDirections"] = False
    service_params["outSR"] = WGSCoords_WKID
    
    # Create the output feature class
    arcpy.management.CreateFeatureclass(outGDB, outRoutesfcName, "POLYLINE", '', '', '', WGSCoords)
    arcpy.management.AddField(outRoutesfc, "Name", "TEXT")

    # Set up insertCursors for output shapes polylines and stop sequences
    # Have to open an edit session to have two simultaneous InsertCursors.
    edit = arcpy.da.Editor(outGDB)
    ucursor = arcpy.da.InsertCursor(outRoutesfc, ["SHAPE@", "Name"])
    cur = arcpy.da.InsertCursor(outSequencePoints, ["SHAPE@X", "SHAPE@Y", "shape_id", "sequence", "stop_id", "CurbApproach", "Bearing", "BearingTol"])
    edit.startEditing()

    # Generate routes with AGOL for sequences we want to make street-based shapes for.
    sequences_Streets = []
    num_shapes = len(sequence_shape_dict)
    next_threshold = 10
    progress = 0.0
    num_routes_calculated = 0
    for sequence in sequence_shape_dict:
        # Print some progress indicators
        progress += 1
        percdone = (progress / num_shapes) * 100
        if percdone > next_threshold:
            last_threshold = percdone - percdone%10
            arcpy.AddMessage("%s%% finished" % str(int(last_threshold)))
            next_threshold = last_threshold + 10
        shape_id = sequence_shape_dict[sequence]
        route_id = sequence[0]
        route_type = RouteDict[route_id][4]
        if route_type not in route_types_Street:
            continue
        if len(sequence[1]) > AGOLRouteHelper.route_stop_limit:
            # There are too many stops in this route to solve with the online services.
            Too_Many_Stops.append(shape_id)
            continue
        bearingdict = getBearingsForSequence(sequence[1])
        sequence_num = 1
        pt = arcpy.Point()
        features = []
        for stop in sequence[1]:
            try:
                stop_lat = stoplatlon_dict[stop][0]
                stop_lon = stoplatlon_dict[stop][1]
            except KeyError:
                badStops.append(stop)
                sequence_num += 1
                continue
            # Add stop sequences to points fc for user to look at.
            pt.X = float(stop_lon)
            pt.Y = float(stop_lat)
            cur.insertRow((float(stop_lon), float(stop_lat), shape_id, sequence_num, stop, CurbApproach, bearingdict[stop], BearingTol))
            sequence_num = sequence_num + 1
            geom = {"x": float(stop_lon), 
                      "y": float(stop_lat),
                      "spatialReference": {"wkid": WGSCoords_WKID}}
            attributes = {"Name": stop,
                        "CurbApproach": CurbApproach}
            if bearingdict[stop] != None:
                attributes["Bearing"] = bearingdict[stop]
                attributes["BearingTol"] = BearingTol
            features.append({"geometry": geom, "attributes": attributes})
        service_params["stops"] = {"features": features}
        routeshapes, errors = AGOLRouteHelper.generate_routes_from_AGOL_as_polylines(AGOLRouteHelper.token, service_params)
        if errors:
            if "User does not have permissions to access" in errors:
                arcpy.AddError("ArcGIS Online route generation failed. Please ensure that your ArcGIS Online account \
has routing privileges and sufficient credits for this analysis.")
                raise CustomError
            arcpy.AddWarning("ArcGIS Online route generation for shape_id %s failed. A straight-line shape will be generated for this shape_id instead. %s" % (shape_id, errors))
            NoRouteGenerated.append(shape_id)
            continue
        for route in routeshapes: # actually, only one shape should be returned here, but loop just in case
            ucursor.insertRow((route, shape_id))
        num_routes_calculated += 1

    del ucursor
    del cur

    edit.stopEditing(True)

    arcpy.AddMessage("Done generating route shapes with ArcGIS Online. Number of ArcGIS Online routes calculated: %s" % str(num_routes_calculated))

    if Too_Many_Stops:
        arcpy.AddWarning("On-street route shapes for the following shape_ids could \
not be generated because the number of stops in the route exceeds the ArcGIS Online \
service limit of %s stops.  Straight-line route shapes will be generated for these \
shape_ids instead:" % str(AGOLRouteHelper.route_stop_limit))
        arcpy.AddWarning(sorted(Too_Many_Stops))
    NoRouteGenerated.append(shape for shape in Too_Many_Stops)


def Generate_Shapes_Straight(Created_Street_Output):
    '''Generate route shapes as straight lines between stops.'''

    arcpy.AddMessage("Generating straight-line route shapes for routes of the following types, if they exist in your data:")
    for rtype in route_type_Straight_textlist:
        arcpy.AddMessage(rtype)
    arcpy.AddMessage("(This step may take a while for large GTFS datasets.)")

    # If we didn't already create the output feature class with the Street-based routes, create it now.
    if not Created_Street_Output or not arcpy.Exists(outRoutesfc):
        arcpy.management.CreateFeatureclass(outGDB, outRoutesfcName, "POLYLINE", '', '', '', WGSCoords)
        arcpy.management.AddField(outRoutesfc, "Name", "TEXT")
        spatial_ref = WGSCoords
    else:
        spatial_ref = arcpy.Describe(outRoutesfc).spatialReference


# ----- Create polylines using stops as vertices -----

    # Set up insertCursors for output shapes polylines and stop sequences
    # Have to open an edit session to have two simultaneous InsertCursors.
    edit = arcpy.da.Editor(outGDB)
    ucursor = arcpy.da.InsertCursor(outRoutesfc, ["SHAPE@", "Name"])
    cur = arcpy.da.InsertCursor(outSequencePoints, ["SHAPE@X", "SHAPE@Y", "shape_id", "sequence", "stop_id"])
    edit.startEditing()

    global badStops

    for sequence in sequence_shape_dict:
        shape_id = sequence_shape_dict[sequence]
        route_id = sequence[0]
        route_type = RouteDict[route_id][4]
        if route_type in route_types_Straight or shape_id in NoRouteGenerated:
            sequence_num = 1
            # Add stop sequence to an Array of Points
            array = arcpy.Array()
            pt = arcpy.Point()
            for stop in sequence[1]:
                try:
                    stop_lat = stoplatlon_dict[stop][0]
                    stop_lon = stoplatlon_dict[stop][1]
                except KeyError:
                    if shape_id not in NoRouteGenerated:
                        # Don't repeat a warning if they already got it once.
                        badStops.append(stop)
                    sequence_num += 1
                    continue
                pt.X = float(stop_lon)
                pt.Y = float(stop_lat)
                # Add stop sequences to points fc for user to look at.
                cur.insertRow((float(stop_lon), float(stop_lat), shape_id, sequence_num, stop))
                sequence_num = sequence_num + 1
                array.add(pt)
            # Generate a Polyline from the Array of stops
            polyline = arcpy.Polyline(array, WGSCoords)
            # Project the polyline to the correct output coordinate system.
            if spatial_ref != WGSCoords:
                polyline.projectAs(spatial_ref)
            # Add the polyline to the Shapes feature class
            ucursor.insertRow((polyline, shape_id))
    del ucursor
    del cur

    edit.stopEditing(True)
    

def connect_to_sql(SQLDbase):
    global c, conn
    conn = sqlite3.connect(SQLDbase)
    c = conn.cursor()


def check_Arc_version(useAGOL=False, useNA=False):
    '''Check that the user has a version of ArcGIS that can support this tool.'''

    ArcVersionInfo = arcpy.GetInstallInfo("desktop")
    ArcVersion = ArcVersionInfo['Version']
    global ProductName
    ProductName = ArcVersionInfo['ProductName']
    global useBearing
    
    if ProductName == "ArcGISPro":
        if ArcVersion in ["1.0", "1.1", "1.1.1"]:
            arcpy.AddError("You must have ArcGIS Pro 1.2 or higher to run this \
tool. You have ArcGIS Pro version %s." % ArcVersion)
            raise CustomError
        if useNA and ArcVersion in ["1.0", "1.0.1", "1.0.2", "1.1", "1.1.1", "1.2", "1.3", "1.3.1", "1.4", "1.4.1"]:
            # Bearing and BearingTol fields did not work until Pro 2.0.
            arcpy.AddWarning("Warning!  Certain functionality was implemented in ArcGIS Pro 2.0 that \
significantly improves the output of this tool. For better results, upgrade to the latest version of ArcGIS Pro or run \
this tool with ArcMap version 10.3 or higher.")
            useBearing = False
    
    else:
        if ArcVersion == "10.0":
            arcpy.AddError("You must have ArcGIS 10.2.1 or higher (or ArcGIS Pro) to run this \
tool. You have ArcGIS version %s." % ArcVersion)
            raise CustomError
        if ArcVersion in ["10.1", "10.2"]:
            arcpy.AddWarning("Warning!  You can run Step 1 of this tool in \
ArcGIS 10.1 or 10.2, but you will not be able to run Step 2 without ArcGIS \
10.2.1 or higher (or ArcGIS Pro).  You have ArcGIS version %s." % ArcVersion)
            if useNA:
                useBearing = False
        if useAGOL and ArcVersion in ["10.2.1", "10.2.2"]:
            arcpy.AddError("You must have ArcGIS 10.3 (or ArcGIS Pro) to run the ArcGIS Online \
version of this tool. You have ArcGIS version %s." % ArcVersion)
            raise CustomError
        if useNA and ArcVersion in ["10.2.1", "10.2.2"]:
            arcpy.AddWarning("Warning!  This version of Step 1 will produce significantly \
better output using ArcGIS version 10.3 or higher or ArcGIS Pro 2.0 or higher. You have ArcGIS version %s." % ArcVersion)
            useBearing = False


def get_stop_lat_lon():
        '''Populate a dictionary of {stop_id: [stop_lat, stop_lon]}'''
        
        arcpy.AddMessage("Collecting and processing GTFS stop information...")
        
        # Find all stops with lat/lon
        global stoplatlon_dict
        stoplatlon_dict = {}
        cs = conn.cursor()
        stoplatlonfetch = '''
            SELECT stop_id, stop_lat, stop_lon FROM stops
            ;'''
        cs.execute(stoplatlonfetch)
        for stop in cs:
            # Add stop lat/lon to dictionary
            stoplatlon_dict[stop[0]] = [stop[1], stop[2]]


def get_stop_geom():
    '''Populate a dictionary of {stop_id: stop point geometry object}'''
    
    global stopgeom_dict
    stopgeom_dict = {}
    
    for stop in stoplatlon_dict:
        lat = stoplatlon_dict[stop][0]
        lon = stoplatlon_dict[stop][1]
        point = arcpy.Point(lon, lat)
        ptGeometry = arcpy.PointGeometry(point, WGSCoords)
        stopgeom_dict[stop] = ptGeometry


def getBearingsForSequence(sequence):
    '''Populate a dictionary of {stop_id: bearing}. Applies only to a given stop sequence. The same stop
    could have a different bearing if visited by a trip with a different shape.'''
    
    bearingdict = {}
    previous_angle = None
    for idx in range(len(sequence)):
        try:
            current_stop = sequence[idx]
            if idx == len(sequence)-1:
                # This is the last stop in the sequence, so just use the previous angle as the bearing.
                bearingdict[current_stop] = previous_angle
                angle_to_next = None
            else:
                # Calculate the angle from this stop to the next one in the sequence
                current_stop_geom = stopgeom_dict[current_stop]
                next_stop_geom = stopgeom_dict[sequence[idx+1]]
                # Note: angleAndDistanceTo was added in ArcGIS 10.3
                angle_to_next = current_stop_geom.angleAndDistanceTo(next_stop_geom, "GEODESIC")[0]
                if previous_angle == None:
                    # This is the first stop, so use the angle to the second stop as the bearing
                    bearingdict[current_stop] = angle_to_next
                else:
                    # If this is an intermediate stop, estimate the bearing based on the angle between this stop and the previous and next one
                    # If the anle to the next one and the angle from the previous one are very different, the route is probably going around a corner,
                    # and we can't reliably estimate what the bearing should be by averaging, so don't try to use a bearing for this one.
                    diff = abs(angle_to_next - previous_angle)
                    if diff >= MaxAngle:
                        bearingdict[current_stop] = None
                    else:
                        # If they're sufficiently similar angles, use some trigonometry to average the angle from the previous stop to this one and the angle of this one to the next one
                        angle_to_next_rad = np.deg2rad(angle_to_next)
                        previous_angle_rad = np.deg2rad(previous_angle)
                        bearing = np.rad2deg(np.arctan2((np.sin(previous_angle_rad) + np.sin(angle_to_next_rad))/2, (np.cos(previous_angle_rad) + np.cos(angle_to_next_rad))/2))
                        bearingdict[current_stop] = bearing
            previous_angle = angle_to_next
        except KeyError as err:
            arcpy.AddWarning("Key error in getBearingsForSequence")
            arcpy.AddWarning(err)
            continue
        
    return bearingdict


def calculate_stop_location_fields():
        '''Calculate location fields for the stops and save them to a dictionary so that Network Analyst Add Locations will be faster later'''
        
        arcpy.AddMessage("Calculating network locations fields...")

        # Temporary feature class of stops for calculating location fields
        arcpy.management.CreateFeatureclass(outGDB, "TempStopswLocationFields", "POINT", "", "", "", WGSCoords)
        LocFieldStops = os.path.join(outGDB, "TempStopswLocationFields")
        arcpy.management.AddField(LocFieldStops, "stop_id", "TEXT")
        with arcpy.da.InsertCursor(LocFieldStops, ["SHAPE@X", "SHAPE@Y", "stop_id"]) as cur:
            for stop in stoplatlon_dict:
                # Insert stop into fc for location field calculation
                stop_lat = stoplatlon_dict[stop][0]
                stop_lon = stoplatlon_dict[stop][1]
                cur.insertRow((float(stop_lon), float(stop_lat), stop))

        # It would be easier to use CalculateLocations, but then we can't
        # exclude restricted network elements.
        # Instead, create a dummy Route layer and Add Locations
        RLayer = arcpy.na.MakeRouteLayer(inNetworkDataset, "DummyLayer", impedanceAttribute,
                    restriction_attribute_name=restrictions).getOutput(0)
        naSubLayerNames = arcpy.na.GetNAClassNames(RLayer)
        stopsSubLayer = naSubLayerNames["Stops"]
        fieldMappings = arcpy.na.NAClassFieldMappings(RLayer, stopsSubLayer)
        fieldMappings["Name"].mappedFieldName = "stop_id"
        arcpy.na.AddLocations(RLayer, stopsSubLayer, LocFieldStops, fieldMappings,
                    search_criteria=search_criteria,
                    snap_to_position_along_network="NO_SNAP",
                    exclude_restricted_elements="EXCLUDE")
        if ProductName == "ArcGISPro":
            StopsLayer = RLayer.listLayers(stopsSubLayer)[0]
        else:
            StopsLayer = arcpy.mapping.ListLayers(RLayer, stopsSubLayer)[0]

        # Iterate over the located stops and create a dictionary of location fields
        global stoplocfielddict
        stoplocfielddict = {}
        with arcpy.da.SearchCursor(StopsLayer, ["Name", "SourceID", "SourceOID", "PosAlong", "SideOfEdge"]) as cur:
            for stop in cur:
                locfields = [stop[1], stop[2], stop[3], stop[4]]
                stoplocfielddict[stop[0]] = locfields
        arcpy.management.Delete(StopsLayer)
        arcpy.management.Delete(LocFieldStops)


def get_route_info():
    '''Create a dictionary of {route_id: [all route.txt fields + route_type_text]}'''
    
    arcpy.AddMessage("Collecting GTFS route information...")
    
    # GTFS route_type information
    #0 - Tram, Streetcar, Light rail. Any light rail or street level system within a metropolitan area.
    #1 - Subway, Metro. Any underground rail system within a metropolitan area.
    #2 - Rail. Used for intercity or long-distance travel.
    #3 - Bus. Used for short- and long-distance bus routes.
    #4 - Ferry. Used for short- and long-distance boat service.
    #5 - Cable car. Used for street-level cable cars where the cable runs beneath the car.
    #6 - Gondola, Suspended cable car. Typically used for aerial cable cars where the car is suspended from the cable.
    #7 - Funicular. Any rail system designed for steep inclines.
    route_type_dict = {0: "Tram, Streetcar, Light rail",
                        1: "Subway, Metro",
                        2: "Rail",
                        3: "Bus",
                        4: "Ferry",
                        5: "Cable car",
                        6: "Gondola, Suspended cable car",
                        7: "Funicular"}

    # Find all routes and associated info.
    global RouteDict
    RouteDict = {}
    cr = conn.cursor()
    routesfetch = '''
        SELECT route_id, agency_id, route_short_name, route_long_name,
        route_desc, route_type, route_url, route_color, route_text_color
        FROM routes
        ;'''
    cr.execute(routesfetch)
    for route in cr:
        # {route_id: [all route.txt fields + route_type_text]}
        try:
            route_type = route[5]
            route_type_text = route_type_dict[int(route_type)]
        except:
            route_type = '100'
            route_type_text = "Other / Type not specified"
        RouteDict[route[0]] = [route[1], route[2], route[3], route[4], route_type,
                                 route[6], route[7], route[8],
                                 route_type_text]


def get_trip_route_info():
    '''Create a dictionary of {trip_id: route_id}'''
    global trip_route_dict
    trip_route_dict = {}
    ctr = conn.cursor()
    triproutefetch = '''
        SELECT trip_id, route_id FROM trips
        ;'''
    ctr.execute(triproutefetch)
    for triproute in ctr:
        # {trip_id: route_id}
        trip_route_dict[triproute[0]] = triproute[1]


def get_trips_with_shape_id(shape):
    '''Return a list of trip_ids that use the specified shape'''
    tripsfetch = '''SELECT trip_id FROM trips WHERE shape_id="%s";''' % shape
    c.execute(tripsfetch)
    trips = c.fetchall()
    return [trip[0] for trip in trips]


def get_trip_stop_sequence(trip_id):
    '''Return a sequence of stop_id values, in the correct order, for a given trip'''
    stopfetch = "SELECT stop_id, stop_sequence FROM stop_times WHERE trip_id='%s'" % trip_id
    c.execute(stopfetch)
    selectedstops = c.fetchall()
    # Sort the stop list by sequence.
    selectedstops.sort(key=operator.itemgetter(1))
    stop_sequence = ()
    for stop in selectedstops:
        stop_sequence += (stop[0],)
    return stop_sequence


def get_unique_stop_sequences():
    '''Find the unique sequences of stops from stop_times.txt. Each unique sequence is a new shape.'''
    
    arcpy.AddMessage("Calculating unique sequences of stops...")
    # Find all trip_ids.
    ct = conn.cursor()
    tripsfetch = '''
        SELECT DISTINCT trip_id FROM stop_times
        ;'''
    ct.execute(tripsfetch)
    # Select stops in that trip
    global sequence_shape_dict, shape_trip_dict
    sequence_shape_dict = {}
    shape_trip_dict = {}
    shape_id = 1
    for trip in ct:
        stop_sequence = get_trip_stop_sequence(trip[0])
        route_id = trip_route_dict[trip[0]]
        sequence_shape_dict_key = (route_id, stop_sequence)
        try:
            sh = sequence_shape_dict[sequence_shape_dict_key]
            shape_trip_dict.setdefault(sh, []).append(trip[0])
        except KeyError:
            sequence_shape_dict[sequence_shape_dict_key] = str(shape_id)
            shape_trip_dict.setdefault(str(shape_id), []).append(trip[0])
            shape_id += 1
    
    numshapes = shape_id - 1
    arcpy.AddMessage("Your GTFS data contains %s unique shapes." % str(numshapes))
    

def append_existing_shape_to_fc(shape, StopsCursor, route=None):

    if route:
        # Retrieve route info for final output file.
        route_short_name = RouteDict[route][1]
        route_long_name = RouteDict[route][2]
        if RouteDict[route][3]:
            route_desc = RouteDict[route][3][:max_route_desc_length]
        else:
            route_desc = ""
        route_type = RouteDict[route][4]
        route_type_text = RouteDict[route][8]
    else:
        # Couldn't get route info for this shape
        route = ""
        route_short_name = ""
        route_long_name = ""
        route_desc = ""
        route_type = 0
        route_type_text = ""

    # Fetch the shape info to create the polyline feature.
    cp = conn.cursor()
    pointsinshapefetch = '''
        SELECT shape_pt_lat, shape_pt_lon FROM shapes
        WHERE shape_id='%s'
        ORDER BY shape_pt_sequence;''' % shape
    cp.execute(pointsinshapefetch)
    
    # Create the polyline feature from the sequence of points
    polyline = [(float(point[1]), float(point[0])) for point in cp]

    # Add the polyline feature to the output feature class
    StopsCursor.insertRow((polyline, shape, route,
                            route_short_name, route_long_name, route_desc,
                            route_type, route_type_text,))