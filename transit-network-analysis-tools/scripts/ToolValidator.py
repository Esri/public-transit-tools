################################################################################
## Toolbox: Transit Network Analysis Tools
## Created by: Melinda Morang, Esri
## Last updated: 16 May 2019
################################################################################
'''Shared tool validation methods.'''
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


import os
import sys
import re
import sqlite3
import datetime
import arcpy
from BBB_SharedFunctions import days

ispy3 = sys.version_info >= (3, 0)

specificDatesRequiredMessage = "Your GTFS dataset does not have a \
calendar.txt file, so you cannot use a generic weekday for this analysis. Please use \
a specific date in YYYYMMDD format that falls within the date range in your calendar_dates.txt file."

def validate_time_increment(param_increment):
    """Validate that the time increment is greater than 0."""
    if param_increment.value <= 0:
        param_increment.setErrorMessage("Time increment must be greater than 0.")

def allow_YYYYMMDD_day(param_day):
    '''Make Day parameter accept a weekday or a YYYYMMDD date string.
    Hack for Pro: Define the filter list in updateMessages to trick UI control
    into allowing free text entry in addition to selection from the list. This
    allows us to accept both a weekday an a YYYYMMDD date.'''

    # Define the filter list
    param_day.filter.list = days
    
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
                        param_day.setWarningMessage("You have chosen to use a specific date for this analysis. \
Please double check your GTFS calendar.txt and/or calendar_dates.txt files to make sure this specific \
date falls within the date range covered by your GTFS data.")
                        # Keep this here in case it starts working at some point
                        param_day.clearMessage()
            except ValueError:
                param_day.setErrorMessage("Please enter a date in YYYYMMDD format or a weekday.")


def check_time_window(param_starttime, param_endtime):
    '''Make sure time window is valid and in the correct HH:MM format'''

    def is_time_valid(param_time):
        if param_time.altered:
            m = re.match ("^\s*([0-9]{2}):([0-9]{2})\s*$", param_time.value)
            if not m:
                param_time.setErrorMessage("Time of day format should be HH:MM (24-hour time). \
For example, 2am is 02:00, and 2pm is 14:00.")
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

    # End time must be later than start time
    if param_starttime.altered and param_endtime.altered and t1valid and t2valid:
        H1,M1 = param_starttime.value.split(':')
        seconds1 = (float(H1) * 3600) + (float(M1) * 60)
        H2,M2 = param_endtime.value.split(':')
        seconds2 = (float(H2) * 3600) + (float(M2) * 60)
        if seconds2 <= seconds1:
            param_endtime.setErrorMessage("Time window invalid!  Make sure the \
time window end is later than the time window start.")


def forbid_shapefile(param_outfc):
    '''Make sure output location is a file geodatabase feature class and not a shapefile.'''
    if param_outfc.altered:
        if ispy3:
            outfc = str(param_outfc.value)
        else:
            outfc = unicode(param_outfc.value)
        outdir = os.path.dirname(outfc)
        if not outdir:
            param_outfc.setErrorMessage("Invalid output feature class path.")
        else:
            desc = arcpy.Describe(outdir)
            if desc.dataType == "Folder":
                param_outfc.setErrorMessage("Output must be a feature class in a geodatabase, not a shapefile.")


def check_out_gdb(param_outGDB, param_outdir):
    '''Make sure the output gdb doesn't already exist and the name doesn't have invalid characters'''

    if param_outGDB.altered:
        # name for the output GDB must contain only text or underscores
        name = re.search ("[^A-za-z0-9_\.]", param_outGDB.value)
        if name:
            param_outGDB.setErrorMessage("Name must not contain special \
characters. Use only letters, numbers, periods, or the underscore.")

        # Make sure geodatabase doesn't already exist.
    if param_outGDB.altered and param_outdir.altered:
        if ispy3:
            outDir = str(param_outdir.value)
            outGDB = str(param_outGDB.value)
        else:
            outDir = unicode(param_outdir.value)
            outGDB = unicode(param_outGDB.value)
        if not outGDB.lower().endswith(".gdb"):
            outGDB += ".gdb"
        outGDBwPath = os.path.join(outDir, outGDB)
        if os.path.exists(outGDBwPath):
            param_outGDB.setErrorMessage("Geodatabase already exists. Please do \
not choose an existing geodatabase.")


def check_out_gdb_type_and_existence(param_outGDB):
    '''Make sure the selected output gdb already exists and is a file gdb'''
    if param_outGDB.altered:
        if ispy3:
            outGDB = str(param_outGDB.value)
        else:
            outGDB = unicode(param_outGDB.value)
        if not os.path.exists(outGDB):
            param_outGDB.setErrorMessage("Output geodatabase does not exist.")
        else:
            desc = arcpy.Describe(outGDB)
            if not desc.workspaceFactoryProgID.startswith("esriDataSourcesGDB.FileGDBWorkspaceFactory"):
                param_outGDB.setErrorMessage("Output geodatabase must be a file geodatabase \
(not a personal geodatabase or folder).")



def check_ND_not_from_AddGTFS(param_ND):
    '''Throw a warning if the network dataset appears to have been created using the Add GTFS to a Network Dataset toolbox'''
    if param_ND.altered:
        inNADataset = param_ND.value
        if arcpy.Exists(inNADataset):
            desc = arcpy.Describe(inNADataset)
            sources = set([src.name for src in desc.sources])
            # Source feature class names typical of a network created with the Add GTFS to a Network Dataset toolbox
            AddGTFSSources = set(["Stops", "TransitLines", "Connectors_Stops2Streets", "Stops_Snapped2Streets", "Streets_UseThisOne"])
            if AddGTFSSources.issubset(sources):
                param_ND.setWarningMessage("This network dataset appears to have been created using the Add GTFS to a Network Dataset tool. \
You should not use a network dataset created with that tool because BetterBusBuffers will handle the GTFS data separately. Please choose a \
network dataset appropriate for modeling pedestrians walking along streets and paths.")
