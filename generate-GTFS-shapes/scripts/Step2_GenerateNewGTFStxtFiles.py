###############################################################################
## Tool name: Generate GTFS Route Shapes
## Step 2: Generate new GTFS text files
## Creator: Melinda Morang, Esri
## Last updated: 4 September 2019
###############################################################################
'''Using the GDB created in Step 1, this tool adds shape information to the
user's GTFS dataset.  A shapes.txt file is created, and the trips.txt and
stop_times.txt files are updated.'''
################################################################################
'''Copyright 2019 Esri
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

import os, csv, sqlite3, codecs
from operator import itemgetter
import arcpy

class CustomError(Exception):
    pass


def get_table_columns(tablename):
    '''Get the columns from a SQL table'''
    c.execute("PRAGMA table_info(%s)" % tablename)
    table_info = c.fetchall()
    columns = ()
    for col in table_info:
        columns = columns + (col[1],)
    return columns


def get_trips_with_shape_id(shape):
    tripsfetch = '''SELECT trip_id FROM trips where shape_id="%s";''' % shape
    c.execute(tripsfetch)
    trips = c.fetchall()
    return [trip[0] for trip in trips]


def write_SQL_table_to_text_file(tablename, csvfile, columns):
    '''Dump all rows in a SQL table out to a text file'''

    def WriteFile(f):
        
        # Initialize csv writer
        wr = csv.writer(f)
        
        # Write columns
        wr.writerow(columns)

        # Grab all the rows in the SQL Table
        ct = conn.cursor()
        selectrowsstmt = "SELECT * FROM %s;" % tablename
        ct.execute(selectrowsstmt)
        
        # Write each row to the csv file
        for row in ct:
            # Encode row in utf-8.
            if ProductName == "ArcGISPro":
                rowToWrite = tuple([t for t in row])
            else:
                rowToWrite = tuple([t.encode("utf-8") if isinstance(t, basestring) else t for t in row])
            wr.writerow(rowToWrite)

    if ProductName == "ArcGISPro":
        with codecs.open(csvfile, "wb", encoding="utf-8") as f:
            WriteFile(f)
    else:         
        with open(csvfile, "wb") as f:
            WriteFile(f)


try:

# ----- Define variables -----

    # User input
    inStep1GDB = arcpy.GetParameterAsText(0)
    outDir = arcpy.GetParameterAsText(1)
    units = arcpy.GetParameterAsText(2)
    update_existing = arcpy.GetParameterAsText(3)
    if update_existing == "true":
        update_existing = True
    else:
        update_existing = False

    # Derived
    SQLDbase = os.path.join(inStep1GDB, "SQLDbase.sql")
    inShapes = os.path.join(inStep1GDB, "Shapes")
    inStops_wShapeIDs = os.path.join(inStep1GDB, "Stops_wShapeIDs")

    # Important user output
    outShapesFile = os.path.join(outDir, 'shapes_new.txt')
    outTripsFile = os.path.join(outDir, 'trips_new.txt')
    outStopTimesFile = os.path.join(outDir, 'stop_times_new.txt')

    # GTFS is in WGS coordinates
    WGSCoords = arcpy.SpatialReference(4326)


# ----- Set some things up -----

    # Check the user's version
    ArcVersionInfo = arcpy.GetInstallInfo("desktop")
    ArcVersion = ArcVersionInfo['Version']
    ProductName = ArcVersionInfo['ProductName']
    if ArcVersion in ["10.0", "10.1", "10.2", "10.2.1", "10.2.2"]:
        arcpy.AddError("You must have ArcGIS 10.3 or higher to run this tool.\
You have ArcGIS version %s." % ArcVersion)
        raise CustomError
    if ProductName == "ArcGISPro" and ArcVersion in ["1.0", "1.1", "1.1.1"]:
        arcpy.AddError("You must have ArcGIS Pro 1.2 or higher to run this \
tool. You have ArcGIS Pro version %s." % ArcVersion)
        raise CustomError

    orig_overwrite = arcpy.env.overwriteOutput
    # It's okay to overwrite stuff.
    arcpy.env.overwriteOutput = True

    # Connect to the SQL database
    conn = sqlite3.connect(SQLDbase)
    c = conn.cursor()

    # Store some useful information
    trip_shape_dict = {} # {trip_id: shape_id}
    if update_existing:
        for line in arcpy.da.SearchCursor(inShapes, ["shape_id"]):
            for trip in get_trips_with_shape_id(line[0]):
                trip_shape_dict[trip] = line[0]
    else:
        cts = conn.cursor()
        tripsfetch = '''SELECT trip_id, shape_id FROM trips;'''
        cts.execute(tripsfetch)
        for trip in cts:
            trip_shape_dict[trip[0]] = trip[1]

    numshapes = int(arcpy.management.GetCount(inShapes)[0])
    tenperc = 0.1 * numshapes

# ----- Generate new trips.txt with shape_id populated -----

    # We don't need to modify the trips.txt file if we're just updating existing shapes.
    if not update_existing:
        try:
            arcpy.AddMessage("Generating new trips.txt file...")
            trip_columns = get_table_columns("trips")
            write_SQL_table_to_text_file("trips", outTripsFile, trip_columns)
            arcpy.AddMessage("Successfully created new trips.txt file.")
        except:
            arcpy.AddError("Error generating new trips.txt file.")
            raise


# ----- Generate the new shapes.txt file -----

    arcpy.AddMessage("Generating new shapes.txt file...")
    arcpy.AddMessage("(This may take some time for datasets with a large number of shapes.)")

    # Write to shapes.txt file
    try:
        
        def WriteShapesFile(f):
            wr = csv.writer(f)
            # Write the headers
            if not update_existing:
                wr.writerow(["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence", "shape_dist_traveled"])

            # Use a Search Cursor and explode to points to get vertex info
            shape_pt_seq = 1
            shape_dist_traveled = 0
            current_shape_id = None
            previous_point = None
            for row in arcpy.da.SearchCursor(inShapes, ["shape_id", "SHAPE@Y", "SHAPE@X"], explode_to_points=True):
                shape_id, shape_pt_lat, shape_pt_lon = row
                current_point = arcpy.Point(shape_pt_lon, shape_pt_lat)
                if shape_id != current_shape_id:
                    # Starting a new shape
                    current_shape_id = shape_id
                    shape_pt_seq = 1
                    shape_dist_traveled = 0
                else:
                    # Create a line segment between the previous vertex and this one so we can calculate geodesic length
                    line_segment = arcpy.Polyline(arcpy.Array([previous_point, current_point]), WGSCoords)
                    shape_dist_traveled += line_segment.getLength("GEODESIC", units.upper())
 
                # Write row to shapes.txt file
                if not update_existing:
                    row_to_add = [shape_id, shape_pt_lat, shape_pt_lon, shape_pt_seq, shape_dist_traveled]
                else:
                    # Do a little jiggering because the user's existing shapes.txt might contain extra fields and might not be in the same order
                    row_to_add = ["" for col in shapes_columns]
                    row_to_add[shape_id_idx] = shape_id
                    row_to_add[shape_pt_lat_idx] = shape_pt_lat
                    row_to_add[shape_pt_lon_idx] = shape_pt_lon
                    row_to_add[shape_pt_sequence_idx] = shape_pt_seq
                    row_to_add[shape_dist_traveled_idx] = shape_dist_traveled
                wr.writerow(row_to_add)
                shape_pt_seq += 1
                previous_point = current_point


        if update_existing:
            # Delete previous entries for these shapes from SQL table
            for row in arcpy.da.SearchCursor(inShapes, ["shape_id"]):
                delete_stmt = "DELETE FROM shapes WHERE shape_id='%s'" % row[0]
                c.execute(delete_stmt)
            
            # Save some info about column order for later
            shapes_columns = get_table_columns("shapes")
            shape_id_idx = shapes_columns.index("shape_id")
            shape_pt_lat_idx = shapes_columns.index("shape_pt_lat")
            shape_pt_lon_idx = shapes_columns.index("shape_pt_lon")
            shape_pt_sequence_idx = shapes_columns.index("shape_pt_sequence")
            shape_dist_traveled_idx = shapes_columns.index("shape_dist_traveled")

            # Write out the existing entries to shapes.txt
            write_SQL_table_to_text_file("shapes", outShapesFile, shapes_columns)
        
            # We'll append the updated shapes to the existing original shapes
            mode = "ab"
        else:
            mode = "wb"

        shapes_with_no_geometry = []
        # Open the new shapes.txt file and write output.
        if ProductName == "ArcGISPro":
            with codecs.open(outShapesFile, mode, encoding="utf-8") as f:
                WriteShapesFile(f)
        else:         
            with open(outShapesFile, mode) as f:
                WriteShapesFile(f)

        # Add warnings for shapes that have them.
        if shapes_with_no_geometry:
            arcpy.AddWarning("Warning! Some shapes had no geometry or 0 length. \
These shapes will be written to shapes.txt, and shape_dist_traveled values will \
be written to stop_times.txt, but all shape_dist_traveled values for \
the shape will have a value of 0.0.  shape_ids affected: " + \
str(shapes_with_no_geometry))

        arcpy.AddMessage("Successfully generated new shapes.txt file.")

    except:
        arcpy.AddError("Error writing new shapes.txt file.")
        raise


# ----- Generate new stop_times.txt file with shape_dist_traveled field -----

    arcpy.AddMessage("Creating new stop_times.txt file...")
    arcpy.AddMessage("(This may take some time for large datasets.)")

    try:
        shapes_with_warnings = []
        progress = 0
        perc = 10
        final_stoptimes_tabledata = {} # {shape_id: {stop_id: shape_dist_traveled}
        for line in arcpy.da.SearchCursor(inShapes, ["SHAPE@", "shape_id"]):
            # Print some progress indicators
            progress += 1
            if progress >= tenperc:
                arcpy.AddMessage(str(perc) + "% finished")
                perc += 10
                progress = 0
            lineGeom = line[0]
            shape_id = line[1]
            where = """"shape_id" = '%s'""" % str(shape_id)
            StopsLayer = arcpy.management.MakeFeatureLayer(inStops_wShapeIDs, "StopsLayer", where)
            with arcpy.da.SearchCursor(StopsLayer, ["SHAPE@", "stop_id", "sequence"]) as ptcur:
                shape_rows = []
                shape_dist_dict_item = {} # {stop_id: shape_dist_traveled}
                for point in ptcur:
                    ptGeom = point[0]
                    stop_id = point[1]
                    sequence = point[2]
                    # If the line has no geometry, default to 0
                    if not lineGeom:
                        shape_dist_traveled = 0.0
                    # Find the distance along the line the stop occurs
                    else:
                        # Find the distance along the line using the line's M values
                        dist_along = lineGeom.measureOnLine(ptGeom, use_percentage=False)
                        # Grab the line segment from 0 to the current location
                        segment = lineGeom.segmentAlongLine(0, dist_along, use_percentage=False)
                        # Get the geodesic length of the line segment in the correct units
                        shape_dist_traveled = segment.getLength("GEODESIC", units.upper())
                    # Data to be added to stop_times.txt
                    shape_rows.append([sequence, shape_dist_traveled])
                    if ProductName == "ArcGISPro":
                        shape_dist_dict_item[str(stop_id)] = shape_dist_traveled
                    else:
                        shape_dist_dict_item[unicode(stop_id)] = shape_dist_traveled
                    sequence += 1
                final_stoptimes_tabledata[str(shape_id)] = shape_dist_dict_item
            # Check if the stops came out in the right order. If they
            # didn't, something is wrong with the user's input shape.
            sortedList_sequence = sorted(shape_rows, key=itemgetter(0,1))
            sortedList_dist = sorted(shape_rows, key=itemgetter(1,0))
            if sortedList_dist != sortedList_sequence:
                shapes_with_warnings.append(shape_id)

        # Add warnings for shapes that have them.
        if shapes_with_warnings:
            arcpy.AddWarning("Warning! For some Shapes, the order of the measured \
shape_dist_traveled for stops along the shape does not match the correct \
sequence of the stops. This likely indicates a problem with the geometry of \
your shapes.  The shape_dist_traveled field will be added to your stop_times.txt \
file and populated, but the values may be incorrect. \
Please review and fix your shape geometry, then run this tool \
again.  See the user's guide for more information.  shape_ids affected: " + \
str(shapes_with_warnings))

    except:
        arcpy.AddError("Error linear referencing stops.")
        raise


    # Write the new stop_times.txt file
    try:

        def WriteStopTimesFile(f):
            wr = csv.writer(f)

            # Get the columns for stop_times.txt.
            c.execute("PRAGMA table_info(stop_times)")
            stoptimes_table_info = c.fetchall()
            columns = ()
            for col in stoptimes_table_info:
                columns += (col[1],)
            # Write the columns to the CSV
            wr.writerow(columns)
            # Find the column indices for things we need later
            stop_id_idx = columns.index("stop_id")
            trip_id_idx = columns.index("trip_id")
            shape_dist_traveled_idx = columns.index("shape_dist_traveled")

            # Read in the rows from the stop_times SQL table, look up the \
            # shape_dist_traveled, and write to CSV
            cst = conn.cursor()
            selectstoptimesstmt = "SELECT * FROM stop_times;"
            cst.execute(selectstoptimesstmt)
            for stoptime in cst:
                # Encode in utf-8.
                if ProductName == "ArcGISPro":
                    stoptimelist = [t for t in stoptime]
                else:
                    stoptimelist = [t.encode("utf-8") if isinstance(t, basestring) else t for t in stoptime]
                trip_id = stoptimelist[trip_id_idx]
                # Only update shape_dist_traveled if we're doing all new shapes or if we're updating this specific shape
                # Otherwise just skip this part and write out the row as it was already.
                if not update_existing or (update_existing and trip_id in trip_shape_dict):
                    shape_id = trip_shape_dict[trip_id]
                    stop_id = stoptimelist[stop_id_idx]
                    try:
                        shape_dist_traveled = final_stoptimes_tabledata[shape_id][stop_id]
                        stoptimelist[shape_dist_traveled_idx] = shape_dist_traveled
                    except KeyError:
                        bad_shapes_stops.append([shape_id, stop_id])
                stoptimetuple = tuple(stoptimelist)
                wr.writerow(stoptimetuple)

        bad_shapes_stops = []
        # Open the new stop_times CSV for writing
        if ProductName == "ArcGISPro":
            with codecs.open(outStopTimesFile, "wb", encoding="utf-8") as f:
                WriteStopTimesFile(f)
        else:         
            with open(outStopTimesFile, "wb") as f:
                WriteStopTimesFile(f)

        if bad_shapes_stops:
            arcpy.AddWarning("Warning! This tool could not calculate the \
shape_dist_traveled value for the following [shape_id, stop_id] pairs. They \
will show up as blank values in the stop_times.txt table.")
            for pair in bad_shapes_stops:
                arcpy.AddWarning(pair)

        arcpy.AddMessage("Successfully generated new stop_times.txt file.")

    except:
        arcpy.AddError("Error writing new stop_times.txt file.")
        raise


# ----- Finish up -----
    arcpy.AddMessage("Finished! Your new GTFS files are:")
    if not update_existing:
        arcpy.AddMessage("- " + outTripsFile)
    arcpy.AddMessage("- " + outShapesFile)
    arcpy.AddMessage("- " + outStopTimesFile)
    arcpy.AddMessage("After checking that these files are correct, remove \
the '_new' from the filenames and add them to your GTFS data folder, overwriting the existing files.")

except CustomError:
    arcpy.AddError("Error generating new GTFS files.")
    pass

except:
    arcpy.AddError("Error generating new GTFS files.")
    raise

finally:
    if orig_overwrite:
        arcpy.env.overwriteOutput = orig_overwrite
    if c:
        c.close()