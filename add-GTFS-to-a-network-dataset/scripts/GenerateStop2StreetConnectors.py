################################################################################
## Toolbox: Add GTFS to a Network Dataset
## Tool name: 2) Generate Stop-Street Connectors
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 16 December 2014
################################################################################
''' This tool snaps the transit stops to the street feature class, generates a
connector line between the original stop location and the snapped stop location,
and adds vertices to the street features at the locations of the snapped stops.
These steps ensure good connectivity in the network dataset.  Alternate methods
can be substituted for this step when the user's data contains more information
about how stops should be connected to streets, such as station entrance
locations or station interior geometry.'''
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

import os, sqlite3
import arcpy

class CustomError(Exception):
    pass

try:

    # Get the original overwrite output setting so we can reset it at the end.
    OverwriteOutput = arcpy.env.overwriteOutput
    # It's okay to overwrite stuff in this tool
    arcpy.env.overwriteOutput = True

    # Check if they have the necessary license.
    # The snap_edit tool requires at least Standard (ArcEditor)
    ArcLicense = arcpy.ProductInfo()
    if ArcLicense != "ArcEditor" and ArcLicense != "ArcInfo":
        message = "To run this tool, you must have the Desktop Standard (ArcEditor) \
    or Advanced (ArcInfo) license.  Your license type is: %s." % ArcLicense
        arcpy.AddError(message)
        raise CustomError


# ----- Collect user inputs -----

    # Location of FD where network dataset will be created
    outFD = arcpy.GetParameterAsText(0)
    # Streets feature class
    Streets = arcpy.GetParameterAsText(1)
    # SQL expression for selecting street features where pedestrians are allowed
    SelectExpression = arcpy.GetParameterAsText(2)
    # Max distance for which stops will be snapped to streets
    snapdist = arcpy.GetParameterAsText(3) # Default: 40m
    # Units of snap distance
    snapunits = arcpy.GetParameterAsText(4) # Default: meters

    outGDB = os.path.dirname(outFD)
    # Stops must exist.  Check is in tool validation
    outStops = os.path.join(outFD, "Stops")
    # The SQL database was created in GenerateStopPairs and placed in the GDB. Name should be correct.
    SQLDbase = os.path.join(outGDB, "GTFS.sql")

    # Output feature classes
    outStopsSnapped = os.path.join(outFD, "Stops_Snapped2Streets")
    outConnectors = os.path.join(outFD, "Connectors_Stops2Streets")
    outStreetsSplit = os.path.join(outFD, "Streets_UseThisOne")
    outTempSelection = os.path.join(outFD, "Temp_SelectedStreets")
    TempSnappedStops = os.path.join(outGDB, "TempStopsSnapped4Integrate")


# ----- Create a feature class for stops snapped to streets -----

    arcpy.AddMessage("Snapping stops to streets network.")

    # Create a copy of the original stops FC.  We don't want to overwrite it.
    arcpy.management.CopyFeatures(outStops, outStopsSnapped)

    # Select only those streets where pedestrians are allowed,
    # as specified by the user's SQL expression
    if SelectExpression:
        SelectionMessage = "Stops will snap only to street features where the \
following is true: " + SelectExpression
        arcpy.AddMessage(SelectionMessage)
    arcpy.analysis.Select(Streets, outTempSelection, SelectExpression)

    # Snap the stops to the streets network, using the snapping tolerance
    # specified in the user's input.
    snapdisttext = str(snapdist) + " " + snapunits # Eg, "40 meters"
    snapenv = [outTempSelection, "EDGE", snapdisttext]
    arcpy.edit.Snap(outStopsSnapped, [snapenv])

    # Clean up.
    arcpy.management.Delete(outTempSelection)


# ----- Generate lines connecting streets with stops -----

    arcpy.AddMessage("Creating connector lines between stops and streets.")

    # Put Stops and Snapped stops into same scratch FC for input to PointsToLine
    outStopsCombined = os.path.join(outGDB, "TempStopswSnapped")
    arcpy.management.CopyFeatures(outStops, outStopsCombined)
    arcpy.management.Append(outStopsSnapped, outStopsCombined)

    # Create Connector lines
    arcpy.management.PointsToLine(outStopsCombined, outConnectors, "stop_id")

    # Clean up.
    arcpy.management.Delete(outStopsCombined)


# ----- Create and populate the wheelchair_boarding field -----

    # Connect to the SQL database
    conn = sqlite3.connect(SQLDbase)
    c = conn.cursor()

    # Determine if wheelchair_boarding is present
    c.execute("PRAGMA table_info(stops)")
    table_info = c.fetchall()
    col_names = []
    for col in table_info:
        col_names.append(col[1])

    if "wheelchair_boarding" in col_names:

        # Make a dictionary of stop wheelchair_boarding info
        GetStopInfoStmt = "SELECT stop_id, wheelchair_boarding, parent_station FROM stops"
        c.execute(GetStopInfoStmt)
        StopInfo = c.fetchall()
        WheelchairBoarding_dict = {} # {stop_id: wheelchair_boarding}
        ParentStation_dict = {} # {stop_id: parent_station}
        for stop in StopInfo:
            WheelchairBoarding_dict[stop[0]] = unicode(stop[1])
            ParentStation_dict[stop[0]] = stop[2]

        # Add wheelchair_boarding information to each stop-street connector
        arcpy.management.AddField(outConnectors, "wheelchair_boarding", "TEXT")
        with arcpy.da.UpdateCursor(outConnectors, ["stop_id", "wheelchair_boarding"]) as cur:
            for row in cur:
                stop_id = row[0]
                wheelchair_boarding = WheelchairBoarding_dict[stop_id]
                if not wheelchair_boarding or wheelchair_boarding==u'0':
                    # If there's a parent station, the stop inherits the value
                    parent_station = ParentStation_dict[stop_id]
                    if WheelchairBoarding_dict.has_key(parent_station):
                        wheelchair_boarding = WheelchairBoarding_dict[parent_station]
                if wheelchair_boarding:
                    row[1] = wheelchair_boarding
                else:
                    row[1] = u'0'
                cur.updateRow(row)


# ----- Create vertices in steets at locations of snapped stops

    arcpy.AddMessage("Creating vertices in streets at location of stops.")
    arcpy.AddMessage("(This step might take a while.)")

    # Copy snapped stops before running integrate because we don't want to make
    # permanent changes to it.
    arcpy.management.CopyFeatures(outStopsSnapped, TempSnappedStops)
    # Copy the streets to a new FC because we're going to modify them.
    arcpy.management.CopyFeatures(Streets, outStreetsSplit)

    # Integrate adds vertices in outStreetsSplit at the locations where
    # TempSnappedStops fall within the default XY Tolerance.  Because the
    # snapped stops are directly on top of the streets, neither streets nor
    # stops should move at all (though Integrate sometimes causes this to
    # happen).
    arcpy.management.Integrate([[outStreetsSplit, 1], [TempSnappedStops, 2]])

    # Clean up.
    arcpy.management.Delete(TempSnappedStops)

    arcpy.AddMessage("Finished!")
    arcpy.AddMessage("Your stop-street connector feature class is:")
    arcpy.AddMessage("- " + outConnectors)
    arcpy.AddMessage("Your feature class of stops snapped to streets is:")
    arcpy.AddMessage("- " + outStopsSnapped)
    arcpy.AddMessage("Your modified streets feature class is:")
    arcpy.AddMessage("- " + outStreetsSplit)

except CustomError:
    arcpy.AddMessage("Failed to generate stop-street connectors.")
    pass

except:
    arcpy.AddMessage("Failed to generate stop-street connectors.")
    raise

finally:
    # Reset the overwrite output to the user's original setting..
    arcpy.env.overwriteOutput = OverwriteOutput