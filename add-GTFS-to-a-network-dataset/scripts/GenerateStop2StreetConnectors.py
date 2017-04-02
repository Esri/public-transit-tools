################################################################################
## Toolbox: Add GTFS to a Network Dataset
## Tool name: 2) Generate Stop-Street Connectors
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 9 February 2017
################################################################################
''' This tool snaps the transit stops to the street feature class, generates a
connector line between the original stop location and the snapped stop location,
and adds vertices to the street features at the locations of the snapped stops.
These steps ensure good connectivity in the network dataset.  Alternate methods
can be substituted for this step when the user's data contains more information
about how stops should be connected to streets, such as station entrance
locations or station interior geometry.'''
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
    

# ----- Collect parent_station info -----

    parent_stations = {}
    where = "location_type = '1'"
    with arcpy.da.SearchCursor(outStops, ["Shape@", "stop_id"], where) as cur:
        for row in cur:
            parent_stations[row[1]] = row[0].firstPoint # Use firstPoint to convert from PointGeometry to Point


# ----- Create a feature class for stops snapped to streets -----

    arcpy.AddMessage("Snapping stops to streets network...")

    # Create a copy of the original stops FC.  We don't want to overwrite it.
    arcpy.management.CopyFeatures(outStops, outStopsSnapped)
    SR = arcpy.Describe(outStopsSnapped).spatialReference


# ----- Handle parent stations and station entrances -----

    # Delete station entrances from Stops - these will only be in the snapped version to connect to streets
    # Also make a list of parent stations with entrances
    parent_stations_with_entrances = []
    where = "location_type = '2'"
    with arcpy.da.UpdateCursor(outStops, ["parent_station"], where) as cur:
        for row in cur:
            parent_stations_with_entrances.append(row[0])
            cur.deleteRow()
    parent_stations_with_entrances = list(set(parent_stations_with_entrances))
                
    # Remove parent stations with valid entrances from snapped stops. They will be connected to streets through the entrances.
    if parent_stations_with_entrances:
        where = "location_type = '1'"
        with arcpy.da.UpdateCursor(outStopsSnapped, ["stop_id"], where) as cur:
            for row in cur:
                if row[0] in parent_stations_with_entrances:
                    cur.deleteRow()

    # Remove any stops that have a parent station.
    # These should be connected to the parent station and not the street
    parent_station_connectors = [] # list of line features
    parent_stations_to_delete = []
    if parent_stations:
        where = "parent_station <> '' and location_type = '0'"
        with arcpy.da.UpdateCursor(outStopsSnapped, ["Shape@", "stop_id", "parent_station", "location_type"], where) as cur:
            for row in cur:
                parent_station_id = row[2]
                if parent_station_id not in parent_stations:
                    # This is a data problem, but we can get around it by just 
                    # snapping the stop to the street instead of the missing parent station
                    continue
                # Generate a straight line between the stop and its parent station
                array = arcpy.Array()
                array.add(row[0].firstPoint) # Use firstPoint to convert from PointGeometry to Point
                array.add(parent_stations[parent_station_id])
                polyline = arcpy.Polyline(array, SR)
                if polyline.length != 0:
                    # Keep the line for later when we'll add it to the connectors feature class
                    parent_station_connectors.append([row[1], polyline, parent_station_id]) # [[stop_id, polyline geometry], [], ...]
                else:
                    # If the stop and parent station are in the same place, don't generate a line because
                    # this will cause network build errors.  Instead, we'll delete the parent_station later.
                    parent_stations_to_delete.append(parent_station_id)
                # Delete this row from the snapped stops because the stop snaps to its parent station and not the street
                cur.deleteRow()
        parent_stations_to_delete = list(set(parent_stations_to_delete))
    
    
# ----- Snap stops to streets -----
    
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

    arcpy.AddMessage("Creating connector lines between stops and streets...")

    # Put Stops and Snapped stops into same scratch FC for input to PointsToLine
    outStopsCombined = os.path.join(outGDB, "TempStopswSnapped")
    arcpy.management.CopyFeatures(outStops, outStopsCombined)
    arcpy.management.Append(outStopsSnapped, outStopsCombined)

    # Create Connector lines
    arcpy.management.PointsToLine(outStopsCombined, outConnectors, "stop_id")
    arcpy.management.AddField(outConnectors, "connector_type", "TEXT")
    arcpy.management.CalculateField(outConnectors, "connector_type", '"Direct stop to street connection"', "PYTHON_9.3")

    # Clean up.
    arcpy.management.Delete(outStopsCombined)


# ----- Generate lines connecting parent stations with their child stops -----

    # Delete parent stations that are coincident with stops.
    if parent_stations_to_delete:
        where = "location_type = '1'"
        with arcpy.da.UpdateCursor(outStops, ["stop_id"], where) as cur:
            for row in cur:
                if row[0] in parent_stations_to_delete:
                    cur.deleteRow()

    # Add connections between child stops and parent stations
    if parent_station_connectors:
        arcpy.management.AddField(outConnectors, "parent_station", "TEXT")
        with arcpy.da.InsertCursor(outConnectors, ["stop_id", "SHAPE@", "parent_station", "connector_type"]) as cur:
            for connector in parent_station_connectors:
                cur.insertRow(connector + ["Stop to parent station connection"])


# ----- Generate lines connecting parent stations with their street entrances

    if parent_stations_with_entrances:
        station_entrance_connectors = []
        where = "location_type = '2'"
        with arcpy.da.UpdateCursor(outStopsSnapped, ["Shape@", "stop_id", "parent_station"], where) as cur:
            for row in cur:
                parent_station_id = row[2]
                # Generate a straight line between the parent station and the street entrance
                array = arcpy.Array()
                array.add(parent_stations[parent_station_id]) 
                array.add(row[0].firstPoint) # Use firstPoint to convert from PointGeometry to Point
                polyline = arcpy.Polyline(array, SR)
                if polyline.length == 0:
                    # If the station entrance and parent station are in the same place, don't generate a line because
                    # this will cause network build errors.  Just delete the entrance because we don't need it.
                    # This should only happen if the parent station coincidentally falls exactly on top of a street feature
                    cur.deleteRow()
                    continue
                # Keep the line for later when we'll add it to the connectors feature class
                station_entrance_connectors.append([row[1], polyline, parent_station_id]) # [[stop_id, polyline geometry], [], ...]
        
        # Actually add the lines
        if station_entrance_connectors:
            with arcpy.da.InsertCursor(outConnectors, ["stop_id", "SHAPE@", "parent_station", "connector_type"]) as cur:
                for connector in station_entrance_connectors:
                    cur.insertRow(connector + ["Parent station to street entrance connection"])
                    

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
        arcpy.AddMessage("Handling wheelchair_boarding...")

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

    arcpy.AddMessage("Creating vertices in streets at location of stops...")
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