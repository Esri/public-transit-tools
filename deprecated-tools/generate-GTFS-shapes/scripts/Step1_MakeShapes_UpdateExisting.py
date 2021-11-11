###############################################################################
## Tool name: Generate GTFS Route Shapes
## Step 1: Update Existing Shapes - Update existing shapes version launcher
## Creator: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 25 December 2016
###############################################################################
''' Reads inputs from ArcMap and passes them to Step1_MakeShapesFC.py
where all the real work is done.'''
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

# Step 1 - read inputs from ArcGIS GUI
# All the main Step 1 work is done in Step1_MakeShapesFC.py.
import Step1_MakeShapesFC
import arcpy

# ----- Get user inputs from GUI -----
# Note: All variables are becoming global variables in the Step1_MakeShapesFC.py.

Step1_MakeShapesFC.inGTFSdir = arcpy.GetParameterAsText(0)
Step1_MakeShapesFC.outDir = arcpy.GetParameterAsText(1)
Step1_MakeShapesFC.outGDBName = arcpy.GetParameterAsText(2)

shapes_to_update = arcpy.GetParameterAsText(3)
# Fix up list shapes (it comes in as a ;-separated list)
shapes_to_update = shapes_to_update.split(";")
# Remove single quotes ArcGIS puts in if there are spaces in the name.
for d in shapes_to_update:
    if d[0] == "'" and d[-1] == "'":
        loc = shapes_to_update.index(d)
        shapes_to_update[loc] = d[1:-1]


# ----- Call the main Step 1 code and feed it the user input -----

# Pass all the parameters to the main function in the shared Step 1 library.
Step1_MakeShapesFC.RunStep1_existing_shapestxt(shapes_to_update)
