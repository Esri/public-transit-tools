################################################################################
## Toolbox: Determine Time Lapse Polygon Percent Accessibility / Transit Analysis Tools
## Tool name: Calculate Accessibility Matrix
## Created by: David Wasserman, Fehr & Peers, d.wasserman@fehrandpeers.com
## Last updated: 18 May 2019
################################################################################
''''''
################################################################################
'''Copyright 2018 Fehr & Peers
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
# Import Modules
import os, arcpy


def construct_sql_equality_query(fieldName, value, dataSource, equalityOperator="=", noneEqualityOperator="is"):
    """Creates a workspace sensitive equality query to be used in arcpy/SQL statements. If the value is a string,
    quotes will be used for the query, otherwise they will be removed. Python 2-3 try except catch.(BaseString not in 3)
    David Wasserman- Apache 2.0 Source:
    https://github.com/Holisticnature/arc-numerical-tools/blob/master/Scripts/SharedArcNumericalLib.py
    :params
    fieldName(str): field name in sql query to return
    value(str): value for target query
    dataSource(str): path of the workspace of the feature receiving the query - impacts delimiter options.
    equalityOperator(str): the operator used to build a query relationship between fieldName and value.
    noneEqualityOperator: operator used if the target value is None/Null
    :returns sql query string with appropriate delimiters
    """
    try:  # Python 2
        if isinstance(value, (basestring, str)):
            return "{0} {1} '{2}'".format(arcpy.AddFieldDelimiters(dataSource, fieldName), equalityOperator, str(value))
        if value is None:
            return "{0} {1} {2}".format(arcpy.AddFieldDelimiters(dataSource, fieldName), noneEqualityOperator, "NULL")
        else:
            return "{0} {1} {2}".format(arcpy.AddFieldDelimiters(dataSource, fieldName), equalityOperator, str(value))
    except:  # Python 3
        if isinstance(value, (str)):  # Unicode only
            return "{0} {1} '{2}'".format(arcpy.AddFieldDelimiters(dataSource, fieldName), equalityOperator, str(value))
        if value is None:
            return "{0} {1} {2}".format(arcpy.AddFieldDelimiters(dataSource, fieldName), noneEqualityOperator, "NULL")
        else:
            return "{0} {1} {2}".format(arcpy.AddFieldDelimiters(dataSource, fieldName), equalityOperator, str(value))


def generate_statistical_fieldmap(target_features, join_features, prepended_name="", merge_rule_dict={}):
    """Generates field map object based on passed field objects based on passed tables (list),
    input_field_objects (list), and passed statistics fields to choose for numeric and categorical variables. Output
    fields take the form of *merge rule*+*prepended_name*+*fieldname* David Wasserman - Apache 2.0 - Source:
    https://github.com/Holisticnature/arc-numerical-tools/blob/master/Scripts/SharedArcNumericalLib.py
    :params
    target_features(str): target feature class that will maintain its field attributes
    join_features(str): join feature class whose numeric fields will be joined based on the merge rule dictionary
    prepended_name(str): modifies output join fields with param text between the statistics and the original field name
    merge_rule_dict (dict): a  dictionary of the form {statistic_type:[Fields,To,Summarize]}
    :returns arcpy field mapping object
    """
    field_mappings = arcpy.FieldMappings()
    field_mappings.addTable(target_features)
    for merge_rule in merge_rule_dict:
        for field in merge_rule_dict[merge_rule]:
            new_field_map = arcpy.FieldMap()
            new_field_map.addInputField(join_features, field)
            new_field_map.mergeRule = merge_rule
            out_field = new_field_map.outputField
            out_field.name = str(merge_rule) + str(prepended_name) + str(field)
            out_field.aliasName = str(merge_rule) + str(prepended_name) + str(field)
            new_field_map.outputField = out_field
            field_mappings.addFieldMap(new_field_map)
    return field_mappings


def get_percentage_access_isochrone(in_path, outfile, facility_field="FacilityID",name_field="Name", tobreak_field="ToBreak",
                                    time_field="TimeOfDay"):
    """This script/notebook aims transform a TimeLapsedPolygon into a percentage of access coverage polygon where
    each polygon represents the percentage of time transit can access a specific location.
    Params:
    in_path: path to the TimeLapsedPolygon output.
    outfile: output path of the percentage coverage polygon.
    facility_field: the facilityID of the chosen TimeLapsePolygons.
    time_field: the datetime field of the chosen TimeLapsePolygons.
    to_break_field: the To Break field of the chosen TimeLapsePolygons.
    """
    arcpy.env.overwriteOutput = True
    workspace = "in_memory"
    # Get facilities as unique values and the number of time periods.
    unique_values = sorted(set([row[0] for row in arcpy.da.SearchCursor(in_path, [facility_field])]))
    unique_times = sorted(set([row[0] for row in arcpy.da.SearchCursor(in_path, [time_field])]))
    unique_breaks = sorted(set([row[0] for row in arcpy.da.SearchCursor(in_path, [tobreak_field])]))
    facility_count = len(unique_values)
    time_period_count = len(unique_times)
    arcpy.AddMessage("Time period count is:{0}".format(time_period_count))

    # Add a field for counting the sum of total time periods
    raw_iso_fields = []
    for idx, brk in enumerate(unique_breaks):
        break_text = "P"+int(brk*100) if brk<1 else int(brk)
        isochrone_count = "TP{0}Cnt{1}".format(break_text, idx)
        arcpy.AddMessage("Adding a field for counting isochrone break {0} named {1}...".format(brk,isochrone_count))
        arcpy.AddField_management(in_path, isochrone_count, "LONG")
        arcpy.CalculateField_management(in_path, isochrone_count, expression="flag_break(!{0}!,{1})".format(
            tobreak_field, brk),expression_type="PYTHON_9.3", code_block=
                                        """def flag_break(break_field,target_break):
                                            if break_field==target_break:
                                                return 1
                                            else:
                                                return 0 """)
        raw_iso_fields.append(isochrone_count)
    sum_fields = ["SUM"+str(fieldname) for fieldname in raw_iso_fields]
    # Establish counters
    counter = 0
    # Define Output Paths
    temp_layer = "FacilityIso"
    temp_union = os.path.join(workspace, "TempUnion")
    temp_join = os.path.join(workspace, "TempJoin")
    temp_final_dis = os.path.join(workspace, "TempDissFin")
    arcpy.AddMessage("Processing isochrones...")
    percent_ranges = list(range(0, 101, 10))
    for value in unique_values:
        try:
            query = construct_sql_equality_query(facility_field, value, workspace)
            arcpy.MakeFeatureLayer_management(in_path, temp_layer, query)
            arcpy.Union_analysis(temp_layer, temp_union, cluster_tolerance=None)
            merge_rules = {"SUM": raw_iso_fields}
            fmap = generate_statistical_fieldmap(temp_union, temp_layer, merge_rule_dict=merge_rules)
            # Spatial join with fmap field map will only associate the count field sum with the unioned feature class
            arcpy.SpatialJoin_analysis(temp_union, temp_layer, temp_join, field_mapping=fmap, search_radius="-.001 Feet")
            # The raw union is very geometrically complex. Dissolve shapes of the same coverage count.
            dissolve_fields = [facility_id]+ sum_fields
            arcpy.Dissolve_management(temp_join, temp_final_dis,dissolve_field=dissolve_fields,statistics_fields=
                                      [[name_field,"FIRST"]])
            # If the file does not exist or the counter is 0- copy the facility selection to a new feature class
            if not arcpy.Exists(outfile) or counter == 0:
                arcpy.CopyFeatures_management(temp_final_dis, outfile)
            # If the file exists, append the facilities output to the output feature class.
            else:
                arcpy.Append_management(temp_final_dis, outfile)
            # Increment Counter and Provide Percentage complete.
            counter += 1
            if 100 * (counter / facility_count) >= percent_ranges[0]:
                arcpy.AddMessage("Processed {0}% of facilities...".format(percent_ranges[0]))
                del percent_ranges[0]
        except:
            arcpy.AddWarning("Failed to compute percentage access polygon for facility : {0}".format(value))
            counter += 1
    for idx, brk in enumerate(unique_breaks):
        break_text = "P" + str(int(brk * 100)) if brk < 1 else int(brk)
        TPCoverage = "TPCv{0}_{1}Perc".format(break_text,idx)
        arcpy.AddMessage("Computing percentage coverage for field {0}...".format(TPCoverage))
        try:
            arcpy.AddField_management(outfile, TPCoverage, "DOUBLE")
            arcpy.CalculateField_management(outfile, TPCoverage,
                                            expression="float(!{0}!)/float({1})".format(sum_fields[idx],
                                                                                        time_period_count),
                                            expression_type="PYTHON_9.3")
        except:
            arcpy.AddWarning("Could not calculate percentage of time periods covered.")
    print("Script Completed Successfully.")


if __name__ == '__main__':
    filepath = arcpy.GetParameterAsText(0)
    outfile = arcpy.GetParameterAsText(1)
    facility_id = arcpy.GetParameterAsText(2)
    name_field = arcpy.GetParameterAsText(3)
    tobreak_field = arcpy.GetParameterAsText(4)
    time_period_field = arcpy.GetParameterAsText(5)
    get_percentage_access_isochrone(filepath, outfile, facility_field=facility_id,name_field=name_field,
                                    tobreak_field=tobreak_field,time_field=time_period_field)
