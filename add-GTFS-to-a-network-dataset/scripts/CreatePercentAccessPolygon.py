################################################################################
## Toolbox: Transit Analysis Tools
## Tool name: Create Percent Access Polygons
## Created by: David Wasserman, Fehr & Peers, https://github.com/d-wasserman
##        and: Melinda Morang, Esri
## Last updated: 8 September 2018
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

import os
import time
import uuid
import arcpy

# Create a GUID for temporary outputs (avoids naming conflicts)
guid = uuid.uuid4().hex


def create_polygon_raster_template(in_polys, outgdb, cell_size):
    '''Creates a raster-like polygon feature class covering the area of the original time lapse polygons.  Each polygon
    in the output is equivalent to one square of a raster.  The dataset is meant to be used with Spatial Join with the 
    original time lapse polygon dataset in order to count the number of original polygons overlapping that cell.
    Params:
    in_polys: path to the input time lapse polygon dataset generated from the Prepare Time Lapse Polygons tool.
    outgdb: path of workspace being used to store output from this tool
    cell_size: The length or width (not area) of the desired raster cell, in the units of the spatial reference of the
    '''

    # Convert the full time lapse dataset into a temporary raster. The cell values are irrelvant.
    poly_oid = arcpy.Describe(in_polys).OIDFieldName
    temp_raster = os.path.join(outgdb, "Temp_" + guid + "_InitialRaster")
    arcpy.conversion.FeatureToRaster(in_polys, poly_oid, temp_raster, cell_size=cell_size)

    # Create a temporary point dataset with one point for the centroid of every raster cell
    # The value of the points is irrelevant. We just need their geometry and an OID.
    temp_points = os.path.join(outgdb, "Temp_" + guid + "_Points")
    arcpy.conversion.RasterToPoint(temp_raster, temp_points)

    # Create a new raster from the points with the same cell size as the initial raster. Set the value of each cell
    # equal to the value of the OID of the point it was created from.  This way, each cell has a unique value.
    pt_oid = arcpy.Describe(temp_points).OIDFieldName
    temp_raster2 = os.path.join(outgdb, "Temp_" + guid + "_ProcessedRaster")
    arcpy.conversion.FeatureToRaster(temp_points, pt_oid, temp_raster2, cell_size=cell_size)

    # Convert this raster to polygons.  The result contains one square polygon per raster cell and can be used for
    # calculating spatial joins with the original time lapse polygon dataset.
    poly_raster_template_fc = os.path.join(outgdb, "Temp_" + guid + "_PolyRasterTemplate")
    arcpy.conversion.RasterToPolygon(temp_raster2, poly_raster_template_fc, simplify=False)

    # Clean up intermediate outputs
    clean_up = [temp_raster, temp_points, temp_raster2]
    for temp_output in clean_up:
        arcpy.management.Delete(temp_output)

    return poly_raster_template_fc


def generate_field_map(in_time_lapse_polys, fields_to_preserve):
    '''Create a FieldMappings object to use in Spatial Join.  For our application, we only want to preserve a few fields
    for informational purposes.  We expect all these field values to be the same, so use the "First" rule so the output
    polygon will just keep the same value as the inputs.  All other fields in the input data will not be transferred to
    the output.
    Params:
    in_time_lapse_polys: Time lapse polygon feature class from which to retrieve the fields
    fields_to_preserve: A list of field names we want to keep for the output.
    '''
    field_mappings = arcpy.FieldMappings()
    for field in fields_to_preserve:
        fmap = arcpy.FieldMap()
        fmap.addInputField(in_time_lapse_polys, field) 
        fmap.mergeRule = "First"
        field_mappings.addFieldMap(fmap)
    return field_mappings


def create_raw_cell_counts_fc(selected_time_lapse_polys, in_poly_raster_template, temp_spatial_join_fc, fmaps, 
                              match_option):
    '''Do a spatial join in order to count the number of time lapse polygons intersect each "cell" in the raster-like
    polylgon template.  We are effectively applying the template to a specific set of time lapse polygons, doing the
    count, and creating the raw output.  The result is a polygon feature class of raster-like cells with a field called
    Join_Count that shows the number of input time lapse polygons that intersect the cell using the specified
    match_option.
    Params:
    selected_time_lapse_polys: Set (or subset) of time lapse polygons to use
    in_poly_raster_template: The raster-like polygon feature class produced from create_polygon_raster_template()
    temp_spatial_join_fc: Path to a temporary output FC which we will overwrite each time this method is called and then
        delete at the end of the tool during clean-up
    fmaps: FieldMappings object indicating which fields to preserve
    match_options: match_options parameter for the Spatial Join tool
    '''

    arcpy.analysis.SpatialJoin(
        in_poly_raster_template,
        selected_time_lapse_polys,
        temp_spatial_join_fc,
        "JOIN_ONE_TO_ONE", # Output keeps only one copy of each "cell" when multiple time lapse polys intersect it
        "KEEP_COMMON", # Delete any "cells" that don't overlap the time lapse polys being considered
        field_mapping=fmaps, # Preserve some fields from the original data
        match_option=match_option
        )


def dissolve_raw_cell_counts_fc(raw_cell_count_fc, out_fc, fields_to_preserve, num_time_steps):
    '''Currently, the feature class contains a large number of little square polygons representing raster cells. The
    Join_Count field added by Spatial Join says how many of the input time lapse polygons overlapped the cell.  We 
    don't need all the little squares.  We can dissolve them so that we have one polygon per unique value of 
    Join_Count. Also calculate a field showing the Percent of times each polygon was reached.
    Params:
    raw_cell_count_fc: The feature class of raster-like polygons created from create_raw_cell_counts_fc()
    out_fc: Path to output feature class
    fields_to_preserve: Informational fields to preserve in the output
    num_time_steps: Number of time steps used in the overall time lapse polygons
    '''

    arcpy.management.Dissolve(raw_cell_count_fc, out_fc, fields_to_preserve + ["Join_Count"])

    # Add a field converting the raw count to the percent of total times accessed
    percent_field = "Percent"
    arcpy.management.AddField(out_fc, percent_field, "DOUBLE")
    expression = "float(!Join_Count!) * 100.0 / float(%d)" % num_time_steps
    arcpy.management.CalculateField(out_fc, percent_field, expression, "PYTHON_9.3")


def create_percent_access_polys(raw_cell_counts, percents, out_fc, fields_to_preserve, scratch_workspace):
    '''For each percent threshold, dissolve the cells where the number of times reached exceeds the threshold. Each
    threshold gets its own polygon, and they are all output to the same feature class.
    Params:
    raw_cell_counts: Feature class of cell-like polygons with counts generated from create_raw_cell_counts_fc()
    count_field: The field in raw_cell_counts containing the number of times the cell was reached
    percents: List of percents to calculate results for. Example: 80 means crate a polygon representing the area that
        could be reached for at least 80% of start times.
    num_time_steps: The total number of time steps present in the input time lapse polygon dataset
    out_fc: Path of the output feature class for storing the percent access polygons
    '''

    first = True
    temp_out_dissolve_fc = os.path.join(scratch_workspace, "Temp_" + guid + "_Dissolve")
    for percent in sorted(percents):

        # Select all the cells where the number of times with access is >= our percent threshold
        # The result is all the cells that are reachable at least X% of start times
        query = arcpy.AddFieldDelimiters(raw_cell_counts, "Percent") + " >= " + str(percent)
        percent_layer = arcpy.management.MakeFeatureLayer(raw_cell_counts, "PercentLayer", query).getOutput(0)

        # Dissolve everything that meets the threshold into one polygon
        if first:
            out_Dissolve = out_fc
        else:
            out_Dissolve = temp_out_dissolve_fc
        arcpy.management.Dissolve(percent_layer, out_Dissolve, fields_to_preserve)

        percent_field = "Percent"
        arcpy.management.AddField(out_Dissolve, percent_field, "DOUBLE")
        arcpy.management.CalculateField(out_Dissolve, percent_field, str(percent))

        if not first:
            # If this wasn't the first percent output, append it to the master output fc
            arcpy.management.Append(out_Dissolve, out_fc, "TEST")
        first = False

    # Clean up temporary output
    if arcpy.Exists(temp_out_dissolve_fc):
        arcpy.management.Delete(temp_out_dissolve_fc)


def main():

    arcpy.env.overwriteOutput = True
    # Use the scratchGDB as a holder for temporary output
    scratchgdb = arcpy.env.scratchGDB

    # Feature class of polygons created by the Prepare Time Lapse Polygons tool
    # The feature class must be in a projected coordinate system, but this is checked in tool validation
    in_time_lapse_polys = arcpy.GetParameterAsText(0)
    out_cell_counts_fc = arcpy.GetParameterAsText(1)
    # Raster cell size for output (length or width of cell, not area)
    cell_size = float(arcpy.GetParameterAsText(2))
    out_percents_fc = arcpy.GetParameterAsText(4)
    # List of percent of times accessed to summarize in results
    if not out_percents_fc:
        percents = []
    else:
        percents = arcpy.GetParameter(5)

    # Hard-coded "options"
    # Field names that must be in the input time lapse polygons
    facility_id_field = "FacilityID"
    name_field = "Name"
    frombreak_field = "FromBreak"
    tobreak_field = "ToBreak"
    time_field = "TimeOfDay"
    # Match option to use in the spatial join
    match_option = "HAVE_THEIR_CENTER_IN"
    # Fields we want to keep around in the output
    fields_to_preserve = [facility_id_field, name_field, frombreak_field, tobreak_field]

    # Create the raster-like polygons we'll use later with spatial joins.
    arcpy.AddMessage("Rasterizing time lapse polygons...")
    poly_raster_template_fc = create_polygon_raster_template(in_time_lapse_polys, scratchgdb, cell_size)

    # Figure out the unique combinations of FacilityID, FromBreak, and ToBreak in the input data. Each of these will
    # be processed sequentially and get a separate output.
    # Also count the number of unique times of day that were used in the original analysis so we can calculate % later.
    unique_output_combos = []
    unique_times = []
    fields = [facility_id_field, frombreak_field, tobreak_field, time_field]
    with arcpy.da.SearchCursor(in_time_lapse_polys, fields) as cur:
        for row in cur:
            unique_output_combos.append((row[0], row[1], row[2]))
            unique_times.append(row[3])
    unique_output_combos = sorted(set(unique_output_combos))
    num_time_steps = len(set(unique_times))

    # For each set of time lapse polygons, generate the cell-like counts
    first = True
    temp_spatial_join_fc = os.path.join(scratchgdb, "Temp_" + guid + "_SpatialJoin")
    temp_raw_dissolve_fc = os.path.join(scratchgdb, "Temp_" + guid + "_RawDissolve")
    for combo in unique_output_combos:
        facility_id = combo[0]
        from_break = combo[1]
        to_break = combo[2]

        if facility_id is None:
            msg = "Processing FacilityID <Null>, FromBreak %d, ToBreak %d" % (from_break, to_break)
        else:
            msg = "Processing FacilityID %i, FromBreak %d, ToBreak %d" % (facility_id, from_break, to_break)
        arcpy.AddMessage(msg + "...")

        # Select the subset of polygons for this FacilityID/FromBreak/ToBreak combo
        # Note: Don't use a feature layer and Select By Attributes because of a bug with field mapping in Spatial Join
        # in 10.6 which caused field maps to be ignored for layers.
        temp_selected_polys = os.path.join(scratchgdb, "Temp_" + guid + "_SelectedPolys")
        if facility_id is None:
            facility_query = arcpy.AddFieldDelimiters(in_time_lapse_polys, facility_id_field) + " IS NULL"
        else:
            facility_query = arcpy.AddFieldDelimiters(in_time_lapse_polys, facility_id_field) + " = " + str(facility_id)
        query = facility_query + " AND " + \
                arcpy.AddFieldDelimiters(in_time_lapse_polys, frombreak_field) + " = " + str(from_break) + " AND " + \
                arcpy.AddFieldDelimiters(in_time_lapse_polys, tobreak_field) + " = " + str(to_break)
        arcpy.analysis.Select(in_time_lapse_polys, temp_selected_polys, query)

        # Create a FieldMappings object for Spatial Join to preserve informational input fields
        fmaps = generate_field_map(temp_selected_polys, fields_to_preserve)

        # Count the number of time lapse polygons that intersect each "cell" in the raster-like polygon template and
        # write out a new feature class to disk that shows the counts
        # Create the raw output
        create_raw_cell_counts_fc(
            temp_selected_polys,
            poly_raster_template_fc,
            temp_spatial_join_fc,
            fmaps,
            match_option
            )
        # Dissolve all the little cells that were reached the same number of times to make the output more manageable
        if first:
            out_raw_dissolve = out_cell_counts_fc
        else:
            out_raw_dissolve = temp_raw_dissolve_fc
        dissolve_raw_cell_counts_fc(temp_spatial_join_fc, out_raw_dissolve, fields_to_preserve, num_time_steps)
        if not first:
            # If this wasn't the first output, append it to the master output fc
            arcpy.management.Append(out_raw_dissolve, out_cell_counts_fc, "TEST")

        # Finished with the first loop
        first = False

    # Dissolve the cell-like polygons that were accessible >= X% of times
    if percents:
        arcpy.AddMessage("Creating percent access polygons...")
        create_percent_access_polys(out_cell_counts_fc, percents, out_percents_fc, fields_to_preserve, scratchgdb)        

    # Clean up intermediate outputs
    clean_up = [
        temp_selected_polys,
        poly_raster_template_fc,
        temp_spatial_join_fc,
        temp_raw_dissolve_fc
        ]
    for temp_output in clean_up:
        if arcpy.Exists(temp_output):
            arcpy.management.Delete(temp_output)


if __name__ == '__main__':
    main()
