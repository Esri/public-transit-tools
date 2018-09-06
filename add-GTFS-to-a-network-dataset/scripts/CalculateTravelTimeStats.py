################################################################################
## Toolbox: Add GTFS to a Network Dataset / Transit Analysis Tools
## Tool name: Calculate Travel Time Statistics
## Created by: Melinda Morang, Esri
## Last updated: 6 September 2018
################################################################################
'''Solve an OD Cost Matrix or Route iteratively over a time window and output a 
table of statistics describing the travel time over the time window for each
origin-destination pair or route:
- minimum travel time
- maximum travel time
- mean travel time
- number of times the origin-destination pair or route was considered
'''
################################################################################
'''Copyright 2018 Esri
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

    # OD or Route layer from the map or .lyr file that with all the desired settings
    # (except time of day - we'll adjust that in this script)
    input_network_analyst_layer = arcpy.GetParameter(0)
    desc = arcpy.Describe(input_network_analyst_layer)
    if desc.dataType != "NALayer" or desc.solverName not in ["OD Cost Matrix Solver", "Route Solver"]:
        arcpy.AddError("Input layer must be an OD Cost Matrix or Route layer.")
        raise CustomError

    # Solver-specific properties used later
    if desc.solverName == "OD Cost Matrix Solver":
        solver_opts = {
            "Friendly Name": "OD Cost Matrix",
            "Output Sublayer Name": "ODLines",
            "Key fields": [("OriginID", "LONG", None), ("DestinationID", "LONG", None)]
        }
    elif desc.solverName == "Route Solver":
        solver_opts = {
            "Friendly Name": "Route",
            "Output Sublayer Name": "Routes",
            "Key fields": [("Name", "TEXT", 1024)]
        }

    # Output table
    output_table = arcpy.GetParameterAsText(1)

    # Start and end day and time
    start_day_input = arcpy.GetParameterAsText(2)
    end_day_input = arcpy.GetParameterAsText(4)
    start_time_input = arcpy.GetParameterAsText(3)
    end_time_input = arcpy.GetParameterAsText(5)
    increment_input = arcpy.GetParameter(6)

    # Make list of times of day to run the analysis
    try:
        timelist = AnalysisHelpers.make_analysis_time_of_day_list(start_day_input, end_day_input, start_time_input, end_time_input, increment_input)
    except:
        raise CustomError

    # Get the sublayer names and objects for use later
    sublayer_names = arcpy.na.GetNAClassNames(input_network_analyst_layer) # To ensure compatibility with localized software
    output_sublayer_name = sublayer_names[solver_opts["Output Sublayer Name"]]
    output_subLayer = arcpy.mapping.ListLayers(input_network_analyst_layer, output_sublayer_name)[0]


    # ----- Solve NA layer in a loop for each time of day -----

    # Grab the solver properties object from the NA layer so we can set the time of day
    solverProps = arcpy.na.GetSolverProperties(input_network_analyst_layer)

    # Throw a warning for OD if the layer uses a cutoff or number of destinations to find because results might be weird.
    if desc.solverName == "OD Cost Matrix Solver":
        if solverProps.defaultCutoff:
            msg = "Your OD Cost Matrix layer uses a default cutoff of %s. At some times of day, the travel time " + \
                "between origins and destinations may exceed this default cutoff, so the travel time between the " + \
                "origin and destination will not be reported. These cases will not be included in the statistics " + \
                "calculated in the output of this tool.  The minimum travel time value should be correct, but the " + \
                "maximum and mean may not."
            arcpy.AddWarning(msg % str(solverProps.defaultCutoff))
        if solverProps.defaultTargetDestinationCount:
            count = int(solverProps.defaultTargetDestinationCount)
            msg = "Your OD Cost Matrix layer uses a default target destination count of %i. This means that the " + \
                "travel time for only the %i closest destinations to each origin will be reported in the OD Cost " + \
                "Matrix output.  Because the travel time between each origin and destination changes throughout " + \
                "the day, the closest destinations may be different at different times of day, so the statistics " + \
                "reported for each origin-destination pair in the output of this tool may be inaccurate."
            arcpy.AddWarning(msg % (count, count))

    # Initialize a dictionary to track output stats
    # {key: [Min travel time, Max travel time, Num times reached, Mean travel time]}
    # OD key: (OriginID, DestinationID)
    # RT key: Name
    travelTimeStatsDict = {}

    # Solve for each time of day and save output
    arcpy.AddMessage("Solving %s at time..." % solver_opts["Friendly Name"])
    for t in timelist:
        arcpy.AddMessage(str(t))

        # Switch the time of day
        solverProps.timeOfDay = t

        # Solve the OD Cost Matrix
        try:
            arcpy.na.Solve(input_network_analyst_layer)
        except:
            # Solve failed.  It could be that no destinations were reachable within the time limit,
            # or it could be another error.  Running out of memory is a distinct possibility.
            errs = arcpy.GetMessages(2)
            if "No solution found" not in errs:
                # Only alert them if it's some weird error.
                arcpy.AddMessage("Solve failed.  Errors: %s. Continuing to next time of day." % errs)
            continue

        # Read the OD matrix output and populate the dictionary with the min travel time for each OD pair
        cur_fields = ["Total_" + solverProps.impedance] + [kf[0] for kf in solver_opts["Key fields"]]
        with arcpy.da.SearchCursor(output_subLayer, cur_fields) as cur:
            for line in cur:
                # The key is a tuple of all the designated key fields for this solver type
                # Example: (1, 2) for OriginID 1 and DestinationID 2
                key = tuple([line[i] for i in range(1, len(cur_fields))])
                if key not in travelTimeStatsDict:
                    # Initialize the stats dictionary entry for this OD pair or Route Name
                    travelTimeStatsDict[key] = [line[0], line[0], 1, line[0]]
                else:
                    # Update the currently stored value if needed
                    # [Min travel time, Max travel time, Num times reached, Mean travel time]
                    # Minimum travel time
                    travelTimeStatsDict[key][0] = min(travelTimeStatsDict[key][0], line[0])
                    # Maximum travel time
                    travelTimeStatsDict[key][1] = max(travelTimeStatsDict[key][1], line[0])
                    # Mean travel time
                    numTimesSoFar = travelTimeStatsDict[key][2]
                    currentMean = travelTimeStatsDict[key][3]
                    travelTimeStatsDict[key][3] = ((numTimesSoFar * currentMean) + line[0]) / (numTimesSoFar + 1)
                    # Number of times this pair has been reached
                    travelTimeStatsDict[key][2] += 1

    # ----- Generate output -----

    arcpy.AddMessage("Writing results...")

    arcpy.management.CreateTable(os.path.dirname(output_table), os.path.basename(output_table))
    out_fields = solver_opts["Key fields"] + [
        ("Min_" + solverProps.impedance, "DOUBLE", None),
        ("Max_" + solverProps.impedance, "DOUBLE", None),
        ("Mean_" + solverProps.impedance, "DOUBLE", None),
        ("NumTimes", "SHORT", None)
    ]
    for field in out_fields:
        arcpy.management.AddField(output_table, field[0], field[1], field_length=field[2])

    # For each origin, calculate statistics
    with arcpy.da.InsertCursor(output_table, [f[0] for f in out_fields]) as cur:
        for key in sorted(travelTimeStatsDict.keys()):
            row = list(key) + [
                travelTimeStatsDict[key][0],
                travelTimeStatsDict[key][1],
                travelTimeStatsDict[key][3],
                travelTimeStatsDict[key][2]
                ]
            cur.insertRow(row)

    arcpy.AddMessage("Done!")

except CustomError:
    pass
except:
    raise
