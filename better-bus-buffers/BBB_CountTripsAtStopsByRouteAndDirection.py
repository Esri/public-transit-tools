############################################################################
## Tool name: BetterBusBuffers - Count Trips at Stops by Route and Direction
## Created by: Melinda Morang, Esri, and David Wasserman, https://github.com/d-wasserman
## Last updated: 7 August 2020
############################################################################
''' BetterBusBuffers - Count Trips at Stops by Route and Direction

BetterBusBuffers provides a quantitative measure of access to public transit
in your city by counting the transit trip frequency at various locations.

The Count Trips at Stops by Route and Direction outputs a feature class where
every GTFS stop is duplicated for every route-direction combination that uses
that stop during the analysis time windows. Each point will represent a unique
combination of stop id, route id, and direction id, and the frequency statistics
that relate to each of them for the analyzed time window.
'''
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
"""Copyright 2020 David J. Wasserman

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
    http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
################################################################################

import arcpy
import BBB_SharedFunctions


def runTool(outStops, SQLDbase, time_window_value_table):
    try:
        # David, put your code here
        # The time_window_value_table will be a list of nested lists of strings like:
        # [[Weekday name or YYYYMMDD date, HH:MM, HH:MM, Departures/Arrivals, Prefix], [], ...]
        arcpy.AddMessage("Tool runs and does nothing!!!")

    except BBB_SharedFunctions.CustomError:
        arcpy.AddError("Failed to count trips at stops.")
        pass

    except:
        arcpy.AddError("Failed to count trips at stops.")
        raise