####################################################
## Tool name: BetterBusBuffers
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 4 February 2016
####################################################
''' BetterBusBuffers Polygon Tool: Step 1 - Preprocess Buffers

BetterBusBuffers provides a quantitative measure of access to public transit
in your city.  It creates buffers around the transit stops and weights them by
the number of trips that pass that stop during the time window you select,
accounting for areas served by more than one stop.
Output can be shown as the total number of trips or the average number of trips
per hour during the time window.  You can use the symbology settings of the
resulting feature class to highlight the frequency of service in different
areas of town.  Note that the tool tells you nothing about the destination of
the buses that pass by the stops, only how many of them there are.
BetterBusBuffers uses GTFS public transit data and ArcGIS Network Analyst.

Step 1 does the following:
- Creates service areas around your transit stops
- Runs some post-processing on those service areas to prepare them for further
  analysis
You should only have to run Step 1 once for the geography and buffer size you
are analyzing.  Step 1 will take a while to run for larger transit systems.
'''
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

import os, sqlite3
from shutil import copyfile
import arcpy
import BBB_SharedFunctions


class CustomError(Exception):
    pass


def runTool(outDir, outGDB, inSQLDbase, inNetworkDataset, imp, BufferSize, restrictions, TrimSettings):
    try:

    # ----- Set up the run -----
        try:

            version_error = BBB_SharedFunctions.CheckProVersion("1.2")
            if version_error:
                arcpy.AddError(version_error)
                raise CustomError

            ArcLicense = arcpy.ProductInfo()
            if ArcLicense != "ArcInfo":
                arcpy.AddError("To run this tool, you must have the Desktop \
    Advanced (ArcInfo) license.  Your license type is: %s." % ArcLicense)
                raise CustomError

            #Check out the Network Analyst extension license
            if arcpy.CheckExtension("Network") == "Available":
                arcpy.CheckOutExtension("Network")
            else:
                arcpy.AddError("You must have a Network Analyst license to use this tool.")
                raise CustomError

            # If running in Pro, make sure an fgdb workspace is set so NA layers can be created.
            if BBB_SharedFunctions.ProductName == "ArcGISPro":
                if not arcpy.env.workspace:
                    arcpy.AddError(BBB_SharedFunctions.CurrentGPWorkspaceError)
                    print(BBB_SharedFunctions.CurrentGPWorkspaceError)
                    raise CustomError
                else:
                    workspacedesc = arcpy.Describe(arcpy.env.workspace)
                    if not workspacedesc.workspaceFactoryProgID.startswith('esriDataSourcesGDB.FileGDBWorkspaceFactory'):
                        arcpy.AddError(BBB_SharedFunctions.CurrentGPWorkspaceError)
                        print(BBB_SharedFunctions.CurrentGPWorkspaceError)
                        raise CustomError

            # It's okay to overwrite in-memory stuff.
            OverwriteOutput = arcpy.env.overwriteOutput # Get the orignal value so we can reset it.
            arcpy.env.overwriteOutput = True

            # Append .gdb to geodatabase name.
            if not outGDB.lower().endswith(".gdb"):
                outGDB = outGDB + ".gdb"
            outGDBwPath = os.path.join(outDir, outGDB)
            # Create a file geodatabase for the results.
            arcpy.management.CreateFileGDB(outDir, outGDB)

            # Make a copy of the input SQL file in the Step 1 output so we can modify it.
            SQLDbase = os.path.join(outGDBwPath, "Step1_GTFS.sql")
            copyfile(inSQLDbase, SQLDbase)
            # Connect to or create the SQL file.
            conn = sqlite3.connect(SQLDbase)
            c = BBB_SharedFunctions.c = conn.cursor()

            # Extract impedance attribute and units from text string
            # The input is formatted as "[Impedance] (Units: [Units])"
            implist = imp.split(" (")
            impedanceAttribute = implist[0]

            if TrimSettings:
                TrimPolys = "TRIM_POLYS"
                TrimPolysValue = str(TrimSettings) + " meters"
            else:
                TrimPolys = "NO_TRIM_POLYS"
                TrimPolysValue = ""

        except:
            arcpy.AddError("Error setting up run.")
            raise


    #----- Make a feature class of GTFS stops that we can use for buffers -----
        try:
            # Create a feature class of transit stops
            arcpy.AddMessage("Creating a feature class of GTFS stops...")
            StopsLayer, StopIDList = BBB_SharedFunctions.MakeStopsFeatureClass(os.path.join(outGDBwPath, "Step1_Stops"))
        except:
            arcpy.AddError("Error creating a feature class of GTFS stops.")
            raise


    #----- Create Service Areas around all stops in the system -----
        try:
            arcpy.AddMessage("Creating service areas around stops...")
            arcpy.AddMessage("(This step will take a while for large networks.)")
            polygons = BBB_SharedFunctions.MakeServiceAreasAroundStops(StopsLayer,
                                inNetworkDataset, impedanceAttribute, BufferSize,
                                restrictions, TrimPolys, TrimPolysValue)
        except:
            arcpy.AddError("Error creating service areas around stops.")
            raise


    #----- Post-process the polygons to prepare for Step 2 -----
        try:

            arcpy.AddMessage("Reformatting polygons for further analysis...")
            arcpy.AddMessage("(This step will take a while for large networks.)")

            polycopy = os.path.join(outGDBwPath, "Temp_Polygons")
            if BBB_SharedFunctions.ArcVersion == "10.0":
                # For some reason, passing an NALayer reference object to FeatureToPolygon
                # in PostProcessPolys() causes ArcMap 10.0 to crash.  Avoid this
                # by saving the layer to a feature class and passing the path.
                arcpy.management.CopyFeatures(polygons, polycopy)
                polygons = polycopy


            # ----- Flatten the overlapping service area polygons -----

            # Use World Cylindrical Equal Area (WKID 54034) to ensure proper use of cluster tolerance in meters
            arcpy.env.outputCoordinateSystem = BBB_SharedFunctions.WorldCylindrical

            # Flatten the overlapping polygons.  This will ultimately be our output.
            # Dummy points to use in FeatureToPolygon to get rid of unnecessary fields.
            dummypoints = arcpy.management.CreateFeatureclass("in_memory",
                                                                "DummyPoints", "POINT")

            # The flattened polygons will be our ultimate output in the end (final
            # output of step 2).
            FlatPolys = os.path.join(outGDBwPath, "Step1_FlatPolys")
            # FeatureToPolygon flattens overalpping polys.
            # Set a large cluster tolerance to eliminate small sliver polygons and to
            # keep the output file size down.  Boundaries may move up to the distance
            # specified in the cluster tolerance, but some amount of movement is
            # acceptable, as service area polygons are inexact anyway.
            # The large cluster tolerance may cause some geometry issues with the output
            # later, but this is the best solution I've found so far that doesn't eat
            # up too much analysis time and memory
            clusTol = "5 meters"
            arcpy.management.FeatureToPolygon(polygons, FlatPolys, clusTol, "", dummypoints)
            arcpy.management.Delete(dummypoints)

            # Add a field to the output file for number of trips and num trips / hour.
            # Also create a polygon id field so we can keep track of them.
            arcpy.management.AddField(FlatPolys, "PolyID", "LONG")
            arcpy.management.AddField(FlatPolys, "NumTrips", "LONG")
            arcpy.management.AddField(FlatPolys, "NumTripsPerHr", "DOUBLE")
            arcpy.management.AddField(FlatPolys, "NumStopsInRange", "LONG")
            arcpy.management.AddField(FlatPolys, "MaxWaitTime", "DOUBLE")


            # ----- Create stacked points, one for each original SA polygon -----

            # Create points for use in the Identity tool (one point per poly)
            FlattenedPoints = os.path.join(outGDBwPath, "Step1_FlattenedPoints")
            arcpy.management.FeatureToPoint(FlatPolys, FlattenedPoints, "INSIDE")

            # Use Identity to stack points and keep the stop_ids from the original SAs.
            # Results in a points layer with fields ORIG_FID for the IDs of the
            # flattened polygons and a stop_id column with the stop ids.
            # Points are stacked, and each has only one stop_id.
            StackedPoints = os.path.join(outGDBwPath, "Step1_StackedPoints")
            arcpy.analysis.Identity(FlattenedPoints, polygons, StackedPoints)
            arcpy.management.Delete(FlattenedPoints)


            # ----- Read the Stacked Points into an SQL table -----

            # Create a SQL table associating the Polygon FID with the stop_ids that serve it.
            c.execute("DROP TABLE IF EXISTS StackedPoints;")
            schema = "Polygon_FID LONG, stop_id TEXT"
            create_stmt = "CREATE TABLE StackedPoints (%s);" % schema
            c.execute(create_stmt)

            # Add data to the table. Track Polygon IDs with no associated stop_ids so we can delete them.
            FIDsToDelete = []
            AddToStackedPts = []
            if BBB_SharedFunctions.ArcVersion == "10.0":
                StackedPtCursor = arcpy.SearchCursor(StackedPoints, "", "", "ORIG_FID; stop_id")
                for row in StackedPtCursor:
                    if not row.stop_id:
                        FIDsToDelete.append(row.ORIG_FID)
                    else:
                        AddToStackedPts.append((row.ORIG_FID, row.stop_id,))
            else:
                StackedPtCursor = arcpy.da.SearchCursor(StackedPoints, ["ORIG_FID", "stop_id"])
                for row in StackedPtCursor:
                    if not row[1]:
                        FIDsToDelete.append(row[0])
                    else:
                        AddToStackedPts.append((row[0], row[1],))
            del StackedPtCursor
            # Add the OD items to the SQL table
            c.executemany('''INSERT INTO StackedPoints \
                            (Polygon_FID, stop_id) \
                            VALUES (?, ?);''', AddToStackedPts)
            conn.commit()
            arcpy.management.Delete(StackedPoints)
            FIDsToDelete = set(FIDsToDelete)


            # ----- Delete polygons not associated with any stop_ids -----
            # These were generated by the FeatureToPolygon tool in areas completely
            # surrounded by other polygons and aren't associated with any stops.

            # Make feature layer containing only the polygons we want to delete.
            desc2 = arcpy.Describe(FlatPolys)
            OutputOIDName = desc2.OIDFieldName
            # Anything with 0 area will just cause problems later.
            WhereClause = '"Shape_Area" = 0'
            if FIDsToDelete:
                WhereClause += ' OR "' + OutputOIDName + '" IN ('
                for FID in FIDsToDelete:
                    WhereClause += str(FID) + ", "
                WhereClause = WhereClause[:-2] + ")"
            arcpy.management.MakeFeatureLayer(FlatPolys, "FlatPolysLayer", WhereClause)

            # Delete the polygons that don't correspond to any stop_ids.
            arcpy.management.DeleteFeatures("FlatPolysLayer")


            # ----- Populate the PolyID field -----

            # Set PolyID equal to the OID.
            expression = "!" + OutputOIDName + "!"
            arcpy.management.CalculateField(FlatPolys, "PolyID", expression, "PYTHON")


        except:
            arcpy.AddError("Error post-processing polygons")
            raise
        finally:
            if arcpy.Exists(polycopy):
                arcpy.management.Delete(polycopy)

        arcpy.AddMessage("Done!")
        arcpy.AddMessage("Files written to output geodatabase " + outGDBwPath + ":")
        arcpy.AddMessage("- Step1_Stops")
        arcpy.AddMessage("- Step1_FlatPolys")
        arcpy.AddMessage("- Step1_GTFS.sql")

        # Tell the tool that this is output. This will add the output to the map.
        arcpy.SetParameterAsText(8, os.path.join(outGDBwPath, "Step1_Stops"))
        arcpy.SetParameterAsText(9, os.path.join(outGDBwPath, "Step1_FlatPolys"))
        arcpy.SetParameterAsText(10, os.path.join(outGDBwPath, "Step1_GTFS.sql"))


    except CustomError:
        arcpy.AddError("Failed to create BetterBusBuffers polygons.")
        pass
    except:
        arcpy.AddError("Failed to create BetterBusBuffers polygons.")
        raise
