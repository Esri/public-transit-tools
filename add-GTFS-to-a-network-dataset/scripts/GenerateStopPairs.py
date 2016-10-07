################################################################################
## Toolbox: Add GTFS to a Network Dataset
## Tool name: 1) Generate Transit Lines and Stops
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 17 January 2016
################################################################################
''' This tool generates feature classes of transit stops and lines from the
information in the GTFS dataset.  The stop locations are taken directly from the
lat/lon coordinates in the GTFS data.  A straight line is generated connecting
each pair of adjacent stops in the network (ie, stops directly connected by at
least one transit trip in the GTFS data with no other stops in between). When
multiple trips or routes travel directly between the same two stops, only one
line is generated unless the routes have different mode types.  This tool also
generates a SQL database version of the GTFS data which is used by the network
dataset for schedule lookups.'''
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

import sqlite3, os, operator, itertools, csv, re
import arcpy
import sqlize_csv, hms

class CustomError(Exception):
    pass

# ----- Collect user inputs -----

# GTFS directories
inGTFSdir = arcpy.GetParameterAsText(0)
# Feature dataset where the network will be built
outFD = arcpy.GetParameterAsText(1)

# Derived inputs
outGDB = os.path.dirname(outFD)
SQLDbaseName = "GTFS.sql"
SQLDbase = os.path.join(outGDB, SQLDbaseName)
outStopPairsFCName = "StopPairs"
outStopPairsFC = os.path.join(outGDB, outStopPairsFCName)
outLinesFC = os.path.join(outFD, "TransitLines")
outStopsFCName = "Stops"
outStopsFC = os.path.join(outFD, outStopsFCName)

# Get the original overwrite output setting so we can reset it at the end.
OverwriteOutput = arcpy.env.overwriteOutput
# It's okay to overwrite stuff in this tool
arcpy.env.overwriteOutput = True

# GTFS stop lat/lon are written in WGS1984 coordinates
WGSCoords = "GEOGCS['GCS_WGS_1984',DATUM['D_WGS_1984', \
SPHEROID['WGS_1984',6378137.0,298.257223563]], \
PRIMEM['Greenwich',0.0],UNIT['Degree',0.0174532925199433]]; \
-400 -400 1000000000;-100000 10000;-100000 10000; \
8.98315284119522E-09;0.001;0.001;IsHighPrecision"
# Output files must be written in the coordinate system of the output FD.
outFD_SR = arcpy.Describe(outFD).spatialReference

# GTFS route_type information
#0 - Tram, Streetcar, Light rail. Any light rail or street level system within a metropolitan area.
#1 - Subway, Metro. Any underground rail system within a metropolitan area.
#2 - Rail. Used for intercity or long-distance travel.
#3 - Bus. Used for short- and long-distance bus routes.
#4 - Ferry. Used for short- and long-distance boat service.
#5 - Cable car. Used for street-level cable cars where the cable runs beneath the car.
#6 - Gondola, Suspended cable car. Typically used for aerial cable cars where the car is suspended from the cable.
#7 - Funicular. Any rail system designed for steep inclines.
route_type_dict = {0: "Tram, Streetcar, Light rail",
                    1: "Subway, Metro",
                    2: "Rail",
                    3: "Bus",
                    4: "Ferry",
                    5: "Cable car",
                    6: "Gondola, Suspended cable car",
                    7: "Funicular"}

try:

# ----- SQLize the GTFS data -----

    arcpy.AddMessage("SQLizing the GTFS data...")

    # Fix up list of GTFS datasets (it comes in as a ;-separated list)
    inGTFSdirList = inGTFSdir.split(";")
    # Remove single quotes ArcGIS puts in if there are spaces in the filename.
    for d in inGTFSdirList:
        if d[0] == "'" and d[-1] == "'":
            loc = inGTFSdirList.index(d)
            inGTFSdirList[loc] = d[1:-1]

    # The main SQLizing work is done in the sqlize_csv module
    # written by Luitien Pan for GTFS_NATools.
    # Connect to or create the SQL file.
    sqlize_csv.connect(SQLDbase)
    # Create tables.
    for tblname in sqlize_csv.sql_schema:
        sqlize_csv.create_table(tblname)
    # SQLize all the GTFS files, for each separate GTFS dataset.
    for gtfs_dir in inGTFSdirList:
        # Run sqlize for each GTFS dataset. Check for returned errors
        GTFSErrors = sqlize_csv.handle_agency(gtfs_dir)
        if GTFSErrors:
            for error in GTFSErrors:
                arcpy.AddError(error)
            raise CustomError

    # Create indices to make queries faster.
    sqlize_csv.create_indices()

    # Check for non-overlapping date ranges to prevent double-counting.
    overlapwarning = sqlize_csv.check_nonoverlapping_dateranges()
    if overlapwarning:
        arcpy.AddWarning(overlapwarning)


# ----- Connect to SQL locally for further queries and entries -----

    # Connect to the SQL database
    conn = sqlite3.connect(SQLDbase)
    c = conn.cursor()


# ----- Make dictionary of route types -----

    # Find all routes and associated info.
    RouteDict = {}
    routesfetch = '''
        SELECT route_id, route_type
        FROM routes
        ;'''
    c.execute(routesfetch)
    routelist = c.fetchall()
    for route in routelist:
        RouteDict[route[0]] = route[1]


# ----- Make dictionary of {trip_id: route_type} -----

    # First, make sure there are no duplicate trip_id values, as this will mess things up later.
    tripDuplicateFetch = "SELECT trip_id, count(*) from trips group by trip_id having count(*) > 1"
    c.execute(tripDuplicateFetch)
    tripdups = c.fetchall()
    tripdupslist = [tripdup for tripdup in tripdups]
    if tripdupslist:
        arcpy.AddError("Your GTFS trips table is invalid.  It contains multiple trips with the same trip_id.")
        for tripdup in tripdupslist:
            arcpy.AddError("There are %s instances of the trip_id value '%s'." % (str(tripdup[1]), unicode(tripdup[0])))
        raise CustomError

    # Now make the dictionary
    trip_routetype_dict = {}
    tripsfetch = '''
        SELECT trip_id, route_id
        FROM trips
        ;'''
    c.execute(tripsfetch)
    triplist = c.fetchall()
    for trip in triplist:
        try:
            trip_routetype_dict[trip[0]] = RouteDict[trip[1]]
        except KeyError:
            arcpy.AddWarning("Trip_id %s in trips.txt has a route_id value, %s, which does not appear in your routes.txt file.  \
This trip can still be used for analysis, but it might be an indication of a problem with your GTFS dataset." % (trip[0], trip[1]))
            trip_routetype_dict[trip[0]] = 100 # 100 is an arbitrary number that doesn't match anything in the GTFS spec


# ----- Make dictionary of frequency information (if there is any) -----

    frequencies_dict = {}
    freqfetch = '''
        SELECT trip_id, start_time, end_time, headway_secs
        FROM frequencies
        ;'''
    c.execute(freqfetch)
    freqlist = c.fetchall()
    for freq in freqlist:
        trip_id = freq[0]
        if freq[3] == 0:
            arcpy.AddWarning("Trip_id %s in your frequencies.txt file has a headway of 0 seconds. \
This is invalid, so trips with this id will not be included in your network." % trip_id)
            continue
        trip_data = [freq[1], freq[2], freq[3]]
        # {trip_id: [start_time, end_time, headway_secs]}
        frequencies_dict.setdefault(trip_id, []).append(trip_data)


# ----- Generate transit stops feature class (for the final ND) -----

    arcpy.AddMessage("Generating transit stops feature class.")

    # Get the combined stops table.
    selectstoptablestmt = "SELECT stop_id, stop_lat, stop_lon, stop_code, \
                        stop_name, stop_desc, zone_id, stop_url, location_type, \
                        parent_station, wheelchair_boarding FROM stops"
    c.execute(selectstoptablestmt)
    StopTable = c.fetchall()

    # Initialize a dictionary of stop lat/lon (filled below)
    # {stop_id: <stop geometry object>} in the output coordinate system
    stoplatlon_dict = {}

    # Create a points feature class for the point pairs.
    arcpy.CreateFeatureclass_management(outFD, outStopsFCName, "POINT", "", "", "", outFD_SR)
    arcpy.management.AddField(outStopsFC, "stop_id", "TEXT")
    arcpy.management.AddField(outStopsFC, "stop_code", "TEXT")
    arcpy.management.AddField(outStopsFC, "stop_name", "TEXT")
    arcpy.management.AddField(outStopsFC, "stop_desc", "TEXT")
    arcpy.management.AddField(outStopsFC, "zone_id", "TEXT")
    arcpy.management.AddField(outStopsFC, "stop_url", "TEXT")
    arcpy.management.AddField(outStopsFC, "location_type", "TEXT")
    arcpy.management.AddField(outStopsFC, "parent_station", "TEXT")
    arcpy.management.AddField(outStopsFC, "wheelchair_boarding", "TEXT")

    # Add the stops table to a feature class.
    with arcpy.da.InsertCursor(outStopsFC, ["SHAPE@", "stop_id",
                                                 "stop_code", "stop_name", "stop_desc",
                                                 "zone_id", "stop_url", "location_type",
                                                 "parent_station", "wheelchair_boarding"]) as cur3:
        for stop in StopTable:
            stop_id = stop[0]
            stop_lat = stop[1]
            stop_lon = stop[2]
            stop_code = stop[3]
            stop_name = stop[4]
            stop_desc = stop[5]
            zone_id = stop[6]
            stop_url = stop[7]
            location_type = stop[8]
            parent_station = stop[9]
            wheelchair_boarding = unicode(stop[10])
            pt = arcpy.Point()
            pt.X = float(stop_lon)
            pt.Y = float(stop_lat)
            # GTFS stop lat/lon is written in WGS1984
            ptGeometry = arcpy.PointGeometry(pt, WGSCoords)
            # But the stops fc must be in the user's FD coordinate system
            ptGeometry_projected = ptGeometry.projectAs(outFD_SR)
            stoplatlon_dict[stop_id] = ptGeometry_projected
            cur3.insertRow((ptGeometry_projected, stop_id, stop_code, stop_name,
                            stop_desc, zone_id, stop_url, location_type,
                            parent_station, wheelchair_boarding))


# ----- Obtain schedule info from the stop_times.txt file and convert it to a line-based model -----

    arcpy.AddMessage("Obtaining and processing transit schedule and line information...")
    arcpy.AddMessage("(This will take a few minutes for large datasets.)")

    # If there are multiple GTFS datasets, handle each one separately to keep memory usage as low as possible
    GTFSCount = 0
    AddToOID = 0
    for gtfs_dir in inGTFSdirList:
        arcpy.AddMessage("- Handling GTFS directory %s" % os.path.basename(gtfs_dir))
        GTFSCount += 1

        stop_times_dict = {} # {trip_id: [stop_id, stop_sequence, arrival_time, departure_time]}
        # One entry per transit line connecting a unique pair of stops (with duplicate entries for different
        # route_type values connecting the same pair of stops). Size shouldn't be terribly much larger than the
        # number of stops for a normal network. Only central stations and transit hubs have large numbers of
        # connections.
        linefeature_dict = {}

        #-- Read in everything from the CSV table
        stop_times_file = os.path.join(gtfs_dir, "stop_times.txt")
        with open(stop_times_file) as f:
            reader = csv.reader(f)

            # Put everything in utf-8 to handle BOMs and weird characters.
            # Eliminate blank rows (extra newlines) while we're at it.
            reader = ([x.decode('utf-8-sig').strip() for x in r] for r in reader if len(r) > 0)

            # First row is column names:
            columns = [name.strip() for name in reader.next()]

            #-- Do some data validity checking and reformatting
            # Check that all required fields are present
            service_label = re.sub("[^A-Za-z0-9]", "", os.path.basename(os.path.normpath(gtfs_dir)))
            sqlize_csv.check_for_required_fields("stop_times", columns, service_label)

            idx_trip_id = columns.index("trip_id")
            idx_stop_id = columns.index("stop_id")
            idx_stop_sequence = columns.index("stop_sequence")
            idx_arrival_time = columns.index("arrival_time")
            idx_departure_time = columns.index("departure_time")

            for row in reader:
                trip_id = "%s:%s" % (service_label, row[idx_trip_id].strip())
                stop_id = "%s:%s" % (service_label, row[idx_stop_id].strip())
                arrival_time = row[idx_arrival_time]
                departure_time = row[idx_departure_time]
                if arrival_time == '' or departure_time == '':
                    msg = u"GTFS dataset " + os.path.basename(gtfs_dir) + u" contains empty \
values for arrival_time or departure_time in stop_times.txt.  Although the \
GTFS spec allows empty values for these fields, this toolbox \
requires exact time values for all stops.  You will not be able to use this \
dataset for your analysis."
                    arcpy.AddError(msg)
                    raise CustomError
                if not sqlize_csv.check_time_str(arrival_time) or not sqlize_csv.check_time_str(departure_time):
                    msg = u"GTFS dataset " + os.path.basename(gtfs_dir) + u" contains invalid \
values for arrival_time or departure_time in stop_times.txt that are not in HH:MM:SS format."
                    arcpy.AddError(msg)
                else:
                    arrival_time = hms.str2sec(arrival_time)
                    departure_time = hms.str2sec(departure_time)
                datarow = [stop_id, int(row[idx_stop_sequence]), arrival_time, departure_time]
                stop_times_dict.setdefault(trip_id, []).append(datarow)

        # For each trip, select stops in the trip, put them in order, and get pairs
        # of directly-connected stops
        for trip in stop_times_dict.keys():
            selectedstops = stop_times_dict[trip]
            selectedstops.sort(key=operator.itemgetter(1))
            for x in range(0, len(selectedstops)-1):
                start_stop = selectedstops[x][0]
                end_stop = selectedstops[x+1][0]
                SourceOIDkey = "%s , %s , %s" % (start_stop, end_stop, str(trip_routetype_dict[trip]))
                # This stop pair needs a line feature
                linefeature_dict[SourceOIDkey] = True


        # ----- Write pairs to a points feature class (this is intermediate and will NOT go into the final ND) -----

        # Create a points feature class for the point pairs.
        arcpy.management.CreateFeatureclass(outGDB, outStopPairsFCName, "POINT", "", "", "", outFD_SR)
        arcpy.management.AddField(outStopPairsFC, "stop_id", "TEXT")
        arcpy.management.AddField(outStopPairsFC, "pair_id", "TEXT")
        arcpy.management.AddField(outStopPairsFC, "sequence", "SHORT")

        # Add pairs of stops to the feature class in preparation for generating line features
        badStops = []
        badkeys = []
        with arcpy.da.InsertCursor(outStopPairsFC, ["SHAPE@", "stop_id", "pair_id", "sequence"]) as cur:
            # linefeature_dict = {"start_stop , end_stop , route_type": True}
            for SourceOIDkey in linefeature_dict:
                stopPair = SourceOIDkey.split(" , ")
                # {stop_id: [stop_lat, stop_lon]}
                try:
                    stop1 = stopPair[0]
                    stop1_geom = stoplatlon_dict[stop1]
                except KeyError:
                    badStops.append(stop1)
                    badkeys.append(SourceOIDkey)
                    continue
                try:
                    stop2 = stopPair[1]
                    stop2_geom = stoplatlon_dict[stop2]
                except KeyError:
                    badStops.append(stop2)
                    badkeys.append(SourceOIDkey)
                    continue
                cur.insertRow((stop1_geom, stop1, SourceOIDkey, 1))
                cur.insertRow((stop2_geom, stop2, SourceOIDkey, 2))

        if badStops:
            badStops = list(set(badStops))
            arcpy.AddWarning("Your stop_times.txt lists times for the following \
stops which are not included in your stops.txt file. Schedule information for \
these stops will be ignored. " + unicode(badStops))

        # Remove these entries from the linefeatures dictionary so it doesn't cause false records later
        if badkeys:
            badkeys = list(set(badkeys))
            for key in badkeys:
                del linefeature_dict[key]

    # ----- Generate lines between all stops (for the final ND) -----

        if GTFSCount == 1:
            outLinesFC_ThisTime = outLinesFC
        else:
            outLinesFC_ThisTime = outLinesFC + service_label

        arcpy.management.PointsToLine(outStopPairsFC, outLinesFC_ThisTime, "pair_id", "sequence")
        arcpy.management.AddField(outLinesFC_ThisTime, "route_type", "SHORT")
        arcpy.management.AddField(outLinesFC_ThisTime, "route_type_text", "TEXT")

        # We don't need the points for anything anymore, so delete them.
        arcpy.Delete_management(outStopPairsFC)

        if GTFSCount == 1:
            AddToOID_firstTime = int(arcpy.management.GetCount(outLinesFC_ThisTime).getOutput(0))

        # Clean up lines with 0 length.  They will just produce build errors and
        # are not valuable for the network dataset in any other way.
        expression = """"Shape_Length" = 0"""
        with arcpy.da.UpdateCursor(outLinesFC_ThisTime, ["pair_id"], expression) as cur2:
            for row in cur2:
                del linefeature_dict[row[0]]
                cur2.deleteRow()

        # Insert the route type into the output lines
        with arcpy.da.UpdateCursor(outLinesFC_ThisTime, ["pair_id", "route_type", "route_type_text", "OID@"]) as cur4:
            # StopPairs: {pairID: [firstStop_id, secondStop_id, route_type]}
            counter = 0
            for row in cur4:
                counter += 1
                pair_id_list = row[0].split(" , ")
                try:
                    route_type = int(pair_id_list[2])
                except ValueError:
                    # The route_type has an invalid non-integer value.  If that's the case, just leave it as a string for now.
                    route_type = pair_id_list[2]
                # While we're at it, add the line's ObjectID value to the linefeature_dict dictionary
                # Ammend it based on the number already in the final output
                if GTFSCount == 1:
                    # If this is the first GTFS dataset, the OID is whatever is in the file (there may be gaps from deleted rows)
                    linefeature_dict[row[0]] = long(row[3])
                else:
                    # If this is not the first GTFS dataset, the append tool will add rows after the highest existing OID value
                    # and remove any gaps from deleted rows
                    linefeature_dict[row[0]] = AddToOID + counter
                try:
                    route_type_text = route_type_dict[route_type]
                except KeyError: # The user's data isn't a standard type from the GTFS spec
                    route_type_text = "Other / Type not specified (%s)" % unicode(route_type)
                if not isinstance(route_type, int):
                    row[1] = None
                else:
                    row[1] = route_type
                row[2] = route_type_text
                cur4.updateRow(row)
            # Increment by the number of lines we added for this GTFS dataset
            if GTFSCount == 1:
                AddToOID += AddToOID_firstTime # There could be OID gaps in the first GTFS dataset
            else:
                AddToOID += counter # After that, gaps are removed when the Append tool is run

        # If this is an additional GTFS dataset, append the line features to the first lines feature class
        if GTFSCount != 1:
            arcpy.management.Append(outLinesFC_ThisTime, outLinesFC, "TEST")
            arcpy.management.Delete(outLinesFC_ThisTime)


        # ----- Add schedule information to the SQL database -----

        def Add_Schedule_To_SQL(trip):
            'Generate rows of ["SourceOID", "trip_id", "start_time", "end_time"] to add to the SQL database'

            # Select the stop_times entries associated with this trip and sort them by sequence
            selectedstops = stop_times_dict[trip]
            selectedstops.sort(key=operator.itemgetter(1))

            stopvisitlist = [] # One entry per line feature per trip instance

            # If the trip uses the frequencies.txt file, extrapolate the stop_times
            # throughout the day using the relative time between the stops given in
            # stop_times and the headways listed in frequencies.
            if trip in frequencies_dict:
                # Collect the stop pairs in the trip and the relative time between them
                freq_trip_time_dict = {} # {pairID: [SourceOID, time_along_trip, time_between]}
                first_stop = True
                for x in range(0, len(selectedstops)-1):
                    start_stop = selectedstops[x][0]
                    end_stop = selectedstops[x+1][0]
                    SourceOIDkey = "%s , %s , %s" % (start_stop, end_stop, str(trip_routetype_dict[trip]))
                    # Calculate the travel time between the two stops
                    start_time = selectedstops[x][3]
                    end_time = selectedstops[x+1][2]
                    if first_stop:
                        trip_start_time = start_time
                        first_stop = False
                    time_between = end_time - start_time
                    time_along_trip = start_time - trip_start_time
                    freq_trip_time_dict[SourceOIDkey] = [time_along_trip, time_between]

                # Extrapolate using the headway and time windows from frequencies to fill in the stop visits
                for window in frequencies_dict[trip]:
                    start_timeofday = window[0]
                    end_timeofday = window[1]
                    headway = window[2]
                    for i in range(int(round(start_timeofday, 0)), int(round(end_timeofday, 0)), headway):
                        for SourceOIDkey in freq_trip_time_dict:
                            try:
                                SourceOID = linefeature_dict[SourceOIDkey]
                            except KeyError:
                                # This was most likely a line feature that was deleted for having 0 length
                                continue
                            start_time = i + freq_trip_time_dict[SourceOIDkey][0] #current trip start time + time along trip
                            end_time = start_time + freq_trip_time_dict[SourceOIDkey][1] #segment start time plus time between start and end
                            stopvisitlist.append((SourceOID, trip, start_time, end_time))

            else:
                # Otherwise, directly insert the stop visits from stop_times into StopPairTimes dictionary
                for x in range(0, len(selectedstops)-1):
                    start_stop = selectedstops[x][0]
                    end_stop = selectedstops[x+1][0]
                    SourceOIDkey = "%s , %s , %s" % (start_stop, end_stop, str(trip_routetype_dict[trip]))
                    try:
                        SourceOID = linefeature_dict[SourceOIDkey]
                    except KeyError:
                        # This was most likely a line feature that was deleted for having 0 length
                        continue
                    # Add the schedule data
                    start_time = selectedstops[x][3]
                    end_time = selectedstops[x+1][2]
                    stopvisitlist.append((SourceOID, trip, start_time, end_time))

            # Delete the entries in the giant stop_times dictionary associated with this trip_id, just to unclog memory
            # (not sure if this actually works)
            del stop_times_dict[trip]

            return stopvisitlist


        # Convert the stop visit list into rows appropriately formatted for insertion into the SQL table
        rows = itertools.chain.from_iterable(itertools.imap(Add_Schedule_To_SQL, stop_times_dict.keys()))

        # Add the rows to the SQL table
        columns = ["SourceOID", "trip_id", "start_time", "end_time"]
        values_placeholders = ["?"] * len(columns)
        c.executemany("INSERT INTO schedules (%s) VALUES (%s);" %
                            (",".join(columns),
                            ",".join(values_placeholders))
                            , rows)
        conn.commit()


    # ----- Add transit line feature information to the SQL database -----

        def retrieve_linefeatures_info(in_key):
            '''Creates the correct rows for insertion into the linefeatures table.'''
            SourceOID = linefeature_dict[in_key]
            pair_id_list = in_key.split(" , ")
            from_stop = pair_id_list[0]
            to_stop = pair_id_list[1]
            try:
                route_type = int(pair_id_list[2])
            except ValueError:
                # The route_type field has an invalid non-integer value, so just set it to a dummy value
                route_type = "NULL"
            out_row = (SourceOID, from_stop, to_stop, route_type)
            return out_row

        # Convert the dictionary into rows appropriately formatted for insertion into the SQL table
        rows = itertools.imap(retrieve_linefeatures_info, linefeature_dict.keys())

        # Add the rows to the SQL table
        columns = ["SourceOID", "from_stop", "to_stop", "route_type"]
        values_placeholders = ["?"] * len(columns)
        c.executemany("INSERT INTO linefeatures (%s) VALUES (%s);" %
                            (",".join(columns),
                            ",".join(values_placeholders))
                            , rows)
        conn.commit()


# Done iterating over GTFS datasets

    # Index the new table for fast lookups later (particularly in GetEIDs)
    c.execute("CREATE INDEX linefeatures_index_SourceOID ON linefeatures (SourceOID);")
    conn.commit()


# ----- Finish up. -----

    # Clean up
    conn.close()
    # We don't need the points for anything anymore, so delete them.
    # Delete the pair_id column from TransitLines since it's no longer needed
    arcpy.management.DeleteField(outLinesFC, "pair_id")

    arcpy.AddMessage("Finished!")
    arcpy.AddMessage("Your SQL table of GTFS data is:")
    arcpy.AddMessage("- " + SQLDbase)
    arcpy.AddMessage("Your transit stops feature class is:")
    arcpy.AddMessage("- " + outStopsFC)
    arcpy.AddMessage("Your transit lines feature class is:")
    arcpy.AddMessage("- " + outLinesFC)

except CustomError:
    arcpy.AddError("Failed to generate transit lines and stops.")
    pass

except:
    arcpy.AddError("Failed to generate transit lines and stops.")
    raise

finally:
    # Reset the overwrite output to the user's original setting..
    arcpy.env.overwriteOutput = OverwriteOutput