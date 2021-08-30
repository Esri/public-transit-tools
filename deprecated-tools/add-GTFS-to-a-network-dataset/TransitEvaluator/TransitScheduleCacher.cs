//##############################################################################
//Copyright 2015 Esri
//   Licensed under the Apache License, Version 2.0 (the "License");
//   you may not use this file except in compliance with the License.
//   You may obtain a copy of the License at
//       http://www.apache.org/licenses/LICENSE-2.0
//   Unless required by applicable law or agreed to in writing, software
//   distributed under the License is distributed on an "AS IS" BASIS,
//   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//   See the License for the specific language governing permissions and
//   limitations under the License.
//##############################################################################

using System;
using System.Collections.Generic;
using System.Diagnostics;
using ESRI.ArcGIS.Geodatabase;
using System.Data.SQLite;

namespace TransitEvaluator
{
    public class TransitScheduleCacher
    {
        #region cache schedules

        // TODO: This method requires too many parameters.
        //  Separate out the UI style cache and the non-ui style in a more elegant way.
        // PATRICK ^ 
        public static void CacheSchedules(ref bool caching_complete, string workspace_path,
            ref int total_row_count, Action setTotalRowCount, ref int one_percent, ref string caching_message,
            ref string current_table_name,
            Action displayTableName, Action<int, Stopwatch> updateTimeUI,
            ref Dictionary<string, Dictionary<DateTime, CalendarExceptionType>> calExceptions,
            ref Dictionary<string, Calendar> calendars,
            ref Dictionary<string, Trip> trips,
            ref Dictionary<long, List<trip_instance>> eids,
            ref Dictionary<long, long> linefeatures)
        {
            caching_complete = false;

            try
            {
                string SQLDataPath = workspace_path + @"\GTFS.sql";
                if (!System.IO.File.Exists(SQLDataPath))
                {
                    // The SQL database is missing.
                    throw new Exception("The SQL database containing your GTFS data is missing.  It should be in the geodatabase where your network dataset is stored.  Please recreate your network dataset using the Add GTFS to a Network Dataset tools.  Alternatively, if you are seeing this message on ArcGIS Server, you need to ensure that GTFS.sql gets copied to the server along with the network dataset.");
                }
                
                string workspaceConnectionString = @"Data Source=" + SQLDataPath + @"; Version=3;";
                using (SQLiteConnection conn = new SQLiteConnection(workspaceConnectionString))
                {
                    conn.Open();

                    bool hasCalendar = false;
                    bool hasCalendarDates = false;

                    // Check that the SQL database contains the necessary tables
                    using (SQLiteCommand cmd = new SQLiteCommand(conn))
                    {
                        List<string> Required_tbls = new List<string> { "trips", "linefeatures", "schedules" };
                        List<string> Existing_tbls = new List<string>();
                        
                        cmd.CommandText = "SELECT * FROM sqlite_master WHERE type='table';";
                        SQLiteDataReader reader = cmd.ExecuteReader();
                        while (reader.Read())
                        {
                            string tblname = reader["name"].ToString();
                            Existing_tbls.Add(tblname);
                            if (tblname == "calendar") {hasCalendar = true;}
                            else if (tblname == "calendar_dates") {hasCalendarDates = true;}                           
                        }

                        if (!hasCalendar && !hasCalendarDates)
                        {
                            // The SQL database is missing a calendar and/or calendar_dates table. This must have resulted from a corrupted SQL database, since the python scripts that generate it already check for this issue in the original GTFS.
                            throw new Exception("The SQL database containing your GTFS data is missing a calendar or calendar_dates table.  It must have at least one of these. Please check your GTFS data and re-create your network using the Add GTFS to a Network Dataset toolbox.");
                        }
                        
                        foreach (string tblName in Required_tbls)
                        {
                            if (!Existing_tbls.Contains(tblName))
                            {
                                // The SQL database is missing a required table. The data might just be messed up, or they might be using an old network dataset.
                                throw new Exception("The SQL database containing your GTFS data is missing a required table. Please re-create your network using the Add GTFS to a Network Dataset toolbox.");
                            }
                        }
                    }

                    // Initialize this ahead of time because we need to use it later.
                    int linefeatures_count = 0;

                    // Count the number of rows we have to process.
                    using (SQLiteCommand cmd = new SQLiteCommand(conn))
                    {
                        total_row_count = 0;
                        cmd.CommandText = "SELECT COUNT(*) from trips";
                        int trip_count = Convert.ToInt32(cmd.ExecuteScalar()); // Cannot be 0
                        int calendar_count = 0;
                        if (hasCalendar)
                        {
                            cmd.CommandText = "SELECT COUNT(*) from calendar";
                            calendar_count = Convert.ToInt32(cmd.ExecuteScalar());
                        } // Can be 0
                        int calendar_dates_count = 0;
                        if (hasCalendarDates)
                        {
                            cmd.CommandText = "SELECT COUNT(*) from calendar_dates";
                            calendar_dates_count = Convert.ToInt32(cmd.ExecuteScalar());
                        } // Can be 0
                        cmd.CommandText = "SELECT COUNT(*) from linefeatures";
                        linefeatures_count = Convert.ToInt32(cmd.ExecuteScalar()); // Cannot be 0
                        cmd.CommandText = "SELECT COUNT(*) from schedules";
                        int schedules_count = Convert.ToInt32(cmd.ExecuteScalar()); // Cannot be 0

                        if (trip_count == 0 || linefeatures_count == 0)
                        {
                            // If the trips or linefeatures tables are empty, something went horrendously wrong.
                            throw new Exception("Transit schedules cannot be cached because your SQL database is empty.  Please re-create your network using the Add GTFS to a Network Dataset toolbox.");
                        }
                        if (calendar_count == 0 && calendar_dates_count == 0)
                        {
                            // If both calendar and calendar_dates are empty, something went horrendously wrong.
                            throw new Exception("Transit schedules cannot be cached because your SQL database is missing calendar information.  Please check that your GTFS data contains either a calendar or a calendar_dates file (or both) and re-create your network using the Add GTFS to a Network Dataset toolbox.");
                        }
                        if (schedules_count == 0)
                        {
                            // If the schedules table is empty, something got messed up in Step 1, or they're using an old network or something
                            throw new Exception("Transit schedules cannot be cached because your SQL database is missing schedule information. Please re-create your network using the Add GTFS to a Network Dataset toolbox.");
                        }

                        total_row_count = trip_count + calendar_count + calendar_dates_count + linefeatures_count + schedules_count;
                        // Update the progress form with the total number of rows
                        if (setTotalRowCount != null)
                            setTotalRowCount();
                    }

                    int processedRowCount = 0; // How many rows counted so far?
                    one_percent = total_row_count / 100;
                    if (one_percent == 0) one_percent = 1;

                    // How long have we taken so far?
                    Stopwatch timeSoFar = new Stopwatch();
                    timeSoFar.Start();

                    ////////////////////////////////////////////////
                    //  Process the calendar table
                    if (hasCalendar)
                    {
                        using (SQLiteCommand cmd = new SQLiteCommand(conn))
                        {
                            SQLiteDataReader reader;
                            current_table_name = "calendar";
                            cmd.CommandText = String.Format("SELECT * from {0}", current_table_name);
                            reader = cmd.ExecuteReader();
                            CacheCalendarTable(ref reader, ref processedRowCount, timeSoFar,
                                ref current_table_name, displayTableName, updateTimeUI, ref calendars);
                        }
                    }

                    /////////////////////////////////////////////////
                    //  Process the calendar exceptions table
                    if (hasCalendarDates)
                    {
                        using (SQLiteCommand cmd = new SQLiteCommand(conn))
                        {
                            SQLiteDataReader reader;
                            current_table_name = "calendar_dates";
                            cmd.CommandText = String.Format("SELECT * from {0}", current_table_name);
                            reader = cmd.ExecuteReader();
                            CacheExceptionsTable(ref reader, ref processedRowCount, timeSoFar,
                                ref current_table_name, displayTableName, updateTimeUI, ref calExceptions);
                        }
                    }

                    /////////////////////////////////////////////////
                    //  Process the trips table
                    using (SQLiteCommand cmd = new SQLiteCommand(conn))
                    {
                        SQLiteDataReader reader;
                        current_table_name = "trips";
                        cmd.CommandText = String.Format("SELECT trip_id, route_id, service_id, wheelchair_accessible, bikes_allowed from {0}", current_table_name);
                        reader = cmd.ExecuteReader();
                        CacheTripTable(ref reader, ref processedRowCount, timeSoFar,
                            ref current_table_name, displayTableName, updateTimeUI, ref trips);
                    }

                    /////////////////////////////////////////////////
                    //  Process the linefeatures table (relating SourceOID and eid)
                    using (SQLiteCommand cmd = new SQLiteCommand(conn))
                    {
                        SQLiteDataReader reader;
                        current_table_name = "linefeatures";
                        cmd.CommandText = String.Format("SELECT SourceOID, eid from {0}", current_table_name);
                        reader = cmd.ExecuteReader();
                        CacheLineFeatures(ref reader, ref processedRowCount, timeSoFar,
                            ref current_table_name, displayTableName, updateTimeUI, ref linefeatures, linefeatures_count);
                    }

                    /////////////////////////////////////////////////
                    //  Process the trip instance / schedules table
                    using (SQLiteCommand cmd = new SQLiteCommand(conn))
                    {
                        SQLiteDataReader reader;
                        current_table_name = "schedules";
                        cmd.CommandText = String.Format("SELECT * from {0}", current_table_name);
                        reader = cmd.ExecuteReader();
                        CacheTripInstances(ref reader, ref processedRowCount, timeSoFar,
                            ref current_table_name, displayTableName, updateTimeUI, ref eids, ref linefeatures);
                    }
                }

                caching_complete = true;
            }
                // There cannot be throw exceptions, or ArcMap will crash
            catch (Exception e)
            {
                caching_complete = false;
                caching_message = e.Message;
                return;
            }
        }

        #region cache each table

        private static void CacheCalendarTable(ref SQLiteDataReader reader, ref int processedRowCount, Stopwatch timeSoFar, ref string current_table_name,
            Action displayTableName, Action<int, Stopwatch> updateTimeUI,
            ref Dictionary<string, Calendar> calendars)
        {
            // Update the table name shown on the progress form
            if (displayTableName != null)
                displayTableName();
            
            // Loop through the calendar table and add the information to a dictionary keyed by service_id
            try
            {
                while (reader.Read())
                {
                    ++processedRowCount;
                    if (updateTimeUI != null)
                        updateTimeUI(processedRowCount, timeSoFar);

                    Calendar cal = new Calendar();
                    cal.monday = Convert.ToBoolean(reader["monday"]);
                    cal.tuesday = Convert.ToBoolean(reader["tuesday"]);
                    cal.wednesday = Convert.ToBoolean(reader["wednesday"]);
                    cal.thursday = Convert.ToBoolean(reader["thursday"]);
                    cal.friday = Convert.ToBoolean(reader["friday"]);
                    cal.saturday = Convert.ToBoolean(reader["saturday"]);
                    cal.sunday = Convert.ToBoolean(reader["sunday"]);

                    String start_date = reader["start_date"].ToString();
                    cal.start_date = DateTime.ParseExact(start_date,
                                                  "yyyyMMdd",
                                                  System.Globalization.CultureInfo.InvariantCulture,
                                                  System.Globalization.DateTimeStyles.None);
                    String end_date = reader["end_date"].ToString();
                    cal.end_date = DateTime.ParseExact(end_date,
                                                  "yyyyMMdd",
                                                  System.Globalization.CultureInfo.InvariantCulture,
                                                  System.Globalization.DateTimeStyles.None);

                    string service_id = reader["service_id"].ToString();

                    // Add the calendar item to the dictionary.
                    calendars[service_id] = cal;
                }
            }
            catch (Exception e)
            {
                throw new Exception("Error caching calendar table. Error: " + e.Message, e);
            }
        }

        private static void CacheExceptionsTable(ref SQLiteDataReader reader,
            ref int processedRowCount, Stopwatch timeSoFar, ref string current_table_name,
            Action displayTableName, Action<int, Stopwatch> updateTimeUI,
            ref Dictionary<string, Dictionary<DateTime, CalendarExceptionType>> calExceptions)
        {
            // Update the table name shown on the progress form
            if (displayTableName != null)
                displayTableName();

            // Loop through the calendar_dates table and add the information to a dictionary keyed by service_id
            try
            {
                while (reader.Read())
                {
                    ++processedRowCount;
                    if (updateTimeUI != null)
                        updateTimeUI(processedRowCount, timeSoFar);

                    String sDate = reader["date"].ToString();
                    DateTime Date = DateTime.ParseExact(sDate,
                                                  "yyyyMMdd",
                                                  System.Globalization.CultureInfo.InvariantCulture,
                                                  System.Globalization.DateTimeStyles.None);
                    Int16 exception_type_int = Convert.ToInt16(reader["exception_type"].ToString());
                    CalendarExceptionType exception_type = (CalendarExceptionType)exception_type_int;

                    string service_id = reader["service_id"].ToString();

                    // Add the exception to the dictionary under the appropriate service_id.
                    if (calExceptions.ContainsKey(service_id))
                    {
                        calExceptions[service_id].Add(Date, exception_type);
                    }
                    else
                    {
                        calExceptions.Add(service_id, new Dictionary<DateTime, CalendarExceptionType> { { Date, exception_type } });
                    }
                }
            }
            catch (Exception e)
            {
                throw new Exception("Error caching calendar exceptions. Error: " + e.Message, e);
            }
        }

        private static void CacheTripTable(ref SQLiteDataReader reader,
            ref int processedRowCount, Stopwatch timeSoFar, ref string current_table_name,
            Action displayTableName, Action<int, Stopwatch> updateTimeUI,
            ref Dictionary<string, Trip> trips)
        {
            // Update the table name shown on the progress form
            if (displayTableName != null)
                displayTableName();

            // Loop through the trips table and add the information to a dictionary keyed by trip_id
            try
            {
                while (reader.Read())
                {
                    ++processedRowCount;
                    if (updateTimeUI != null)
                        updateTimeUI(processedRowCount, timeSoFar);

                    Trip trip = new Trip();
                    trip.route_id = reader["route_id"].ToString();
                    trip.service_id = reader["service_id"].ToString();

                    // Assign the correct wheelchair_accesssible enumerator value based on input
                    string whchr = reader["wheelchair_accessible"].ToString();
                    if (whchr == null)
                    {
                        trip.wheelchair_accessible = TripRestrictionType.nodata;
                    }
                    else
                    {
                        Int16 wheelchair_accessible_int = Convert.ToInt16(whchr);
                        if (wheelchair_accessible_int < 0 || wheelchair_accessible_int > 2)
                        {
                            trip.wheelchair_accessible = TripRestrictionType.nodata;
                        }
                        else
                        {
                            TripRestrictionType wheelchair_accessible = (TripRestrictionType)wheelchair_accessible_int;
                            trip.wheelchair_accessible = wheelchair_accessible;
                        }
                    }

                    // Assign the correct bikes_allowed enumerator value based on input
                    string bike = reader["bikes_allowed"].ToString();
                    if (bike == null)
                    {
                        trip.bikes_allowed = TripRestrictionType.nodata;
                    }
                    else
                    {
                        Int16 bikes_allowed_int = Convert.ToInt16(bike);
                        if (bikes_allowed_int < 0 || bikes_allowed_int > 2)
                        {
                            trip.bikes_allowed = TripRestrictionType.nodata;
                        }
                        else
                        {
                            TripRestrictionType bikes_allowed = (TripRestrictionType)bikes_allowed_int;
                            trip.bikes_allowed = bikes_allowed;
                        }
                    }

                    string trip_id = reader["trip_id"].ToString();

                    // Add the current trip to the dictionary of all trips
                    trips.Add(trip_id, trip);
                }
            }
            catch (Exception e)
            {
                throw new Exception("Error caching trips table. Error: " + e.Message, e);
            }
        }

        private static void CacheLineFeatures(ref SQLiteDataReader reader,
            ref int processedRowCount, Stopwatch timeSoFar, ref string current_table_name,
            Action displayTableName, Action<int, Stopwatch> updateTimeUI,
            ref Dictionary<long, long> linefeatures, int total_features)
        {
            // Update the table name shown on the progress form
            if (displayTableName != null)
                displayTableName();

            // Loop through the linefeatures table and add the information to a dictionary of <SourceOID, EID>
            try
            {
                int nullEIDCount = 0;
                while (reader.Read())
                {
                    ++processedRowCount;
                    if (updateTimeUI != null)
                        updateTimeUI(processedRowCount, timeSoFar);
                    
                    long SourceOID = Convert.ToInt64(reader["SourceOID"].ToString());
                    object eid_obj = reader["eid"];
                    if (eid_obj == System.DBNull.Value)
                    {
                        ++nullEIDCount;
                        continue;
                    }
                    
                    long EID = Convert.ToInt64(eid_obj);
                    // Add the current trip to the dictionary of all trips
                    linefeatures.Add(SourceOID, EID);
                }

                if (nullEIDCount == total_features)
                {
                    // If there were no EID values in the table, the user probably just forgot to run GetEIDs.
                    throw new Exception("FAILURE: All EIDs were null in the transit schedule table. Please run Get Network EIDs.");
                }
            }
            catch (Exception e)
            {
                throw new Exception("Error caching linefeatures table. Error: " + e.Message, e);
            }
        }

        private static void CacheTripInstances(ref SQLiteDataReader reader,
            ref int processedRowCount, Stopwatch timeSoFar,
            ref string current_table_name, Action displayTableName, Action<int, Stopwatch> updateTimeUI,
            ref Dictionary<long, List<trip_instance>> eids,
            ref Dictionary<long, long> linefeatures)
        {
            // Update the table name shown on the progress form
            if (displayTableName != null)
                displayTableName();

            // Loop through the trip instances and add a list of them to a dictionary keyed by EID.
            try
            {
                while (reader.Read())
                {
                    ++processedRowCount;
                    if (updateTimeUI != null)
                        updateTimeUI(processedRowCount, timeSoFar);

                    trip_instance TI = new trip_instance();
                    TI.trip_id = reader["trip_id"].ToString();
                    TI.start_time = Convert.ToInt32(reader["start_time"].ToString());
                    TI.end_time = Convert.ToInt32(reader["end_time"].ToString());

                    long SourceOID = Convert.ToInt64(reader["SourceOID"].ToString());
                    long EID;
                    try{EID = linefeatures[SourceOID];}
                    catch
                    {
                        // If there's a problem, it's probably because there was a build error and
                        // the sourceOID never got put into the network, so an EID was never generated
                        // Just skip these.
                        continue;
                    }

                    // Add the trip to the dictionary under the appropriate eid.
                    if (eids.ContainsKey(EID))
                    {
                        eids[EID].Add(TI);
                    }
                    else
                    {
                        eids.Add(EID, new List<trip_instance>() { TI });
                    }
                }
                   
            }
            catch (Exception e)
            {
                throw new Exception("Error caching trip instances table. Error: " + e.Message, e);
            }
        }

        #endregion

        #endregion
    }
}
