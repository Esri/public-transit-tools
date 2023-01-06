################################################################################
## Toolbox: Transit Network Analysis Tools
## Created by: Melinda Morang, Esri
## Last updated: 6 January 2023
################################################################################
"""Shared tool validation methods."""
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
import re
import datetime
import arcpy
from AnalysisHelpers import is_nds_service, MAX_AGOL_PROCESSES, MAX_ALLOWED_MAX_PROCESSES

ispy3 = sys.version_info >= (3, 0)

# Days of the week
days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def validate_time_increment(param_increment):
    """Validate that the time increment is greater than 0."""
    if param_increment.value <= 0:
        param_increment.setErrorMessage("Time increment must be greater than 0.")


def allow_YYYYMMDD_day(param_day):
    """Make Day parameter accept a weekday or a YYYYMMDD date string.

    Hack for Pro: Define the filter list in updateMessages to trick UI control
    into allowing free text entry in addition to selection from the list. This
    allows us to accept both a weekday an a YYYYMMDD date."""
    # Define the filter list
    param_day.filter.list = days
    validate_day(param_day)


def validate_day(param_day):
    if param_day.altered:
        # Make sure if it's not a weekday that it's in YYYYMMDD date format
        if param_day.valueAsText not in days:
            # If it's not one of the weekday strings, it must be in YYYYMMDD format
            try:
                datetime.datetime.strptime(param_day.valueAsText, '%Y%m%d')
                # This is a valid YYYYMMDD date, so clear the filter list error
                if param_day.hasError():
                    msg_id = param_day.message.split(':')[0]
                    if msg_id == 'ERROR 000800':
                        # clearMessage() does not work in python toolboxes because of an ArcGIS bug,
                        # so catch the error and convert it to a warning so that the tool will run.
                        # This is the only solution I've been able to come up with.
                        param_day.setWarningMessage((
                            "You have chosen to use a specific date for this analysis. Please double check your GTFS "
                            "calendar.txt and/or calendar_dates.txt files to make sure this specific date falls within "
                            "the date range covered by your GTFS data."
                        ))
                        # Keep this here in case it starts working at some point
                        param_day.clearMessage()
            except ValueError:
                param_day.setErrorMessage("Please enter a date in YYYYMMDD format or a weekday.")


def set_end_day(param_startday, param_endday):
    """Set the end day to the same as start day by default, unless it's explicitly set the end day to something else.

    Also, the end day should be grayed out unless the start day is a specific date.
    """

    if param_startday.valueAsText:
        param_endday.value = param_startday.value

    if param_startday.valueAsText in days:
        param_endday.enabled = False
    else:
        param_endday.enabled = True


def check_time_window(param_starttime, param_endtime, param_startday, param_endday):
    """Make sure time window is valid and in the correct HH:MM format"""

    def is_time_valid(param_time):
        if param_time.altered:
            m = re.match ("^\s*([0-9]{2}):([0-9]{2})\s*$", param_time.value)
            if not m:
                param_time.setErrorMessage(
                    "Time of day format should be HH:MM (24-hour time). For example, 2am is 02:00, and 2pm is 14:00.")
                return False
            else:
                TimeNumErrorMessage = "Hours cannot be > 48; minutes cannot be > 59."
                hours = int(m.group(1))
                minutes = int(m.group(2))
                if hours < 0 or hours > 48:
                    param_time.setErrorMessage(TimeNumErrorMessage)
                    return False
                if minutes < 0 or minutes > 59:
                    param_time.setErrorMessage(TimeNumErrorMessage)
                    return False
        return True

    # Time of day format should be HH:MM (24-hour time).
    t1valid = is_time_valid(param_starttime)
    t2valid = is_time_valid(param_endtime)

    # End time must be later than start time if the start and end day are the same
    if param_startday.valueAsText == param_endday.valueAsText:
        if param_starttime.altered and param_endtime.altered and t1valid and t2valid:
            H1,M1 = param_starttime.value.split(':')
            seconds1 = (float(H1) * 3600) + (float(M1) * 60)
            H2,M2 = param_endtime.value.split(':')
            seconds2 = (float(H2) * 3600) + (float(M2) * 60)
            if seconds2 <= seconds1:
                param_endtime.setErrorMessage(
                    "Time window invalid!  Make sure the time window end is later than the time window start.")


def validate_output_is_gdb(param_outTable):
    """Output table should be in a geodatabase, not a dbf or info table."""
    if param_outTable.altered:
        wdesc = arcpy.Describe(os.path.dirname(param_outTable.valueAsText))
        if wdesc.dataType == "Folder" or (wdesc.dataType == "Workspace" and wdesc.workspaceType == "FileSystem"):
            param_outTable.setErrorMessage("Output table must be in a geodatabase.")


def update_precalculate_parameter(param_network, param_precalculate):
    """Turn off and hide Precalculate Network Locations parameter if the network data source is a service.

    Args:
        param_network (arcpy.Parameter): Parameter for the network data source
        param_precalculate (arcpy.Parameter): Parameter for precalculate network locations
    """
    if not param_network.hasBeenValidated and param_network.altered and param_network.valueAsText:
        if is_nds_service(param_network.valueAsText):
            param_precalculate.value = False
            param_precalculate.enabled = False
        else:
            param_precalculate.enabled = True


def show_only_time_travel_modes(param_network, param_travel_mode):
    """Populate the travel mode parameter with time-based travel modes only."""
    if not param_network.hasBeenValidated and param_network.altered and param_network.valueAsText:
        try:
            travel_modes = arcpy.nax.GetTravelModes(param_network.value)
            param_travel_mode.filter.list = [
                tm_name for tm_name in travel_modes if
                travel_modes[tm_name].impedance == travel_modes[tm_name].timeAttributeName
            ]
        except Exception:  # pylint: disable=broad-except
            # We couldn't get travel modes for this network for some reason.
            pass


def cap_max_processes(param_max_processes, param_network=None):
    """Validate max processes and cap it when required.

    Args:
        param_network (arcpy.Parameter): Parameter for the network data source
        param_max_processes (arcpy.Parameter): Parameter for the max processes
    """
    if param_max_processes.altered and param_max_processes.valueAsText:
        max_processes = param_max_processes.value
        # Don't allow 0 or negative numbers
        if max_processes <= 0:
            param_max_processes.setErrorMessage("The maximum number of parallel processes must be positive.")
            return
        # Cap max processes to the limit allowed by the concurrent.futures module
        if max_processes > MAX_ALLOWED_MAX_PROCESSES:
            param_max_processes.setErrorMessage((
                f"The maximum number of parallel processes cannot exceed {MAX_ALLOWED_MAX_PROCESSES:} due "
                "to limitations imposed by Python's concurrent.futures module."
            ))
            return
        # If the network data source is arcgis.com, cap max processes
        if (
            param_network and
            max_processes > MAX_AGOL_PROCESSES and
            param_network.altered and
            param_network.valueAsText and
            is_nds_service(param_network.valueAsText) and
            "arcgis.com" in param_network.valueAsText
        ):
            param_max_processes.setErrorMessage((
                f"The maximum number of parallel processes cannot exceed {MAX_AGOL_PROCESSES} when the "
                "ArcGIS Online service is used as the network data source."
            ))
            return
        # Set a warning if the user has put more processes than the number of logical cores on their machine
        if max_processes > os.cpu_count():
            param_max_processes.setWarningMessage((
                "The maximum number of parallel processes is greater than the number of logical cores "
                f"({os.cpu_count()}) in your machine."
            ))
