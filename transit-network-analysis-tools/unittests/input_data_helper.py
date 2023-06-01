"""Helper for unit tests to create required inputs.

Copyright 2023 Esri
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
import zipfile
import arcpy


def make_feature_classes_from_json(input_data_folder):
    """Create feature classes needed for test inputs."""
    cinci_gdb = os.path.join(input_data_folder, "CincinnatiTransitNetwork.gdb")
    if not os.path.exists(cinci_gdb):
        raise RuntimeError(f"Required test input gdb {cinci_gdb} does not exist.")
    # Create point feature classes for use in testing
    in_data_names = ["TestOrigins", "TestOrigins_Subset", "TestDestinations", "TestDestinations_Subset"]
    for in_data_name in in_data_names:
        out_fc = os.path.join(cinci_gdb, in_data_name)
        if not arcpy.Exists(out_fc):
            in_json = os.path.join(input_data_folder, in_data_name + ".json")
            arcpy.conversion.JSONToFeatures(in_json, out_fc)
            print(f"Created test dataset {out_fc}.")
    # Create polygon feature classes for use in testing. The actual polygons don't matter very much, so just create
    # buffers around the point feature classes.
    for in_data_name in ["TestOrigins", "TestDestinations"]:
        pg_fc = os.path.join(cinci_gdb, in_data_name + "_Polygons")
        if not arcpy.Exists(pg_fc):
            pt_fc = os.path.join(cinci_gdb, in_data_name)
            arcpy.analysis.Buffer(pt_fc, pg_fc, "100 Meters")
            print(f"Created test dataset {pg_fc}.")


def extract_toy_network(input_data_folder):
    """Extract the transit toy network from zip file."""
    toy_gdb = os.path.join(input_data_folder, "TransitToyNetwork.gdb")
    if os.path.exists(toy_gdb):
        # Data is already present and extracted
        return
    toy_zip = toy_gdb + ".zip"
    if not os.path.exists(toy_zip):
        raise RuntimeError(f"Required test input zip file {toy_zip} does not exist.")
    if not zipfile.is_zipfile(toy_zip):
        raise RuntimeError(f"Required test input zip file {toy_zip} is not a valid zip file.")
    with zipfile.ZipFile(toy_zip) as zf:
        zf.extractall(input_data_folder)
    if not os.path.exists(toy_gdb):
        raise RuntimeError(f"Required test input gdb file {toy_gdb} does not exist after unzipping.")
    print(f"Extracted {toy_gdb} from {toy_zip}.")
