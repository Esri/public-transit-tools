################################################################################
## Toolbox: Transit Network Analysis Tools
## Created by: Melinda Morang, Esri
## Last updated: 30 August 2023
################################################################################
"""Helper methods for analysis tools."""
################################################################################
"""Copyright 2023 Esri
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at
       http://www.apache.org/licenses/LICENSE-2.0
   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License."""
################################################################################

import os
import sys
import time
import datetime
import enum
import subprocess
import uuid
import logging
import traceback
from concurrent import futures
import arcpy

# Determine if this is python 3 (which means probably ArcGIS Pro)
isPy3 = sys.version_info > (3, 0)
arcgis_version = arcpy.GetInstallInfo()["Version"]

# Set some shared global variables that can be referenced from the other scripts
MSG_STR_SPLITTER = " | "
TIME_UNITS = ["Days", "Hours", "Minutes", "Seconds"]
MAX_AGOL_PROCESSES = 4  # AGOL concurrent processes are limited so as not to overload the service for other users.
MAX_ALLOWED_MAX_PROCESSES = 61  # Windows limitation for concurrent.futures ProcessPoolExecutor
MAX_RETRIES = 3  # Max allowed retries if a parallel process errors (eg, temporary service glitch or read/write error)
TIME_FIELD = "TimeOfDay"  # Used for the output of Prepare Time Lapse Polygons
# Create Percent Access Polygons: Field names that must be in the input time lapse polygons
FACILITY_ID_FIELD = "FacilityID"
NAME_FIELD = "Name"
FROM_BREAK_FIELD = "FromBreak"
TO_BREAK_FIELD = "ToBreak"
FIELDS_TO_PRESERVE = [FACILITY_ID_FIELD, NAME_FIELD, FROM_BREAK_FIELD, TO_BREAK_FIELD]


class TransitNetworkAnalysisToolsError(Exception):
    """Generic error class that can be raised for known problems in these tools."""

    pass


def validate_input_feature_class(feature_class):
    """Validate that the designated input feature class exists and is not empty.

    Args:
        feature_class (str, layer): Input feature class or layer to validate

    Raises:
        ValueError: The input feature class does not exist.
        ValueError: The input feature class has no rows.
    """
    if not arcpy.Exists(feature_class):
        err = f"Input dataset {feature_class} does not exist."
        arcpy.AddError(err)
        raise ValueError(err)
    if int(arcpy.management.GetCount(feature_class).getOutput(0)) <= 0:
        err = f"Input dataset {feature_class} has no rows."
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


def get_tool_limits_and_is_agol(network_data_source, service_name, tool_name):
    """Retrieve a dictionary of various limits supported by a portal tool and whether the portal uses AGOL services.

    Assumes that we have already determined that the network data source is a service.

    Args:
        network_data_source (str): URL to the service being used as the network data source.
        service_name (str): Name of the service, such as "asyncODCostMatrix" or "asyncRoute".
        tool_name (_type_): Tool name for the designated service, such as "GenerateOriginDestinationCostMatrix" or
            "FindRoutes".

    Returns:
        (dict, bool): Dictionary of service limits; Boolean indicating if the service is ArcGIS Online or a hybrid
            portal that falls back to ArcGIS Online.
    """
    arcpy.AddMessage("Getting tool limits from the portal...")
    try:
        tool_info = arcpy.nax.GetWebToolInfo(service_name, tool_name, network_data_source)
        # serviceLimits returns the maximum origins and destinations allowed by the service, among other things
        service_limits = tool_info["serviceLimits"]
        # isPortal returns True for Enterprise portals and False for AGOL or hybrid portals that fall back to using
        # the AGOL services
        is_agol = not tool_info["isPortal"]
        return service_limits, is_agol
    except Exception:
        arcpy.AddError("Error getting tool limits from the portal.")
        errs = traceback.format_exc().splitlines()
        for err in errs:
            arcpy.AddError(err)
        raise


def does_travel_mode_use_transit_evaluator(network: str, travel_mode: arcpy.nax.TravelMode) -> bool:
    """Check if the travel mode uses the Public Transit evaluator.

    Args:
        network (str): Network data source path
        travel_mode (arcpy.nax.TravelMode): Travel mode

    Returns:
        bool: True if the travel mode's impedance uses the Public Transit evaluator and False otherwise.
    """
    if not is_nds_service(network):
        nd_desc = arcpy.Describe(network)
        impedance_desc = [attr for attr in nd_desc.attributes if attr.name == travel_mode.impedance][0]
        for x in range(impedance_desc.evaluatorCount):
            if getattr(impedance_desc, f"evaluatorType{x}") == "Public Transit":
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
    """Convert a string representation of geometry at overlap to an arcpy.nax enum.

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
    return layer


def get_catalog_path_from_param(param):
    """Get the catalog path for the designated input parameter if possible.

    Args:
        param (arcpy.Parameter): Parameter from which to retrieve the catalog path.

    Returns:
        string: Catalog path to the data
    """
    if hasattr(param.value, "dataSource"):
        return param.value.dataSource
    return param.valueAsText


def are_input_layers_the_same(input_layer_1, input_layer_2):
    """Determine whether two input layers are actually the same layer.

    This is used, for example, to determine if the layers the user has passed in to the Origins and Destinations
    parameters are actually the same layers.

    Layer equivalency is not completely straightforward.  The value retrieved from parameter.value for a Feature Layer
    parameter may be a layer object (if the input is a layer object/file/name), a record set object (if the input is a
    feature set), or a GP value object (if the input is a catalog path).  This function
    """
    def get_layer_repr(lyr):
        """Get the unique representation of the layer according to its type."""
        if hasattr(lyr, "URI"):
            # The input is a layer.  The URI property uniquely defines the layer in the map and in memory.
            layer_repr = lyr.URI
        elif hasattr(lyr, "JSON"):
            # The input is a feature set.  The JSON representation of the feature set fully defines it.
            layer_repr = lyr.JSON
        else:
            # The input is likely a catalog path, which is returned as a GP value object.  The string representation is
            # the catalog path.
            layer_repr = str(lyr)
        return layer_repr

    lyr_repr1 = get_layer_repr(input_layer_1)
    lyr_repr2 = get_layer_repr(input_layer_2)

    return lyr_repr1 == lyr_repr2


def make_analysis_time_of_day_list(start_day_input, end_day_input, start_time_input, end_time_input, increment_input):
    """Make a list of datetimes to use as input for a network analysis time of day run in a loop."""
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
    """Parse start and end day and time from tool inputs and convert them to datetimes."""
    # For an explanation of special generic weekday dates, see this documentation:
    # https://pro.arcgis.com/en/pro-app/latest/help/analysis/networks/dates-and-times.htm
    days = {
        "Monday": datetime.datetime(1900, 1, 1),
        "Tuesday": datetime.datetime(1900, 1, 2),
        "Wednesday": datetime.datetime(1900, 1, 3),
        "Thursday": datetime.datetime(1900, 1, 4),
        "Friday": datetime.datetime(1900, 1, 5),
        "Saturday": datetime.datetime(1900, 1, 6),
        "Sunday": datetime.datetime(1899, 12, 31)
    }

    # Lower end of time window (HH:MM in 24-hour time)
    generic_weekday = False
    if start_day_input in days:  # Generic weekday
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


def cell_size_to_meters(cell_size_param_value):
    """Convert the cell size tool parameter string value to a numerical value in units of meters.

    Args:
        cell_size_param_value (str): cell size tool parameter string value

    Raises:
        ValueError: If the units are invalid.

    Returns:
        Optional[float]: Cell size numerical value in units of meters. If the input is empty, return None.
    """
    if not cell_size_param_value:
        return None
    # Split the cell size string value from the tool parameter into its numerical value and units.
    # This text splitting behavior works adequately even with language packs and RTL languages because the
    # Linear Unit type parameter always reads in the valueAsText as "[number] [English units]"
    cell_size, units = cell_size_param_value.split(" ")
    # Locales that use a comma as a decimal may return numbers like 10,5, so replace commas with periods before
    # converting to float.
    cell_size = float(cell_size.replace(",", "."))

    # Convert the numerical value to meters
    if units == "Meters":
        return cell_size
    if units == "Kilometers":
        return cell_size * 1000.0
    if units == "Feet":
        return cell_size / 3.28084
    if units == "Yards":
        return cell_size / 1.0936133
    if units == "Miles":
        return cell_size / 0.0006213712121
    # If we got this far, units are invalid. Tool validation should ensure this never happens, but raise an error
    # just in case.
    raise ValueError(f"Invalid cell size units: {units}")


def get_oid_ranges_for_input(input_fc, max_chunk_size):
    """Construct ranges of ObjectIDs for use in where clauses to split large data into chunks.

    Args:
        input_fc (str, layer): Data that needs to be split into chunks
        max_chunk_size (int): Maximum number of rows that can be in a chunk

    Returns:
        list: list of ObjectID ranges for the current dataset representing each chunk. For example,
            [[1, 1000], [1001, 2000], [2001, 2478]] represents three chunks of no more than 1000 rows.
    """
    ranges = []
    num_in_range = 0
    current_range = [0, 0]
    # Loop through all OIDs of the input and construct tuples of min and max OID for each chunk
    # We do it this way and not by straight-up looking at the numerical values of OIDs to account
    # for definition queries, selection sets, or feature layers with gaps in OIDs
    for row in arcpy.da.SearchCursor(input_fc, "OID@"):  # pylint: disable=no-member
        oid = row[0]
        if num_in_range == 0:
            # Starting new range
            current_range[0] = oid
        # Increase the count of items in this range and set the top end of the range to the current oid
        num_in_range += 1
        current_range[1] = oid
        if num_in_range == max_chunk_size:
            # Finishing up a chunk
            ranges.append(current_range)
            # Reset range trackers
            num_in_range = 0
            current_range = [0, 0]
    # After looping, close out the last range if we still have one open
    if current_range != [0, 0]:
        ranges.append(current_range)

    return ranges


def run_gp_tool(log_to_use, tool, tool_args=None, tool_kwargs=None):
    """Run a geoprocessing tool with nice logging.

    The purpose of this function is simply to wrap the call to a geoprocessing tool in a way that we can log errors,
    warnings, and info messages as well as tool run time into our logging. This helps pipe the messages back to our
    script tool dialog.

    Args:
        tool (arcpy geoprocessing tool class): GP tool class command, like arcpy.management.CreateFileGDB
        tool_args (list, optional): Ordered list of values to use as tool arguments. Defaults to None.
        tool_kwargs (dictionary, optional): Dictionary of tool parameter names and values that can be used as named
            arguments in the tool command. Defaults to None.
        log_to_use (logging.logger, optional): logger class to use for messages. Defaults to LOGGER. When calling this
            from the Route class, use self.logger instead so the messages go to the processes's log file instead
            of stdout.

    Returns:
        GP result object: GP result object returned from the tool run.

    Raises:
        arcpy.ExecuteError if the tool fails
    """
    # Try to retrieve and log the name of the tool
    tool_name = repr(tool)
    try:
        tool_name = tool.__esri_toolname__
    except Exception:  # pylint: disable=broad-except
        try:
            tool_name = tool.__name__
        except Exception:  # pylint: disable=broad-except
            # Probably the tool didn't have an __esri_toolname__ property or __name__. Just don't worry about it.
            pass
    log_to_use.debug(f"Running geoprocessing tool {tool_name}...")

    # Try running the tool, and log all messages
    try:
        if tool_args is None:
            tool_args = []
        if tool_kwargs is None:
            tool_kwargs = {}
        result = tool(*tool_args, **tool_kwargs)
        info_msgs = [msg for msg in result.getMessages(0).splitlines() if msg]
        warning_msgs = [msg for msg in result.getMessages(1).splitlines() if msg]
        for msg in info_msgs:
            log_to_use.debug(msg)
        for msg in warning_msgs:
            log_to_use.warning(msg)
    except arcpy.ExecuteError:
        log_to_use.error(f"Error running geoprocessing tool {tool_name}.")
        # First check if it's a tool error and if so, handle warning and error messages.
        info_msgs = [msg for msg in arcpy.GetMessages(0).strip("\n").splitlines() if msg]
        warning_msgs = [msg for msg in arcpy.GetMessages(1).strip("\n").splitlines() if msg]
        error_msgs = [msg for msg in arcpy.GetMessages(2).strip("\n").splitlines() if msg]
        for msg in info_msgs:
            log_to_use.debug(msg)
        for msg in warning_msgs:
            log_to_use.warning(msg)
        for msg in error_msgs:
            log_to_use.error(msg)
        raise
    except Exception:
        # Unknown non-tool error
        log_to_use.error(f"Error running geoprocessing tool {tool_name}.")
        errs = traceback.format_exc().splitlines()
        for err in errs:
            log_to_use.error(err)
        raise

    log_to_use.debug(f"Finished running geoprocessing tool {tool_name}.")
    return result


class ODTool(enum.Enum):
    """Enum defining the tool being run.

    Used as a switch in shared code where minor behavior differences are necessary.
    """

    CalculateAccessibilityMatrix = 1
    CalculateTravelTimeStatistics = 2


class GPError(Exception):
    """Class for passing through exceptions raised in tool code.

    Used for catching a failed GP tool run within a script and failing out nicely
    without throwing a traceback.
    """

    def __init__(self):  # pylint:disable=super-init-not-called
        """Raise an error."""
        # Use AddReturnMessage to pass through GP errors.
        # This ensures that the hyperlinks to the message IDs will work in the UI.
        for msg in range(0, arcpy.GetMessageCount()):
            if arcpy.GetSeverity(msg) == 2:
                arcpy.AddReturnMessage(msg)
        sys.exit()


def construct_search_criteria_string(sources_to_use, all_sources):
    """Construct a search criteria string from a list of network sources to use.

    We use the string-based format for search criteria to allow it to be passed through to a subprocess CLI.

    Args:
        sources_to_use (list): Names of network sources to use for locating
        all_sources (list): List of all network sources

    Returns:
        str: String properly formatted for use in the Calculate Locations Search Criteria parameter
    """
    search_criteria = [s + " SHAPE" for s in sources_to_use] + \
                      [s + " NONE" for s in all_sources if s not in sources_to_use]
    return ";".join(search_criteria)  # Ex: Streets SHAPE;Streets_ND_Junctions NONE


def get_locatable_network_source_names(network_dataset):
    """Return a list of all locatable network dataset source feature class names.

    Suitable for constructing a list of values for the Search Criteria parameter.

    Args:
        network_dataset (str, layer): Network dataset catalog path or layer

    Returns:
        list: List of network source feature class names.  Does not include turn sources.
    """
    # The most reliable way to get the locatable sources for a network dataset is to create a dummy arcpy.nax solver
    # object and retrieve the source names from the searchQuery property.  That isn't the property's intended use, but
    # as a hack, it works great!  Note that you could also retrieve this information using the network dataset Describe
    # object and getting the list of edges and junction sources.  However, the sort order won't be the same as a user
    # would typically see in the Pro UI in the Calculate Locations tool, for example.  Also, rarely (especially with)
    # public transit network, some sources aren't considered locatable (LineVariantElements) and would not be filtered
    # from this list.
    rt = arcpy.nax.Route(network_dataset)
    network_sources = [q[0] for q in rt.searchQuery]
    del rt
    return network_sources


def get_locate_settings_from_config_file(config_file_props, network_dataset):
    """Get location settings from config file if present."""
    search_tolerance = ""
    search_criteria = ""
    search_query = ""
    if "searchTolerance" in config_file_props and "searchToleranceUnits" in config_file_props:
        search_tolerance = f"{config_file_props['searchTolerance']} {config_file_props['searchToleranceUnits'].name}"
    if "searchSources" in config_file_props:
        # searchSources covers both search_criteria and search_tolerance.
        search_sources = config_file_props["searchSources"]
        if search_sources:
            search_query = search_sources
            search_criteria = construct_search_criteria_string(
                [s[0] for s in search_sources],
                get_locatable_network_source_names(network_dataset)
            )
    elif "searchQuery" in config_file_props:
        # searchQuery is only used if searchSources is not present.
        search_query = config_file_props["searchQuery"]
        if not search_query:
            # Reset to empty string in case it was an empty list
            search_query = ""
    # Convert the search_query to string format to allow it to be passed through to a subprocess CLI
    # Use a value table to ensure proper conversion of SQL expressions
    if search_query:
        value_table = arcpy.ValueTable(["GPString", "GPSQLExpression"])
        for query in search_query:
            value_table.addRow(query)
        search_query = value_table.exportToString()
    return search_tolerance, search_criteria, search_query


def execute_subprocess(script_name, inputs):
    """Execute a subprocess with the designated inputs and write the returned messages to the GP UI.

    This is used by the tools in this toolset to launch the scripts that parallelize processes using concurrent.futures.
    It is necessary to launch these parallelization scripts as subprocess so they can spawn parallel processes because a
    tool running in the Pro UI cannot call concurrent.futures without opening multiple instances of Pro.

    Args:
        script_name (str): The name of the Python file to run as a subprocess, like parallel_route_pairs.py.
        inputs (list): A list that includes each command line argument flag followed by its value appropriate for
            calling a subprocess.  Do not include the Python executable path or the script path in this list because
            the function will automatically add them. Ex: ["--my-param1", "my_value_1", "--my-param2", "my_value_2]
    """
    # Set up inputs to run the designated module with the designated inputs
    cwd = os.path.dirname(os.path.abspath(__file__))
    inputs = [
        os.path.join(sys.exec_prefix, "python.exe"),
        os.path.join(cwd, script_name)
    ] + inputs

    # We do not want to show the console window when calling the command line tool from within our GP tool.
    # This can be done by setting this hex code.
    create_no_window = 0x08000000

    # Launch the subprocess and periodically check results
    with subprocess.Popen(
        inputs,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=create_no_window
    ) as process:
        # The while loop reads the subprocess's stdout in real time and writes the stdout messages to the GP UI.
        # This is the only way to write the subprocess's status messages in a way that a user running the tool from
        # the ArcGIS Pro UI can actually see them.
        # When process.poll() returns anything other than None, the process has completed, and we should stop
        # checking and move on.
        while process.poll() is None:
            output = process.stdout.readline()
            if output:
                msg_string = output.strip().decode(encoding="utf-8")
                parse_std_and_write_to_gp_ui(msg_string)
            time.sleep(.1)

        # Once the process is finished, check if any additional errors were returned. Messages that came after the
        # last process.poll() above will still be in the queue here. This is especially important for detecting
        # messages from raised exceptions, especially those with tracebacks.
        output, _ = process.communicate()
        if output:
            out_msgs = output.decode(encoding="utf-8").splitlines()
            for msg in out_msgs:
                parse_std_and_write_to_gp_ui(msg)

        # In case something truly horrendous happened and none of the logging caught our errors, at least fail the
        # tool when the subprocess returns an error code. That way the tool at least doesn't happily succeed but not
        # actually do anything.
        return_code = process.returncode
        if return_code != 0:
            err = f"Parallelization using {script_name} failed."
            arcpy.AddError(err)
            raise RuntimeError(err)


def configure_global_logger(log_level):
    """Configure a global logger for the main process.

    The logger logs everything from the main process to stdout using a specific format that the tools in this
    toolbox can parse and write to the geoprocessing message feed.

    Args:
        log_level: logging module message level, such as logging.INFO or logging.DEBUG.
    """
    logger = logging.getLogger(__name__)  # pylint:disable=invalid-name
    logger.setLevel(log_level)
    sys.stdout.reconfigure(encoding="utf-8")
    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setLevel(log_level)
    # Used by script tool to split message text from message level to add correct message type to GP window
    console_handler.setFormatter(logging.Formatter("%(levelname)s" + MSG_STR_SPLITTER + "%(message)s"))
    logger.addHandler(console_handler)
    return logger


def run_parallel_processes(
        logger, function_to_call, static_args, chunks, total_jobs, max_processes,
        msg_intro_verb, msg_process_str
):
    """Launch and manage parallel processes and return a results dictionary.

    Args:
        logger (logging.logger): Logger to use for the parallelized process
        function_to_call (function): Function called in each parallelized job
        static_args (list): List of values used as static arguments to the function_to_call
        chunks (iterator): Iterator with values that will be passed one at a time to the function_to_call, with each
            value being one parallelized chunk.
        total_jobs (int): Total number of jobs that will be run. Used in messaging.
        max_processes (int): Maximum number of parallel processes allowed.
        msg_intro_verb (str): Text to include in the intro message f"{msg_intro_verb} in parallel..."
        msg_process_str (_type_): Text to include in messages representing whatever is being parallelized.

    Returns:
        list: List of returned values from the parallel processes.
    """
    logger.info(f"{msg_intro_verb} in parallel ({total_jobs} chunks)...")
    completed_jobs = 0  # Track the number of jobs completed so far to use in logging
    job_results = []
    # Use the concurrent.futures ProcessPoolExecutor to spin up parallel processes that call the function
    with futures.ProcessPoolExecutor(max_workers=max_processes) as executor:
        # Each parallel process calls the designated function with the designated static inputs and a unique chunk
        jobs = {executor.submit(
            function_to_call, chunk, *static_args): chunk for chunk in chunks}
        # As each job is completed, add some logging information and store the results to post-process later
        for future in futures.as_completed(jobs):
            try:
                # Retrieve the results returned by the process
                result = future.result()
            except Exception:  # pylint: disable=broad-except
                # If we couldn't retrieve the result, some terrible error happened and the job errored.
                # Note: For processes that do network analysis workflows, this does not mean solve failed.
                # It means some unexpected error was thrown. The most likely
                # causes are:
                # a) If you're calling a service, the service was temporarily down.
                # b) You had a temporary file read/write or resource issue on your machine.
                # c) If you're actively updating the code, you introduced an error.
                # To make the tool more robust against temporary glitches, retry submitting the job up to the number
                # of times designated in MAX_RETRIES.  If the job is still erroring after that many
                # retries, fail the entire tool run.
                errs = traceback.format_exc().splitlines()
                failed_range = jobs[future]
                logger.debug((
                    f"Failed to get results for {msg_process_str} chunk {failed_range} from the parallel process. "
                    f"Will retry up to {MAX_RETRIES} times. Errors: {errs}"
                ))
                job_failed = True
                num_retries = 0
                while job_failed and num_retries < MAX_RETRIES:
                    num_retries += 1
                    try:
                        future = executor.submit(function_to_call, failed_range, *static_args)
                        result = future.result()
                        job_failed = False
                        logger.debug(f"{msg_process_str} chunk {failed_range} succeeded after {num_retries} retries.")
                    except Exception:  # pylint: disable=broad-except
                        # Update exception info to the latest error
                        errs = traceback.format_exc().splitlines()
                if job_failed:
                    # The job errored and did not succeed after retries.  Fail the tool run because something
                    # terrible is happening.
                    logger.debug(
                        f"{msg_process_str} chunk {failed_range} continued to error after {num_retries} retries.")
                    logger.error(f"Failed to get {msg_process_str} result from parallel processing.")
                    errs = traceback.format_exc().splitlines()
                    for err in errs:
                        logger.error(err)
                    raise

            # If we got this far, the job completed successfully and we retrieved results.
            completed_jobs += 1
            logger.info(
                f"Finished {msg_process_str} {completed_jobs} of {total_jobs}.")
            job_results.append(result)

        return job_results


class PrecalculateLocationsMixin:  # pylint:disable = too-few-public-methods
    """Used to precalculate network locations either directly or calling the parallelized version."""

    def _precalculate_locations(self, fc_to_precalculate, config_props):
        """Precalculate network locations for the designated feature class.

        Args:
            fc_to_precalculate (str): Catalog path to the feature class to calculate locations for.
            config_props (dict): Dictionary of solver object properties that includes locate settings.  Must be OD_PROPS
                from CalculateAccessibilityMatrix_OD_config.py or CalculateTravelTimeStatistics_OD_config.py or SA_PROPS
                from CreateTimeLapsePolygons_SA_config.py.

        Returns:
            str: Catalog path to the feature class with the network location fields
        """
        search_tolerance, search_criteria, search_query = get_locate_settings_from_config_file(
            config_props, self.network_data_source)
        num_features = int(arcpy.management.GetCount(fc_to_precalculate).getOutput(0))
        if num_features <= self.chunk_size:
            # Do not parallelize Calculate Locations since the number of features is less than the chunk size, and it's
            # more efficient to run the tool directly.
            arcpy.nax.CalculateLocations(
                fc_to_precalculate,
                self.network_data_source,
                search_tolerance,
                search_criteria,
                search_query=search_query,
                travel_mode=self.travel_mode
            )
        else:
            # Run Calculate Locations in parallel.
            precalculated_fc = fc_to_precalculate + "_Precalc"
            cl_inputs = [
                "--input-features", fc_to_precalculate,
                "--output-features", precalculated_fc,
                "--network-data-source", self.network_data_source,
                "--chunk-size", str(self.chunk_size),
                "--max-processes", str(self.max_processes),
                "--travel-mode", self.travel_mode,
                "--search-tolerance", search_tolerance,
                "--search-criteria", search_criteria,
                "--search-query", search_query
            ]
            execute_subprocess("parallel_calculate_locations.py", cl_inputs)
            fc_to_precalculate = precalculated_fc
        return fc_to_precalculate  # Updated feature class


class JobFolderMixin:  # pylint:disable = too-few-public-methods
    """Used to define and create a job folder for a parallel process."""

    def _create_job_folder(self):
        """Create a job ID and a folder and scratch gdb for this job."""
        self.job_id = uuid.uuid4().hex
        self.job_folder = os.path.join(self.scratch_folder, self.job_id)
        os.mkdir(self.job_folder)

    def _create_output_gdb(self):
        """Create a scratch geodatabase in the job folder.

        Returns:
            str: Catalog path to output geodatabase
        """
        self.logger.debug("Creating output geodatabase...")
        out_gdb = os.path.join(self.job_folder, "scratch.gdb")
        run_gp_tool(
            self.logger,
            arcpy.management.CreateFileGDB,
            [os.path.dirname(out_gdb), os.path.basename(out_gdb)],
        )
        return out_gdb


class LoggingMixin:
    """Used to set up and tear down logging for a parallel process."""

    def setup_logger(self, name_prefix):
        """Set up the logger used for logging messages for this process. Logs are written to a text file.

        Args:
            logger_obj: The logger instance.
        """
        self.log_file = os.path.join(self.job_folder, name_prefix + ".log")
        self.logger = logging.getLogger(f"{name_prefix}_{self.job_id}")

        self.logger.setLevel(logging.DEBUG)
        if len(self.logger.handlers) <= 1:
            file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            self.logger.addHandler(file_handler)
            formatter = logging.Formatter("%(process)d | %(message)s")
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

    def teardown_logger(self):
        """Clean up and close the logger."""
        for handler in self.logger.handlers:
            handler.close()
            self.logger.removeHandler(handler)


class MakeNDSLayerMixin:  # pylint:disable = too-few-public-methods
    """Used to make a network dataset layer for a parallel process."""

    def _make_nds_layer(self):
        """Create a network dataset layer if one does not already exist."""
        nds_layer_name = os.path.basename(self.network_data_source)
        if arcpy.Exists(nds_layer_name):
            # The network dataset layer already exists in this process, so we can re-use it without having to spend
            # time re-opening the network dataset and making a fresh layer.
            self.logger.debug(f"Using existing network dataset layer: {nds_layer_name}")
        else:
            # The network dataset layer does not exist in this process, so create the layer.
            self.logger.debug("Creating network dataset layer...")
            run_gp_tool(
                self.logger,
                arcpy.na.MakeNetworkDatasetLayer,
                [self.network_data_source, nds_layer_name],
            )
        self.network_data_source = nds_layer_name
