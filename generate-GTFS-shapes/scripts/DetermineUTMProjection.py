''' Given a lat/lon, determine the most appropriate UTM projection and return
it as text.  Does not handle special UTM zones, just the standard ones.'''
## Melinda Morang, Esri mmorang@esri.com, 909-793-2853 x3315
## Last updated: 8 October 2015
################################################################################
'''Copyright 2015 Esri
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

import arcpy

def GetUTMZoneAsText(lat, lon):

    # Determine the hemisphere
    if lat > 0:
        hemisphere = "N"
    else:
        hemisphere = "S"

    # Determine the UTM zone
    UTMZone = int((lon + 180)/6) + 1

    # Determine the central meridian
    centralMeridian = -177 + 6 * (UTMZone-1)

    # Add these to the text definition of the spatial reference
    proj = '''PROJCS['WGS_1984_UTM_Zone_%s%s',GEOGCS['GCS_WGS_1984', \
    DATUM['D_WGS_1984',SPHEROID['WGS_1984',6378137.0,298.257223563]], \
    PRIMEM['Greenwich',0.0],UNIT['Degree',0.0174532925199433]], \
    PROJECTION['Transverse_Mercator'],PARAMETER['False_Easting',500000.0], \
    PARAMETER['False_Northing',0.0],PARAMETER['Central_Meridian',%s.0], \
    PARAMETER['Scale_Factor',0.9996],PARAMETER['Latitude_Of_Origin',0.0], \
    UNIT['Meter',1.0]];-5120900 -9998100 10000;-100000 10000;-100000 10000;0.001;0.001;0.001;IsHighPrecision''' % (str(UTMZone), str(hemisphere), str(centralMeridian))

    return proj