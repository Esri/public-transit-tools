############################################################################
## Tool name: Transit Network Analysis Tools
## Created by: Melinda Morang, Esri
## Last updated: 16 August 2024
############################################################################
"""
This is a shared module with classes for replacing the geometry of routes
generated by Route or Closest Facility solves using the Public Transit
evaluator.  The original routes use the geometry of the LineVariantElements
feature class of the Public Transit Data Model, and these features are generally
straight lines connecting adjacent stops and are not intended for visualization.
If the Public Transit Data Model includes the LVEShapes feature class, the
straight-line geometry can be swapped for the cartographic lines from LVEShapes
as a post-process, and that's what this class does.

The RouteShapeReplacer class can be used with a traversal result generated from
a network analysis layer or a Route solver object.

Copyright 2024 Esri
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
import os
import arcpy
from AnalysisHelpers import TransitNetworkAnalysisToolsError


class TransitDataModel:  # pylint: disable=too-many-instance-attributes
    """Defines and validates the Public Transit Data Model as relevant to this tool."""

    def __init__(self, transit_fd: str):
        """Define the Public Transit Data Model as relevant to this tool."""
        # For details on the Public Transit Data Model, see
        # https://pro.arcgis.com/en/pro-app/latest/help/analysis/networks/transit-data-model.htm
        self.line_variant_elements = os.path.join(transit_fd, "LineVariantElements")
        self.lve_shapes = os.path.join(transit_fd, "LVEShapes")
        self.required_tables = [self.line_variant_elements, self.lve_shapes]
        self.required_fields = {
            self.line_variant_elements: ["LVEShapeID"],
            self.lve_shapes: ["ID"]
        }

    def validate_tables_exist(self):
        """Validate that the required Public Transit Data Model feature classes and tables exist.

        Raises:
            TransitNetworkAnalysisToolsError: If not all required fields are present.
        """
        # Check for required feature classes and tables
        tables_exist = True
        for table in self.required_tables:
            if not arcpy.Exists(table):
                tables_exist = False
        if not tables_exist:
            # One or more Public Transit Data Model tables does not exist.
            raise TransitNetworkAnalysisToolsError(
                arcpy.GetIDMessage(2922) + f" Required: LineVariantElements, LVEShapes")

    def validate_required_fields(self):
        """Validate that the transit data model feature classes and tables have the required fields for this tool.

        Raises:
            TransitNetworkAnalysisToolsError: If not all required fields are present.
        """
        for table in self.required_fields:
            # Compare in lower case because SDE switches the case around. Oracle is all upper. Postgres is all lower.
            required_fields_lower = [f.lower() for f in self.required_fields[table]]
            actual_fields = [f.name.lower() for f in arcpy.ListFields(table)]
            if not set(required_fields_lower).issubset(set(actual_fields)):
                # Public transit data model table %1 is missing one or more required fields. Required fields: %2
                msg = arcpy.GetIDMessage(2925) % (table, ", ".join(self.required_fields[table]))
                raise TransitNetworkAnalysisToolsError(msg)


class RouteShapeReplacer:
    """Enrich an ordinary traversal result with public transit info."""

    def __init__(self, traversed_edges_fc, transit_fd):
        """Initialize the route shape replacer for the given analysis.

        Args:
            traversed_edges_fc (str or layer): Feature class layer or catalog path containing the Edges portion of a
                traversal result. Typically obtained from the Copy Traversed Source Features tool or the RouteEdges
                output from a solver result object.
            transit_fd (str): Catalog path to the feature dataset containing the transit-enabled network dataset used
                for the analysis and its associated Public Transit Data Model feature classes.
        """
        self.traversed_edges_fc = traversed_edges_fc

        # Validate basic inputs
        if not isinstance(transit_fd, str):
            raise TransitNetworkAnalysisToolsError("Invalid Public Transit Data Model feature dataset.")

        # Initialize the Public Transit Data Model tables
        self.transit_dm = TransitDataModel(transit_fd)
        # Validate Public Transit Data Model
        self.transit_dm.validate_tables_exist()
        self.transit_dm.validate_required_fields()

        # Validate traversal result
        if not arcpy.Exists(self.traversed_edges_fc):
            raise TransitNetworkAnalysisToolsError(
                f"The input traversed edges feature class {self.traversed_edges_fc} does not exist.")
        self.te_desc = arcpy.Describe(self.traversed_edges_fc)
        required_fields = ["SourceName", "SourceOID", "RouteID"]
        if not set(required_fields).issubset(set([f.name for f in self.te_desc.fields])):
            raise TransitNetworkAnalysisToolsError((
                f"The input traversed edges feature class {self.traversed_edges_fc} is missing one or more required "
                f"fields. Required fields: {required_fields}"
            ))

    def replace_route_shapes_with_lveshapes(self) -> dict:
        """Replace route shape geometry."""
        # Make layers to speed up search cursor queries later
        lve_lyr_name = "LineVariantElements"
        arcpy.management.MakeFeatureLayer(self.transit_dm.line_variant_elements, lve_lyr_name)
        lve_oid_field = arcpy.Describe(lve_lyr_name).oidFieldName
        lveshapes_lyr_name = "LVEShapes"
        arcpy.management.MakeFeatureLayer(self.transit_dm.lve_shapes, lveshapes_lyr_name)

        # Loop over traversed route segments and replace LineVariantElements geometry with LVEShapes geometry
        route_segments = {}
        fields = ["RouteID", "SHAPE@", "SourceName", "SourceOID"]
        for row in arcpy.da.SearchCursor(self.traversed_edges_fc, fields):  # pylint: disable=no-member
            segment_geom = row[1]
            if row[2] == "LineVariantElements":
                # Retrieve LVEShapes geometry
                try:
                    with arcpy.da.SearchCursor(lve_lyr_name, ["LVEShapeID"], f"{lve_oid_field} = {row[3]}") as cur:
                        lveshape_id = next(cur)[0]
                    if lveshape_id is not None:
                        with arcpy.da.SearchCursor(lveshapes_lyr_name, ["SHAPE@"], f"ID = {lveshape_id}") as cur:
                            lveshape_geom = next(cur)[0]
                            if lveshape_geom:
                                segment_geom = lveshape_geom
                except Exception:  # pylint: disable=broad-except
                    # Probably some kind of mismatch in OIDs or LVEShapeID field values. Just ignore this as invalid
                    # and leave the original geometry
                    pass

            # Store the route segment geometry as an array of vertices we'll use to construct the final polylines
            # getPart() retrieves an array of arrays of points representing the vertices of the polyline.
            for part in segment_geom.getPart():
                route_segments.setdefault(row[0], arcpy.Array()).extend(part)

        # Combine route segments into single lines per route
        route_geoms = {}
        for route_id, vertex_array in route_segments.items():
            route_geom = arcpy.Polyline(vertex_array, self.te_desc.spatialReference)
            route_geoms[route_id] = route_geom

        # Return dictionary of {route_id: route_geom}
        return route_geoms


if __name__ == "__main__":
    pass
