###############################################################################
## Tool name: Generate GTFS Route Shapes
## Helper functions for routing in ArcGIS Online
## Creator: Melinda Morang, Esri, mmorang@esri.com
## Modified and expanded from a code sample written by Deelesh Mandloi, Esri
## Last updated: 16 May 2016
###############################################################################
'''Helper functions for using the ArcGIS Online services to generate routes.'''
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

import sys
ispy3 = sys.version_info > (3, 0)

import json
import time
import datetime
import gzip
import arcpy

# urllib changed a lot with python3
if ispy3:
    import urllib.parse as urllib
    import urllib.request as urllib2
    import io as sio
    import codecs
else:
    import urllib
    import urllib2
    try:
        import cStringIO as sio
    except ImportError as ex:
        import StringIO as sio

# Note: Accessing the ArcGIS Online services to solve routes will use credits.
# See the rates for "Simple Routes" here: http://www.esri.com/software/arcgis/arcgisonline/credits

# Online services limits defined in the RestAPI documentation for synchronous route service
# http://resources.arcgis.com/en/help/arcgis-rest-api/#/Route_service_with_synchronous_execution/02r300000036000000/
route_stop_limit = 150

# Travel mode dictionary - these are the settings that will be used in the route analysis
travel_mode = """{
   "attributeParameterValues": [
    {
     "parameterName": "Restriction Usage",
     "attributeName": "Avoid Unpaved Roads",
     "value": "AVOID_HIGH"
    },
    {
     "parameterName": "Restriction Usage",
     "attributeName": "Avoid Private Roads",
     "value": "AVOID_MEDIUM"
    },
    {
     "parameterName": "Restriction Usage",
     "attributeName": "Driving an Automobile",
     "value": "PROHIBITED"
    },
    {
     "parameterName": "Restriction Usage",
     "attributeName": "Through Traffic Prohibited",
     "value": "AVOID_HIGH"
    },
    {
     "parameterName": "Restriction Usage",
     "attributeName": "Avoid Gates",
     "value": "AVOID_MEDIUM"
    }
   ],
   "description": "Custom travel mode created for Generate GTFS Shapes",
   "impedanceAttributeName": "TravelTime",
   "simplificationToleranceUnits": "esriMeters",
   "uturnAtJunctions": "esriNFSBAtDeadEndsAndIntersections",
   "restrictionAttributeNames": [
    "Avoid Unpaved Roads",
    "Avoid Private Roads",
    "Driving an Automobile",
    "Through Traffic Prohibited",
    "Avoid Gates"
   ],
   "useHierarchy": true,
   "simplificationTolerance": 2,
   "timeAttributeName": "TravelTime",
   "distanceAttributeName": "Kilometers",
   "type": "AUTOMOBILE",
   "id": "",
   "name": "Driving Time for Generate GTFS Shapes"
  }"""

token = None

def get_token():
    global token
    token = arcpy.GetSigninToken()

def makeHTTPRequest(url, query_params=None, content_coding_token="gzip", referer=None):
    """Makes an HTTP request and returns the JSON response. content_coding_token
       must be gzip or identity.
       If content_coding_token is identity, response does not need any transformation.
       If content_coding_token is gzip, the response special handling before converting to JSON."""

    response_dict = {}
    if query_params == None:
        query_params = {}
    if not "f" in query_params:
        query_params["f"] = "json"

    request = urllib2.Request(url)
    if ispy3:
        data = urllib.urlencode(query_params)
        binary_data = data.encode('utf-8')
        request.data = binary_data
    else:        
        request.add_data(urllib.urlencode(query_params))
    request.add_header("Accept-Encoding", content_coding_token)
    if referer:
        request.add_header("Referer", referer)
    response = urllib2.urlopen(request)
    if content_coding_token == "gzip":
        if response.info().get("Content-Encoding") == "gzip":
            if ispy3:
                # Encoding is complicated in python3
                buf = sio.BytesIO(response.read())
                response = gzip.GzipFile(fileobj=buf, mode='rb')
                reader = codecs.getreader("utf-8")
                response = reader(response)
            else:
                buf = sio.StringIO(response.read())
                response = gzip.GzipFile(fileobj=buf)
    response_dict = json.load(response)
    return response_dict

def execute_request(task_url, token, referer, task_params):

    common_parameters = {"f" : "json"}
    if token:
        common_parameters["token"] = token
    else:
        referer = None

    parameters = dict(task_params)
    parameters.update(common_parameters)
    
    before_time = time.time()

    response = makeHTTPRequest(task_url, parameters, referer=referer)
    after_time = time.time()
    return response, after_time - before_time

def generate_polyline_objects_from_json(json_response):
    
    # Route features
    features = json_response["routes"]["features"]
    spatialref = json_response["routes"]["spatialReference"]
    
    # Use AsShape to convert Esri JSON to polyline features
    polylines = []
    for feature in features:
        esri_json = {
            "paths" : feature["geometry"]["paths"],
            "spatialReference" : spatialref}
        polylines.append(arcpy.AsShape(esri_json, True))

    return polylines

def solve_routes(tokenstuff, service_params):

    # URL to Esri ArcGIS Online asynchronous routing service
    service_url = "http://route.arcgis.com/arcgis/rest/services/World/Route/NAServer/Route_World/solve"

    # Make sure the token isn't about to expire. If it is, wait until it expires and then get a new one.
    now = datetime.datetime.now()
    tokenexpiretime = datetime.datetime.fromtimestamp(tokenstuff['expires'])
    if tokenexpiretime - now < datetime.timedelta(seconds=5):
        time.sleep(5)
        get_token()
        tokenstuff = token

    #Execute the request
    response, response_time = execute_request(service_url, tokenstuff['token'], tokenstuff['referer'], service_params)
    
    return response

def generate_routes_from_AGOL_as_polylines(tokenstuff, service_params):

    polylines = ""
    errors = ""

    # Solve the route and grab the json response
    response = solve_routes(tokenstuff, service_params)
    
    # Check if any errors were returned.
    if "error" in response:
        code = response["error"]["code"]
        message = response["error"]["message"]
        details = response["error"]["details"]
        detailsstr = "; ".join(details)
        errors = "Error code %s, %s. Details: %s" % (str(code), message, detailsstr)
    
    else:
    # Convert the json into a list of arcpy polyline shape object
        polylines = generate_polyline_objects_from_json(response)
    
    return polylines, errors