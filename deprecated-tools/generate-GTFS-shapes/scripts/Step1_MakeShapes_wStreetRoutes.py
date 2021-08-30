###############################################################################
## Tool name: Generate GTFS Route Shapes
## Step 1: Generate Shapes on Map - Network Analyst version launcher
## Creator: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 18 January 2017
###############################################################################
''' Reads inputs from ArcMap and passes them to Step1_MakeShapesFC.py
where all the real work is done.'''
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

# Step 1 - read inputs from ArcGIS GUI
# All the main Step 1 work is done in Step1_MakeShapesFC.py.
import Step1_MakeShapesFC
import arcpy

# ----- Get user inputs from GUI -----
# Note: All variables are becoming global variables in the Step1_MakeShapesFC.py.

Step1_MakeShapesFC.inGTFSdir = arcpy.GetParameterAsText(0)
Step1_MakeShapesFC.outDir = arcpy.GetParameterAsText(1)
Step1_MakeShapesFC.outGDBName = arcpy.GetParameterAsText(2)
Step1_MakeShapesFC.in_route_type_Street = arcpy.GetParameterAsText(3)
Step1_MakeShapesFC.in_route_type_Straight = arcpy.GetParameterAsText(4)
Step1_MakeShapesFC.inNetworkDataset = arcpy.GetParameterAsText(5)

imp = arcpy.GetParameterAsText(6)
# Extract impedance attribute and units from text string
# The input is formatted as "[Impedance] (Units: [Units])"
implist = imp.split(" (")
Step1_MakeShapesFC.impedanceAttribute = implist[0]
Step1_MakeShapesFC.driveSide = arcpy.GetParameterAsText(7)
Step1_MakeShapesFC.UTurn_input = arcpy.GetParameterAsText(8)
Step1_MakeShapesFC.restrictions = arcpy.GetParameterAsText(9)
Step1_MakeShapesFC.BearingTol = float(arcpy.GetParameterAsText(10))
Step1_MakeShapesFC.MaxAngle = float(arcpy.GetParameterAsText(11))

Step1_MakeShapesFC.useNA = True
Step1_MakeShapesFC.useBearing = True # Maybe be overridden later if ArcGIS version doesn't support this functionality

# ----- Call the main Step 1 code and feed it the user input -----

# Pass all the parameters to the main function in the shared Step 1 library.
Step1_MakeShapesFC.RunStep1()

