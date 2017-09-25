############################################################################
## Tool name: Simple interpolation
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 9 August 2017
############################################################################
'''
This tool assigns values to blank arrival_time and departure_time values in the
stop_times.txt file using a simple interpolation method.  Stops with blank times
are assigned times evenly spaced between surrounding stops that do have stop
time values.  This simple method does not consider the distance or drive time
between stops.
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

import sqlite3, operator, codecs, csv
import hms
import arcpy


class CustomError(Exception):
    pass


def interpolate_times(time_point_1, time_point_2, blank_times):
    ''' Simple interpolation method. Assume stop times are evenly spaced between time points.'''
    # [arrival_time, departure_time, id]
    num_blank_stops = len(blank_times)
    # Find the total number of seconds between departing the first time point and arriving at the second time point.
    total_time_interval_secs = hms.hmsdiff(time_point_2[0], time_point_1[1])
    # Find the interval size that divides the total time evenly.
    time_between_stops_secs = total_time_interval_secs / float(num_blank_stops + 1)
    # Increment the interval and assign values to the blank stops
    current_secs = hms.str2sec(time_point_1[1])
    for blank_time in blank_times:
        current_secs += time_between_stops_secs
        blank_time[0] = hms.sec2str(current_secs)
        # Set arrival_time and departure_time to the same value.
        blank_time[1] = blank_time[0]
    return blank_times
    
    
try:
    
    # Check the user's version
    ArcVersionInfo = arcpy.GetInstallInfo("desktop")
    ProductName = ArcVersionInfo['ProductName']

    # Gather inputs
    SQLDbase = arcpy.GetParameterAsText(0)
    outStopTimesFile = arcpy.GetParameterAsText(1)


    # ----- First add values for anything that has only arrival_time or only departure_time blank -----

    arcpy.AddMessage("Analyzing data...")

    conn = sqlite3.connect(SQLDbase)
    c = conn.cursor()
    
    # Just set them equal to one another
    CountEasyOnesStmt = "SELECT COUNT(sqliteprimarykeyid) FROM stop_times WHERE arrival_time='' and departure_time!=''"
    c.execute(CountEasyOnesStmt)
    numeasyones = c.fetchone()[0]
    if numeasyones > 0:
        arcpy.AddMessage("There are %s stop time values that have a departure_time but not an arrival_time. For \
these cases, the arrival_time will simply be set equal to the departure_time value." % str(numeasyones))
        UpdateEasyOnesStmt = "UPDATE stop_times SET arrival_time=departure_time WHERE arrival_time='' and departure_time!=''"
        c.execute(UpdateEasyOnesStmt)
        conn.commit()
    
    CountEasyOnesStmt = "SELECT COUNT(sqliteprimarykeyid) FROM stop_times WHERE arrival_time!='' and departure_time=''"
    c.execute(CountEasyOnesStmt)
    numeasyones = c.fetchone()[0]
    if numeasyones > 0:
        arcpy.AddMessage("There are %s stop time values that have a arrival_time but not a departure_time. For \
these cases, the departure_time will simply be set equal to the arrival_time value." % str(numeasyones))
        UpdateEasyOnesStmt = "UPDATE stop_times SET departure_time=arrival_time WHERE arrival_time!='' and departure_time=''"
        c.execute(UpdateEasyOnesStmt)
        conn.commit()

    # Make sure there are at least some non-blank values
    CountStmt = "SELECT COUNT(sqliteprimarykeyid) FROM stop_times WHERE arrival_time!=''"
    c.execute(CountStmt)
    numnotblank = c.fetchone()[0]
    if numnotblank == 0:
        arcpy.AddError("Your stop_times.txt does not contain any arrival_time values \
that are not blank.  No interpolation will be possible because there is no data to \
start with!")
        raise CustomError

    # Count unique trip_ids with blank times
    CountStmt = "SELECT DISTINCT trip_id FROM stop_times WHERE arrival_time='';"
    c.execute(CountStmt)
    blanktrips = [trip[0] for trip in c.fetchall()]
    numblanktrips = len(blanktrips)
    if numblanktrips == 0:
        arcpy.AddMessage("There are no blank stop times in your stop_times.txt file, so there is no further work to be done!")
        raise CustomError
    arcpy.AddMessage("Number of trip_ids with blank arrival_times: %s" % numblanktrips)


    # ----- Interpolate blank times for all trips that have them -----
    
    arcpy.AddMessage("Interpolating blank stop times...")

    # Do some accounting to print a progress report
    tenperc = 0.1 * numblanktrips
    progress = 0
    perc = 10    
    
    # Do each trip one by one
    badtrips = []
    for trip in blanktrips:
        progress += 1
        if progress >= tenperc:
            arcpy.AddMessage(str(perc) + "% finished")
            perc += 10
            progress = 0
        
        # Get all stop_times associated with this trip.
        GetTripInfoStmt = "SELECT sqliteprimarykeyid, stop_sequence, arrival_time, departure_time FROM stop_times WHERE trip_id='%s';" % trip
        c.execute(GetTripInfoStmt)
        tripinfo = [list(trip) for trip in c.fetchall()]
        tripinfo.sort(key=operator.itemgetter(1))
        
        # Check that the first and last stop_times are not blank.
        if not tripinfo[0][2] or not tripinfo[-1][2]:
            badtrips.append(trip)
            continue
        
        # Figure out which are the time points and which are blank, and split them into groups to interpolate
        time_point_1 = ""
        time_point_2 = ""
        current_blank_times = []
        updated_tripinfo = [] # [arrival_time, departure_time, id]
        for stop in tripinfo:
            stop_formatted = [stop[2], stop[3], stop[0]]
            if stop_formatted[0]: # We found a time point
                if not time_point_1:
                    # This is the first time point in the trip
                    time_point_1 = stop_formatted
                elif not time_point_2:
                    # We have encountered the next time piont
                    time_point_2 = stop_formatted
                    # Calculate the interpolated stop times
                    updated_tripinfo += interpolate_times(time_point_1, time_point_2, current_blank_times)
                    # Prepare for the next segment
                    current_blank_times = []
                    time_point_1 = stop_formatted # time_point_2 becomes time_point_1 of the next segment
                    time_point_2 = ""
            else:
                # The time was blank. Append it to our list to deal with later.
                current_blank_times.append(stop_formatted)
            
        # Update SQL table with the interpolated values
        UpdateStmt = "UPDATE stop_times SET arrival_time=?,departure_time=?,timepoint=0 WHERE sqliteprimarykeyid=?"
        c.executemany(UpdateStmt, updated_tripinfo)
        conn.commit()
    
    # Throw a warning or error about any bad trips
    if badtrips:
        missing_timepoint_msg = "Blank stop time values could not be interpolated for %s of the trips \
in your dataset. %s trips with blank stop time values were missing times for the first stop, the last stop, or both."
        numbadtrips = len(badtrips)
        if numbadtrips == numblanktrips:
            arcpy.AddError(missing_timepoint_msg % ("any", "All"))
            raise CustomError
        else:
            missing_timepoint_msg = missing_timepoint_msg % ("some", str(numbadtrips) + " of " + str(numblanktrips)) + " Bad trips: "
            if numbadtrips < 10:
                missing_timepoint_msg += str(badtrips)
            else:
                missing_timepoint_msg += "(Showing the first 10) "
                missing_timepoint_msg += str(badtrips[0:10])
            arcpy.AddWarning(missing_timepoint_msg)


    # ----- Write stop_times back out to a csv file -----
    
    arcpy.AddMessage("Writing new stop_times.txt file...")

    def WriteStopTimesFile(f):
        wr = csv.writer(f)

        # Get the columns for stop_times.txt.
        c.execute("PRAGMA table_info(stop_times)")
        stoptimes_table_info = c.fetchall()
        columns = ()
        for col in stoptimes_table_info:
            if col[1] != "sqliteprimarykeyid":
                columns += (col[1],)
        # Write the columns to the CSV
        wr.writerow(columns)

        # Read in the rows from the stop_times SQL table
        columnquery = ", ".join(columns)
        selectstoptimesstmt = "SELECT %s FROM stop_times;" % columnquery
        c.execute(selectstoptimesstmt)
        for stoptime in c:
            # Encode in utf-8.
            if ProductName == "ArcGISPro":
                stoptimelist = [t for t in stoptime]
            else:
                stoptimelist = [t.encode("utf-8") if isinstance(t, basestring) else t for t in stoptime]
            stoptimetuple = tuple(stoptimelist)
            wr.writerow(stoptimetuple)

    # Open the new stop_times CSV for writing
    if ProductName == "ArcGISPro":
        with codecs.open(outStopTimesFile, "wb", encoding="utf-8") as f:
            WriteStopTimesFile(f)
    else:         
        with open(outStopTimesFile, "wb") as f:
            WriteStopTimesFile(f)

    arcpy.AddMessage("Done! Your updated stop_times.txt file is located at %s" % outStopTimesFile)

    conn.close()

except CustomError:
    pass

except:
    raise