############################################################################
## Tool name: Transit Network Analysis Tools
## Created by: Melinda Morang, Esri
## Last updated: 7 June 2021
############################################################################
''' Python toolbox that defines all the tools in the Transit Network Analysis Tools tool
suite.'''
################################################################################
'''Copyright 2021 Esri
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

import os
import arcpy
import ToolValidator
from AnalysisHelpers import isPy3, TIME_UNITS, MAX_AGOL_PROCESSES, is_nds_service


class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "Transit Network Analysis Tools"
        self.alias = "TransitNetworkAnalysisTools"

        # List of tool classes associated with this toolbox
        cam_tool = CalculateAccessibilityMatrixPro if isPy3 else CalculateAccessibilityMatrix
        self.tools = [
            PrepareTimeLapsePolygons,
            cam_tool,
            CalculateTravelTimeStatistics,
            CreatePercentAccessPolygons
        ]


class PrepareTimeLapsePolygons(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Prepare Time Lapse Polygons"
        self.description = (
            "Run a Service Area analysis incrementing the time of day. ",
            "Save the polygons to a feature class that can be used to generate a time lapse video."
        )
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define parameter definitions"""

        params = [

            arcpy.Parameter(
                displayName="Service Area Layer",
                name="Service_Area_Layer",
                datatype="GPNALayer",
                parameterType="Required",
                direction="Input"),

            arcpy.Parameter(
                displayName="Output Polygons Feature Class",
                name="Output_Polygons_Feature_Class",
                datatype="DEFeatureClass",
                parameterType="Required",
                direction="Output"),

            make_parameter(param_startday),
            make_parameter(param_starttime),
            make_parameter(param_endday),
            make_parameter(param_endtime),
            make_parameter(param_timeinc)
        ]

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        if not arcpy.CheckExtension("network"):
            return False
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        start_day = parameters[2]
        end_day = parameters[4]
        start_time = parameters[3]
        end_time = parameters[5]
        increment = parameters[6]

        # Show a filter list of weekdays but also allow YYYYMMDD dates
        ToolValidator.allow_YYYYMMDD_day(start_day)
        ToolValidator.validate_day(end_day)

        ToolValidator.set_end_day(start_day, end_day)

        # Make sure time of day format is correct and time window is valid
        ToolValidator.check_time_window(start_time, end_time, start_day, end_day)

        # Make sure time increment is good
        ToolValidator.validate_time_increment(increment)

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import CreateTimeLapsePolygons
        SAlayer = parameters[0].value
        outfc = parameters[1].valueAsText
        start_day = parameters[2].valueAsText
        start_time = parameters[3].valueAsText
        end_day = parameters[4].valueAsText
        end_time = parameters[5].valueAsText
        increment = parameters[6].value

        # For some reason there are problems passing layer objects through in ArcMap when the input is a map layer,
        # so create a fresh layer object from it.
        if not ToolValidator.ispy3:
            if not isinstance(SAlayer, (unicode, str)):
                SAlayer = arcpy.mapping.Layer(SAlayer.name)

        CreateTimeLapsePolygons.runTool(
            SAlayer,
            outfc,
            start_day,
            start_time,
            end_day,
            end_time,
            increment
            )
        return


class CreatePercentAccessPolygons(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Create Percent Access Polygons"
        self.description = (
            "This script will compute the percentage of times an isochrone represents an areas transit access based ",
            "on the union of time lapsed polygons. It will provide a polyon representation of transit's range of ",
            "access that can be used for weighted accessibiilty calculations."
        )
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define parameter definitions"""

        params = [

            arcpy.Parameter(
                displayName="Input time lapse polygons feature class",
                name="Input_time_lapse_polygons_feature_class",
                datatype="GPFeatureLayer",
                parameterType="Required",
                direction="Input"),

            arcpy.Parameter(
                displayName="Output percent access polygons feature class",
                name="Output_percent_access_polygons_feature_class",
                datatype="DEFeatureClass",
                parameterType="Required",
                direction="Output"),

            arcpy.Parameter(
                displayName="Cell size",
                name="Cell_size",
                datatype="GPDouble",
                parameterType="Required",
                direction="Input"),

            arcpy.Parameter(
                displayName="Cell size units",
                name="Cells_size_units",
                datatype="GPString",
                parameterType="Optional",
                direction="Input"),

            arcpy.Parameter(
                displayName="Output threshold percentage feature class",
                name="Output_threshold_percentage_feature_class",
                datatype="DEFeatureClass",
                parameterType="Optional",
                direction="Output"),

            arcpy.Parameter(
                displayName="Percentage thresholds",
                name="Percentage_thresholds",
                datatype="GPDouble",
                parameterType="Optional",
                direction="Input",
                multiValue=True)
        ]

        params[0].filter.list = ["Polygon"]
        params[1].symbology = os.path.join(os.path.dirname(__file__), 'Symbology_Cells.lyr')
        params[2].value = 100
        params[3].enabled = False
        params[5].filter.type = "Range"
        params[5].filter.list = [0, 100]

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        if not arcpy.CheckExtension("network"):
            return False
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        param_in_time_lapse_polys = parameters[0]
        param_cell_size_units = parameters[3]
        param_fc2 = parameters[4]
        param_percents = parameters[5]

        if param_in_time_lapse_polys.altered and param_in_time_lapse_polys.value:
            in_polys = param_in_time_lapse_polys.valueAsText
            if arcpy.Exists(in_polys):
                SR = arcpy.Describe(in_polys).spatialReference
                # Populate the cell size units box with the linear units of the spatial reference
                param_cell_size_units.value = SR.linearUnitName

        # Disable the percent list if no output feature class has been selected
        if param_fc2.value:
            param_percents.enabled = True
        else:
            param_percents.enabled = False

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""

        param_in_time_lapse_polys = parameters[0]
        param_cell_size = parameters[2]
        param_cell_size_units = parameters[3]
        param_fc2 = parameters[4]
        param_percents = parameters[5]
        required_input_fields = set(["FacilityID", "Name", "FromBreak", "ToBreak", "TimeOfDay"])
        unit_limits = {
            "Meter": 5,
            "Foot": 16.4,
            "Foot_US": 16.4
        }

        # Make sure the input time lapse polygons are projected and have the correct fields
        if param_in_time_lapse_polys.altered and param_in_time_lapse_polys.value:
            in_polys = param_in_time_lapse_polys.valueAsText
            if arcpy.Exists(in_polys):
                desc = arcpy.Describe(in_polys)
                SR = desc.spatialReference
                if SR.type != "Projected":
                    param_in_time_lapse_polys.setErrorMessage(
                        "Input time lapse polygons must be in a projected coordinate system."
                        )
                fields = set([f.name for f in desc.fields])
                if not required_input_fields.issubset(fields):
                    param_in_time_lapse_polys.setErrorMessage(
                        "Input time lapse polygons are missing one or more required fields. Required: " + \
                        str(required_input_fields)
                        )

        # Make sure the cell size is reasonable
        if param_cell_size.altered and param_cell_size_units.value in unit_limits:
            if float(param_cell_size.value) < unit_limits[param_cell_size_units.value]:
                param_cell_size.setWarningMessage(
                    "Your chosen cell size is very small. The tool may run slowly or run out of memory."
                )

        if param_fc2.value and not param_percents.value:
            param_percents.setWarningMessage(
                    "You designated an output threshold percentage feature class but did not set any percentage " +
                    "thresholds. No output threshold percentage feature class will be created."
                )

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import CreatePercentAccessPolygon
        in_time_lapse_polys = parameters[0].value
        outfc = parameters[1].valueAsText
        cell_size = parameters[2].value
        fc2 = parameters[4].valueAsText
        percents = parameters[5].values

        CreatePercentAccessPolygon.main(
            in_time_lapse_polys,
            outfc,
            cell_size,
            fc2,
            percents
            )
        return


class CalculateTravelTimeStatistics(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Calculate Travel Time Statistics"
        self.description = (
            "Solve an OD Cost Matrix or Route iteratively over a time window and output a table of statistics ",
            "describing the travel time over the time window for each origin-destination pair or route:",
            "- minimum travel time",
            "- maximum travel time",
            "- mean travel time"
            "- number of times the origin-destination pair or route was considered"
        )
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define parameter definitions"""

        params = [

            arcpy.Parameter(
                displayName="Input Network Analyst Layer",
                name="Input_Network_Analyst_Layer",
                datatype="GPNALayer",
                parameterType="Required",
                direction="Input"),

            arcpy.Parameter(
                displayName="Output table",
                name="Output_table",
                datatype="DETable",
                parameterType="Required",
                direction="Output"),

            make_parameter(param_startday),
            make_parameter(param_starttime),
            make_parameter(param_endday),
            make_parameter(param_endtime),
            make_parameter(param_timeinc),

            make_parameter(CommonParameter(
                "Save combined network analysis results",
                "Save_combined_network_analysis_results",
                "GPBoolean",
                "Optional",
                "Input",
                default_val=False
                )),

            arcpy.Parameter(
                displayName="Output combined network analysis results",
                name="Output_combined_network_analysis_results",
                datatype="DEFeatureClass",
                parameterType="Optional",
                direction="Output")
        ]

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        if not arcpy.CheckExtension("network"):
            return False
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""

        param_saveCombined = parameters[7]
        param_combinedOutFC = parameters[8]

        # Disable output combined fc parameter if the user doesn't plan to generate it
        if not param_saveCombined.value:
            param_combinedOutFC.enabled = False
        else:
            param_combinedOutFC.enabled = True

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        out_table = parameters[1]
        start_day = parameters[2]
        end_day = parameters[4]
        start_time = parameters[3]
        end_time = parameters[5]
        increment = parameters[6]
        combinedOutFC = parameters[8]

        ToolValidator.validate_output_is_gdb(out_table)
        ToolValidator.validate_output_is_gdb(combinedOutFC)

        # Show a filter list of weekdays but also allow YYYYMMDD dates
        ToolValidator.allow_YYYYMMDD_day(start_day)
        ToolValidator.validate_day(end_day)

        ToolValidator.set_end_day(start_day, end_day)

        # Make sure time of day format is correct and time window is valid
        ToolValidator.check_time_window(start_time, end_time, start_day, end_day)

        # Make sure time increment is good
        ToolValidator.validate_time_increment(increment)

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import CalculateTravelTimeStats
        NAlayer = parameters[0].value
        out_table = parameters[1].valueAsText
        start_day = parameters[2].valueAsText
        start_time = parameters[3].valueAsText
        end_day = parameters[4].valueAsText
        end_time = parameters[5].valueAsText
        increment = parameters[6].value
        saveCombined = parameters[7].value
        combinedOutFC = parameters[8].valueAsText

        # For some reason there are problems passing layer objects through in ArcMap when the input is a map layer,
        # so create a fresh layer object from it.
        if not ToolValidator.ispy3:
            if not isinstance(NAlayer, (unicode, str)):
                NAlayer = arcpy.mapping.Layer(NAlayer.name)

        CalculateTravelTimeStats.runTool(
            NAlayer,
            out_table,
            start_day,
            start_time,
            end_day,
            end_time,
            increment,
            saveCombined,
            combinedOutFC
            )
        return


class CalculateAccessibilityMatrix(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Calculate Accessibility Matrix"
        self.description = (
            "Count the number of destinations reachable from each origin by transit and walking. The tool calculates ",
            "an Origin-Destination Cost Matrix for each start time within a time window because the reachable ",
            "destinations change depending on the time of day because of the transit schedules. The output gives the ",
            "total number of destinations reachable at least once as well as the number of destinations reachable at ",
            "least 10%, 20%, ...90% of start times during the time window. The number of reachable destinations can ",
            "be weighted based on a field, such as the number of jobs available at each destination. The tool also ",
            "calculates the percentage of total destinations reachable. (ArcMap layer-based version.)"
        )
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define parameter definitions"""

        params = [

            arcpy.Parameter(
                displayName="OD Cost Matrix Layer",
                name="OD_Cost_Matrix_Layer",
                datatype="GPNALayer",
                parameterType="Required",
                direction="Input"),

            arcpy.Parameter(
                displayName="Origins",
                name="Origins",
                datatype="GPFeatureLayer",
                parameterType="Required",
                direction="Input"),

            arcpy.Parameter(
                displayName="Destinations",
                name="Destinations",
                datatype="GPFeatureLayer",
                parameterType="Required",
                direction="Input"),

            arcpy.Parameter(
                displayName="Destinations Weight Field",
                name="Destinations_Weight_Field",
                datatype="Field",
                parameterType="Optional",
                direction="Input"),

            make_parameter(param_startday),
            make_parameter(param_starttime),
            make_parameter(param_endday),
            make_parameter(param_endtime),
            make_parameter(param_timeinc)
        ]

        params[1].filter.list = ["Point"]
        params[2].filter.list = ["Point"]
        params[3].filter.list = ["Short", "Long", "Double"]
        params[3].parameterDependencies = [params[2].name]

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        if not arcpy.CheckExtension("network"):
            return False
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        start_day = parameters[4]
        end_day = parameters[6]
        start_time = parameters[5]
        end_time = parameters[7]
        increment = parameters[8]

        # Show a filter list of weekdays but also allow YYYYMMDD dates
        ToolValidator.allow_YYYYMMDD_day(start_day)
        ToolValidator.validate_day(end_day)

        ToolValidator.set_end_day(start_day, end_day)

        # Make sure time of day format is correct and time window is valid
        ToolValidator.check_time_window(start_time, end_time, start_day, end_day)

        # Make sure time increment is good
        ToolValidator.validate_time_increment(increment)

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import CalculateAccessibility
        NALayer = parameters[0].value
        origins = parameters[1].value
        destinations = parameters[2].value
        weight_field = parameters[3].valueAsText
        start_day = parameters[4].valueAsText
        start_time = parameters[5].valueAsText
        end_day = parameters[6].valueAsText
        end_time = parameters[7].valueAsText
        increment = parameters[8].value

        # For some reason there are problems passing layer objects through in ArcMap when the input is a map layer,
        # so create a fresh layer object from it.
        if not ToolValidator.ispy3:
            if not isinstance(NALayer, (unicode, str)):
                NALayer = arcpy.mapping.Layer(NALayer.name)

        CalculateAccessibility.runTool(
            NALayer,
            origins,
            destinations,
            weight_field,
            start_day,
            start_time,
            end_day,
            end_time,
            increment
            )
        return


class CalculateAccessibilityMatrixPro(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Calculate Accessibility Matrix"
        self.description = (
            "Count the number of destinations reachable from each origin by transit and walking. The tool calculates ",
            "an Origin-Destination Cost Matrix for each start time within a time window because the reachable ",
            "destinations change depending on the time of day because of the transit schedules. The output gives the ",
            "total number of destinations reachable at least once as well as the number of destinations reachable at ",
            "least 10%, 20%, ...90% of start times during the time window. The number of reachable destinations can ",
            "be weighted based on a field, such as the number of jobs available at each destination. The tool also ",
            "calculates the percentage of total destinations reachable. (ArcGIS Pro version with parallelized solves.)"
        )
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define parameter definitions"""

        params = [

            arcpy.Parameter(
                displayName="Origins",
                name="Origins",
                datatype="GPFeatureLayer",
                parameterType="Required",
                direction="Input"),

            arcpy.Parameter(
                displayName="Destinations",
                name="Destinations",
                datatype="GPFeatureLayer",
                parameterType="Required",
                direction="Input"),

            arcpy.Parameter(
                displayName="Destinations Weight Field",
                name="Destinations_Weight_Field",
                datatype="Field",
                parameterType="Optional",
                direction="Input"),

            arcpy.Parameter(
                displayName="Network Data Source",
                name="Network_Data_Source",
                datatype="GPNetworkDataSource",
                parameterType="Required",
                direction="Input"
            ),

            arcpy.Parameter(
                displayName="Travel Mode",
                name="Travel_Mode",
                datatype="NetworkTravelMode",
                parameterType="Required",
                direction="Input"
            ),

            arcpy.Parameter(
                displayName="Output Updated Origins",
                name="Output_Updated_Origins",
                datatype="DEFeatureClass",
                parameterType="Required",
                direction="Output"
            ),

            arcpy.Parameter(
                displayName="Cutoff Time",
                name="Cutoff_Time",
                datatype="GPDouble",
                parameterType="Required",
                direction="Input"
            ),

            arcpy.Parameter(
                displayName="Cutoff Time Units",
                name="Cutoff_Time_Units",
                datatype="GPString",
                parameterType="Required",
                direction="Input"
            ),

            make_parameter(param_startday),
            make_parameter(param_starttime),
            make_parameter(param_endday),
            make_parameter(param_endtime),
            make_parameter(param_timeinc),

            arcpy.Parameter(
                displayName="Maximum Origins and Destinations per Chunk",
                name="Max_Inputs_Per_Chunk",
                datatype="GPLong",
                parameterType="Required",
                direction="Input"
            ),

            arcpy.Parameter(
                displayName="Maximum Number of Parallel Processes",
                name="Max_Processes",
                datatype="GPLong",
                parameterType="Required",
                direction="Input"
            ),

            arcpy.Parameter(
                displayName="Barriers",
                name="Barriers",
                datatype="GPFeatureLayer",
                parameterType="Optional",
                direction="Input",
                multiValue=True,
                category="Advanced"
            ),

            arcpy.Parameter(
                displayName="Precalculate Network Locations",
                name="Precalculate_Network_Locations",
                datatype="GPBoolean",
                parameterType="Optional",
                direction="Input",
                category="Advanced"
            )

        ]

        params[0].filter.list = ["Point"]
        params[1].filter.list = ["Point"]
        params[2].filter.list = ["Short", "Long", "Double"]
        params[2].parameterDependencies = [params[1].name]
        params[4].parameterDependencies = [params[3].name]
        params[7].filter.list = TIME_UNITS
        params[7].value = "Minutes"
        params[13].value = 1000  # chunk size
        params[14].value = 4  # number of processes
        params[16].value = True  # precalculate locations

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        param_network = parameters[3]
        param_precalculate = parameters[16]

        # Turn off and hide Precalculate Network Locations parameter if the network data source is a service
        if param_network.altered and param_network.value:
            if is_nds_service(param_network.valueAsText):
                param_precalculate.value = False
                param_precalculate.enabled = False
            else:
                param_precalculate.enabled = True
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        start_day = parameters[8]
        end_day = parameters[10]
        start_time = parameters[9]
        end_time = parameters[11]
        increment = parameters[12]
        param_network = parameters[3]
        param_max_processes = parameters[14]

        # Show a filter list of weekdays but also allow YYYYMMDD dates
        ToolValidator.allow_YYYYMMDD_day(start_day)
        ToolValidator.validate_day(end_day)

        ToolValidator.set_end_day(start_day, end_day)

        # Make sure time of day format is correct and time window is valid
        ToolValidator.check_time_window(start_time, end_time, start_day, end_day)

        # Make sure time increment is good
        ToolValidator.validate_time_increment(increment)

        # If the network data source is arcgis.com, cap max processes
        if param_max_processes.altered and param_max_processes.value and \
                param_network.altered and param_network.value:
            if "arcgis.com" in param_network.valueAsText and param_max_processes.value > MAX_AGOL_PROCESSES:
                param_max_processes.setErrorMessage((
                    f"The maximum number of parallel processes cannot exceed {MAX_AGOL_PROCESSES} when the "
                    "ArcGIS Online services are used as the network data source."
                ))

        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        import CalculateAccessibilityMatrixInParallel
        od_solver = CalculateAccessibilityMatrixInParallel.ODCostMatrixSolver(**{
            "origins": parameters[0].value,
            "destinations": parameters[1].value,
            "weight_field": parameters[2].valueAsText if parameters[2].value else None,
            "network_data_source": parameters[3].value,
            "travel_mode": parameters[4].value,
            "output_origins": parameters[5].valueAsText,
            "cutoff": parameters[6].value,
            "time_units": parameters[7].valueAsText,
            "time_window_start_day": parameters[8].valueAsText,
            "time_window_start_time": parameters[9].valueAsText,
            "time_window_end_day": parameters[10].valueAsText,
            "time_window_end_time": parameters[11].valueAsText,
            "time_increment": parameters[12].value,
            "chunk_size": parameters[13].value,
            "max_processes": parameters[14].value,
            "barriers": parameters[15].values if parameters[15].values else None,
            "precalculate_network_locations": parameters[16].value
        })
        od_solver.solve_large_od_cost_matrix()
        return

# region parameters

class CommonParameter(object):
    """Class for defining shared parameters across tools."""

    def __init__(self, displayName, name, datatype, parameterType, direction, multiValue=None, default_val=None,
                 filter_list=None):
        self.parameter_def = {
            "displayName": displayName,
            "name": name,
            "datatype": datatype,
            "parameterType": parameterType,
            "direction": direction,
            "multiValue": multiValue
            }
        self.default_val = default_val
        self.filter_list = filter_list

def make_parameter(common_param):
    """Construct a parameter for use in a tool."""
    param = arcpy.Parameter(**common_param.parameter_def)
    if common_param.default_val:
        param.value = common_param.default_val
    if common_param.filter_list:
        param.filter.list = common_param.filter_list
    return param

param_startday = CommonParameter(
    "Start Day (Weekday or YYYYMMDD date)",
    "Start_Day__Weekday_or_YYYYMMDD_date_",
    "GPString",
    "Required",
    "Input",
    default_val="Wednesday")

param_endday = CommonParameter(
    "End Day (Weekday or YYYYMMDD date)",
    "End_Day__Weekday_or_YYYYMMDD_date_",
    "GPString",
    "Required",
    "Input",
    default_val="Wednesday")

param_starttime = CommonParameter(
    "Start Time (HH:MM) (24 hour time)",
    "Start_Time__HH_MM___24_hour_time_",
    "GPString",
    "Required",
    "Input",
    default_val="08:00")

param_endtime = CommonParameter(
    "End Time (HH:MM) (24 hour time)",
    "End_Time__HH_MM___24_hour_time_",
    "GPString",
    "Required",
    "Input",
    default_val="09:00")

param_timeinc = CommonParameter(
    "Time Increment (minutes)",
    "Time_Increment__minutes_",
    "GPLong",
    "Required",
    "Input",
    default_val="1")

# endregion parameters
