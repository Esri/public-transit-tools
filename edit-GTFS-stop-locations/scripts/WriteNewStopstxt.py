################################################################################
## Toolbox: Edit GTFS Stop Locations
## Tool name: 2) Write New stops.txt
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 14 December 2017
################################################################################
'''Using the feature class created in Step 1 and edited by the user, this tool
generates a new stops.txt GTFS file with the lat/lon values updated to the
edited stop locations.'''
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

    # GTFS stop lat/lon are written in WGS1984 coordinates
    WGSCoords = "GEOGCS['GCS_WGS_1984',DATUM['D_WGS_1984', \
    SPHEROID['WGS_1984',6378137.0,298.257223563]], \
    PRIMEM['Greenwich',0.0],UNIT['Degree',0.0174532925199433]]; \
    -400 -400 1000000000;-100000 10000;-100000 10000; \
    8.98315284119522E-09;0.001;0.001;IsHighPrecision"
    WGSCoords_name = 'GCS_WGS_1984'

    # User input
    inStopsFC = arcpy.GetParameterAsText(0)
    outStopstxt = arcpy.GetParameterAsText(1)

    # Get the fields from the stops feature class
    desc = arcpy.Describe(inStopsFC)
    fieldobjs = desc.fields
    columns = []
    for field in fieldobjs:
        # Eliminate the OID and shape fields, since we don't write that to the csv
        if not field.type in ["OID", "Geometry", "GUID"]:
            columns.append(field.name)
    # Shapefiles automatically generate a useless column called Id, so get rid of it.
    if ".shp" in os.path.basename(inStopsFC) and "Id" in columns:
        del columns[columns.index("Id")]
    
    # Check input coordinate system
    convert_coords = False
    input_SR = desc.spatialReference
    if input_SR.name != WGSCoords_name:
        convert_coords = True

    # Make sure the required GTFS fields are present.
    required_fields = ["stop_id", "stop_name", "stop_lat", "stop_lon"]
    for field in required_fields:
        if not field in columns:
            arcpy.AddError("Your Stops feature class does not contain the \
required %s field.  Please choose a valid stops feature class generated in \
Step 1 of this toolbox." % field)
            raise CustomError

    # Open the new stops.txt file for writing.
    if ProductName == 'ArcGISPro':
        f = open(outStopstxt, "w", encoding="utf-8", newline='')
    else:
        f = open(outStopstxt, "wb")
    wr = csv.writer(f)
    # Write the headers
    cols_towrite = []
    # If the input is a shapefile, the field names were truncated, so let's restore them.
    if ".shp" in os.path.basename(inStopsFC):
        fullcolnames = {"location_t": "location_type", "parent_sta": "parent_station", "wheelchair": "wheelchair_boarding"}

        for col in columns:
            try:
                cols_towrite.append(fullcolnames[col])
            except KeyError:
                cols_towrite.append(col)
    else:
        cols_towrite = columns
    wr.writerow(cols_towrite)

    # Read in the info from the stops feature class and write it to the new csv file
    fields = ["SHAPE@"] + columns
    stop_lat_idx = fields.index("stop_lat")
    stop_lon_idx = fields.index("stop_lon")
    with arcpy.da.SearchCursor(inStopsFC, fields) as cur:
        for row in cur:
            ptGeometry = row[0]
            if convert_coords:
                ptGeometry = ptGeometry.projectAs(WGSCoords)
            # Extract the lat/lon values from the shape info
            pt = ptGeometry.firstPoint
            stop_lon = pt.X
            stop_lat = pt.Y
            toWrite = list(row)
            # Assign the new lat/lon to the appropriate columns
            toWrite[stop_lat_idx] = stop_lat
            toWrite[stop_lon_idx] = stop_lon
            # Delete the shape info from the stuff to write to the csv file
            toWrite.pop(0)
            if ProductName != 'ArcGISPro':
                toWrite = [x.encode("utf-8") if isinstance(x, basestring) else x for x in toWrite]
            wr.writerow(toWrite)

    f.close()

except CustomError:
    arcpy.AddError("Failed to generate new GTFS stops.txt file.")
    pass

except Exception as err:
    raise
