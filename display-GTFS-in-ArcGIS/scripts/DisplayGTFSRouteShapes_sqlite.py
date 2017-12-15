############################################################################
## Tool name: Display GTFS in ArcGIS
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 14 December 2017
############################################################################
''' Display GTFS Route Shapes
Display GTFS Route Shapes converts GTFS route and shape data into an ArcGIS
feature class so you can visualize your GTFS routes on a map.
This older version of the tool uses sqlite3. The newer pandas version isinstance
better, but pandas wasn't shipped until ArcGIS 10.4, so users with older
software will need to use this version.
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

import sqlite3, operator, os
import arcpy
import sqlize_csv

ArcVersion = None
ProductName = None

conn = None
StopsCursor = None

# Read in as GCS_WGS_1984 because that's what the GTFS spec uses
WGSCoords = "GEOGCS['GCS_WGS_1984',DATUM['D_WGS_1984', \
    SPHEROID['WGS_1984',6378137.0,298.257223563]], \
    PRIMEM['Greenwich',0.0],UNIT['Degree',0.0174532925199433]]; \
    -400 -400 1000000000;-100000 10000;-100000 10000; \
    8.98315284119522E-09;0.001;0.001;IsHighPrecision"
output_coords = None

# Explicitly set max allowed length for route_desc. Some agencies are wordy.
max_route_desc_length = 250

RouteDict = {}

# GTFS route_type information
##0 - Tram, Streetcar, Light rail. Any light rail or street level system within a metropolitan area.
##1 - Subway, Metro. Any underground rail system within a metropolitan area.
##2 - Rail. Used for intercity or long-distance travel.
##3 - Bus. Used for short- and long-distance bus routes.
##4 - Ferry. Used for short- and long-distance boat service.
##5 - Cable car. Used for street-level cable cars where the cable runs beneath the car.
##6 - Gondola, Suspended cable car. Typically used for aerial cable cars where the car is suspended from the cable.
##7 - Funicular. Any rail system designed for steep inclines.
route_type_dict = {0: "Tram, Streetcar, Light rail",
                    1: "Subway, Metro",
                    2: "Rail",
                    3: "Bus",
                    4: "Ferry",
                    5: "Cable car",
                    6: "Gondola, Suspended cable car",
                    7: "Funicular"}

class CustomError(Exception):
    pass


def make_GTFS_lines_from_Shapes(shape, route=None):

    if route:
        # Retrieve route info for final output file.
        ShapeRoute = shape + "_" + route
        agency_id = RouteDict[route][0]
        route_short_name = RouteDict[route][1]
        route_long_name = RouteDict[route][2]
        if RouteDict[route][3]:
            route_desc = RouteDict[route][3][:max_route_desc_length]
        else:
            route_desc = ""
        route_type = RouteDict[route][4]
        route_type_text = RouteDict[route][8]
        route_url = RouteDict[route][5]
    
        route_color = RouteDict[route][6]
        if route_color:
            if ProductName == "ArcGISPro":
                route_color_formatted = "#" + RouteDict[route][6]
            else:
                route_color_formatted = rgb(RouteDict[route][6])
        else:
            route_color_formatted = ""
    
        route_text_color = RouteDict[route][7]
        if route_text_color:
            if ProductName == "ArcGISPro":
                route_text_color_formatted = "#" + RouteDict[route][7]
            else:
                route_text_color_formatted = rgb(RouteDict[route][7])
        else:
            route_text_color_formatted = ""

    else:
        # Couldn't get route info for this shape
        ShapeRoute = shape
        agency_id = ""
        route_short_name = ""
        route_long_name = ""
        route_desc = ""
        route_type = 0
        route_type_text = ""
        route_url = ""
        route_color = ""
        route_color_formatted = ""
        route_text_color = ""
        route_text_color_formatted = ""

    # Fetch the shape info to create the polyline feature.
    c3 = conn.cursor()
    pointsinshapefetch = '''
        SELECT shape_pt_lat, shape_pt_lon, shape_pt_sequence,
        shape_dist_traveled FROM shapes WHERE shape_id='%s'
        ORDER BY shape_pt_sequence;''' % shape
    c3.execute(pointsinshapefetch)

    # Create the polyline feature from the sequence of points
    array = arcpy.Array()
    pt = arcpy.Point()
    for point in c3:
        pt.X = float(point[1])
        pt.Y = float(point[0])
        array.add(pt)
    polyline = arcpy.Polyline(array, WGSCoords)
    if output_coords != WGSCoords:
        polyline = polyline.projectAs(output_coords)

    # Add the polyline feature to the output feature class
    if ArcVersion == "10.0":
        if ".shp" in OutShapesFCname:
            row = StopsCursor.newRow()
            row.shape = polyline
            row.setValue("RtShpName", ShapeRoute)
            row.setValue("shape_id", shape)
            row.setValue("route_id", route)
            row.setValue("agency_id", agency_id)
            row.setValue("rt_shrt_nm", route_short_name)
            row.setValue("rt_long_nm", route_long_name)
            row.setValue("route_desc", route_desc)
            row.setValue("route_type", route_type)
            row.setValue("rt_typ_txt", route_type_text)
            row.setValue("route_url", route_url)
            row.setValue("rt_color", route_color)
            row.setValue("rt_col_fmt", route_color_formatted)
            row.setValue("rt_txt_col", route_text_color)
            row.setValue("rt_txt_fmt", route_text_color_formatted)
            StopsCursor.insertRow(row)
        else:
            row = StopsCursor.newRow()
            row.shape = polyline
            row.setValue("RouteShapeName", ShapeRoute)
            row.setValue("shape_id", shape)
            row.setValue("route_id", route)
            row.setValue("agency_id", agency_id)
            row.setValue("route_short_name", route_short_name)
            row.setValue("route_long_name", route_long_name)
            row.setValue("route_desc", route_desc)
            row.setValue("route_type", route_type)
            row.setValue("route_type_text", route_type_text)
            row.setValue("route_url", route_url)
            row.setValue("route_color", route_color)
            row.setValue("route_color_formatted", route_color_formatted)
            row.setValue("route_text_color", route_text_color)
            row.setValue("route_text_color_formatted", route_text_color_formatted)
            StopsCursor.insertRow(row)
    else:
        # For everything 10.1 and forward
        StopsCursor.insertRow((polyline, ShapeRoute, shape, route, agency_id,
                                route_short_name, route_long_name, route_desc,
                                route_type, route_type_text, route_url,
                                route_color, route_color_formatted, route_text_color,
                                route_text_color_formatted))


def rgb(triplet):
    ''' Converts a hex color triplet to an RGB value (R, G, B).  Code found on
    stackoverflow at http://stackoverflow.com/questions/4296249/how-do-i-convert-a-hex-triplet-to-an-rgb-tuple-and-back.'''
    HEX = '0123456789abcdef'
    HEX2 = dict((a+b, HEX.index(a)*16 + HEX.index(b)) for a in HEX for b in HEX)
    triplet = triplet.lower()
    try:
        rgbcolor = str((HEX2[triplet[0:2]], HEX2[triplet[2:4]], HEX2[triplet[4:6]]))
    except KeyError:
        rgbcolor = ""
    return rgbcolor


def main(inGTFSdir, OutShapesFC):
    try:

    # ----- Set up inputs and other stuff -----

        orig_overwrite = arcpy.env.overwriteOutput
        arcpy.env.overwriteOutput = True

        outGDB = os.path.dirname(OutShapesFC)
        # If the output location is a feature dataset, we have to match the coordinate system
        global output_coords
        desc_outgdb = arcpy.Describe(outGDB)
        if hasattr(desc_outgdb, "spatialReference"):
            output_coords = desc_outgdb.spatialReference
            SQLDbaseLoc = os.path.dirname(outGDB)
        else:
            output_coords = WGSCoords
            SQLDbaseLoc = outGDB
        
        OutShapesFCname = os.path.basename(OutShapesFC)
        SQLDbase = os.path.join(SQLDbaseLoc, OutShapesFCname.replace(".shp", "") + ".sql")

        # Check the user's version
        if not ArcVersion or not ProductName:
            global ArcVersion, ProductName
            ArcVersionInfo = arcpy.GetInstallInfo("desktop")
            ArcVersion = ArcVersionInfo['Version']
            ProductName = ArcVersionInfo['ProductName']

    # ----- SQLize the GTFS data -----

        arcpy.AddMessage("SQLizing the GTFS data...")

        # Fix up list of GTFS datasets
        inGTFSdirList = inGTFSdir.split(";")
        # Remove single quotes ArcGIS puts in if there are spaces in the filename.
        for d in inGTFSdirList:
            if d[0] == "'" and d[-1] == "'":
                loc = inGTFSdirList.index(d)
                inGTFSdirList[loc] = d[1:-1]

        # The main SQLizing work is done in the sqlize_csv module
        # originally written by Luitien Pan for GTFS_NATools.
        # Connect to or create the SQL file.
        sqlize_csv.connect(SQLDbase)
        # Create tables.
        for tblname in sqlize_csv.sql_schema:
            sqlize_csv.create_table(tblname)
        # SQLize all the GTFS files, for each separate GTFS dataset.
        for gtfs_dir in inGTFSdirList:
            # Run sqlize each GTFS dataset. Check for returned errors
            GTFSErrors = sqlize_csv.handle_agency(gtfs_dir)
            if GTFSErrors:
                for error in GTFSErrors:
                    arcpy.AddError(error)
                raise CustomError
        # Create indices to make queries faster.
        sqlize_csv.create_indices()
        sqlize_csv.db.close()
        
        # Connect to the SQL database
        global conn
        conn = sqlite3.connect(SQLDbase)


    # ----- Make dictionary of route info -----

        global RouteDict

        if not sqlize_csv.populate_route_info:
            arcpy.AddWarning("Your GTFS trips.txt file does not have a shape_id column. \
This tool can still draw the route shapes in the map, but it will not be able to populate \
the output feature class's attribute table with route information.")

        else: # Only do this if it's possible to populate the route info

            arcpy.AddMessage("Collecting Route info...")
        
            # Find all routes and associated info.
            c = conn.cursor()
            routesfetch = '''
                SELECT route_id, agency_id, route_short_name, route_long_name,
                route_desc, route_type, route_url, route_color, route_text_color
                FROM routes
                ;'''
            c.execute(routesfetch)
            for routeitem in c:
                # Convert from a tuple to a list so the .shp logic below doesn't mess up
                route = list(routeitem)
                # {route_id: [all route.txt fields + route_type_text]}
                try:
                    route_type_text = route_type_dict[int(route[5])]
                except:
                    route_type_text = ""
                # Shapefile output can't handle null values, so make them empty strings.
                if ".shp" in OutShapesFCname:
                    possiblenulls = [1, 4, 6, 7, 8]
                    for idx in possiblenulls:
                        if not route[idx]:
                            route[idx] = ""
                RouteDict[route[0]] = [route[1], route[2], route[3], route[4], route[5],
                                        route[6], route[7], route[8],
                                        route_type_text]


    # ----- Create output feature class and prepare InsertCursor -----

        arcpy.AddMessage("Creating output feature class...")

        # Create the output feature class and add the right fields
        arcpy.management.CreateFeatureclass(outGDB, OutShapesFCname, "POLYLINE", "", "", "", output_coords)
        # Shapefiles can't have field names longer than 10 characters
        if ".shp" in OutShapesFCname:
            arcpy.management.AddField(OutShapesFC, "RtShpName", "TEXT")
            arcpy.management.AddField(OutShapesFC, "shape_id", "TEXT")
            arcpy.management.AddField(OutShapesFC, "route_id", "TEXT")
            arcpy.management.AddField(OutShapesFC, "agency_id", "TEXT")
            arcpy.management.AddField(OutShapesFC, "rt_shrt_nm", "TEXT")
            arcpy.management.AddField(OutShapesFC, "rt_long_nm", "TEXT")
            arcpy.management.AddField(OutShapesFC, "route_desc", "TEXT", "", "", max_route_desc_length)
            arcpy.management.AddField(OutShapesFC, "route_type", "SHORT")
            arcpy.management.AddField(OutShapesFC, "rt_typ_txt", "TEXT")
            arcpy.management.AddField(OutShapesFC, "route_url", "TEXT")
            arcpy.management.AddField(OutShapesFC, "rt_color", "TEXT")
            arcpy.management.AddField(OutShapesFC, "rt_col_fmt", "TEXT")
            arcpy.management.AddField(OutShapesFC, "rt_txt_col", "TEXT")
            arcpy.management.AddField(OutShapesFC, "rt_txt_fmt", "TEXT")

        else:
            arcpy.management.AddField(OutShapesFC, "RouteShapeName", "TEXT")
            arcpy.management.AddField(OutShapesFC, "shape_id", "TEXT")
            arcpy.management.AddField(OutShapesFC, "route_id", "TEXT")
            arcpy.management.AddField(OutShapesFC, "agency_id", "TEXT")
            arcpy.management.AddField(OutShapesFC, "route_short_name", "TEXT")
            arcpy.management.AddField(OutShapesFC, "route_long_name", "TEXT")
            arcpy.management.AddField(OutShapesFC, "route_desc", "TEXT", "", "", max_route_desc_length)
            arcpy.management.AddField(OutShapesFC, "route_type", "SHORT")
            arcpy.management.AddField(OutShapesFC, "route_type_text", "TEXT")
            arcpy.management.AddField(OutShapesFC, "route_url", "TEXT")
            arcpy.management.AddField(OutShapesFC, "route_color", "TEXT")
            arcpy.management.AddField(OutShapesFC, "route_color_formatted", "TEXT")
            arcpy.management.AddField(OutShapesFC, "route_text_color", "TEXT")
            arcpy.management.AddField(OutShapesFC, "route_text_color_formatted", "TEXT")

        # Create the InsertCursors
        global StopsCursor
        if ArcVersion == "10.0":
            StopsCursor = arcpy.InsertCursor(OutShapesFC)
        else:
            # For everything 10.1 and forward
            if ".shp" in OutShapesFCname:
                StopsCursor = arcpy.da.InsertCursor(OutShapesFC, ["SHAPE@",
                        "RtShpName", "shape_id", "route_id", "agency_id",
                        "rt_shrt_nm", "rt_long_nm", "route_desc",
                        "route_type", "rt_typ_txt", "route_url",
                        "rt_color", "rt_col_fmt", "rt_txt_col", "rt_txt_fmt"])
            else:
                StopsCursor = arcpy.da.InsertCursor(OutShapesFC, ["SHAPE@",
                        "RouteShapeName", "shape_id", "route_id", "agency_id",
                        "route_short_name", "route_long_name", "route_desc",
                        "route_type", "route_type_text", "route_url",
                        "route_color", "route_color_formatted", "route_text_color",
                        "route_text_color_formatted"])


    # ----- Add the shapes to the feature class -----

        arcpy.AddMessage("Adding route shapes to output feature class...")

        # Get list of shape_ids
        c = conn.cursor()
        shapesfetch = '''
            SELECT DISTINCT shape_id FROM shapes
            ;'''
        c.execute(shapesfetch)

        # Actually add the shapes to the feature class
        unused_shapes = False
        c2 = conn.cursor()
        for shape in c:
            if not sqlize_csv.populate_route_info:
                # Don't worry about populating route info
                make_GTFS_lines_from_Shapes(shape[0])
            else:
                # Get the route ids that have this shape.
                # There should probably be a 1-1 relationship, but not sure.
                shapesroutesfetch = '''
                    SELECT DISTINCT route_id FROM trips WHERE shape_id='%s'
                    ;''' % shape[0]
                c2.execute(shapesroutesfetch)
                weresome = False
                for route in c2:
                    weresome = True
                    make_GTFS_lines_from_Shapes(shape[0], route[0])
                if not weresome:
                    # No trips actually use this shape, so skip adding route info
                    make_GTFS_lines_from_Shapes(shape[0])
                    unused_shapes = True

        if unused_shapes:
            arcpy.AddWarning("One or more of the shapes in your GTFS shapes.txt file are not used by any \
trips in your trips.txt file.  These shapes were included in the output from this tool, but route \
information was not populated.")

        # Clean up. Delete the cursor.
        del StopsCursor

        # Close things up and delete the SQL database
        conn.close()
        os.remove(SQLDbase)

        arcpy.AddMessage("Finished!")


    except CustomError:
        arcpy.AddError("Failed to generate a feature class of GTFS shapes.")
        pass

    except:
        arcpy.AddError("Failed to generate a feature class of GTFS shapes.")
        raise

    finally:
        # Reset the overwrite output to the user's original setting..
        arcpy.env.overwriteOutput = orig_overwrite

if __name__ == '__main__':
    main()