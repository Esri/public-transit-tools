############################################################################
## Tool name: Display GTFS in ArcGIS
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 14 December 2017 2017
############################################################################
''' Display GTFS Route Shapes
Display GTFS Route Shapes converts GTFS route and shape data into an ArcGIS
feature class so you can visualize your GTFS routes on a map.
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

import os, csv, sys
import arcpy
# Pandas started shipping with 10.4 (and always in Pro).
# Tool will fail if pandas isn't available, but launcher script should prevent us from getting this far.
import pandas as pd

ispy3 = sys.version_info >= (3, 0)
ArcVersion = None
ProductName = None

# Required GTFS files and the fields they must contain for this tool to work
required_data = {"shapes.txt": ["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"],
                "routes.txt": ["route_id"],
                "trips.txt": ["route_id"]}
# Note: The shape_id field in trips.txt is not required to produce output, but it is required if we
# are to add the route information to the shape feature in the map.  If this field is missing, we'll
# just generate the shapes but skip populating the route info in the shapes output table.
populate_route_info = True
route_fields_to_use = sorted(["route_id", "agency_id", "route_short_name", "route_long_name", "route_desc", "route_type", "route_url", "route_color", "route_text_color"])

# Read in as GCS_WGS_1984 because that's what the GTFS spec uses
WGSCoords = "GEOGCS['GCS_WGS_1984',DATUM['D_WGS_1984', \
    SPHEROID['WGS_1984',6378137.0,298.257223563]], \
    PRIMEM['Greenwich',0.0],UNIT['Degree',0.0174532925199433]]; \
    -400 -400 1000000000;-100000 10000;-100000 10000; \
    8.98315284119522E-09;0.001;0.001;IsHighPrecision"
output_coords = None

# Explicitly set max allowed length for route_desc. Some agencies are wordy.
max_route_desc_length = 250

# GTFS route_type information
##0 - Tram, Streetcar, Light rail. Any light rail or street level system within a metropolitan area.
##1 - Subway, Metro. Any underground rail system within a metropolitan area.
##2 - Rail. Used for intercity or long-distance travel.
##3 - Bus. Used for short- and long-distance bus routes.
##4 - Ferry. Used for short- and long-distance boat service.
##5 - Cable car. Used for street-level cable cars where the cable runs beneath the car.
##6 - Gondola, Suspended cable car. Typically used for aerial cable cars where the car is suspended from the cable.
##7 - Funicular. Any rail system designed for steep inclines.
route_type_dict = {'0': "Tram, Streetcar, Light rail",
                    '1': "Subway, Metro",
                    '2': "Rail",
                    '3': "Bus",
                    '4': "Ferry",
                    '5': "Cable car",
                    '6': "Gondola, Suspended cable car",
                    '7': "Funicular"}


def check_required_data(csv_file, required_cols):
    '''Check that GTFS file exists and has required columns'''
    global populate_route_info
    if not os.path.exists(csv_file):
        if os.path.basename(csv_file) == "shapes.txt":
            # This is the only truely-required file
            arcpy.AddError("Your GTFS dataset is missing the file %s required to run this tool." % os.path.basename(csv_file))
            raise CustomError
        else:
            # Otherwise we can't populate the route data for shapes, but we can still draw them.
            populate_route_info = False
            return
    
    if ispy3:
        f = open(csv_file, encoding="utf-8-sig")
    else:
        f = open(csv_file)
    reader = csv.reader(f)
    # Put everything in utf-8 to handle BOMs and weird characters.
    # Eliminate blank rows (extra newlines) while we're at it.
    if ispy3:
        columns = [name.strip() for name in next(reader)]
    else:
        columns = [name.decode('utf-8-sig').strip() for name in next(reader)]
    f.close()

    for col in required_cols:
        if not col in columns:
            msg = "GTFS file " + os.path.basename(csv_file) + " is missing required field '" + col + "'."
            arcpy.AddError(msg)
            raise CustomError
    if os.path.basename(csv_file) == "trips.txt":
        # If trips has no shape_id column, we can't populate route info in the output,
        # but we can still draw the shapes in the map.
        if "shape_id" not in columns:
            populate_route_info = False
    if os.path.basename(csv_file) == "routes.txt":
        # Update route_fields_to_use to include only the ones actually in routes.txt.
        global route_fields_to_use
        route_fields_to_use = [str(col) for col in columns if col in route_fields_to_use]


def make_GTFS_lines_from_Shapes(shape, shapesdf, ShapesCursor, route="", routesdf=""):

    route_data_dict = {"agency_id": "",
                        "route_short_name": "",
                        "route_long_name": "",
                        "route_desc": "",
                        "route_type": 0,
                        "route_type_text": "",
                        "route_url": "",
                        "route_color": "",
                        "route_color_formatted": "",
                        "route_text_color": "",
                        "route_text_color_formatted": ""}

    if route:

        # Grab the route data from the dataframe
        thisroute = routesdf.loc[route].dropna().to_dict()

        # Update route data dictionary with values from data frame.
        for prop in ["agency_id", "route_short_name", "route_long_name", "route_desc", "route_type", "route_url", "route_color", "route_text_color"]:
            try:
                route_data_dict[prop] = thisroute[prop]
            except KeyError:
                continue

        # Truncate route_desc if it's too long (some agencies are wordy)
        if route_data_dict["route_desc"]:
            route_data_dict["route_desc"] = route_data_dict["route_desc"][:max_route_desc_length] 

        # Make a nice text description of the route_type 
        try:
            route_data_dict["route_type_text"] = route_type_dict[route_data_dict["route_type"]]
        except KeyError:
            route_data_dict["route_type_text"] = ""
        
        # Format colors for easier display in the map
        if route_data_dict["route_color"]:
            if ProductName == "ArcGISPro":
                # Attribute-driven symbology in Pro can read directly from a hex color value
                route_data_dict["route_color_formatted"] = "#" + route_data_dict["route_color"]
            else:
                route_data_dict["route_color_formatted"] = rgb(route_data_dict["route_color"])
        if route_data_dict["route_text_color"]:
            if ProductName == "ArcGISPro":
                # Attribute-driven symbology in Pro can read directly from a hex color value
                route_data_dict["route_text_color_formatted"] = "#" + route_data_dict["route_text_color"]
            else:
                route_data_dict["route_text_color_formatted"] = rgb(route_data_dict["route_text_color"])

    # Fetch the shape points for this shape.
    if hasattr(pd.DataFrame, 'sort_values'):
        thisshapedf = shapesdf.get_group(shape).sort_values(by="shape_pt_sequence")
    else:
        # sort_values was introduced in pandas 0.17.0. Fall back to the older, deprecated sort method if it isn't available.
        thisshapedf = shapesdf.get_group(shape).sort("shape_pt_sequence")

    # Create the polyline feature from the sequence of points
    lats = thisshapedf.shape_pt_lat.tolist()
    lons = thisshapedf.shape_pt_lon.tolist()
    array = arcpy.Array()
    pt = arcpy.Point()
    for idx in range(0, len(lats)):
        pt.X = float(lons[idx])
        pt.Y = float(lats[idx])
        array.add(pt)
    polyline = arcpy.Polyline(array, WGSCoords)
    if output_coords != WGSCoords:
        polyline = polyline.projectAs(output_coords)

    # Add the information to the feature class
    ShapesCursor.insertRow((polyline, shape, route, route_data_dict["agency_id"],
                            route_data_dict["route_short_name"], route_data_dict["route_long_name"], route_data_dict["route_desc"],
                            route_data_dict["route_type"], route_data_dict["route_type_text"], route_data_dict["route_url"],
                            route_data_dict["route_color"], route_data_dict["route_color_formatted"], route_data_dict["route_text_color"],
                            route_data_dict["route_text_color_formatted"]))


def rgb(triplet):
    ''' Converts a hex color triplet to an RGB value (R, G, B).  Code found on
    stackoverflow at http://stackoverflow.com/questions/4296249/how-do-i-convert-a-hex-triplet-to-an-rgb-tuple-and-back.'''
    try:
        HEX = '0123456789abcdef'
        HEX2 = dict((a+b, HEX.index(a)*16 + HEX.index(b)) for a in HEX for b in HEX)
        triplet = triplet.lower()
        rgbcolor = str((HEX2[triplet[0:2]], HEX2[triplet[2:4]], HEX2[triplet[4:6]]))
    except:
        # Something weird happened, and we couldn't parse the hex triplet, so just ignore it.
        rgbcolor = ""
    return rgbcolor

class CustomError(Exception):
    pass

def main(inGTFSdir, OutShapesFC):
    try:
        # ----- Set up inputs and other stuff -----

        orig_overwrite = arcpy.env.overwriteOutput
        arcpy.env.overwriteOutput = True

        outGDB = os.path.dirname(OutShapesFC)
        OutShapesFCname = os.path.basename(OutShapesFC)
        # If the output location is a feature dataset, we have to match the coordinate system
        global output_coords
        desc_outgdb = arcpy.Describe(outGDB)
        if hasattr(desc_outgdb, "spatialReference"):
            output_coords = desc_outgdb.spatialReference
        else:
            output_coords = WGSCoords
        

        # ----- Read in the GTFS data and perform some checks -----

        arcpy.AddMessage("Reading GTFS files...")

        # Check that the GTFS files have the required fields for this tool
        check_required_data(os.path.join(inGTFSdir, "shapes.txt"), required_data["shapes.txt"])
        check_required_data(os.path.join(inGTFSdir, "trips.txt"), required_data["trips.txt"])
        if populate_route_info: # Don't care about routes.txt file if trips.txt doesn't have shape_id
            check_required_data(os.path.join(inGTFSdir, "routes.txt"), required_data["routes.txt"])

        # Read in shapes.txt
        dtypes = {"shape_id": str, "shape_pt_lat": float, "shape_pt_lon": float, "shape_pt_sequence": int}
        try:
            shapesdf = pd.read_csv(os.path.join(inGTFSdir, "shapes.txt"), encoding="utf-8-sig", dtype=dtypes, usecols=required_data["shapes.txt"], skipinitialspace=True)
        except ValueError as ex:
            if "could not convert string to float" in str(ex):
                # Indication that there is a non-numeric value in shape_pt_lat or shape_pt_lon
                msg = 'Your GTFS shapes.txt file contains one or more invalid non-numerical values \
for the shape_pt_lat or shape_pt_lon field. Please double-check all lat/lon values in your \
shapes.txt file.'
            elif "cannot safely convert passed user dtype of <i4 for object" in str(ex):
                # Indication that there is a non-numeric value in shape_pt_sequence
                msg = 'Your GTFS shapes.txt file contains one or more invalid non-integer values \
for the shape_pt_sequence field.'
            else:
                msg = "Could not read in GTFS shapes.txt file: " + str(ex)
            arcpy.AddError(msg)
            raise CustomError
        except UnicodeDecodeError:
            arcpy.AddError("Unicode decoding of your GTFS shapes.txt file failed. Please \
ensure that your GTFS files have the proper utf-8 encoding required by the GTFS \
specification.")
            raise CustomError

        # Check that lat/lon values fall within the correct ranges
        if not shapesdf.shape_pt_lat.between(-90.0, 90.0).all():
            msg = 'Your GTFS shapes.txt file contains one or more latitude values in the shape_pt_lat field \
outside the range (-90, 90). The shape_pt_lat and shape_pt_lon values must be in valid WGS 84 \
coordinates.  Please double-check all latitude and longitude values in your shapes.txt file.'
            arcpy.AddError(msg)
            raise CustomError
        if not shapesdf.shape_pt_lon.between(-180.0, 180.0).all():
            msg = 'Your GTFS shapes.txt file contains one or more longitude values in the shape_pt_lon field \
outside the range (-180, 180). The shape_pt_lat and shape_pt_lon values must be in valid WGS 84 \
coordinates.  Please double-check all latitude and longitude values in your shapes.txt file.'
            arcpy.AddError(msg)
            raise CustomError

        # Handle pesky whitespaces
        shapesdf["shape_id"] = shapesdf["shape_id"].str.strip()

        # Group shapes by shape_id for quicker look-ups later
        # Because many rows have the same shape_id, it ends up being faster to use groupby than to index the table and use .loc[].
        shapesdf = shapesdf.groupby("shape_id")

        if not populate_route_info:
            arcpy.AddWarning("Your GTFS trips.txt file does not have a shape_id column, or you are missing a trips.txt or routes.txt file. \
This tool can still draw the route shapes in the map, but it will not be able to populate \
the output feature class's attribute table with route information.")

        # Read in routes.txt and trips.txt
        else: # Only do this if it's possible to populate the route info. Otherwise, we don't need it.
            
            # Read the routes.txt file into a pandas dataframe
            try:
                # Use dtype=str so pandas doesn't try to interpret the fields as different data types unpredictably
                routesdf = pd.read_csv(os.path.join(inGTFSdir, "routes.txt"), encoding="utf-8-sig", dtype=str, usecols=route_fields_to_use, skipinitialspace=True)
            except UnicodeDecodeError:
                arcpy.AddError("Unicode decoding of your GTFS routes.txt file failed. Please \
ensure that your GTFS files have the proper utf-8 encoding required by the GTFS \
specification.")
                raise CustomError
            # Handle pesky whitespaces
            routesdf["route_id"] = routesdf["route_id"].str.strip()
            # Index it based on route_id for fast lookups later
            routesdf.set_index("route_id", inplace=True)
            # Fill empty values with empty strings
            routesdf.fillna('')

            # Read in trips.txt
            try:
                tripsdf = pd.read_csv(os.path.join(inGTFSdir, "trips.txt"), usecols=["shape_id", "route_id"], encoding="utf-8-sig", dtype=str, skipinitialspace=True)
            except UnicodeDecodeError:
                arcpy.AddError("Unicode decoding of your GTFS trips.txt file failed. Please \
ensure that your GTFS files have the proper utf-8 encoding required by the GTFS \
specification.")
                raise CustomError
            # Remove duplicate shape_id/route_id pairs from the table
            tripsdf.drop_duplicates(inplace=True)
            # Handle pesky whitespaces
            tripsdf["route_id"] = tripsdf["route_id"].str.strip()
            tripsdf["shape_id"] = tripsdf["shape_id"].str.strip()

            # Effectively creates a dictionary where we can look up the route_id values associated with a particular shape_id
            tripsdf.set_index("shape_id", inplace=True)


    # ----- Create output feature class and prepare InsertCursor -----

        arcpy.AddMessage("Creating output feature class...")

        # Create the output feature class and add the right fields
        arcpy.management.CreateFeatureclass(outGDB, OutShapesFCname, "POLYLINE", "", "", "", output_coords)
        # Shapefiles can't have field names longer than 10 characters
        if ".shp" in OutShapesFCname:
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
        if ".shp" in OutShapesFCname:
            ShapesCursor = arcpy.da.InsertCursor(OutShapesFC, ["SHAPE@",
                        "shape_id", "route_id", "agency_id",
                        "rt_shrt_nm", "rt_long_nm", "route_desc",
                        "route_type", "rt_typ_txt", "route_url",
                        "rt_color", "rt_col_fmt", "rt_txt_col", "rt_txt_fmt"])
        else:
            ShapesCursor = arcpy.da.InsertCursor(OutShapesFC, ["SHAPE@",
                        "shape_id", "route_id", "agency_id",
                        "route_short_name", "route_long_name", "route_desc",
                        "route_type", "route_type_text", "route_url",
                        "route_color", "route_color_formatted", "route_text_color",
                        "route_text_color_formatted"])


    # ----- Add the shapes to the feature class -----

        arcpy.AddMessage("Adding route shapes to output feature class...")

        # Actually add the shapes to the feature class
        unused_shapes = False
        for shapething in shapesdf.shape_id.unique():
            shape = shapething[0]
        #for shape in shapesdf.index.unique():
            if not populate_route_info:
                # Don't worry about populating route info
                make_GTFS_lines_from_Shapes(shape, shapesdf, ShapesCursor)
            else:
                # Get the route ids that have this shape.
                # There should probably be a 1-1 relationship, but not sure.
                try:
                    routes = tripsdf.loc[shape].route_id
                except KeyError:
                    # No trips actually use this shape, so skip adding route info
                    make_GTFS_lines_from_Shapes(shape, shapesdf, ShapesCursor)
                    unused_shapes = True
                    continue
                if isinstance(routes, pd.core.series.Series):
                    # If more than one route uses the same shape_id, pandas returns a series
                    routes = routes.tolist()
                else:
                    # Otherwise (more likely) it returns a single string value of the route_id
                    routes = [routes]
                for route in routes:
                    make_GTFS_lines_from_Shapes(shape, shapesdf, ShapesCursor, route, routesdf)

        if unused_shapes:
            arcpy.AddWarning("One or more of the shapes in your GTFS shapes.txt file are not used by any \
trips in your trips.txt file.  These shapes were included in the output from this tool, but route \
information was not populated.")

        # Clean up. Delete the cursor.
        # 10.x doesn't care about this, but Pro seems to.
        del ShapesCursor

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