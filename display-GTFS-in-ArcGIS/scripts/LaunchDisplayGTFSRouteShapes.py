############################################################################
## Tool name: Display GTFS in ArcGIS
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 1 April 2017
############################################################################
''' Display GTFS Route Shapes launcher
Display GTFS Route Shapes converts GTFS route and shape data into an ArcGIS
feature class so you can visualize your GTFS routes on a map.
This script launches the correct code depending on the user's ArcGIS verison.
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

class CustomError(Exception):
    pass

try:
    # Check the user's version
    ArcVersionInfo = arcpy.GetInstallInfo("desktop")
    ArcVersion = ArcVersionInfo['Version']
    ProductName = ArcVersionInfo['ProductName']

    if ArcVersion == "10.0":
        arcpy.AddError("Sorry, this tool requires ArcGIS 10.1 or higher.")
    
    if ProductName == "ArcGISPro":
        import DisplayGTFSRouteShapes as disp    
    else:
        if ArcVersion in ["10.1", "10.2", "10.2.1", "10.2.2", "10.3", "10.3.1"]:
            # Use the old sqlite version because pandas wasn't available until 10.4.
            import DisplayGTFSRouteShapes_sqlite as disp
        else:
            import DisplayGTFSRouteShapes as disp

    # Collect input variables from script tool
    inGTFSdir = arcpy.GetParameterAsText(0)
    OutShapesFC = arcpy.GetParameterAsText(1)

    # Recycle these
    disp.ArcVersion = ArcVersion
    disp.ProductName = ProductName

    # Call script
    disp.main(inGTFSdir, OutShapesFC)

except CustomError:
    arcpy.AddError("Failed to generate a feature class of GTFS shapes.")
    pass

except:
    arcpy.AddError("Failed to generate a feature class of GTFS shapes.")
    raise