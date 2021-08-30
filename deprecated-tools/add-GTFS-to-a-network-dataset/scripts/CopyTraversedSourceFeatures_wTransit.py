####################################################
## Tool name: Copy Traversed Source Features (with Transit)
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 21 October 2017
####################################################
''' Copy Traversed Source Features (with Transit)

This tool is designed to be used with Network Analyst layers referencing network
datasets created using the Add GTFS to a Network Dataset tools.

The ArcGIS Network Analyst tool Copy Traversed Source Features produces feature
classes showing the network edges, junctions, and turns that were traversed when
solving a network analysis layer.  It shows the actual network features that
were used.  This tool is an extension of the ArcGIS tool designed for use with
transit network datasets.  It adds GTFS transit information to the traversal
result produced by the ArcGIS Copy Traversed Source Features tool.  GTFS stop
information is added to the output Junctions. GTFS route information, trip_id,
arrive and depart time and stop names, and the transit time and wait time are
added to the output Edges for each transit leg.  An additional feature class is
produced containing only the transit edges.
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

import arcpy, os, sqlite3, datetime
import hms


class CustomError(Exception):
    pass


def MakeServiceIDList(date):
    '''Find the service ids for the selected day of the week from calendar.txt'''
    day = weekdays[date.weekday()]
    dayindex = Calendar_Columns.index(day)
    SIDsForToday = []
    for SID in CalendarList: # [service_id, start_date, end_date, monday, ..., sunday]
        if SID[dayindex] == 1:
            if specificDates:
                start_datetime = datetime.datetime.strptime(SID[1], "%Y%m%d")
                end_datetime = datetime.datetime.strptime(SID[2], "%Y%m%d")
                end_datetime = end_datetime.replace(hour=11, minute=59, second=59)
                if start_datetime <= date <= end_datetime:
                    SIDsForToday.append(SID[0])
            else:
                SIDsForToday.append(SID[0])
    return SIDsForToday


def EditServiceIDList_CalendarDates(date, SIDList):
    '''Modify the service_id list using info from the calendar_dates.txt file.'''
    datestring = date.strftime("%Y%m%d")
    cs = conn.cursor()
    GetServiceIDstmt = '''
        SELECT service_id, exception_type FROM calendar_dates
        WHERE date == "%s";''' % datestring
    cs.execute(GetServiceIDstmt)
    for SID in cs:
        if SID[1] == 2:
            SIDList = [p for p in SIDList if p != SID[0]]
        elif SID[1] == 1:
            SIDList.append(SID[0])
    return list(set(SIDList))


def GetTransitTrips(row, end_time_sec_clean_1, end_time_sec_clean_2, SIDList):
    rows_to_insert = []
    row = list(row)

    # Time direction determines which time we should use
    if BackInTime:
        time_to_use = "start_time"
    else:
        time_to_use = "end_time"

    # Pull out the trip info from the TransitScheduleTable
    cs = conn.cursor()
    scheduleFetch = "SELECT trip_id, start_time, end_time FROM schedules WHERE SOURCEOID=%s AND %s=%s" % (row[0], time_to_use, end_time_sec_clean_1)
    cs.execute(scheduleFetch)
    EvalTableList = [sched for sched in cs]

    if not EvalTableList:
        # Try to find trips after rounding in the other direction
        scheduleFetch = "SELECT trip_id, start_time, end_time FROM schedules WHERE SOURCEOID=%s AND %s=%s" % (row[0], time_to_use, end_time_sec_clean_2)
        cs.execute(scheduleFetch)
        EvalTableList = [sched for sched in cs]

    if not EvalTableList:
        return rows_to_insert

    for trip in EvalTableList:
        trip_id = trip[0]
        service_id = trip_info_dict[trip_id][1]
        if service_id in SIDList:
            trip_start_time = trip[1]
            if trip_start_time > SecsInDay:
                trip_start_time = trip_start_time - SecsInDay
            trip_end_time = trip[2]
            if trip_end_time > SecsInDay:
                trip_end_time = trip_end_time - SecsInDay

            row[3] = trip_id #trip_id
            route_id = trip_info_dict[trip_id][0]
            row[4] = RouteDict[route_id][0] #agency_id
            row[5] = route_id #route_id
            row[6] = RouteDict[route_id][4] #route_type
            row[7] = RouteDict[route_id][8] #route_type_text
            row[8] = RouteDict[route_id][1] #route_short_name
            row[9] = RouteDict[route_id][2] #route_long_name
            # Assign stop info
            try: start_stop = stop_junctionID_dict[row[24]]
            except KeyError: start_stop = "Unknown"
            try: end_stop = stop_junctionID_dict[row[25]]
            except KeyError: end_stop = "Unknown"
            row[14] = start_stop #start_stop_id
            try: row[15] = stopid_dict[start_stop] #start_stop_name
            except KeyError: row[15] = "Unknown"
            row[16] = end_stop #end_stop_id
            try: row[17] = stopid_dict[end_stop] #end_stop_name
            except KeyError: row[17] = "Unknown"
            # Calculate wait time and transit time
            row[12] = hms.sec2str(trip_start_time) #depart_timeofday
            row[13] = hms.sec2str(trip_end_time) #arrive_timeofday
            transit_time = float((float(trip_end_time) - float(trip_start_time)) / 60.0)
            row[11] = round(transit_time, 2) #transit_time
            leg_time = row[2]
            # Note: When travel is back in time, the wait time occurs after the
            # last transit leg instead of before the first one.
            row[10] = round(leg_time - transit_time, 2) #wait_time
            if len(EvalTableList) > 1 and row[10] < 0:
                # If multiple route choices were returned, and if this one has a wait time < 0 (a very small <0 value occurs
                # occasionally), skip this because it's the wrong one.
                continue

            rows_to_insert.append(tuple(row))

    return rows_to_insert


try:

    try:

        # ----- Collect and validate user inputs -----

        arcpy.AddMessage("Collecting and validating inputs...")

        # Random global variables.
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        SecsInDay = 86400
        # ArcMap's indication that this layer was solved for "Today" instead of a specific weekday
        floatingToday = datetime.date(1899, 12, 30)

        orig_overwrite = arcpy.env.overwriteOutput
        arcpy.env.overwriteOutput = True

        #Check out the Network Analyst extension license
        if arcpy.CheckExtension("Network") == "Available":
            arcpy.CheckOutExtension("Network")
        else:
            arcpy.AddError("Network Analyst license is unavailable.")
            raise CustomError

        # Get the NALayer they want to run copy traversed on.
        inNALayerPath = arcpy.GetParameterAsText(0)

        # Get output location and names for fcs
        outGDB = arcpy.GetParameterAsText(1)
        edgesName = arcpy.GetParameterAsText(2)
        tempedgesName = "TempEdges"
        junctionsName = arcpy.GetParameterAsText(3)
        turnsName = arcpy.GetParameterAsText(4)
        transitsName = arcpy.GetParameterAsText(5)
        Edges = os.path.join(outGDB, edgesName)
        TempEdges = os.path.join(outGDB, tempedgesName)
        Junctions = os.path.join(outGDB, junctionsName)
        Turns = os.path.join(outGDB, turnsName)
        # A special added output that shows only the transit edges traversed
        TransitEdges = os.path.join(outGDB, transitsName)

        # Extract the network dataset and solver properties from the NALayer
        inNALayer = arcpy.mapping.Layer(inNALayerPath)
        if not inNALayer.isNetworkAnalystLayer:
            arcpy.AddError("The input layer must be a network analysis layer.")
            raise CustomError
        solverProps = arcpy.na.GetSolverProperties(inNALayer)
        desc = arcpy.Describe(inNALayerPath)
        nds = desc.network
        inNetworkDataset = nds.catalogPath

        SupportedSolvers = ["Route Solver", "Closest Facility Solver"]
        # Get solver name
        solvername = desc.solverName
        if solvername not in SupportedSolvers:
            arcpy.AddError("Network analysis layers of type %s are not supported \
in this tool. Please choose a different layer." % solvername)
            raise CustomError

        # Extract the impedance attribute name
        impedanceAttribute = desc.impedance
        ndsAttributes = nds.attributes
        for attr in ndsAttributes:
            if attr.name == impedanceAttribute:
                impObject = attr

        # Check if the it used the transit evaluator.
        evalCount = impObject.evaluatorCount
        ValidTransitEval = 0
        if evalCount > 0:
            for i in range(0, evalCount):
                evalType = getattr(impObject, "evaluatorType" + str(i))
                if evalType == "TransitEvaluator.TransitEvaluator":
                    ValidTransitEval = 1
        if not ValidTransitEval:
            arcpy.AddError(u"This network analysis layer was solved with an impedance \
attribute (%s) that does not use the TransitEvaluator from Add GTFS to a \
Network Dataset. Please re-solve your analysis with the correct impedance \
attribute or use a valid transit network dataset created using the Add GTFS to \
a Network Dataset tool." % impedanceAttribute)
            raise CustomError

        # Check if the Use Specific Dates parameter is there.
        paramCount = impObject.parameterCount
        ValidSpecDates = 0
        if paramCount > 0:
            for i in range(0, paramCount):
                paramName = getattr(impObject, "parameterName" + str(i))
                if paramName == "Use Specific Dates":
                    ValidSpecDates = 1

        # Extract the time of day from the layer
        ## Note: VRP does not use timeOfDay. If we implement this tool for VRP,
        ## We will need an alternate method
        analysis_timeofday = solverProps.timeOfDay
        if not analysis_timeofday:
            arcpy.AddError("Your network analysis layer must use a time of day. If \
your layer does not use GTFS transit data or a time of day, please use the \
regular Copy Traversed Source Features tool.")
            raise CustomError
        # If the user chose the floating "Today" instead of a specific Day of Week,
        # assume the solve occurred on today's day of week.
        if analysis_timeofday.date() == floatingToday:
            now = datetime.date.today()
            nowyear = now.year
            nowmonth = now.month
            nowday = now.day
            a_hr = analysis_timeofday.hour
            a_min = analysis_timeofday.minute
            a_sec = analysis_timeofday.second
            analysis_timeofday = datetime.datetime(nowyear, nowmonth, nowday, a_hr, a_min, a_sec)
            arcpy.AddWarning(u"Warning! Your NALayer was solved using 'Today' as \
the Day of Week instead of a specific weekday. If you are running Copy Traversed \
Source Features (with Transit) on a different day of the week than the weekday on \
which you solved your NALayer, the tool might find incorrect transit information. \
This tool is assuming your NALayer was solved on a %s. If your results are unsatisfactory, \
resolve your NALayer on a specific weekday instead of 'Today'." % now.strftime("%A"))
        yesterday = analysis_timeofday - datetime.timedelta(days=1)
        tomorrow = analysis_timeofday + datetime.timedelta(days=1)
        if ValidSpecDates:
            specificDates = solverProps.attributeParameters[(impedanceAttribute, 'Use Specific Dates')]
        else:
            specificDates = False
        journey_start_sec = (analysis_timeofday.hour * 3600) + (analysis_timeofday.minute * 60) + analysis_timeofday.second

        # See if the analysis_timeofday is actually the end time, as this affects
        # how we search for the trips that were used.
        BackInTime = False
        if solvername == "Closest Facility Solver":
            TimeDir = solverProps.timeOfDayUsage
            if TimeDir == "END_TIME":
                BackInTime = True

        # Get any cutoff values
        cutoffs = []
        if solvername == "Closest Facility Solver":
            cutoffs = [solverProps.defaultCutoff]
## If/when we implement Service Area, we will need to consider break values
##        elif solvername == "Service Area Solver":
##            cutoffs = solverProps.defaultBreaks

        # Extract the FD and GDB paths and the required input files
        naFD = os.path.dirname(inNetworkDataset)
        # The assumed name of their transit lines feature class is hard-wired.
        TransitFCName = "TransitLines"
        TransitLines = os.path.join(naFD, TransitFCName)
        if not arcpy.Exists(TransitLines):
            arcpy.AddError(u"Your network analysis layer's network dataset must have \
a source feature class named 'TransitLines' in the feature dataset %s. Please \
repair your transit network or choose a different layer." % naFD)
            raise CustomError
        StopsFCName = "Stops"
        Stops = os.path.join(naFD, StopsFCName)
        if not arcpy.Exists(Stops):
            arcpy.AddError(u"Your network analysis layer's network dataset must have \
a source feature class named 'Stops' in the feature dataset %s. Please repair \
your transit network or choose a different layer." % naFD)
            raise CustomError
        naGDB = os.path.dirname(naFD)
        # The SQL database was created in GenerateStopPairs and placed in the GDB. Name should be correct.
        SQLDbase = os.path.join(naGDB, "GTFS.sql")
        if not os.path.exists(SQLDbase):
            arcpy.AddError(u"The geodatabase (%s) where your network analysis layer's \
network dataset is located must have a SQL database naded 'GTFS.sql'. Please \
repair your transit network or choose a different layer." % naGDB)
            raise CustomError

        # Check to see if points are located on Stops (matters later)
        locatorCount = desc.locatorCount
        locators = desc.locators
        locate_on_stops = False
        for i in range(0, locatorCount):
            sourceName = getattr(locators, "source" + str(i))
            snapType = getattr(locators, "snapType" + str(i))
            if sourceName == StopsFCName and snapType != "NONE":
                locate_on_stops = True

        junction_source_dict = {}
        if locate_on_stops:
            junctions = nds.junctionSources
            for junc in junctions:
                junction_source_dict[junc.name] = junc.sourceID

        # Connect to the SQL database
        conn = sqlite3.connect(SQLDbase)
        c = conn.cursor()

        # Determine if we have the correct tables
        RequiredTables = ["schedules", "trips", "routes"]
        ct = conn.cursor()
        GetTblNamesStmt = "SELECT name FROM sqlite_master WHERE type='table';"
        ct.execute(GetTblNamesStmt)
        tblnamelist = []
        containsCalendar = False
        for name in ct:
            tblnamelist.append(name[0])
            if name[0] == "calendar" or name == "calendar_dates":
                containsCalendar = True
        message = "The SQL database (GTFS.sql) associated with \
your transit network dataset does not have all of the required tables.  Before \
running Copy Traversed Source Features (with Transit), run the Update \
Transit Network Dataset tool, or re-create your network dataset from scratch."
        if not containsCalendar:
            arcpy.AddError(message)
            raise CustomError
        for table in RequiredTables:
            if not table in tblnamelist:
                arcpy.AddError(message)
                raise CustomError

        # ----- Create helpful indices on the SQL database if they don't already exist -----

        # Create a date index on the calendar_dates table for fast lookups
        if "calendar_dates" in tblnamelist:
            hasIndex = False
            idxName = "calendardates_index_date"
            c.execute("PRAGMA index_list(calendar_dates)")
            for index in c:
                if index[1] == idxName:
                    hasIndex = True
            if not hasIndex:
                arcpy.AddMessage("Adding a date index to the calendar_dates table in your GTFS SQL database \
for fast schedule lookups.  This will only be done once for this dataset.")
                arcpy.AddMessage("Indexing calendar_dates table...")
                c.execute("CREATE INDEX %s ON calendar_dates (date);" % idxName)
                conn.commit()

        if not BackInTime: # We need fast lookups for SourceOID and end_time
            hasIndex = False
            idxName = "schedules_index_SourceOID_endtime"
            c.execute("PRAGMA index_list(schedules)")
            for index in c:
                if index[1] == idxName:
                    hasIndex = True
            if not hasIndex:
                arcpy.AddMessage("Adding a SourceOID/end_time index to the schedules table in your GTFS SQL database \
for fast schedule lookups.  The indexing process may take a few minutes, \
but the table need only be indexed once, and future runs of this tool will be fast.")
                arcpy.AddMessage("Indexing schedules table...")
                c.execute("CREATE INDEX %s ON schedules (SourceOID, end_time);" % idxName)
                conn.commit()

        else: # We need fast lookups for SourceOID and start_time
            hasIndex = False
            idxName = "schedules_index_SourceOID_starttime"
            c.execute("PRAGMA index_list(schedules)")
            for index in c:
                if index[1] == idxName:
                    hasIndex = True
            if not hasIndex:
                arcpy.AddMessage("Adding a SourceOID/start_time index to the schedules table in your GTFS SQL database \
for fast schedule lookups.  The indexing process may take a few minutes, \
but the table need only be indexed once, and future runs of this tool will be fast.")
                arcpy.AddMessage("Indexing schedules table...")
                c.execute("CREATE INDEX %s ON schedules (SourceOID, start_time);" % idxName)
                conn.commit()

    except Exception as e:
        arcpy.AddError("Error collecting and validating user inputs.")
        raise

    try: # The real action starts here...

    # ---- Run Copy Traversed Source Features -----

        arcpy.AddMessage("Calculating traversal result...")

        TraversalResult = arcpy.na.CopyTraversedSourceFeatures(inNALayerPath, outGDB, tempedgesName,
                                                junctionsName, turnsName).getOutput(3)

    except Exception as e:
        arcpy.AddError("Unable to run Copy Traversed Source Features.")
        raise


    try:

        arcpy.AddMessage("Collecting GTFS information...")


    # ----- Get service_ids for the analysis day -----

        # Read in the calendar table
        Calendar_Columns = ["service_id", "start_date", "end_date"] + weekdays
        GetServiceIDstmt = "SELECT %s FROM calendar;" % ", ".join(Calendar_Columns)
        c.execute(GetServiceIDstmt)
        CalendarList = []
        for SID in c:
            CalendarList.append(SID) # [service_id, start_date, end_date, monday, ..., sunday]

        # If we have calendar, get the service_ids for today, yesterday, and tomorrow
        if "calendar" in tblnamelist:
            service_id_list_today = MakeServiceIDList(analysis_timeofday)
            service_id_list_yesterday = MakeServiceIDList(yesterday)
            service_id_list_tomorrow = MakeServiceIDList(tomorrow)
        else:
            service_id_list_today = []
            service_id_list_yesterday = []
            service_id_list_tomorrow = []

        # If we have calendar_dates and used specific dates in the analysis, modify the valid service_ids
        if specificDates and ("calendar_dates" in tblnamelist):
            service_id_list_today = EditServiceIDList_CalendarDates(analysis_timeofday, service_id_list_today)
            service_id_list_yesterday = EditServiceIDList_CalendarDates(yesterday, service_id_list_yesterday)
            service_id_list_tomorrow = EditServiceIDList_CalendarDates(tomorrow, service_id_list_tomorrow)


    # ----- Get largest stop_time -----

        if BackInTime:
            time_to_use = "start_time"
        else:
            time_to_use = "end_time"

        # We need to know the largest stop time so we can determine whether or
        # not we need to consider trips still running from the previous day.
        MaxTimeFetch = '''SELECT MAX(%s) FROM schedules;''' % time_to_use
        c.execute(MaxTimeFetch)
        MaxTime = c.fetchone()[0]


    # ----- Match trip_ids with route_id and service_id -----

        trip_info_dict = {}
        tripsfetch = '''
            SELECT trip_id, route_id, service_id
            FROM trips
            ;'''
        c.execute(tripsfetch)
        for trip in c:
            trip_info_dict[trip[0]] = [trip[1], trip[2]]


    # ----- Make dictionary of route info -----

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

        # Find all routes and associated info.
        RouteDict = {}
        routesfetch = '''
            SELECT route_id, agency_id, route_short_name, route_long_name,
            route_desc, route_type, route_url, route_color, route_text_color
            FROM routes
            ;'''
        c.execute(routesfetch)
        routelist = c.fetchall()
        for route in routelist:
            # {route_id: [all route.txt fields + route_type_text]}
            route_type = route[5]
            try:
                route_type_text = route_type_dict[route_type]
            except KeyError:
                route_type_text = "Other / Type not specified (%s)" % str(route_type)
            if not isinstance(route_type, int):
                # Remove potential type conflicts for invalid route_types by setting this to none
                route_type = None
            RouteDict[route[0]] = [route[1], route[2], route[3], route[4], route_type,
                                     route[6], route[7], route[8],
                                     route_type_text]


    # ----- Get stop info from stops fc -----

        # Make a dictionary relating Stops OID with stop_id for lookups later
        stopinfo_dict = {}
        stopid_dict = {}
        stop_junctionID_dict = {} # Filled later
        with arcpy.da.SearchCursor(Stops, ["OID@", "stop_id", "stop_name"]) as StopsCursor:
            for st in StopsCursor:
                stopinfo_dict[st[0]] = [st[1], st[2]]
                stopid_dict[st[1]] = st[2]

        inputClass_loc_info = {} # {(SourceName, OID): [stop_id, stop_name]}
        # In the unfortunate event that the user has located their input features on either Stops, Stops_Snapped2Streets,
        # or both, we need another lookup table so we can make sense of the junctions output in the traversal result.
        # The traversal result doesn't return a separate junction feature for the terminating stop but instead just returns
        # the terminating stop, so we have to look up the terminating stop stop_id from the location fields of the stops.
        if locate_on_stops:
            # To further complicate matters, the SourceID field is a long, not text, so we have to extract the text values from the ND describe object.
            where = '''"SourceID" = %s''' % junction_source_dict[StopsFCName]
            if solvername == "Route Solver":
                classesnames_to_check = ["Stops"]
            elif solvername == "Closest Facility Solver":
                classesnames_to_check = ["Facilities", "Incidents"]
            NAClassNames = arcpy.na.GetNAClassNames(inNALayer)
            for classname in classesnames_to_check:
                actual_class_name = NAClassNames[classname]
                sublayer = arcpy.mapping.ListLayers(inNALayer, actual_class_name)[0]
                with arcpy.da.SearchCursor(sublayer, ["OID@", "SourceID", "SourceOID"], where) as NAClassCur:
                    for st in NAClassCur:
                        stop_info = stopinfo_dict[st[2]]
                        inputClass_loc_info[(classname, st[0])] = stop_info

    except Exception as e:
        arcpy.AddError("Error collecting GTFS information.")
        raise


    try:

    # ----- Update Junctions with GTFS stop info -----

        arcpy.AddMessage("Adding GTFS stop information to output Junctions...")

        arcpy.management.AddField(Junctions, "stop_id", "TEXT")
        arcpy.management.AddField(Junctions, "stop_name", "TEXT")

        # We have to qualify the SourceType because the stops in Route are called "Stops" also
        where1 = '''"SourceName" = \'Stops\' AND "SourceType" = \'NETWORK\''''
        with arcpy.da.UpdateCursor(Junctions,
                                ["SourceName", "SourceOID", "stop_id", "stop_name", "OID@"],
                                where1) as JunctionCursor:
            for row in JunctionCursor:
                stop_id = stopinfo_dict[row[1]][0]
                row[2] = stop_id
                row[3] = stopinfo_dict[row[1]][1]
                stop_junctionID_dict[row[4]] = stop_id
                JunctionCursor.updateRow(row)

        if locate_on_stops:
            # If the user has located points on Stops, we have to do some gymnastics to determine the stop_id
            where1 = '''"SourceType" = \'NA_CLASS\' AND "EID" <> -1'''
            with arcpy.da.UpdateCursor(Junctions,
                                    ["SourceName", "SourceOID", "stop_id", "stop_name", "OID@"],
                                    where1) as JunctionCursor:
                for row in JunctionCursor:
                    stopkey = (row[0], row[1])
                    try:
                        stop_info = inputClass_loc_info[stopkey] # {(SourceName, OID): [stop_id, stop_name]}
                        stop_id = stop_info[0]
                        stop_name = stop_info[1]
                    except KeyError:
                        stop_id = "Unknown"
                        stop_name = "Unknown"
                    row[2] = stop_id
                    row[3] = stop_name
                    stop_junctionID_dict[row[4]] = stop_id
                    JunctionCursor.updateRow(row)

    except Exception as e:
        arcpy.AddError("Error updating Junctions feature class with GTFS info.")
        raise


    try:

    # ----- Update Edges with GTFS route info -----

        arcpy.AddMessage("Adding GTFS route and trip information to output Edges...")

        if outGDB == "in_memory":
            arcpy.management.AddField(TempEdges, "Shape_Length", "DOUBLE")
        arcpy.management.AddField(TempEdges, "trip_id", "TEXT")
        arcpy.management.AddField(TempEdges, "agency_id", "TEXT")
        arcpy.management.AddField(TempEdges, "route_id", "TEXT")
        arcpy.management.AddField(TempEdges, "route_type", "SHORT")
        arcpy.management.AddField(TempEdges, "route_type_text", "TEXT")
        arcpy.management.AddField(TempEdges, "route_short_name", "TEXT")
        arcpy.management.AddField(TempEdges, "route_long_name", "TEXT")
        arcpy.management.AddField(TempEdges, "wait_time", "DOUBLE")
        arcpy.management.AddField(TempEdges, "transit_time", "DOUBLE")
        arcpy.management.AddField(TempEdges, "depart_timeofday", "TEXT")
        arcpy.management.AddField(TempEdges, "arrive_timeofday", "TEXT")
        arcpy.management.AddField(TempEdges, "from_stop_id", "TEXT")
        arcpy.management.AddField(TempEdges, "from_stop_name", "TEXT")
        arcpy.management.AddField(TempEdges, "to_stop_id", "TEXT")
        arcpy.management.AddField(TempEdges, "to_stop_name", "TEXT")

        Cumul_field = "Cumul_" + impedanceAttribute # Total transit travel time up to this point
        attr_field = "attr_" + impedanceAttribute # Transit travel time for this leg
        ## Might need to un-hardwire RouteID if we support other solver types
        with arcpy.da.SearchCursor(TempEdges, ["SourceOID", Cumul_field,
                                                    attr_field,
                                                    "trip_id", "agency_id",
                                                    "route_id", "route_type",
                                                    "route_type_text", "route_short_name",
                                                    "route_long_name", "wait_time",
                                                    "transit_time", "depart_timeofday",
                                                    "arrive_timeofday", "from_stop_id",
                                                    "from_stop_name", "to_stop_id",
                                                    "to_stop_name",
                                                    "SourceName", "SourceOID", "SourceType",
                                                    "EID", "FromPosition", "ToPosition", "FromJunctionID",
                                                    "ToJunctionID", "RouteID", "Shape_Length",
                                                    "SHAPE@"]) as EdgeCursor:

            # Now loop through the transit edges and find the transit info.
            rows_to_insert = []
            CurrentRouteID = 0
            FinalCumulTime = 0
            orig_journey_start_sec = journey_start_sec
            for row in EdgeCursor:

                # If travel was back in time, journey_start_sec is actually the end time
                # We need to figure out what the start time was so that we can figure out
                # what time to check in the transit schedules
                # The Cumul_Time in first entry in the traversal result = end time
                if BackInTime:
                    RouteID = row[26]
                    if RouteID != CurrentRouteID:
                        CurrentRouteID = RouteID
                        FinalCumulTime = row[1] * 60
                        journey_start_sec = orig_journey_start_sec - FinalCumulTime

                SourceName = row[18]
                if SourceName == "TransitLines":

                    # If the end time is the cutoff time, we can't extract the trip info
                    # because we don't know the true end time, and we can't extract the
                    # true start time because the wait time is bundled in, so just skip it.
                    # This should only be a problem in ServiceArea
                    if not row[1] in cutoffs:
                        rows_to_insert_init_length = len(rows_to_insert)

                        # Find the correct entry from TransitScheduleTable
                        if BackInTime:
                            # For backwards traversal, end_time_sec is actually the start time
                            end_time_sec = journey_start_sec + ((row[1] - row[2]) * 60)
                        else:
                            end_time_sec = (row[1] * 60) + journey_start_sec
                        # Round to the nearest seconds and check both
                        end_time_sec_clean_1 = int(round(end_time_sec))
                        if end_time_sec_clean_1 > end_time_sec:
                            end_time_sec_clean_2 = end_time_sec_clean_1 - 1
                        else:
                            end_time_sec_clean_2 = end_time_sec_clean_1 + 1

                        # Gather the trips running today
                        # There might be more than one possible trip in the table that runs at the exact same time.
                        # There is no way to know which one is "correct". In fact, either is correct.
                        rows_to_insert = rows_to_insert + GetTransitTrips(row, end_time_sec_clean_1, end_time_sec_clean_2, service_id_list_today)

                        # Determine if it's early enough in the day that we need to consider trips
                        # still running from yesterday
                        if min(end_time_sec_clean_1, end_time_sec_clean_2) < MaxTime - SecsInDay:
                            rows_to_insert = rows_to_insert + GetTransitTrips(row, end_time_sec_clean_1 + SecsInDay, end_time_sec_clean_2 + SecsInDay, service_id_list_yesterday)

                        # If our time window spans midnight, we need to check tomorrow's trips, too.
                        if min(end_time_sec_clean_1, end_time_sec_clean_2) > SecsInDay:
                            rows_to_insert = rows_to_insert + GetTransitTrips(row, end_time_sec_clean_1 - SecsInDay, end_time_sec_clean_2 - SecsInDay, service_id_list_tomorrow)

                        # If we didn't find trip information, just add the row as-is to the output
                        if len(rows_to_insert) == rows_to_insert_init_length:
                            rows_to_insert.append(row)

                else:
                    # If it's not a transit row, just add the row as-is.
                    rows_to_insert.append(row)

        # Create an empty feature class for Edges which we will fill with rows_to_insert
        arcpy.management.CreateFeatureclass(outGDB, edgesName, "POLYLINE", TempEdges, spatial_reference=TempEdges)

        # Insert all the rows with the GTFS info we collected, including
        # duplicates for the same edge.
        with arcpy.da.InsertCursor(Edges, ["SourceOID", Cumul_field,
                                            attr_field,
                                            "trip_id", "agency_id",
                                            "route_id", "route_type",
                                            "route_type_text", "route_short_name",
                                            "route_long_name", "wait_time",
                                            "transit_time", "depart_timeofday",
                                            "arrive_timeofday", "from_stop_id",
                                            "from_stop_name", "to_stop_id",
                                            "to_stop_name",
                                            "SourceName", "SourceOID", "SourceType",
                                            "EID", "FromPosition", "ToPosition", "FromJunctionID",
                                            "ToJunctionID", "RouteID", "Shape_Length",
                                            "SHAPE@"]) as EdgeCursor2:
            for row in rows_to_insert:
                EdgeCursor2.insertRow(row)

        # Clean up
        arcpy.management.Delete(TempEdges)

    except Exception as e:
        raise


    try:

    # ----- Produce the transit-only output table -----

        arcpy.AddMessage("Generating Transit Edges feature class...")

        # Copy out only the transit lines
        arcpy.analysis.Select(Edges, TransitEdges, '''"SourceName" = \'TransitLines\'''')

        # Set output parameters so outputs draw in the map
        arcpy.SetParameterAsText(6, Edges)
        arcpy.SetParameterAsText(7, Junctions)
        arcpy.SetParameterAsText(8, Turns)
        arcpy.SetParameterAsText(9, TransitEdges)
        arcpy.SetParameterAsText(10, TraversalResult)

        arcpy.AddMessage("Finished!")
        arcpy.AddMessage("Outputs:")
        arcpy.AddMessage("- " + Edges)
        arcpy.AddMessage("- " + Junctions)
        arcpy.AddMessage("- " + Turns)
        arcpy.AddMessage("- " + TransitEdges)

    except Exception as e:
        raise

except CustomError:
    pass

except Exception as e:
    raise

finally:
    arcpy.env.overwriteOutput = orig_overwrite