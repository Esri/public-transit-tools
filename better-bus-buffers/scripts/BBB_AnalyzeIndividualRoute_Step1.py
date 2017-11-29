############################################################################
## Tool name: BetterBusBuffers - Count Trips for Individual Route
## Step 1 - Preprocess Route Buffers
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 25 September 2017
############################################################################
''' BetterBusBuffers - Count Trips for Individual Route: Step 1 - Preprocess Route Buffers

BetterBusBuffers provides a quantitative measure of access to public transit
in your city by counting the transit trip frequency at various locations.

The Count Trips for Individual Route tool creates walking service areas around
all the stops visited by a GTFS route and also generates a point feature class
of the stops. It counts the number of transit trips that pass those stops during
the time window selected, as well as number of trips per hour, the maximum time
between subsequent trips, and the average headway.

Step 1 - Preprocess Route Buffers creates the service areas around the stops.
The trip count information is filled in Step 2.
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


import os, sqlite3
import arcpy
import BBB_SharedFunctions

class CustomError(Exception):
    pass

OverwriteOutput = None
conn = None


def runTool(outGDB, SQLDbase, RouteText, inNetworkDataset, imp, BufferSize, restrictions, TrimSettings):
    try:
        # ------ Get input parameters and set things up. -----
        try:
            # Figure out what version of ArcGIS they're running
            BBB_SharedFunctions.DetermineArcVersion()
            if BBB_SharedFunctions.ProductName == "ArcGISPro" and BBB_SharedFunctions.ArcVersion in ["1.0", "1.1", "1.1.1"]:
                arcpy.AddError("The BetterBusBuffers toolbox does not work in versions of ArcGIS Pro prior to 1.2.\
    You have ArcGIS Pro version %s." % BBB_SharedFunctions.ArcVersion)
                raise CustomError
            
            #Check out the Network Analyst extension license
            if arcpy.CheckExtension("Network") == "Available":
                arcpy.CheckOutExtension("Network")
            else:
                arcpy.AddError("You must have a Network Analyst license to use this tool.")
                raise CustomError

            # Extract impedance attribute and units from text string
            # The input is formatted as "[Impedance] (Units: [Units])"
            implist = imp.split(" (")
            impedanceAttribute = implist[0]

            # Determine the trim settings
            if TrimSettings:
                TrimPolys = "TRIM_POLYS"
                TrimPolysValue = str(TrimSettings) + " meters"
            else:
                TrimPolys = "NO_TRIM_POLYS"
                TrimPolysValue = ""
            
            OverwriteOutput = arcpy.env.overwriteOutput # Get the orignal value so we can reset it.
            arcpy.env.overwriteOutput = True
            # Source FC names are not prepended to field names.
            arcpy.env.qualifiedFieldNames = False

            # If running in Pro, make sure an fgdb workspace is set so NA layers can be created.
            if BBB_SharedFunctions.ProductName == "ArcGISPro":
                if not arcpy.env.workspace:
                    arcpy.AddError(BBB_SharedFunctions.CurrentGPWorkspaceError)
                    raise CustomError
                else:
                    workspacedesc = arcpy.Describe(arcpy.env.workspace)
                    if not workspacedesc.workspaceFactoryProgID.startswith('esriDataSourcesGDB.FileGDBWorkspaceFactory'):
                        arcpy.AddError(BBB_SharedFunctions.CurrentGPWorkspaceError)
                        raise CustomError

        except:
            arcpy.AddError("Error getting user inputs.")
            raise


        # ===== Get trips and stops associated with this route =====

        # ----- Figure out which route the user wants to analyze based on the text input -----
        try:

            arcpy.AddMessage("Gathering route, trip, and stop information...")

            # Connect to or create the SQL file.
            conn = sqlite3.connect(SQLDbase)
            c = BBB_SharedFunctions.c = conn.cursor()

            # Get list of routes in the GTFS data
            routefetch = "SELECT route_short_name, route_long_name, route_id FROM routes;"
            c.execute(routefetch)
            # Extract the route_id based on what the user picked from the GUI list
            # It's better to do it by searching the database instead of trying to extract
            # the route_id from the text they chose because we don't know what kind of
            # characters will be in the route names and id, so parsing could be unreliable
            route_id = ""
            for route in c:
                routecheck = route[0] + ": " + route[1] + " [" + route[2] + "]"
                if routecheck == RouteText:
                    route_id = route[2]
                    route_short_name = route[0]
                    break

            if not route_id:
                arcpy.AddError("Could not parse route selection.")
                raise CustomError

            # Name feature classes
            outStopsname = arcpy.ValidateTableName("Stops_" + route_short_name, outGDB)
            outPolysname = arcpy.ValidateTableName("Buffers_" + route_short_name, outGDB)

        except:
            arcpy.AddError("Error determining route_id for analysis.")
            raise


        # ----- Get trips associated with route and split into directions -----
        try:
            # Some GTFS datasets use the same route_id to identify trips traveling in
            # either direction along a route. Others identify it as a different route.
            # We will consider each direction separately if there is more than one.

            # Get list of trips
            trip_route_dict = {}
            triproutefetch = '''
                SELECT trip_id, direction_id FROM trips
                WHERE route_id='%s'
                ;''' % route_id
            c.execute(triproutefetch)

            # Fill some dictionaries for use later.
            trip_dir_dict = {} # {Direction: [trip_id, trip_id, ...]}
            for triproute in c:
                trip_dir_dict.setdefault(triproute[1], []).append(triproute[0])
            if not trip_dir_dict:
                arcpy.AddError("There are no trips in the GTFS data for the route \
    you have selected (%s).  Please select a different route or fix your GTFS \
    dataset." % RouteText)
                raise CustomError

        except:
            arcpy.AddError("Error getting trips associated with route.")
            raise


        # ----- Get list of stops associated with trips and split into directions -----
        try:
            # If a stop is used for trips going in both directions, count them separately.

            # Select unique set of stops used by trips in each direction
            stoplist = {} # {Direction: [stop_id, stop_id, ...]}
            for direction in trip_dir_dict:
                stops = []
                for trip in trip_dir_dict[direction]:
                    stopsfetch = '''SELECT stop_id FROM stop_times
                                WHERE trip_id == ?'''
                    c.execute(stopsfetch, (trip,))
                    for stop in c:
                        stops.append(stop[0])
                stoplist[direction] = list(set(stops))

            # If there is more than one direction, we will append the direction number
            # to the output fc names, so add an _ here for prettiness.
            if len(stoplist) > 1:
                arcpy.AddMessage("Route %s contains trips going in more than one \
    direction. A separate feature class will be created for each direction, and the \
    GTFS direction_id will be appended to the feature class name." % route_short_name)
                outStopsname += "_"
                outPolysname += "_"

        except:
            arcpy.AddError("Error getting stops associated with route.")
            raise


        # ===== Create output =====

        # ----- Create a feature class of stops ------
        try:

            arcpy.AddMessage("Creating feature class of GTFS stops...")

            for direction in stoplist:
                stops = stoplist[direction]
                outputname = outStopsname
                if direction != None:
                    outputname += str(direction)
                outStops = os.path.join(outGDB, outputname)

                outStops, outStopList = BBB_SharedFunctions.MakeStopsFeatureClass(outStops, stops)

                # Add a route_id and direction_id field and populate it
                arcpy.management.AddField(outStops, "route_id", "TEXT")
                arcpy.management.AddField(outStops, "direction_id", "TEXT")
                fields = ["route_id", "direction_id"]
                if BBB_SharedFunctions.ArcVersion == "10.0":
                    cursor = arcpy.UpdateCursor(outStops)
                    for row in cursor:
                        row.setValue("route_id", route_id)
                        row.setValue("direction_id", direction)
                        cursor.updateRow(row)
                    del cursor
                else:
                    with arcpy.da.UpdateCursor(outStops, fields) as cursor:
                        for row in cursor:
                            row[0] = route_id
                            row[1] = direction
                            cursor.updateRow(row)

        except:
            arcpy.AddError("Error creating feature class of GTFS stops.")
            raise


        #----- Create Service Areas around stops -----
        try:

            arcpy.AddMessage("Creating buffers around stops...")

            for direction in stoplist:
                outputname = outStopsname
                if direction != None:
                    outputname += str(direction)
                outStops = os.path.join(outGDB, outputname)

                polygons = BBB_SharedFunctions.MakeServiceAreasAroundStops(outStops, inNetworkDataset, impedanceAttribute, BufferSize, restrictions, TrimPolys, TrimPolysValue)

                # Join stop information to polygons and save as feature class
                arcpy.management.AddJoin(polygons, "stop_id", outStops, "stop_id")
                outPolys = outPolysname
                if direction != None:
                    outPolys += str(direction)
                outPolysFC = os.path.join(outGDB, outPolys)
                arcpy.management.CopyFeatures(polygons, outPolysFC)

                # Add a route_id and direction_id field and populate it
                arcpy.management.AddField(outPolysFC, "route_id", "TEXT")
                arcpy.management.AddField(outPolysFC, "direction_id", "TEXT")
                fields = ["route_id", "direction_id"]
                if BBB_SharedFunctions.ArcVersion == "10.0":
                    cursor = arcpy.UpdateCursor(outPolysFC)
                    for row in cursor:
                        row.setValue("route_id", route_id)
                        row.setValue("direction_id", direction)
                        cursor.updateRow(row)
                    del cursor
                else:
                    with arcpy.da.UpdateCursor(outPolysFC, fields) as cursor:
                        for row in cursor:
                            row[0] = route_id
                            row[1] = direction
                            cursor.updateRow(row)

        except:
            arcpy.AddError("Error creating buffers around stops.")
            raise

        arcpy.AddMessage("Done!")
        arcpy.AddMessage("Output written to %s is:" % outGDB)
        outFClist = []
        for direction in stoplist:
            outPolysFC = outPolysname
            outStopsFC = outStopsname
            if direction != None:
                outStopsFC += str(direction)
                outPolysFC += str(direction)
            outFClist.append(outStopsFC)
            outFClist.append(outPolysFC)
            arcpy.AddMessage("- " + outStopsFC)
            arcpy.AddMessage("- " + outPolysFC)

        # Tell the tool that this is output. This will add the output to the map.
        outFClistwpaths = [os.path.join(outGDB, fc) for fc in outFClist]
        arcpy.SetParameterAsText(8, ';'.join(outFClistwpaths))

    except CustomError:
        arcpy.AddError("Failed to create buffers around stops for this route.")
        pass

    except:
        arcpy.AddError("Failed to create buffers around stops for this route.")
        raise

    finally:
        if OverwriteOutput:
            arcpy.env.overwriteOutput = OverwriteOutput
