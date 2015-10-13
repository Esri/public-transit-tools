################################################################################
## Toolbox: Add GTFS to a Network Dataset / Transit Analysis Tools
## Tool name: Transit Identify
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 16 December 2014
################################################################################
'''This tool prints the schedule information for selected transit lines, to
facilitate network dataset debugging.  You can optionally save the printed
schedule information to a text file for easier reading.'''
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

import arcpy, sqlite3, os, operator, codecs
import hms

class CustomError(Exception):
    pass

try:
    # User inputs
    TransitLines = arcpy.GetParameter(0)
    outFile = arcpy.GetParameterAsText(1)

    # First make sure the user isn't trying to look at more than just a few transit lines at a time
    count = int(arcpy.management.GetCount(TransitLines).getOutput(0))
    if count > 5:
        arcpy.AddError("This tool is designed to print schedule information for a small number of transit \
lines in your network to help with network debugging.  Please use the select tools to select no more than 5 \
transit lines and run the tool again.  For more information, please read the description of this tool in the \
user's guide.")
        raise CustomError

    # Infer the SQL database to use based on the input transit lines
    SQLDbase = os.path.join(os.path.dirname(os.path.dirname(TransitLines.dataSource)), "GTFS.sql")

    # Connect to the SQL database
    conn = sqlite3.connect(SQLDbase)
    c = conn.cursor()

    # ----- Check if the schedules table is indexed and index it if not -----

    hasIndex = False
    idxName = "schedules_index_SourceOID_endtime"
    c.execute("PRAGMA index_list(schedules)")
    indices = c.fetchall()
    for index in indices:
        if index[1] == idxName:
            hasIndex = True

    if not hasIndex:
        arcpy.AddMessage("Your GTFS SQL database is not yet indexed.  This tool will index \
the schedules table for faster schedule lookups.  The indexing process may take a few minutes, \
but the table need only be indexed once, and future runs of this tool will be fast.")
        arcpy.AddMessage("Indexing schedules table...")
        c.execute("CREATE INDEX %s ON schedules (SourceOID, end_time);" % idxName)
        conn.commit()
    # Note: We don't need the extra index on end_time here, but Copy Traversed Source Features (with Transit)
    # uses it, so no need for that tool to create yet another large index.


    # ----- Collect some GTFS information for reference -----

    trip_info_dict = {}
    tripsfetch = '''
        SELECT trip_id, route_id, service_id
        FROM trips
        ;'''
    c.execute(tripsfetch)
    triplist = c.fetchall()
    for trip in triplist:
        trip_info_dict[trip[0]] = [trip[1], trip[2]]

    cal_info_dict = {}
    calfetch = '''
        SELECT service_id, monday, tuesday, wednesday, thursday, friday, saturday, sunday
        FROM calendar
        ;'''
    c.execute(calfetch)
    callist = c.fetchall()
    for cal in callist:
        weekdaystring = ""
        if bool(cal[1]): weekdaystring += "M"
        else: weekdaystring += "-"
        if bool(cal[2]): weekdaystring += "T"
        else: weekdaystring += "-"
        if bool(cal[3]): weekdaystring += "W"
        else: weekdaystring += "-"
        if bool(cal[4]): weekdaystring += "Th"
        else: weekdaystring += "-"
        if bool(cal[5]): weekdaystring += "F"
        else: weekdaystring += "-"
        if bool(cal[6]): weekdaystring += "S"
        else: weekdaystring += "-"
        if bool(cal[7]): weekdaystring += "Su"
        else: weekdaystring += "-"
        cal_info_dict[cal[0]] = weekdaystring


    # ----- For each selected transit line, pull the schedules and print them nicely -----

    if outFile:
        arcpy.AddMessage("Writing the schedule information to a text file: %s" % outFile)
        f = codecs.open(outFile, 'w', "utf-8-sig")

    with arcpy.da.SearchCursor(TransitLines, ["OID@", "route_type_text"]) as cur:
        for line in cur:
            SourceOID = line[0]
            route_type = line[1]
            prettyPrint = u"\n\n-- Schedule for TransitLine with ObjectID %s --\nRoute type: %s" % (SourceOID, route_type)
            prettyPrint += "\nstart_time  end_time  weekdays  trip_id  route_id  service_id"

            scheduleFetch = "SELECT trip_id, start_time, end_time from schedules WHERE SourceOID=%s" % SourceOID
            c.execute(scheduleFetch)
            schedules = c.fetchall()
            alltrips = [] # {route_id: {service_id: [trip, trip, trip]}}
            for sched in schedules:
                trip_id = sched[0]
                start_time = hms.sec2str(float(sched[1]))
                end_time = hms.sec2str(float(sched[2]))
                route_id = trip_info_dict[trip_id][0]
                service_id = trip_info_dict[trip_id][1]
                try:
                    weekdays = cal_info_dict[service_id]
                except KeyError:
                    # service_id wasn't present in calendar.txt. Presumably it's handled in calendar_dates.txt
                    weekdays = "-------"
                alltrips.append([start_time, end_time, weekdays, trip_id, route_id, service_id])
            alltrips.sort(key=operator.itemgetter(0))
            for trip in alltrips:
                prettyPrint += u"\n%s  %s  %s  %s  %s  %s" % (trip[0], trip[1], trip[2], trip[3], trip[4], trip[5])

            arcpy.AddMessage(prettyPrint)
            if outFile:
                f.write(prettyPrint)


except CustomError:
    arcpy.AddError("Failed to retrieve transit edge schedule information.")
    pass

except:
    arcpy.AddError("Failed to retrieve transit edge schedule information.")
    raise

finally:
    if outFile:
        f.close()