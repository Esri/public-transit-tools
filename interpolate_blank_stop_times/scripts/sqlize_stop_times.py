############################################################################
## Tool name: Preproces stop_times
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 11 March 2016
############################################################################
'''
This tool creates a SQL table from a GTFS stop_times.txt file and analyzes
the number of blank arrival_time and departure_time values present.  The SQL
table can be used as input to other tools to replace the blank values with 
interpolated estimates.
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

import sqlite3, os, csv
import arcpy

class CustomError(Exception):
    pass

try:
    # Check the user's version
    ArcVersionInfo = arcpy.GetInstallInfo("desktop")
    ProductName = ArcVersionInfo['ProductName']
    
    # Collect user inputs
    stop_times_file = arcpy.GetParameterAsText(0)
    SQLDbase = arcpy.GetParameterAsText(1)
    
    
    # ----- Turn stop_times.txt into a SQL table -----
    
    # Grab the data from the stop_times.txt file and insert it into the SQL table
    arcpy.AddMessage("Inserting stop_times.txt data into SQL table...")
    col_idxs = []
    with open(stop_times_file) as f:
        
        # Get the csv data
        reader = csv.reader(f)
        if ProductName == "ArcGISPro":
            reader = ([x.strip() for x in r] for r in reader if len(r) > 0)
        else:
            reader = ([x.decode('utf-8-sig').strip() for x in r] for r in reader if len(r) > 0)
        columns = [name.strip() for name in next(reader)]
        
        # Make sure the necessary columns are there to start with
        relevant_cols = {"trip_id": "trip_id CHAR,\n",
                        "arrival_time": "arrival_time CHAR,\n",
                        "departure_time": "departure_time CHAR,\n",
                        "stop_id": "stop_id CHAR,\n",
                        "stop_sequence": "stop_sequence INT,\n"}
        table_schema = "sqliteprimarykeyid INTEGER PRIMARY KEY,\n"
        for col in relevant_cols:
            if not col in columns:
                arcpy.AddError("Your GTFS dataset's stop_times.txt file is missing a required column: %s" % col)
                raise CustomError
        
        # Create the SQL database and table with the appropriate schema
        for col in columns:
            if col in relevant_cols:
                table_schema += relevant_cols[col]
            else:
                table_schema += col + " CHAR,\n"
        table_schema = table_schema.strip(",\n")
        conn = sqlite3.connect(SQLDbase)
        conn.execute("DROP TABLE IF EXISTS stop_times;")
        create_stmt = "CREATE TABLE stop_times (%s);" % table_schema
        conn.execute(create_stmt)
        conn.commit()
        
        # Add the stop_times data to the SQL table
        values_placeholders = ["?"] * len(columns)
        c = conn.cursor()
        c.executemany("INSERT INTO stop_times (%s) VALUES (%s);" %
                            (",".join(columns),
                            ",".join(values_placeholders))
                            , reader)
        conn.commit()
        
        # Create indices to speed up searching later
        c.execute("CREATE INDEX idx_arrivaltime ON stop_times (arrival_time);")
        c.execute("CREATE INDEX idx_departuretime ON stop_times (departure_time);")
        c.execute("CREATE INDEX idx_arrivaltime_stopid ON stop_times (stop_id, arrival_time);")
        c.execute("CREATE INDEX idx_tripid ON stop_times (trip_id);")
        conn.commit()


    # ----- Analyze the stop_times.txt file to try to understand how it's constructed -----
    
    # Gather some information about the data
    arcpy.AddMessage("Analyzing the stop_times.txt data...")
    
    # Make sure there are at least some non-blank values
    CountStmt = "SELECT COUNT(sqliteprimarykeyid) FROM stop_times WHERE arrival_time!=''"
    c.execute(CountStmt)
    numnotblank = c.fetchone()[0]
    if numnotblank == 0:
        arcpy.AddError("Your stop_times.txt does not contain any arrival_time values \
that are not blank.  No interpolation will be possible because there is no data to \
start with!")
        raise CustomError
    
    # Count total number of unique trip_ids
    CountStmt = "SELECT COUNT (DISTINCT trip_id) FROM stop_times;"
    c.execute(CountStmt)
    numtrips = c.fetchone()[0]
    arcpy.AddMessage("Total number of trip_ids: %s" % str(numtrips))
    
    # Count unique trip_ids with blank arrival_times
    CountStmt = "SELECT COUNT(DISTINCT trip_id) FROM stop_times WHERE arrival_time='';"
    c.execute(CountStmt)
    numblanktrips = c.fetchone()[0]
    arcpy.AddMessage("Number of trip_ids with blank arrival_times: %s" % numblanktrips)

    # If there were no blank arrival_times, then perhaps we need to look at departure_times.
    use_departures = False
    if numblanktrips == 0:
        use_departures = True
        # Count unique trip_ids with blank departure_times
        CountStmt = "SELECT COUNT(DISTINCT trip_id) FROM stop_times WHERE departure_time='';"
        c.execute(CountStmt)
        numblanktrips = c.fetchone()[0]
        arcpy.AddMessage("Number of trip_ids with blank departure_times: %s" % numblanktrips)

        # If there are also no blank departure_times, then this data doesn't need to be fixed.
        if numblanktrips == 0:
            arcpy.AddWarning("Your stop_times.txt file does not contain any blank arrival_time \
or departure_time values. No interpolation is needed.")
            raise CustomError
    
    # Calculate the percent of trips which have blank stop times and then make some assumptions
    percentblanktrips = round((float(numblanktrips) / float(numtrips)) * 100, 1)
    arcpy.AddMessage("Percent of trips with blank stop times: %s%%" % str(percentblanktrips))
    time_points_message = "Because %s of your trips contain blank stop times, it is likely that your GTFS dataset was \
intentionally constructed using time points.  The stops in between time points are not given a specific \
stop time value because the the arrival and departure time are not guaranteed to be consistent or exact. A lot of \
interpolation will be necessary for this data, and the procedure could take some time."
    if percentblanktrips == 100:
        arcpy.AddMessage(time_points_message % "all")
    elif percentblanktrips >= 80: # Note: this limit is fairly arbitrary
        arcpy.AddMessage(time_points_message % "most")

    # If only some trips contain blank stop times, then it's less obvious why the data contains blanks.
    # It could be a mistake, it could be a merged dataset, or it could be something else.
    else:
        # Count total number of unique stop_ids
        CountStmt = "SELECT COUNT (DISTINCT stop_id) FROM stop_times;"
        c.execute(CountStmt)
        numstops = c.fetchone()[0]
        arcpy.AddMessage("Total number of stop_ids: %s" % str(numstops))
        
        # Count unique stop_ids with blank times
        stop_time = "arrival_time"
        if use_departures:
            stop_time = "departure_time"
        CountStmt = "SELECT COUNT (DISTINCT stop_id) FROM stop_times WHERE %s='';" % stop_time
        c.execute(CountStmt)
        numblankstops = c.fetchone()[0]
        arcpy.AddMessage("Number of stop_ids with blank %s: %s" % (stop_time, numblankstops))
        
        percentblankstops = round((float(numblankstops) / float(numstops)) * 100, 1)
        arcpy.AddMessage("Percent of stops with blank stop times: %s%%" % str(percentblankstops))
        
        # Take some more guesses
        if percentblankstops <= 10: # Note: this limit is fairly arbitrary
            arcpy.AddMessage("Because the number of stops with blank stop time values is small, it is likely that \
these stop time values are blank by mistake and that your GTFS dataset was not constructed this way \
intentionally. Simple interpolation should correct these mistakes fairly quickly.")
        # Sometimes, it may be impossible to take a reasonable guess
        else:
            arcpy.AddMessage("It is unclear why some trips and stops in your GTFS dataset have blank stop time values \
and others do not.  It is possible that your GTFS dataset contains data merged from multiple transit \
systems, some of which assign values to all stop times and some of which intentionally leave stop time \
values blank in order to represent time points.  Interpolation can be used to estimate blank stop time values.")

    conn.close()

except CustomError:
    pass

except:
    raise