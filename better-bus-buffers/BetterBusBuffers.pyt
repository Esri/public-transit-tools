############################################################################
## Tool name: BetterBusBuffers
## Created by: Melinda Morang, Esri
## Last updated: 7 August 2020
############################################################################
''' Python toolbox that defines all the tools in the BetterBusBuffers tool
suite.'''
################################################################################
'''Copyright 2020 Esri
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

import arcpy
import os
import ToolValidator

class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "BetterBusBuffers"
        self.alias = "BetterBusBuffers"

        # List of tool classes associated with this toolbox
        self.tools = [PreprocessGTFS,
                        CountTripsAtStops,
                        CountTripsAtPoints,
                        CountTripsAtPointsOnline,
                        BBBPolygons_PreprocessBuffers,
                        BBBPolygons_CountTripsInBuffers,
                        BBBIndividualRoute_PreprocessRouteBuffers,
                        BBBIndividualRoute_CountTripsForRoute,
                        BBBLines_PreprocessLines,
                        BBBLines_CountTripsOnLines,
                        CountHighFrequencyRoutesAtStops,
                        CountTripsAtStopsByRouteAndDirection]


#region PreprocessGTFS
class PreprocessGTFS(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Preprocess GTFS"
        self.description = '''This tool turns your GTFS datasets into a SQL database that 
can be used as input for the BetterBusBuffers tools.  You only need to run this step once 
for each geographic area you will be analyzing.  You can use multiple GTFS datasets that 
operate in the same area.'''
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define parameter definitions"""

        params = [
        
        arcpy.Parameter(
            displayName="GTFS directories",
            name="GTFS_directories",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input",
            multiValue=True),

        arcpy.Parameter(
            displayName="Name and location for output SQL database",
            name="out_SQL_database",
            datatype="DEFile",
            parameterType="Required",
            direction="Output")
        ]

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        param_GTFSDirs = parameters[0]
        ToolValidator.check_input_gtfs(param_GTFSDirs)
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import SQLizeGTFS
        inGTFSdir = parameters[0].valueAsText
        SQLDbase = parameters[1].valueAsText
        SQLizeGTFS.runTool(inGTFSdir, SQLDbase)
        return
#endregion


#region CountTripsAtStops
class CountTripsAtStops(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Count Trips at Stops"
        self.description = '''The Count Trips at Stops tool counts the number of \
transit trips that visit the stops in your network during a time window. The output \
is a feature class of your GTFS stops with fields indicating the number of transit \
trips that visit those stops.'''
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define parameter definitions"""

        params = [make_parameter(param_output_feature_class),
                    make_parameter(param_SQLDbase),
                    make_parameter(param_day), 
                    make_parameter(param_time_window_start), 
                    make_parameter(param_time_window_end),
                    make_parameter(param_depOrArr)]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        param_SQLDbase = parameters[1]
        param_day = parameters[2]
        start_time = parameters[3]
        end_time = parameters[4]

        ToolValidator.check_SQLDBase(param_SQLDbase, param_SQLDbase.valueAsText, ["stops", "trips", "stop_times"], ["calendar", "calendar_dates"], param_day)
        ToolValidator.allow_YYYYMMDD_day(param_day, param_SQLDbase.valueAsText)
        ToolValidator.check_time_window(start_time, end_time)

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import BBB_CountTripsAtStops
        outStops = parameters[0].valueAsText
        SQLDbase = parameters[1].valueAsText
        day = parameters[2].valueAsText
        start_time = parameters[3].valueAsText
        end_time = parameters[4].valueAsText
        DepOrArrChoice = parameters[5].valueAsText
        BBB_CountTripsAtStops.runTool(outStops, SQLDbase, day, start_time, end_time, DepOrArrChoice)
        return
#endregion


#region CountTripsAtPoints
class CountTripsAtPoints(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Count Trips at Points"
        self.description = '''The Count Trips at Points tool counts the number of \
transit trips available within a designated distance of specific point locations during \
a time window. The output is a copy of the input point locations with fields indicating \
the number of transit trips available within a short walk during a time window.'''
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define parameter definitions"""

        param_max_impedance = arcpy.Parameter(
            displayName="Max travel time or distance between points and stops (in the units of your impedance attribute)",
            name="max_impedance",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input")

        params = [make_parameter(param_output_feature_class),
                    make_parameter(param_SQLDbase),
                    make_parameter(param_points_to_analyze),
                    make_parameter(param_points_UniqueID),
                    make_parameter(param_day), 
                    make_parameter(param_time_window_start), 
                    make_parameter(param_time_window_end),
                    make_parameter(param_network_dataset),
                    make_parameter(param_impedance),
                    param_max_impedance,
                    make_parameter(param_restrictions),
                    make_parameter(param_depOrArr)]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        param_fc = parameters[2]
        param_UID = parameters[3]
        param_ND = parameters[7]
        param_restr = parameters[10]
        param_imp = parameters[8]

        ToolValidator.populate_UniqueID(param_fc, param_UID)
        ToolValidator.populate_restrictions_and_impedances(param_ND, param_restr, param_imp)

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        param_SQLDbase = parameters[1]
        param_day = parameters[4]
        start_time = parameters[5]
        end_time = parameters[6]
        param_ND = parameters[7]

        ToolValidator.check_SQLDBase(param_SQLDbase, param_SQLDbase.valueAsText, ["stops", "trips", "stop_times"], ["calendar", "calendar_dates"], param_day)
        ToolValidator.allow_YYYYMMDD_day(param_day, param_SQLDbase.valueAsText)
        ToolValidator.check_time_window(start_time, end_time)
        ToolValidator.check_ND_not_from_AddGTFS(param_ND)

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import BBB_CountTripsAtPoints
        outFile = parameters[0].valueAsText
        SQLDbase = parameters[1].valueAsText
        inPointsLayer = parameters[2].valueAsText
        inLocUniqueID = parameters[3].valueAsText
        day = parameters[4].valueAsText
        start_time = parameters[5].valueAsText
        end_time = parameters[6].valueAsText
        inNetworkDataset = parameters[7].value
        imp = parameters[8].valueAsText
        BufferSize = parameters[9].value
        restrictions = parameters[10].valueAsText
        DepOrArrChoice = parameters[11].valueAsText
        BBB_CountTripsAtPoints.runTool(outFile, SQLDbase, inPointsLayer, inLocUniqueID, day, start_time, end_time,
            inNetworkDataset, imp, BufferSize, restrictions, DepOrArrChoice)
        return
#endregion


#region CountTripsAtPointsOnline
class CountTripsAtPointsOnline(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Count Trips at Points Online"
        self.description = '''The Count Trips at Points tool counts the number of \
transit trips available within a designated distance of specific point locations during \
a time window. The output is a copy of the input point locations with fields indicating \
the number of transit trips available within a short walk during a time window. It uses \
the ArcGIS Online Origin-Destination Cost Matrix service so that you don't need your own \
network datasets or a Network Analyst license'''
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define parameter definitions"""

        param_max_dist = arcpy.Parameter(
            displayName="Max distance between stops and points",
            name="max_distance",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input")

        param_max_dist_units = arcpy.Parameter(
            displayName="Units of max distance",
            name="max_distance_units",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param_max_dist_units.filter.list = ["Meters", "Kilometers", "Feet", "Yards", "Miles"]

        param_username = arcpy.Parameter(
            displayName="username",
            name="username",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")

        param_password = arcpy.Parameter(
            displayName="password",
            name="password",
            datatype="GPStringHidden",
            parameterType="Optional",
            direction="Input")
        
        params = [make_parameter(param_output_feature_class),
                    make_parameter(param_SQLDbase),
                    make_parameter(param_points_to_analyze),
                    make_parameter(param_points_UniqueID),
                    make_parameter(param_day), 
                    make_parameter(param_time_window_start), 
                    make_parameter(param_time_window_end),
                    param_max_dist,
                    param_max_dist_units,
                    make_parameter(param_depOrArr),
                    param_username,
                    param_password]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        param_fc = parameters[2]
        param_UID = parameters[3]
        ToolValidator.populate_UniqueID(param_fc, param_UID)

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        param_fc = parameters[0]
        param_SQLDbase = parameters[1]
        param_day = parameters[4]
        start_time = parameters[5]
        end_time = parameters[6]

        ToolValidator.check_SQLDBase(param_SQLDbase, param_SQLDbase.valueAsText, ["stops", "trips", "stop_times"], ["calendar", "calendar_dates"], param_day)
        ToolValidator.forbid_shapefile(param_fc)
        ToolValidator.allow_YYYYMMDD_day(param_day, param_SQLDbase.valueAsText)
        ToolValidator.check_time_window(start_time, end_time)

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import BBB_CountTripsAtPoints_Online
        outFile = parameters[0].valueAsText
        SQLDbase = parameters[1].valueAsText
        inPointsLayer = parameters[2].valueAsText
        inLocUniqueID = parameters[3].valueAsText
        day = parameters[4].valueAsText
        start_time = parameters[5].valueAsText
        end_time = parameters[6].valueAsText
        BufferSize = parameters[7].value
        BufferUnits = parameters[8].valueAsText
        DepOrArrChoice = parameters[9].valueAsText
        username = parameters[10].valueAsText
        password = parameters[11].valueAsText
        BBB_CountTripsAtPoints_Online.runTool(outFile, SQLDbase, inPointsLayer, inLocUniqueID, day, start_time, end_time, 
            BufferSize, BufferUnits, DepOrArrChoice, username, password)
        return
#endregion


#region BBBPolygons_PreprocessBuffers
class BBBPolygons_PreprocessBuffers(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Step 1 - Preprocess Buffers"
        self.description = '''The Count Trips in Polygon Buffers around Stops tool \
generates polygon service areas around the stops in your transit system and counts the \
number of transit trips available in those areas during a time window. The output is a \
transit coverage map that can be color-coded by the number of available trips.

Step 1 takes care of several time-intensive processes and produces some output files that \
are referenced by Step 2.  Step 1 only needs to be run once for a given geography and \
buffer size.  You can vary the days of the week and time window in Step 2, and you will \
save time by not having to re-run the Step 1 processes each time.'''
        self.canRunInBackground = True
        self.category = "Count Trips in Polygon Buffers around Stops"

    def getParameterInfo(self):
        """Define parameter definitions"""
        
        param_output_directory = arcpy.Parameter(
            displayName="Output directory",
            name="output_directory",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input")

        param_out_gdb_name = arcpy.Parameter(
            displayName="Name for output geodatabase (created when the tool is run)",
            name="out_gdb_name",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        param_derived_outStops = arcpy.Parameter(
            displayName="",
            name="outStops",
            datatype="DEFeatureClass",
            parameterType="Derived",
            direction="Output")
        
        param_derived_outFlatPolys = arcpy.Parameter(
            displayName="",
            name="outFlatPolys",
            datatype="DEFeatureClass",
            parameterType="Derived",
            direction="Output")
        
        param_derived_outSQL = arcpy.Parameter(
            displayName="",
            name="outSQL",
            datatype="DEFile",
            parameterType="Derived",
            direction="Output")

        params = [param_output_directory,
                    param_out_gdb_name,
                    make_parameter(param_SQLDbase),
                    make_parameter(param_network_dataset),
                    make_parameter(param_impedance),
                    make_parameter(param_buffer_size),
                    make_parameter(param_restrictions),
                    make_parameter(param_polygon_trim),
                    param_derived_outStops,
                    param_derived_outFlatPolys,
                    param_derived_outSQL]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        param_ND = parameters[3]
        param_restr = parameters[6]
        param_imp = parameters[4]
        ToolValidator.populate_restrictions_and_impedances(param_ND, param_restr, param_imp)

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        
        param_outDir = parameters[0]
        param_outGDB = parameters[1]
        param_SQLDbase = parameters[2]
        param_ND = parameters[3]

        ToolValidator.check_out_gdb(param_outGDB, param_outDir)
        ToolValidator.check_SQLDBase(param_SQLDbase, param_SQLDbase.valueAsText, ["stops", "trips", "stop_times"], ["calendar", "calendar_dates"])
        ToolValidator.check_ND_not_from_AddGTFS(param_ND)

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import BBB_Polygons_Step1
        outDir = parameters[0].valueAsText
        outGDB = parameters[1].valueAsText
        inSQLDbase = parameters[2].valueAsText
        inNetworkDataset = parameters[3].value
        imp = parameters[4].valueAsText
        BufferSize = parameters[5].value
        restrictions = parameters[6].valueAsText
        TrimSettings = parameters[7].value
        BBB_Polygons_Step1.runTool(outDir, outGDB, inSQLDbase, inNetworkDataset, imp, BufferSize, restrictions, TrimSettings)
        return
#endregion


#region BBBPolygons_CountTripsInBuffers
class BBBPolygons_CountTripsInBuffers(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Step 2 - Count Trips in Buffers"
        self.description = '''The Count Trips in Polygon Buffers around Stops tool \
generates polygon service areas around the stops in your transit system and counts the \
number of transit trips available in those areas during a time window. The output is a \
transit coverage map that can be color-coded by the number of available trips.

Step 2 uses the template feature class created in Step 1 and counts the trips in a \
specific time window.'''
        self.canRunInBackground = True
        self.category = "Count Trips in Polygon Buffers around Stops"

    def getParameterInfo(self):
        """Define parameter definitions"""
        
        param_gdb = arcpy.Parameter(
            displayName="Step 1 results geodatabase",
            name="step1_gdb",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input")

        params = [param_gdb,
                    make_parameter(param_output_feature_class),
                    make_parameter(param_day), 
                    make_parameter(param_time_window_start), 
                    make_parameter(param_time_window_end),
                    make_parameter(param_depOrArr)]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        param_inStep1GDB = parameters[0]
        param_day = parameters[2]
        start_time = parameters[3]
        end_time = parameters[4]

        ToolValidator.check_Step1_gdb(param_inStep1GDB, param_day)

        SQLDbase = None
        if param_inStep1GDB.value and not param_inStep1GDB.hasError():
            SQLDbase = os.path.join(param_inStep1GDB.valueAsText, "Step1_GTFS.sql")
        ToolValidator.allow_YYYYMMDD_day(param_day, SQLDbase)

        ToolValidator.check_time_window(start_time, end_time)

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import BBB_Polygons_Step2
        inStep1GDB = parameters[0].valueAsText
        outFile = parameters[1].valueAsText
        day = parameters[2].valueAsText
        start_time = parameters[3].valueAsText
        end_time = parameters[4].valueAsText
        DepOrArrChoice = parameters[5].valueAsText
        BBB_Polygons_Step2.runTool(inStep1GDB, outFile, day, start_time, end_time, DepOrArrChoice)
        return
#endregion


#region BBBIndividualRoute_PreprocessRouteBuffers
class BBBIndividualRoute_PreprocessRouteBuffers(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Step 1 - Preprocess Route Buffers"
        self.description = '''TThe Count Trips for Individual Route tool allows you to \
examine individual routes in your system in detail. It generates a feature class of transit \
stops associated with the route you select as well as polygon service areas around the stops, \
and it calculates the number of visits, frequency, maximum wait time, and average headway for \
each stop during a time window.

Step 1 need only be run once for a given route and buffer size (eg. Route 10x and 0.25 miles).  \
Step 1 creates the stops and service area feature classes.'''
        self.canRunInBackground = True
        self.category = "Count Trips for Individual Route"

    def getParameterInfo(self):
        """Define parameter definitions"""
        
        param_output_gdb = arcpy.Parameter(
            displayName="Output geodatabase",
            name="output_gdb",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input")

        param_route = arcpy.Parameter(
            displayName="Transit route to analyze",
            name="route",
            datatype="GPString",
            parameterType="Required",
            direction="Input")

        param_derived_outFCs = arcpy.Parameter(
            displayName="",
            name="outFCs",
            datatype="DEFeatureClass",
            parameterType="Derived",
            direction="Output",
            multiValue=True)

        params = [param_output_gdb,
                    make_parameter(param_SQLDbase),
                    param_route,
                    make_parameter(param_network_dataset),
                    make_parameter(param_impedance),
                    make_parameter(param_buffer_size),
                    make_parameter(param_restrictions),
                    make_parameter(param_polygon_trim),
                    param_derived_outFCs]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        param_SQLDbase = parameters[1]
        param_route = parameters[2]
        param_ND = parameters[3]
        param_restr = parameters[6]
        param_imp = parameters[4]

        ToolValidator.populate_restrictions_and_impedances(param_ND, param_restr, param_imp)
        ToolValidator.populate_GTFS_routes(param_SQLDbase, param_route)

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        
        param_outGDB = parameters[0]
        param_SQLDbase = parameters[1]
        param_ND = parameters[3]

        ToolValidator.check_out_gdb_type_and_existence(param_outGDB)
        ToolValidator.check_SQLDBase(param_SQLDbase, param_SQLDbase.valueAsText, ["stops", "trips", "routes", "stop_times"], ["calendar", "calendar_dates"])
        ToolValidator.check_ND_not_from_AddGTFS(param_ND)

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import BBB_AnalyzeIndividualRoute_Step1
        outGDB = parameters[0].valueAsText
        SQLDbase = parameters[1].valueAsText
        RouteText = parameters[2].valueAsText
        inNetworkDataset = parameters[3].value
        imp = parameters[4].valueAsText
        BufferSize = parameters[5].value
        restrictions = parameters[6].valueAsText
        TrimSettings = parameters[7].value
        BBB_AnalyzeIndividualRoute_Step1.runTool(outGDB, SQLDbase, RouteText, inNetworkDataset, imp, BufferSize, restrictions, TrimSettings)
        return
#endregion


#region BBBIndividualRoute_CountTripsForRoute
class BBBIndividualRoute_CountTripsForRoute(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Step 2 - Count Trips for Route"
        self.description = '''The Count Trips in Polygon Buffers around Stops tool \
generates polygon service areas around the stops in your transit system and counts the \
number of transit trips available in those areas during a time window. The output is a \
transit coverage map that can be color-coded by the number of available trips.

Step 2 uses the template feature class created in Step 1 and counts the trips in a specific \
time window.'''
        self.canRunInBackground = True
        self.category = "Count Trips for Individual Route"

    def getParameterInfo(self):
        """Define parameter definitions"""
        
        param_input_feature_classes = arcpy.Parameter(
            displayName="Feature classes to analyze (created in Step 1)",
            name="input_feature_classes",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input",
            multiValue=True)

        param_derived_outFCs = arcpy.Parameter(
            displayName="",
            name="outFCs",
            datatype="DEFeatureClass",
            parameterType="Derived",
            direction="Output",
            multiValue=True)

        params = [param_input_feature_classes,
                    make_parameter(param_SQLDbase),
                    make_parameter(param_day), 
                    make_parameter(param_time_window_start), 
                    make_parameter(param_time_window_end),
                    make_parameter(param_depOrArr),
                    param_derived_outFCs]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        
        param_SQLDbase = parameters[1]
        param_day = parameters[2]
        start_time = parameters[3]
        end_time = parameters[4]

        ToolValidator.check_SQLDBase(param_SQLDbase, param_SQLDbase.valueAsText, ["stops", "trips", "routes", "stop_times"], ["calendar", "calendar_dates"], param_day)
        ToolValidator.allow_YYYYMMDD_day(param_day, param_SQLDbase.valueAsText)
        ToolValidator.check_time_window(start_time, end_time)

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import BBB_AnalyzeIndividualRoute_Step2
        FCs = parameters[0].valueAsText
        SQLDbase = parameters[1].valueAsText
        day = parameters[2].valueAsText
        start_time = parameters[3].valueAsText
        end_time = parameters[4].valueAsText
        DepOrArrChoice = parameters[5].valueAsText
        BBB_AnalyzeIndividualRoute_Step2.runTool(FCs, SQLDbase, day, start_time, end_time, DepOrArrChoice)
        return
#endregion


#region BBBLines_PreprocessLines
class BBBLines_PreprocessLines(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Step 1 - Preprocess Lines"
        self.description = '''The Count Trips on Lines tool counts the number of transit \
trips that travel along corridors between stops during a time window. The output is a lines \
feature class that can by symbolized to emphasize high-frequency corridors and connections. 

This pre-processing step generates a feature class of transit lines and updates a SQL database \
of transit schedules so that the frequency of transit service along the lines can be calculated. \
The counts are done in Step 2 for specific time windows. Step 1 need only be run once for a given \
transit system.'''
        self.canRunInBackground = True
        self.category = "Count Trips on Lines"

    def getParameterInfo(self):
        """Define parameter definitions"""
        
        param_output_FC = arcpy.Parameter(
            displayName="Output transit lines template feature class",
            name="output_template_feature_class",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")

        param_combine_routes = arcpy.Parameter(
            displayName="Combine routes along corridors",
            name="combine_routes",
            datatype="GPBoolean",
            parameterType="Required",
            direction="Input")
        param_combine_routes.value = True

        params = [param_output_FC,
                    make_parameter(param_SQLDbase),
                    param_combine_routes]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        
        param_linesFC = parameters[0]
        param_SQLDbase = parameters[1]

        ToolValidator.forbid_shapefile(param_linesFC)
        ToolValidator.check_SQLDBase(param_SQLDbase, param_SQLDbase.valueAsText, ["stops", "trips", "stop_times"], ["calendar", "calendar_dates"])

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import BBB_Lines_Step1
        outLinesFC = parameters[0].valueAsText
        SQLDbase = parameters[1].valueAsText
        combine_corridors = parameters[2].value
        BBB_Lines_Step1.runTool(outLinesFC, SQLDbase, combine_corridors)
        return
#endregion


#region BBBLines_CountTripsOnLines
class BBBLines_CountTripsOnLines(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Step 2 - Count Trips on Lines"
        self.description = '''The Count Trips in Polygon Buffers around Stops tool \
generates polygon service areas around the stops in your transit system and counts the \
number of transit trips available in those areas during a time window. The output is a \
transit coverage map that can be color-coded by the number of available trips.

Step 2 counts the number of transit trips that travel along corridors between stops \
during a time window. This step uses the output of Step 1 and counts the frequency of \
service during specific time windows.'''
        self.canRunInBackground = True
        self.category = "Count Trips on Lines"

    def getParameterInfo(self):
        """Define parameter definitions"""
        
        param_input_template_feature_class = arcpy.Parameter(
            displayName="Transit lines template (created in Step 1)",
            name="input_template_feature_class",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")

        params = [param_input_template_feature_class,
                    make_parameter(param_SQLDbase),
                    make_parameter(param_output_feature_class),
                    make_parameter(param_day), 
                    make_parameter(param_time_window_start), 
                    make_parameter(param_time_window_end)]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        
        param_SQLDbase = parameters[1]
        param_linesFC = parameters[2]
        param_day = parameters[3]
        start_time = parameters[4]
        end_time = parameters[5]

        msg = " Additionally, make sure you have run Step 1 of the %s tool." % self.category
        nonexist_msg = ToolValidator.sql_nonexist_msg + msg
        missing_tables_msg = ToolValidator.sql_missing_tables_msg + msg

        ToolValidator.check_SQLDBase(param_SQLDbase, param_SQLDbase.valueAsText, ["stops", "trips", "stop_times", "schedules"], 
                                    ["calendar", "calendar_dates"], param_day, nonexist_msg, missing_tables_msg)
        ToolValidator.forbid_shapefile(param_linesFC)
        ToolValidator.allow_YYYYMMDD_day(param_day, param_SQLDbase.valueAsText)
        ToolValidator.check_time_window(start_time, end_time)

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import BBB_Lines_Step2
        step1LinesFC = parameters[0].value
        SQLDbase = parameters[1].valueAsText
        linesFC = parameters[2].valueAsText
        day = parameters[3].valueAsText
        start_time = parameters[4].valueAsText
        end_time = parameters[5].valueAsText
        BBB_Lines_Step2.runTool(step1LinesFC, SQLDbase, linesFC, day, start_time, end_time)
        return
#endregion


#region CountHighFrequencyRoutesAtStops
class CountHighFrequencyRoutesAtStops(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Count High Frequency Routes at Stops"
        self.description = '''The Count High Frequency Routes at Stops tool counts the \
number of routes at each stop that meet a desired headway threshold. The output is a \
feature class of your GTFS stops with field indicating trip and headway statistics along \
with a count of the number of routes at the stop that has headways of a desired threshold \
or shorter.'''
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define parameter definitions"""

        param_headway_threshold = arcpy.Parameter(
            displayName="Headway Threshold",
            name="headway_threshold",
            datatype="GPDouble",
            parameterType="Required",
            direction="Input")

        param_snap_to_nearest_5_minutes = arcpy.Parameter(
            displayName="Snap to Nearest 5 Minutes",
            name="snap_to_nearest_5_minutes",
            datatype="GPBoolean",
            parameterType="Required",
            direction="Input")
        param_snap_to_nearest_5_minutes.value = True

        params = [make_parameter(param_output_feature_class),
                    make_parameter(param_SQLDbase),
                    make_parameter(param_day),
                    make_parameter(param_time_window_start), 
                    make_parameter(param_time_window_end),
                    make_parameter(param_depOrArr),
                    param_headway_threshold,
                    param_snap_to_nearest_5_minutes]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        param_SQLDbase = parameters[1]
        param_day = parameters[2]
        start_time = parameters[3]
        end_time = parameters[4]

        ToolValidator.check_SQLDBase(param_SQLDbase, param_SQLDbase.valueAsText, ["stops", "trips", "stop_times"], ["calendar", "calendar_dates"], param_day)
        ToolValidator.allow_YYYYMMDD_day(param_day, param_SQLDbase.valueAsText)
        ToolValidator.check_time_window(start_time, end_time)

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import BBB_CountHighFrequencyRoutesAtStops
        outStops = parameters[0].valueAsText
        SQLDbase = parameters[1].valueAsText
        day = parameters[2].valueAsText
        start_time = parameters[3].valueAsText
        end_time = parameters[4].valueAsText
        DepOrArrChoice = parameters[5].valueAsText
        FrequencyThreshold = float(parameters[6].value)
        SnapToNearest5MinuteBool = bool(parameters[7].value)
        BBB_CountHighFrequencyRoutesAtStops.runTool(outStops, SQLDbase, day, start_time, end_time, DepOrArrChoice, FrequencyThreshold, SnapToNearest5MinuteBool)
        return
#endregion


#region CountTripsAtStopsByRouteAndDirection
class CountTripsAtStopsByRouteAndDirection(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Count Trips at Stops by Route and Direction"
        self.description = ("The Count Trips at Stops by Route and Direction outputs a"
        "feature class where every GTFS stop is duplicated for every route-direction combination"
        "that uses that stop during the analysis time windows. Each point will represent a unique"
        "combination of stop id, route id, and direction id, and the frequency statistics that"
        "relate to each of them for the analyzed time window.") 
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define parameter definitions"""

        param_time_windows = arcpy.Parameter(
            displayName="Time Windows",
            name="Time_Windows",
            datatype="GPValueTable",
            parameterType="Required",
            direction="Input")
        param_time_windows.columns = [
            ['GPString', 'Weekday or YYYYMMDD Date'],
            ['GPString', 'Time Window Start'],
            ['GPString', 'Time Window End'],
            ['GPString', 'Count Arrivals Or Departures'],
            ['GPString', 'Output Field Prefix']
            ]
        param_time_windows.filters[0].type = 'ValueList'
        param_time_windows.filters[0].list = ToolValidator.days
        param_time_windows.filters[3].type = 'ValueList'
        param_time_windows.filters[3].list = ['Arrivals', 'Departures']
        param_time_windows.values = [['Monday', '00:00', '23:59', 'Departures', 'TW1']]

        param_snap_to_nearest_5_minutes = arcpy.Parameter(
            displayName="Round Headway to Nearest 5 Minutes",
            name="round_headway_to_nearest_5_minutes",
            datatype="GPBoolean",
            parameterType="Required",
            direction="Input")
        param_snap_to_nearest_5_minutes.value = True

        params = [
            make_parameter(param_output_feature_class),
            make_parameter(param_SQLDbase),
            param_time_windows,
            param_snap_to_nearest_5_minutes
            ]

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        param_fc = parameters[0]
        param_time_windows = parameters[2]

        if param_fc.valueAsText:
            out_gdb = os.path.dirname(param_fc.valueAsText)
            ToolValidator.clean_time_window_prefix_strings(param_time_windows, 4, out_gdb)

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        param_fc = parameters[0]
        param_SQLDbase = parameters[1]
        param_time_windows = parameters[2]

        ToolValidator.forbid_shapefile(param_fc)
        ToolValidator.check_SQLDBase(param_SQLDbase, param_SQLDbase.valueAsText, ["stops", "trips", "stop_times"], ["calendar", "calendar_dates"])
        ToolValidator.check_date_param_value_table(param_time_windows, 0, param_SQLDbase.valueAsText)
        ToolValidator.check_time_window_value_table(param_time_windows, 1, 2)
        ToolValidator.validate_time_window_prefix_strings(param_time_windows, 4)

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import BBB_CountTripsAtStopsByRouteAndDirection
        outStops = parameters[0].valueAsText
        SQLDbase = parameters[1].valueAsText
        time_window_value_table = parameters[2].values
        snap_to_nearest_5 = parameters[3].value
        BBB_CountTripsAtStopsByRouteAndDirection.runTool(
            outStops, SQLDbase, time_window_value_table, snap_to_nearest_5)
        return
#endregion


class CommonParameter(object):
    def __init__(self, displayName, name, datatype, parameterType, direction, multiValue=None, default_val=None, filter_list=None):
        self.parameter_def = {"displayName": displayName,
                                "name": name,
                                "datatype": datatype,
                                "parameterType": parameterType,
                                "direction": direction,
                                "multiValue": multiValue}
        self.default_val = default_val
        self.filter_list = filter_list

def make_parameter(common_param):
    param = arcpy.Parameter(**common_param.parameter_def)
    if common_param.default_val:
        param.value = common_param.default_val
    if common_param.filter_list:
        param.filter.list = common_param.filter_list
    return param

#region parameters

param_output_feature_class = CommonParameter(
    "Output feature class",
    "output_feature_class",
    "DEFeatureClass",
    "Required",
    "Output")

param_SQLDbase = CommonParameter(
    "SQL database of preprocessed GTFS data",
    "sql_database",
    "DEFile",
    "Required",
    "Input",
    filter_list=["sql"])

param_day = CommonParameter(
    "Weekday or YYYYMMDD date",
    "day",
    "GPString",
    "Required",
    "Input",
    default_val="Monday")

param_time_window_start = CommonParameter(
    "Time window start (HH:MM) (24 hour time)",
    "time_window_start",
    "GPString",
    "Required",
    "Input",
    default_val="00:00")

param_time_window_end = CommonParameter(
    "Time window end (HH:MM) (24 hour time)",
    "time_window_end",
    "GPString",
    "Required",
    "Input",
    default_val="23:59")

param_depOrArr = CommonParameter(
    "Count arrivals or departures",
    "count_arrivals_or_departures",
    "GPString",
    "Required",
    "Input",
    default_val="Departures",
    filter_list=["Departures", "Arrivals"])

param_points_to_analyze = CommonParameter(
    "Points to Analyze",
    "points_to_analyze",
    "GPFeatureLayer",
    "Required",
    "Input")

param_points_UniqueID = CommonParameter(
    "Unique ID field for Points to Analyze",
    "points_unique_id",
    "GPString",
    "Required",
    "Input")

param_network_dataset = CommonParameter(
    "Network dataset",
    "network_dataset",
    "GPNetworkDatasetLayer",
    "Required",
    "Input")

param_impedance = CommonParameter(
    "Impedance attribute (Choose one that works for pedestrians.)",
    "impedance",
    "GPString",
    "Required",
    "Input")

param_restrictions = CommonParameter(
    "Network restrictions (Choose ones appropriate for pedestrians.)",
    "restrictions",
    "GPString",
    "Optional",
    "Input",
    True)

param_buffer_size = CommonParameter(
    "Buffer size (in the same units as your impedance attribute)",
    "buffer_size",
    "GPDouble",
    "Required",
    "Input")

param_polygon_trim = CommonParameter(
    "Polygon trim (in meters) (Enter -1 for no trim.)",
    "polygon_trim",
    "GPDouble",
    "Optional",
    "Input",
    default_val=20)

#endregion
