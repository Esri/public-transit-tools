################################################################################
## Toolbox: Display GTFS in ArcGIS
## Tool name: Display GTFS Stops
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 28 April 2017
################################################################################
''' This tool generates feature classes of transit stops from the GTFS stop.txt
file for display and analysis in ArcGIS for Desktop.'''
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

import csv, os
import arcpy

class CustomError(Exception):
    pass


try:

    # Check the user's version
    InstallInfo = arcpy.GetInstallInfo()
    ArcVersion = InstallInfo['Version']
    ProductName = InstallInfo['ProductName']
    if ArcVersion == "10.0":
        arcpy.AddError("Sorry, this tool requires ArcGIS 10.1 or higher.")
        raise CustomError

    orig_overwrite = arcpy.env.overwriteOutput
    arcpy.env.overwriteOutput = True

    # GTFS stop lat/lon are written in WGS1984 coordinates
    WGSCoords = "GEOGCS['GCS_WGS_1984',DATUM['D_WGS_1984', \
    SPHEROID['WGS_1984',6378137.0,298.257223563]], \
    PRIMEM['Greenwich',0.0],UNIT['Degree',0.0174532925199433]]; \
    -400 -400 1000000000;-100000 10000;-100000 10000; \
    8.98315284119522E-09;0.001;0.001;IsHighPrecision"

    # Explicitly set max allowed length for stop_desc. Some agencies are wordy.
    max_stop_desc_length = 250

    # Fields other than stop_lat and stop_lon required by the GTFS spec.
    other_required_fields = ["stop_id", "stop_name"]

    # User input
    inStopstxt = arcpy.GetParameterAsText(0)
    outfc = arcpy.GetParameterAsText(1)
    outGDB = os.path.dirname(outfc)
    outfilename = os.path.basename(outfc)

    # If the output location is a feature dataset, we have to match the coordinate system
    desc_outgdb = arcpy.Describe(outGDB)
    if hasattr(desc_outgdb, "spatialReference"):
        output_coords = desc_outgdb.spatialReference
    else:
        output_coords = WGSCoords

    # ----- Read in the stops.txt csv file -----
    arcpy.AddMessage("Reading input stops.txt file...")
    try:
        # Open the stops.txt csv for reading
        if ProductName == 'ArcGISPro':
            f = open(inStopstxt, encoding="utf-8")
        else:
            f = open(inStopstxt)
        reader = csv.reader(f)

        # Put everything in utf-8 to handle BOMs and weird characters.
        # Eliminate blank rows (extra newlines) while we're at it.
        if ProductName == 'ArcGISPro':
            reader = ([x.strip() for x in r] for r in reader if len(r) > 0)
        else:
            reader = ([x.decode('utf-8-sig').strip() for x in r] for r in reader if len(r) > 0)

        # First row is column names:
        columns = [name.strip() for name in next(reader)]

    except Exception as err:
        arcpy.AddError("Error reading stops.txt file.")
        raise

    # ----- Check the stops.txt file for the correct fields -----
    try:
        # Make sure lat/lon values are present
        if not "stop_lat" in columns:
            arcpy.AddError("Your stops.txt file does not contain a 'stop_lat' field. Please choose a valid stops.txt file.")
            raise CustomError
        if not "stop_lon" in columns:
            arcpy.AddError("Your stops.txt file does not contain a 'stop_lon' field. Please choose a valid stops.txt file.")
            raise CustomError

        # Add a warning if other required fields aren't present
        for field in other_required_fields:
            if not field in columns:
                arcpy.AddWarning("Warning! Your stops.txt file does not contain the required %s field. This tool will run correctly anyway, but your GTFS file is invalid.")

        # Find incides of stop_lat and stop_lon columns
        stop_lat_idx = columns.index("stop_lat")
        stop_lon_idx = columns.index("stop_lon")
        stop_id_idx = columns.index("stop_id")

        # Shapefiles can only handle field names up to 10 characters, so truncate the long ones.
        if ".shp" in outfilename:
            columns = [c[0:10] for c in columns]

    except Exception as err:
        arcpy.AddError("Error validating stops.txt file fields.")
        raise

    # ----- Create new feature class and add the right fields -----
    arcpy.AddMessage("Initializing stops feature class...")
    try:
        # Create the output feature class
        arcpy.management.CreateFeatureclass(outGDB, outfilename, "POINT", spatial_reference=output_coords)

        # Add the appropriate fields to the feature class
        for col in columns:
            # Hard-wire all the columns to be text values
            arcpy.management.AddField(outfc, col, "TEXT")

    except Exception as err:
        arcpy.AddError("Error creating new stops feature class.")
        raise

    # ----- Write the stops.txt data to the new feature class -----
    arcpy.AddMessage("Writing stops feature class...")
    try:
        fields = ["SHAPE@"] + columns
        with arcpy.da.InsertCursor(outfc, fields) as cur:
            for row in reader:
                stop_id = row[stop_id_idx]
                # Get the lat/lon values. If float covnersion fails, there is a problem
                try:
                    stop_lat = float(row[stop_lat_idx])
                except ValueError:
                    msg = 'stop_id "%s" contains an invalid non-numerical value \
for the stop_lat field: "%s". Please double-check all lat/lon values in your \
stops.txt file.' % (stop_id, str(row[stop_lat_idx]))
                    arcpy.AddError(msg)
                    raise CustomError
                try:
                    stop_lon = float(row[stop_lon_idx])
                except ValueError:
                    msg = 'stop_id "%s" contains an invalid non-numerical value \
for the stop_lon field: "%s". Please double-check all lat/lon values in your \
stops.txt file.' % (stop_id, str(row[stop_lon_idx]))
                    arcpy.AddError(msg)
                    raise CustomError
                # Check that the lat/lon values are in the right range.
                if not (-90.0 <= stop_lat <= 90.0):
                    msg = 'stop_id "%s" contains an invalid value outside the \
range (-90, 90) the stop_lat field: "%s". stop_lat values must be in valid WGS 84 \
coordinates.  Please double-check all lat/lon values in your stops.txt file.\
' % (stop_id, str(stop_lat))
                    arcpy.AddError(msg)
                    raise CustomError
                if not (-180.0 <= stop_lon <= 180.0):
                    msg = 'stop_id "%s" contains an invalid value outside the \
range (-180, 180) the stop_lon field: "%s". stop_lon values must be in valid WGS 84 \
coordinates.  Please double-check all lat/lon values in your stops.txt file.\
    ' % (stop_id, str(stop_lon))
                    arcpy.AddError(msg)
                    raise CustomError
                if "stop_desc" in columns:
                    stop_desc_idx = columns.index("stop_desc")
                    if row[stop_desc_idx]:
                        # Some agencies are wordy. Truncate stop_desc so it fits in the field length.
                        row[stop_desc_idx] = row[stop_desc_idx][:max_stop_desc_length] 
                
                pt = arcpy.Point()
                pt.X = float(stop_lon)
                pt.Y = float(stop_lat)
                # GTFS stop lat/lon is written in WGS1984
                ptGeometry = arcpy.PointGeometry(pt, WGSCoords)
                if output_coords != WGSCoords:
                    ptGeometry = ptGeometry.projectAs(output_coords)

                cur.insertRow((ptGeometry,) + tuple(row))

        arcpy.AddMessage("Done!")

    except Exception as err:
        arcpy.AddError("Error writing stops.txt data to feature class.")
        raise

except UnicodeDecodeError:
    arcpy.AddError("Your input stops.txt file has an encoding problem. According to the GTFS \
specification, all GTFS files should be encoded in UTF-8.  Please fix your input file and try again.")
    pass

except CustomError:
    arcpy.AddError("Failed to create a feature class of GTFS stops.")
    pass

except Exception as err:
    arcpy.AddError("Failed to create a feature class of GTFS stops.")
    raise

finally:
    arcpy.env.overwriteOutput = orig_overwrite
