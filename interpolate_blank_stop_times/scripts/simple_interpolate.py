import sqlite3, operator
import hms


def interpolate_times(time_point_1, time_point_2, blank_times):
    # [arrival_time, departure_time, id]
    num_blank_stops = len(blank_times)
    time_interval_secs = hms.hmsdiff(time_point_2[0], time_point_1[1])
    time_gap = time_interval_secs / float(num_blank_stops + 1)
    current_secs = hms.str2sec(time_point_1[1])
    for blank_time in blank_times:
        current_secs += time_gap
        blank_time[0] = hms.sec2str(current_secs)
        blank_time[1] = blank_time[0]
    return blank_times
    
    


##SQLDbase = r'E:\public-transit-tools\interpolate_blank_stop_times\testdata\Clemson.sql'
##SQLDbase = r'E:\public-transit-tools\interpolate_blank_stop_times\testdata\SiouxFalls.sql'
SQLDbase = r'E:\public-transit-tools\interpolate_blank_stop_times\testdata\Clemson2.sql'

conn = sqlite3.connect(SQLDbase)
c = conn.cursor()

### Count blank arrival_time values
##CountStmt = "SELECT COUNT (DISTINCT stop_id) FROM stop_times WHERE arrival_time='';"
##c.execute(CountStmt)
##count = c.fetchone()[0]
##print("Distinct stop_ids with blank arrival_times:")
##print(count)

### Count unique stop_ids with blank times
##CountStmt = "SELECT DISTINCT stop_id FROM stop_times WHERE arrival_time='';"
##c.execute(CountStmt)
##blankstops = [stop[0] for stop in c.fetchall()]
##print("Distinct stop_ids with blank arrival_times:")
##print(len(blankstops))
####print(blankstops)


# First add values for anything that has only arrival_time or only departure_time blank
CountEasyOnesStmt = "SELECT COUNT(id) FROM stop_times WHERE arrival_time='' and departure_time!=''"
c.execute(CountEasyOnesStmt)
numeasyones = c.fetchone()[0]
if numeasyones > 0:
    print("There are %s stop time values that have a departure_time but not an arrival_time. For \
these cases, the arrival_time will simply be set equal to the departure_time value." % str(numeasyones))
    UpdateEasyOnesStmt = "UPDATE stop_times SET arrival_time=departure_time WHERE arrival_time='' and departure_time!=''"
    c.execute(UpdateEasyOnesStmt)
    conn.commit()

CountEasyOnesStmt = "SELECT COUNT(id) FROM stop_times WHERE arrival_time!='' and departure_time=''"
c.execute(CountEasyOnesStmt)
numeasyones = c.fetchone()[0]
if numeasyones > 0:
    print("There are %s stop time values that have a arrival_time but not a departure_time. For \
these cases, the departure_time will simply be set equal to the arrival_time value." % str(numeasyones))
    UpdateEasyOnesStmt = "UPDATE stop_times SET departure_time=arrival_time WHERE arrival_time!='' and departure_time=''"
    c.execute(UpdateEasyOnesStmt)
    conn.commit()


# Count total number of unique trip_ids
CountStmt = "SELECT COUNT (DISTINCT trip_id) FROM stop_times;"
c.execute(CountStmt)
numtrips = c.fetchone()[0]
print("Distinct trip_ids:")
print(numtrips)

# Count unique trip_ids with blank times
CountStmt = "SELECT DISTINCT trip_id FROM stop_times WHERE arrival_time='';"
c.execute(CountStmt)
blanktrips = [trip[0] for trip in c.fetchall()]
numblanktrips = len(blanktrips)
print("Distinct trip_ids with blank arrival_times:")
print(numblanktrips)

print("Percent of trips that contain blank times:")
percentblank = (float(numblanktrips) / float(numtrips)) * 100
print(percentblank)





### What if first stop_time is blank?
##
##for trip in blanktrips:
##    print trip
##    GetTripInfoStmt = "SELECT id, stop_sequence, arrival_time, departure_time FROM stop_times WHERE trip_id='%s';" % trip
##    c.execute(GetTripInfoStmt)
##    tripinfo = [list(trip) for trip in c.fetchall()]
##    tripinfo.sort(key=operator.itemgetter(1))
##    time_point_1 = ""
##    time_point_2 = ""
##    current_blank_times = []
##    updated_tripinfo = [] # [arrival_time, departure_time, id]
##    for stop in tripinfo:
##        stop_formatted = [stop[2], stop[3], stop[0]]
##        if stop_formatted[0]:
##            if not time_point_1:
##                # This is the first time point in the trip
##                time_point_1 = stop_formatted
##            elif not time_point_2:
##                # We have encountered the next time piont
##                time_point_2 = stop_formatted
##                updated_tripinfo += interpolate_times(time_point_1, time_point_2, current_blank_times)
##                current_blank_times = []
##                time_point_1 = stop_formatted
##                time_point_2 = ""
##        else:
##            # The time was blank. Append it to our list to deal with later.
##            current_blank_times.append(stop_formatted)
##        
##    # Update SQL table
##    UpdateStmt = "UPDATE stop_times SET arrival_time=?,departure_time=? WHERE id=?"
##    c.executemany(UpdateStmt, updated_tripinfo)
##    conn.commit()
##
##for thing in updated_tripinfo:
##    print thing
##
### ----- Cases -----
##
### 1) A few blank instances by mistake
##''' In this case, when the blank stops have times at other times of day, we can use the existing times.'''
##
### 2) A few stops for which all instances are blank
##''' Interpolate these few stops and insert them'''
##
### 3) The GTFS is constructed purposefully using time points.