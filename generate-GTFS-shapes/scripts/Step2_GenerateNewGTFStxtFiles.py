###############################################################################
## Tool name: Generate GTFS Route Shapes
## Step 2: Generate new GTFS text files
## Creator: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 25 September 2017
###############################################################################
'''Using the GDB created in Step 1, this tool adds shape information to the
user's GTFS dataset.  A shapes.txt file is created, and the trips.txt and
stop_times.txt files are updated.'''
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

import os, csv, sqlite3, codecs
from operator import itemgetter
import arcpy
import DetermineUTMProjection

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


def get_trips_with_shape_id(shape):
    tripsfetch = '''SELECT trip_id FROM trips where shape_id="%s";''' % shape
    c.execute(tripsfetch)
    trips = c.fetchall()
    return [trip[0] for trip in trips]


def convert_meters_to_other_units(meters, units):
    if units == "miles":
        return meters * 0.000621371
    elif units == "kilometers":
        return meters / 1000.0
    elif units == "feet":
        return meters * 3.28084
    elif units == "yards":
        return meters * 1.09361


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
    inShapes_vertices_name = "Shapes_vertices"
    inShapes_vertices = os.path.join(inStep1GDB, inShapes_vertices_name)

    # Important user output
    outShapesFile = os.path.join(outDir, 'shapes_new.txt')
    outTripsFile = os.path.join(outDir, 'trips_new.txt')
    outStopTimesFile = os.path.join(outDir, 'stop_times_new.txt')

    # GTFS stops are in WGS coordinates
    WGSCoords = "GEOGCS['GCS_WGS_1984',DATUM['D_WGS_1984', \
    SPHEROID['WGS_1984',6378137.0,298.257223563]], \
    PRIMEM['Greenwich',0.0],UNIT['Degree',0.0174532925199433]]; \
    -400 -400 1000000000;-100000 10000;-100000 10000; \
    8.98315284119522E-09;0.001;0.001;IsHighPrecision"


# ----- Set some things up -----

    # Check the user's version
    ArcVersionInfo = arcpy.GetInstallInfo("desktop")
    ArcVersion = ArcVersionInfo['Version']
    ProductName = ArcVersionInfo['ProductName']
    if ArcVersion in ["10.0", "10.1", "10.2"]:
        arcpy.AddError("You must have ArcGIS 10.2.1 or higher to run this tool.\
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


# ----- Generate new trips.txt with shape_id populated -----

    # We don't need to modify the trips.txt file is we're just updating existing shapes.
    if not update_existing:
        try:
            arcpy.AddMessage("Generating new trips.txt file...")
            trip_columns = get_table_columns("trips")
            write_SQL_table_to_text_file("trips", outTripsFile, trip_columns)
            arcpy.AddMessage("Successfully created new trips.txt file.")
        except:
            arcpy.AddError("Error generating new trips.txt file.")
            raise


# ----- Prepare projected shapes for use in linear referencing -----

    arcpy.AddMessage("Preparing Shapes for shapes.txt and stop_times.txt creation...")

    # Project Shapes into a good coordinate system for generating measures in meters
    try:
        # Find the shapes fc centroid lat/lon and get the right UTM spatial reference to use
        # Describe the shapes feature class and find the extent
        desc = arcpy.Describe(inShapes)
        extent = desc.extent
        extent_sr = desc.spatialReference

        # Create a polygon object and then find the centroid
        extent_polygon_vertices = arcpy.Array([extent.lowerLeft, extent.lowerRight, extent.upperRight, extent.upperLeft, extent.lowerLeft])
        extent_polygon = arcpy.Polygon(extent_polygon_vertices, extent_sr)
        extent_polygon_WGS84 = extent_polygon.projectAs(WGSCoords)
        centroid = extent_polygon_WGS84.centroid
        lon = centroid.X
        lat = centroid.Y

        # Get the UTM coordinates appropriate for this analysis area
        UTMCoords = DetermineUTMProjection.GetUTMZoneAsText(lat, lon)

        # Project the shapes first to the appropriate UTM so the linear referencing will
        # be in a good system of units and properly measured
        outShapes = os.path.join(inStep1GDB, "Shapes_Projected")
        arcpy.management.Project(inShapes, outShapes, UTMCoords)

        # Store the line shape info for use later.
        with arcpy.da.SearchCursor(outShapes, ["SHAPE@", "shape_id"]) as linecur:
            linetable = []
            for line in linecur:
                linetable.append(line)
        # Sort by shape_id so they'll be written in a nice order.
        if update_existing:
            # If they're using existing shape_ids, we just sort regularly as strings.
            linetable = sorted(linetable, key=itemgetter(1))
        else:
            # Sort the shapes as integers because Step 1 guarantees that the shape_ids are integers written as strings
            def getKey(listitem):
                return int(listitem[1])
            linetable = sorted(linetable, key=getKey)     
        # Prepare the progress reports by finding 10% of the length
        numshapes = len(linetable)
        tenperc = 0.1 * numshapes
        if update_existing:
            arcpy.AddMessage("Updating " + str(numshapes) + " shape(s).")
        else:
            arcpy.AddMessage("Your dataset contains " + str(numshapes) + " shapes.")

        trip_shape_dict = {} # {trip_id: shape_id}
        if update_existing:
            for line in linetable:
                for trip in get_trips_with_shape_id(line[1]):
                    trip_shape_dict[trip] = line[1]
        else:
            cts = conn.cursor()
            tripsfetch = '''SELECT trip_id, shape_id FROM trips;'''
            cts.execute(tripsfetch)
            for trip in cts:
                trip_shape_dict[trip[0]] = trip[1]
            
    except:
        arcpy.AddError("Error preparing Shapes for measurement.")
        raise


# ----- Generate the new shapes.txt file -----

    arcpy.AddMessage("Generating new shapes.txt file...")
    arcpy.AddMessage("(This may take some time for datasets with a large number of shapes.)")

    # Turn the vertices of the shapes fc into points
    try:
        # (We could use FeatureVerticesToPoints, but that tool requires Advanced license)
        arcpy.management.CreateFeatureclass(inStep1GDB, inShapes_vertices_name,
                                            "POINT", spatial_reference=UTMCoords)
        arcpy.management.AddField(inShapes_vertices, "shapept_id", "LONG")
        arcpy.management.AddField(inShapes_vertices, "shape_id", "TEXT")
        with arcpy.da.SearchCursor(outShapes, ["SHAPE@XY", "shape_id"], explode_to_points=True) as linescur:
            with arcpy.da.InsertCursor(inShapes_vertices, ["SHAPE@XY", "shapept_id", "shape_id"]) as ptscur:
                # Add an ID field for the vertices which will indicate the correct order
                shapept_id = 1
                for row in linescur:
                    shape = row[0]
                    shape_id = row[1]
                    ptscur.insertRow((shape, shapept_id, shape_id))
                    shapept_id += 1

        # Store the lat/long of each vertex.
        vert_dict = {} # {shapept_id: shapegeom}
        # Read in the lat/lon values in WGSCoords
        with arcpy.da.SearchCursor(inShapes_vertices, ["SHAPE@XY", "shapept_id"], '', WGSCoords) as vertexcursor:
            for vert in vertexcursor:
                vert_dict[vert[1]] = vert[0]

    except:
        arcpy.AddError("Error creating a feature class of Shape vertices.")
        raise

    # Write to shapes.txt file
    try:
        
        def WriteShapesFile(f):
            wr = csv.writer(f)
            # Write the headers
            if not update_existing:
                wr.writerow(["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence", "shape_dist_traveled"])

            # Find the location of each vertex along the line
            # Linear reference the vertices of each shape and write to shapes.txt
            progress = 0
            perc = 10
            for line in linetable:
                # Print some progress indicators
                progress += 1
                if progress >= tenperc:
                    arcpy.AddMessage(str(perc) + "% finished")
                    perc += 10
                    progress = 0
                lineGeom = line[0]
                shape_id = line[1]
                where = """"shape_id" = '%s'""" % str(shape_id)
                VerticesLayer = arcpy.management.MakeFeatureLayer(inShapes_vertices, "VerticesLayer", where)
                with arcpy.da.SearchCursor(VerticesLayer, ["SHAPE@", "shapept_id"]) as ptcur:
                    shape_rows = []
                    sequence = 1
                    for point in ptcur:
                        ptGeom = point[0]
                        ptid = point[1]
                        # Check for lines with no geometry and default them to 0.
                        if not lineGeom:
                            shape_dist_traveled = 0.0
                            shapes_with_no_geometry.append(shape_id)
                        # Find the distance along the line the vertex occurs
                        else:
                            # measureOnLine returns result as either a percent along the line or in the units of the line geometry (meters, in our case)
                            if units == "percent":
                                # Even though the parameter is called used_percentage, it returns a proportion between 0 and 1, so multiply by 100 to convert to a true percentage
                                shape_dist_traveled = 100.0 * lineGeom.measureOnLine(ptGeom, use_percentage=True)
                            else:
                                shape_dist_traveled = lineGeom.measureOnLine(ptGeom, use_percentage=False)
                                if units != "meters":
                                    # Do a unit conversion if the user wants it
                                    shape_dist_traveled = convert_meters_to_other_units(shape_dist_traveled, units)
                        # Retrieve the lat/lon values
                        shape_pt_lon = vert_dict[ptid][0]
                        shape_pt_lat = vert_dict[ptid][1]
                        # Prepare a row for the shapes.txt file
                        shape_rows.append([sequence, shape_dist_traveled])
                        if not update_existing:
                            row_to_add = [shape_id, shape_pt_lat, shape_pt_lon, sequence, shape_dist_traveled]
                        else:
                            # Do a little jiggering because the user's existing shapes.txt might contain extra fields and might not be in the same order
                            row_to_add = ["" for col in shapes_columns]
                            row_to_add[shape_id_idx] = shape_id
                            row_to_add[shape_pt_lat_idx] = shape_pt_lat
                            row_to_add[shape_pt_lon_idx] = shape_pt_lon
                            row_to_add[shape_pt_sequence_idx] = sequence
                            row_to_add[shape_dist_traveled_idx] = shape_dist_traveled
                        wr.writerow(row_to_add)
                        sequence += 1
                # Check if the vertices came out in the right order. If they
                # didn't, something is wrong with the user's input shape.
                sortedList_sequence = sorted(shape_rows, key=itemgetter(0,1))
                sortedList_dist = sorted(shape_rows, key=itemgetter(1,0))
                if sortedList_dist != sortedList_sequence:
                    shapes_with_warnings.append(shape_id)

        if update_existing:
    
            # Delete previous entries for these shapes from SQL table
            for line in linetable:
                shape_id = line[1]
                delete_stmt = "DELETE FROM shapes WHERE shape_id='%s'" % shape_id
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

        shapes_with_warnings = []
        shapes_with_no_geometry = []
        # Open the new shapes.txt file and write output.
        if ProductName == "ArcGISPro":
            with codecs.open(outShapesFile, mode, encoding="utf-8") as f:
                WriteShapesFile(f)
        else:         
            with open(outShapesFile, mode) as f:
                WriteShapesFile(f)

        # Add warnings for shapes that have them.
        if shapes_with_warnings:
            arcpy.AddWarning("Warning! For some Shapes, the order of the measured \
shape_dist_traveled for vertices along the shape does not match the correct \
sequence of the vertices. This likely indicates a problem with the geometry of \
your shapes.  Your new shapes.txt file will be generated, and the shapes may \
look correct, but the shape_dist_traveled value may be incorrect. \
Please review and fix your shape geometry, then run this tool \
again.  See the user's guide for more information.  shape_ids affected: " + \
str(shapes_with_warnings))

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

    # Find the location of each stop along the line
    try:
        # Project the Stops feature class so that the measures come out correctly
        inStops_wShapeIDs_projected = os.path.join(inStep1GDB, "Stops_Projected")
        arcpy.management.Project(inStops_wShapeIDs, inStops_wShapeIDs_projected, UTMCoords)

        shapes_with_warnings = []
        progress = 0
        perc = 10
        final_stoptimes_tabledata = {} # {shape_id: {stop_id: shape_dist_traveled}
        for line in linetable:
            # Print some progress indicators
            progress += 1
            if progress >= tenperc:
                arcpy.AddMessage(str(perc) + "% finished")
                perc += 10
                progress = 0
            lineGeom = line[0]
            shape_id = line[1]
            where = """"shape_id" = '%s'""" % str(shape_id)
            StopsLayer = arcpy.management.MakeFeatureLayer(inStops_wShapeIDs_projected, "StopsLayer", where)
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
                        # measureOnLine returns result as either a percent along the line or in the units of the line geometry (meters, in our case)
                        if units == "percent":
                            # Even though the parameter is called used_percentage, it returns a proportion between 0 and 1, so multiply by 100 to convert to a true percentage
                            shape_dist_traveled = 100.0 * lineGeom.measureOnLine(ptGeom, use_percentage=True)
                        else:
                            shape_dist_traveled = lineGeom.measureOnLine(ptGeom, use_percentage=False)
                            if units != "meters":
                                # Do a unit conversion if the user wants it
                                shape_dist_traveled = convert_meters_to_other_units(shape_dist_traveled, units)
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

        # Clean up
        arcpy.management.Delete(inStops_wShapeIDs_projected)

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
    arcpy.management.Delete(inShapes_vertices)
    arcpy.management.Delete(outShapes)
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