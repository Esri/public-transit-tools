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
import arcpy


def make_feature_classes_from_json(input_data_folder):
    """Create feature classes needed for test inputs."""
    cinci_gdb = os.path.join(input_data_folder, "CincinnatiTransitNetwork.gdb")
    if not os.path.exists(cinci_gdb):
        raise RuntimeError(f"Required test input gdb {cinci_gdb} does not exist.")
    in_data_names = ["TestOrigins", "TestOrigins_Subset", "TestDestinations", "TestDestinations_Subset"]
    for in_data_name in in_data_names:
        in_json = os.path.join(input_data_folder, in_data_name + ".json")
        out_fc = os.path.join(cinci_gdb, in_data_name)
        if not arcpy.Exists(out_fc):
            arcpy.conversion.JSONToFeatures(in_json, out_fc)
            print(f"Created test dataset {out_fc}.")
