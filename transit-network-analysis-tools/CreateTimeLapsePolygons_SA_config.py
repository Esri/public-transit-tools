"""Defines Service Area solver object properties that are not specified in the tool dialog.

A list of Service Area solver properties is documented here:
https://pro.arcgis.com/en/pro-app/latest/arcpy/network-analyst/servicearea.htm

You can include any of them in the dictionary in this file, and the tool will
use them. However, values for any of the properties in SA_PROPS_SET_BY_TOOL
will be ignored because they are specified in the tool dialog.

Copyright 2021 Esri
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at
       http://www.apache.org/licenses/LICENSE-2.0
   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""
import arcpy

# These properties are set by the tool dialog or can be specified as command line arguments. Do not set the values for
# these properties in the SA_PROPS dictionary below because they will be ignored.
SA_PROPS_SET_BY_TOOL = [
    "defaultImpedanceCutoffs",
    "geometryAtCutoff",
    "geometryAtOverlap",
    "timeUnits",
    "timeOfDay",
    "travelDirection",
    "travelMode"
]

# You can customize these properties to your needs, and the parallel OD cost matrix calculations will use them.
SA_PROPS = {
    "accumulateAttributeNames": [],
    "allowSaveLayerFile": False,
    "distanceUnits": arcpy.nax.DistanceUnits.Kilometers,
    "excludeSourcesFromPolygonGeneration": ["LineVariantElements", "StopConnectors"],
    "ignoreInvalidLocations": True,
    "outputType": arcpy.nax.ServiceAreaOutputType.Polygons,  # Tool won't work if you change this.
    "overrides": "",
    "polygonBufferDistance": 30,
    "polygonBufferDistance": arcpy.nax.DistanceUnits.Meters,
    "polygonDetail": arcpy.nax.ServiceAreaPolygonDetail.High,
    # "searchQuery": [],  # This parameter is very network specific. Only uncomment if you are using it.
    "searchTolerance": 500,
    "searchToleranceUnits": arcpy.nax.DistanceUnits.Meters,
    "timeZone": arcpy.nax.TimeZoneUsage.LocalTimeAtLocations
}
