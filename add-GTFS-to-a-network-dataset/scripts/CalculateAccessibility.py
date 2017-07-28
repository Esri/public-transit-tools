################################################################################
## Toolbox: Add GTFS to a Network Dataset / Transit Analysis Tools
## Tool name: Calculate Accessibility Matrix
## Created by: Melinda Morang, Esri, mmorang@esri.com
## Last updated: 28 July 2017
################################################################################
'''Count the number of destinations reachable from each origin by transit and 
walking. The tool calculates an Origin-Destination Cost Matrix for each start 
time within a time window because the reachable destinations change depending 
on the time of day because of the transit schedules.  The output gives the 
total number of destinations reachable at least once as well as the number of 
destinations reachable at least 10%, 20%, ...90% of start times during the time 
window.  The number of reachable destinations can be weighted based on a field, 
such as the number of jobs available at each destination.  The tool also 
calculates the percentage of total destinations reachable.'''
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
import AnalysisHelpers
arcpy.env.overwriteOutput = True

class CustomError(Exception):
    pass

try:

    #Check out the Network Analyst extension license
    if arcpy.CheckExtension("Network") == "Available":
        arcpy.CheckOutExtension("Network")
    else:
        arcpy.AddError("You must have a Network Analyst license to use this tool.")
        raise CustomError


    # ----- Get and process inputs -----

    # OD layer from the map or .lyr file that with all the desired settings
    # (except time of day - we'll adjust that in this script)
    # Does not need Origins and Destinations loaded. We'll do that in the script.
    input_network_analyst_layer = arcpy.GetParameter(0)
    desc = arcpy.Describe(input_network_analyst_layer)
    if desc.dataType != "NALayer" or desc.solverName != "OD Cost Matrix Solver":
        arcpy.AddError("Input layer must be an OD Cost Matrix layer.")
        raise CustomError
    
    # Origins and Destinations
    origins_feature_class = arcpy.GetParameterAsText(1)
    destinations_feature_class = arcpy.GetParameterAsText(2)
    destinations_weight_field = arcpy.GetParameterAsText(3)

    # Start and end day and time
    start_day_input = arcpy.GetParameterAsText(4)
    end_day_input = arcpy.GetParameterAsText(6)
    start_time_input = arcpy.GetParameterAsText(5)
    end_time_input = arcpy.GetParameterAsText(7)
    increment_input = arcpy.GetParameter(8)

    # Make list of times of day to run the analysis
    timelist = AnalysisHelpers.make_analysis_time_of_day_list(start_day_input, end_day_input, start_time_input, end_time_input, increment_input)

    
    # ----- Add Origins and Destinations to the OD layer -----

    arcpy.AddMessage("Adding Origins and Destinations to OD Cost Matrix Layer...")

    # Get the sublayer names and objects for use later
    sublayer_names = arcpy.na.GetNAClassNames(input_network_analyst_layer) # To ensure compatibility with localized software
    origins_sublayer_name = sublayer_names["Origins"]
    destinations_sublayer_name = sublayer_names["Destinations"]
    lines_sublayer_name = sublayer_names["ODLines"]
    origins_subLayer = arcpy.mapping.ListLayers(input_network_analyst_layer, origins_sublayer_name)[0]
    destinations_subLayer = arcpy.mapping.ListLayers(input_network_analyst_layer, destinations_sublayer_name)[0]
    lines_subLayer = arcpy.mapping.ListLayers(input_network_analyst_layer, lines_sublayer_name)[0]

    # Keep track of the ObjectID field of the input
    desc = arcpy.Describe(origins_feature_class)
    origins_objectID = desc.OIDFieldName
    desc = arcpy.Describe(destinations_sublayer_name)
    destinations_objectID = desc.OIDFieldName
    arcpy.na.AddFieldToAnalysisLayer(input_network_analyst_layer, origins_sublayer_name, "InputOID", "LONG")
    fieldMappings_origins = arcpy.na.NAClassFieldMappings(input_network_analyst_layer, origins_sublayer_name)
    fieldMappings_origins["InputOID"].mappedFieldName = origins_objectID
    arcpy.na.AddFieldToAnalysisLayer(input_network_analyst_layer, destinations_sublayer_name, "InputOID", "LONG")
    fieldMappings_destinations = arcpy.na.NAClassFieldMappings(input_network_analyst_layer, destinations_sublayer_name)
    fieldMappings_destinations["InputOID"].mappedFieldName = destinations_objectID

    # Add origins and destinations
    arcpy.na.AddLocations(input_network_analyst_layer, origins_sublayer_name, origins_feature_class, fieldMappings_origins, "", append="CLEAR")
    arcpy.na.AddLocations(input_network_analyst_layer, destinations_sublayer_name, destinations_feature_class, fieldMappings_destinations, "", append="CLEAR")

    # Create dictionary linking the ObjectID fields of the input feature classes and the NA sublayers
    # We need to do this because, particularly when the NA layer already had data in it, the ObjectID
    # values don't always start with 1.
    origins_oid_dict = {} # {Input feature class Object ID: Origins sublayer OID}
    origin_ids = []
    with arcpy.da.SearchCursor(origins_subLayer, ["OID@", "InputOID"]) as cur:
        for row in cur:
            origin_ids.append(row[0])
            origins_oid_dict[row[1]] = row[0]
    destinations_oid_dict = {} # {Destination sublayer OID, Input feature class Object ID: }
    with arcpy.da.SearchCursor(destinations_subLayer, ["OID@", "InputOID"]) as cur:
         for row in cur:
             destinations_oid_dict[row[0]] = row[1]


    # ----- Solve NA layer in a loop for each time of day -----

    # Initialize a dictionary for counting the number of times each destination is reached by each origin
    OD_count_dict = {} # {Origin OID: {Destination OID: Number of times reached}}
    for oid in origin_ids:
        OD_count_dict[oid] = {}
        for did in destinations_oid_dict:
            OD_count_dict[oid][did] = 0

    # Grab the solver properties object from the NA layer so we can set the time of day
    solverProps = arcpy.na.GetSolverProperties(input_network_analyst_layer)

    # Solve for each time of day and save output
    arcpy.AddMessage("Solving OD Cost matrix at time...")
    for t in timelist:
        arcpy.AddMessage(str(t))
        
        # Switch the time of day
        solverProps.timeOfDay = t
        
        # Solve the OD Cost Matrix
        arcpy.na.Solve(input_network_analyst_layer)

        # Read the OD matrix output and increment the dictionary
        # There is one entry in Lines for each OD pair that was reached within the cutoff time
        with arcpy.da.SearchCursor(lines_subLayer, ["OriginID", "DestinationID"]) as cur:
            for line in cur:
                OD_count_dict[line[0]][line[1]] += 1


    # ----- Calculate statistics and generate output -----

    arcpy.AddMessage("Calculating statistics and writing results...")

    # If the destinations are weighted (eg, number of jobs at each destination), track them here
    destination_weight_dict = {} # {Input Destinations feature class ObjectID: Weight}
    num_dests = 0
    if destinations_weight_field:
        with arcpy.da.SearchCursor(destinations_feature_class, ["OID@", destinations_weight_field]) as cur:
            for row in cur:
                destination_weight_dict[row[0]] = row[1]
                num_dests += row[1]
    else:
        num_dests = len(destinations_oid_dict)

    # Add fields to input origins for output statistics. If the fields already exist, this will do nothing.
    arcpy.management.AddField(origins_feature_class, "TotalDests", "LONG")
    arcpy.management.AddField(origins_feature_class, "PercDests", "DOUBLE")
    stats_fields = ["TotalDests", "PercDests"]
    for i in range(1, 10):
        dest_field = "DsAL%i0Perc" % i
        perc_field = "PsAL%i0Perc" % i
        stats_fields.append(dest_field)
        stats_fields.append(perc_field)
        arcpy.management.AddField(origins_feature_class, dest_field, "LONG")
        arcpy.management.AddField(origins_feature_class, perc_field, "DOUBLE")
    
    # For each origin, calculate statistics
    with arcpy.da.UpdateCursor(origins_feature_class, ["OID@"] + stats_fields) as cur:
        for row in cur:
            origin_OID = origins_oid_dict[row[0]]
            reachable_dests = 0
            # Dictionary to track not just whether a destination was ever reachable, but how frequently it was reachable
            # Keys are percentage of times reachable, 10% of times, 20% of times, etc.
            reachable_dests_perc = {i:0 for i in range(10, 100, 10)}
            # Loop through all destinations
            for dest in OD_count_dict[origin_OID]:
                if OD_count_dict[origin_OID][dest] > 0: # If this destination was ever reachable by this origin
                    # Calculate the percentage of start times when this destination was reachable
                    percent_of_times_reachable = (float(OD_count_dict[origin_OID][dest]) / float(len(timelist))) * 100
                    if destination_weight_dict:
                        # If using a weight field, determine how much weight reaching this destination contributes to the total
                        dests_to_add = destination_weight_dict[destinations_oid_dict[dest]]
                    else:
                        # Otherwise, just count it as 1
                        dests_to_add = 1
                    # Increment the total number of destinations that were ever reached by this origin
                    reachable_dests += dests_to_add
                    # Also increment the percentage counters
                    for perc in reachable_dests_perc:
                        # If the actual percent of times reached is greater than the counter threshold, increment the counter
                        if percent_of_times_reachable >= perc:
                            reachable_dests_perc[perc] += dests_to_add
            # Calculate the percentage of all destinations that were ever reached
            percent_dests = (float(reachable_dests) / float(num_dests)) * 100
            row[1] = reachable_dests
            row[2] = percent_dests
            # Populate the percent of times fields
            for r in range(0, 9):
                row[3 + 2*r] = reachable_dests_perc[10 + 10*r]
                # Calculate the percentage of all destinations that were reached at least this percent of times
                row[3 + 2*r + 1] = (float(reachable_dests_perc[10 + 10*r]) / float(num_dests)) * 100
            cur.updateRow(row)

    arcpy.AddMessage("Done!  Statistics fields have been added to your input Origins layer.")

except CustomError:
    pass
except:
    raise
