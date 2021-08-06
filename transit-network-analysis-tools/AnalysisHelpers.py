################################################################################
## Toolbox: Transit Network Analysis Tools
## Created by: Melinda Morang, Esri
## Last updated: 23 July 2021
################################################################################
'''Helper methods for analysis tools.'''
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

import sys
import datetime
import arcpy

# Determine if this is python 3 (which means probably ArcGIS Pro)
isPy3 = sys.version_info > (3, 0)

# Set some shared global variables that can be referenced from the other scripts
MSG_STR_SPLITTER = " | "
TIME_UNITS = ["Days", "Hours", "Minutes", "Seconds"]
MAX_AGOL_PROCESSES = 4  # AGOL concurrent processes are limited so as not to overload the service for other users.
TIME_FIELD = "TimeOfDay"  # Used for the output of Prepare Time Lapse Polygons
# Create Percent Access Polygons: Field names that must be in the input time lapse polygons
FACILITY_ID_FIELD = "FacilityID"
NAME_FIELD = "Name"
FROM_BREAK_FIELD = "FromBreak"
TO_BREAK_FIELD = "ToBreak"
FIELDS_TO_PRESERVE = [FACILITY_ID_FIELD, NAME_FIELD, FROM_BREAK_FIELD, TO_BREAK_FIELD]

def validate_input_feature_class(feature_class):
    """Validate that the designated input feature class exists and is not empty.

    Args:
        feature_class (str, layer): Input feature class or layer to validate

    Raises:
        ValueError: The input feature class does not exist.
        ValueError: The input feature class has no rows.
    """
    if not arcpy.Exists(feature_class):
        err = "Input dataset %s does not exist." % feature_class
        arcpy.AddError(err)
        raise ValueError(err)
    if int(arcpy.management.GetCount(feature_class).getOutput(0)) <= 0:
        err = "Input dataset %s has no rows." % feature_class
        arcpy.AddError(err)
        raise ValueError(err)


def is_nds_service(network_data_source):
    """Determine if the network data source points to a service.

    Args:
        network_data_source (network data source): Network data source to check.

    Returns:
        bool: True if the network data source is a service URL. False otherwise.
    """
    if isinstance(network_data_source, str) and network_data_source.startswith("http"):
        return True
    return False


def convert_time_units_str_to_enum(time_units):
    """Convert a string representation of time units to an arcpy.nax enum.

    Raises:
        ValueError: If the string cannot be parsed as a valid arcpy.nax.TimeUnits enum value.
    """
    if time_units.lower() == "minutes":
        return arcpy.nax.TimeUnits.Minutes
    if time_units.lower() == "seconds":
        return arcpy.nax.TimeUnits.Seconds
    if time_units.lower() == "hours":
        return arcpy.nax.TimeUnits.Hours
    if time_units.lower() == "days":
        return arcpy.nax.TimeUnits.Days
    # If we got to this point, the input time units were invalid.
    err = "Invalid time units: " + str(time_units)
    arcpy.AddError(err)
    raise ValueError(err)


def convert_travel_direction_str_to_enum(travel_direction):
    """Convert a string representation of travel direction to an arcpy.nax enum.

    Raises:
        ValueError: If the string cannot be parsed as a valid arcpy.nax.TravelDirection enum value.
    """
    if travel_direction.lower() == "toward facilities":
        return arcpy.nax.TravelDirection.ToFacility
    if travel_direction.lower() == "away from facilities":
        return arcpy.nax.TravelDirection.FromFacility
    # If we got to this point, the input was invalid.
    err = "Invalid travel direction: " + str(travel_direction)
    arcpy.AddError(err)
    raise ValueError(err)


def convert_geometry_at_cutoff_str_to_enum(geometry_at_cutoff):
    """Convert a string representation of geometry at cutoff to an arcpy.nax enum.

    Raises:
        ValueError: If the string cannot be parsed as a valid arcpy.nax.ServiceAreaPolygonCutoffGeometry enum value.
    """
    if geometry_at_cutoff.lower() == "rings":
        return arcpy.nax.ServiceAreaPolygonCutoffGeometry.Rings
    if geometry_at_cutoff.lower() == "disks":
        return arcpy.nax.ServiceAreaPolygonCutoffGeometry.Disks
    # If we got to this point, the input was invalid.
    err = "Invalid geometry at cutoff: " + str(geometry_at_cutoff)
    arcpy.AddError(err)
    raise ValueError(err)


def convert_geometry_at_overlap_str_to_enum(geometry_at_overlap):
    """Convert a string representation of geometry at cutoff to an arcpy.nax enum.

    Raises:
        ValueError: If the string cannot be parsed as a valid arcpy.nax.ServiceAreaOverlapGeometry enum value.
    """
    if geometry_at_overlap.lower() == "overlap":
        return arcpy.nax.ServiceAreaOverlapGeometry.Overlap
    if geometry_at_overlap.lower() == "dissolve":
        return arcpy.nax.ServiceAreaOverlapGeometry.Dissolve
    if geometry_at_overlap.lower() == "split":
        return arcpy.nax.ServiceAreaOverlapGeometry.Split
    # If we got to this point, the input was invalid.
    err = "Invalid geometry at overlap: " + str(geometry_at_overlap)
    arcpy.AddError(err)
    raise ValueError(err)


def parse_std_and_write_to_gp_ui(msg_string):
    """Parse a message string returned from the subprocess's stdout and write it to the GP UI according to type.

    Logged messages in the ParallelODCM module start with a level indicator that allows us to parse them and write them
    as errors, warnings, or info messages.  Example: "ERROR | Something terrible happened" is an error message.

    Args:
        msg_string (str): Message string (already decoded) returned from parallel_odcm.py subprocess stdout
    """
    try:
        level, msg = msg_string.split(MSG_STR_SPLITTER)
        if level in ["ERROR", "CRITICAL"]:
            arcpy.AddError(msg)
        elif level == "WARNING":
            arcpy.AddWarning(msg)
        else:
            arcpy.AddMessage(msg)
    except Exception:  # pylint: disable=broad-except
        arcpy.AddMessage(msg_string)


def get_catalog_path(layer):
    """Get the catalog path for the designated layer if possible. Ensures we can pass map layers to the subprocess.

    If it's already a string, assume it's a catalog path and return it as is.

    Args:
        layer (layer object or string): Layer from which to retrieve the catalog path.

    Returns:
        string: Catalog path to the data
    """
    if hasattr(layer, "dataSource"):
        return layer.dataSource
    else:
        return layer


def make_analysis_time_of_day_list(start_day_input, end_day_input, start_time_input, end_time_input, increment_input):
    '''Make a list of datetimes to use as input for a network analysis time of day run in a loop'''

    start_time, end_time = convert_inputs_to_datetimes(start_day_input, end_day_input, start_time_input, end_time_input)

    # How much to increment the time in each solve, in minutes
    increment = datetime.timedelta(minutes=increment_input)
    timelist = []  # Actual list of times to use for the analysis.
    t = start_time
    while t <= end_time:
        timelist.append(t)
        t += increment

    return timelist


def convert_inputs_to_datetimes(start_day_input, end_day_input, start_time_input, end_time_input):
    '''Parse start and end day and time from tool inputs and convert them to datetimes'''

    # For an explanation of special ArcMap generic weekday dates, see the time_of_day parameter
    # description in the Make Service Area Layer tool documentation
    # http://desktop.arcgis.com/en/arcmap/latest/tools/network-analyst-toolbox/make-service-area-layer.htm
    days = {
        "Monday": datetime.datetime(1900, 1, 1),
        "Tuesday": datetime.datetime(1900, 1, 2),
        "Wednesday": datetime.datetime(1900, 1, 3),
        "Thursday": datetime.datetime(1900, 1, 4),
        "Friday": datetime.datetime(1900, 1, 5),
        "Saturday": datetime.datetime(1900, 1, 6),
        "Sunday": datetime.datetime(1899, 12, 31)}

    # Lower end of time window (HH:MM in 24-hour time)
    generic_weekday = False
    if start_day_input in days: # Generic weekday
        generic_weekday = True
        start_day = days[start_day_input]
    else:  # Specific date
        start_day = datetime.datetime.strptime(start_day_input, '%Y%m%d')
    start_time_dt = datetime.datetime.strptime(start_time_input, "%H:%M")
    start_time = datetime.datetime(
        start_day.year,
        start_day.month,
        start_day.day,
        start_time_dt.hour,
        start_time_dt.minute
        )

    # Upper end of time window (HH:MM in 24-hour time)
    # End time is inclusive.  An analysis will be run using the end time.
    if end_day_input in days:  # Generic weekday
        if not generic_weekday:
            # The tool UI validation should prevent them from encountering this problem.
            err = ("Your Start Day is a specific date, but your End Day is a generic weekday. Please use either a "
                   "specific date or a generic weekday for both Start Date and End Date.")
            arcpy.AddError(err)
            raise ValueError(err)
        end_day = days[end_day_input]
        if start_day != end_day:
            # We can't interpret what the user intends if they choose two different generic weekdays,
            # and the solver won't be happy if the start day is after the end day, even if we add a \
            # week to the end day. So just don't support this case. If they want to solve across \
            # multiple days, they should use specific dates.
            # The tool UI validation should prevent them from encountering this problem.
            err = "If using a generic weekday, the Start Day and End Day must be the same."
            arcpy.AddError(err)
            raise ValueError(err)

    else:  # Specific date
        if generic_weekday:
            err = ("Your Start Day is a generic weekday, but your End Day is a specific date. Please use either a "
                   "specific date or a generic weekday for both Start Date and End Date.")
            arcpy.AddError(err)
            raise ValueError(err)
        end_day = datetime.datetime.strptime(end_day_input, '%Y%m%d')
    end_time_dt = datetime.datetime.strptime(end_time_input, "%H:%M")
    end_time = datetime.datetime(end_day.year, end_day.month, end_day.day, end_time_dt.hour, end_time_dt.minute)

    if start_time == end_time:
        err = "Start and end date and time are the same."
        arcpy.AddError(err)
        raise ValueError(err)
    if end_time < start_time:
        err = "End time is earlier than start time."
        arcpy.AddError(err)
        raise ValueError(err)

    return start_time, end_time


def add_TimeOfDay_field_to_sublayer(nalayer, sublayer_object, sublayer_name):
    '''Add a field called TimeOfDay of type DATE to an NA sublayer'''
    # Clean up any pre-existing fields with this name (unlikely case)
    poly_fields = [f for f in arcpy.Describe(sublayer_object).fields if f.name == TIME_FIELD]
    if poly_fields:
        for f in poly_fields:
            if f.name == TIME_FIELD and f.type != "Date":
                msg = "Your network analysis layer's %s sublayer already contained a field called %s of a type " + \
                      "other than Date.  This field will be deleted and replaced with a field of type Date used " + \
                      "for the output of this tool."
                arcpy.AddWarning(msg % (sublayer_name, TIME_FIELD))
                arcpy.management.DeleteField(sublayer_object, TIME_FIELD)

    # Add the TimeOfDay field to the sublayer.  If it already exists, this will do nothing.
    arcpy.na.AddFieldToAnalysisLayer(nalayer, sublayer_name, TIME_FIELD, "DATE")

    return TIME_FIELD


def calculate_TimeOfDay_field(sublayer_object, time_field, time_of_day):
    '''Set the TimeOfDay field to a specific time of day'''
    expression = '"' + str(time_of_day) + '"'  # Unclear why a DATE field requires a string expression, but it does.
    arcpy.management.CalculateField(sublayer_object, time_field, expression, "PYTHON_9.3")
