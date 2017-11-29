############################################################################
## Tool name: BetterBusBuffers
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 29 November 2017
############################################################################
''' GP tool validation code'''
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


import arcpy
import os
import sys

ispy3 = sys.version_info >= (3, 0)

def check_input_gtfs(param_GTFSDirs):

    # --- Make sure the appropriate GTFS files are present. ---
    if param_GTFSDirs.altered:
        BadGTFS = []
        if ispy3:
            inGTFSdirList = [str(folder) for folder in param_GTFSDirs.values]
        else:
            try:
                inGTFSdirList = [unicode(folder) for folder in param_GTFSDirs.values]
            except:
                inGTFSdir = str(param_GTFSDirs.value)
                inGTFSdirList = inGTFSdir.split(";")
        # Remove single quotes ArcGIS puts in if there are spaces in the name
        for d in inGTFSdirList:
            if d[0] == "'" and d[-1] == "'":
                loc = inGTFSdirList.index(d)
                inGTFSdirList[loc] = d[1:-1]
        for GTFS in inGTFSdirList:
            invalid = 0
            calendar = os.path.join(GTFS, "calendar.txt")
            calendar_dates = os.path.join(GTFS, "calendar_dates.txt")
            if not os.path.exists(calendar) and not os.path.exists(calendar_dates):
                # One of these is required
                invalid = 1
            # All of these are required
            requiredFiles = [os.path.join(GTFS, "stops.txt"),
                                os.path.join(GTFS, "stop_times.txt"),
                                os.path.join(GTFS, "trips.txt"),
                                os.path.join(GTFS, "routes.txt")]
            for f in requiredFiles:
                if not os.path.exists(f):
                    invalid = 1
            if invalid == 1:
                BadGTFS.append(GTFS)
        if BadGTFS:
            message = u"The following folder(s) you selected do not contain \
the required GTFS files: "
            for bad in BadGTFS:
                message += bad + u";"
            message += u". You must have the following files: \
stops.txt, stop_times.txt, trips.txt, routes.txt, and either calendar.txt, \
calendar_dates.txt, or both."
            param_GTFSDirs.setErrorMessage(message)

