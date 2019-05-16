############################################################################
## Tool name: Transit Network Analysis Tools
## Created by: Melinda Morang, Esri
## Last updated: 16 May 2019
############################################################################
''' Python toolbox that defines all the tools in the Transit Network Analysis Tools tool
suite.'''
################################################################################
'''Copyright 2019 Esri
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
import ToolValidator


class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "Transit Network Analysis Tools"
        self.alias = "TransitNetworkAnalysisTools"

        # List of tool classes associated with this toolbox
        self.tools = [
            PrepareTimeLapsePolygons,
            # CalculateAccessibilityMatrix,
            # CalculateTravelTimeStatistics,
            # CreatePercentAccessPolygons
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