# display-GTFS-in-ArcGIS

The Display GTFS in ArcGIS toolbox allows you to add GTFS transit stops and route shapes to ArcMap or ArcGIS Pro.

The Display GTFS Route Shapes tool converts the information from the GTFS routes.txt and shapes.txt files into an ArcGIS feature class, allowing you to view your transit lines on a map.  The output will contain one line feature for each unique shape in your GTFS data.  The attributes for each line contain all the information about the routes represented by the shape.

The Display GTFS Stops tool makes a feature class of stops using information from the GTFS stops.txt file.

## Features
* Conversion - Convert GTFS shapes.txt and stops.txt data to an ArcGIS feature class
* ArcGIS toolbox - No coding is required to use this tool.  Just add the toolbox to ArcMap and use the tools like any other geoprocessing tools.

## Instructions

1. To simply use the tools, download the latest release and follow the included User's Guide.
2. If you want to play with the code, fork it and have fun.

## Requirements

* ArcGIS 10.1 or higher with a Desktop Basic (ArcView) license, or ArcGIS Pro. *This toolbox is deprecated in ArcGIS Pro 2.2 and higher.  To convert your GTFS stops and shapes to feature classes in ArcGIS Pro 2.2 and higher, please use the [GTFS Stops To Features](http://pro.arcgis.com/en/pro-app/tool-reference/conversion/gtfs-stops-to-features.htm) and [GTFS Shapes To Features](http://pro.arcgis.com/en/pro-app/tool-reference/conversion/gtfs-shapes-to-features.htm) tools in the Conversion Tools toolbox.*
* A valid GTFS dataset. To use the Display GTFS Route Shapes tool, your GTFS dataset must include the optional shapes.txt file.

## Resources

* [User's Guide](https://github.com/ArcGIS/public-transit-tools/blob/master/display-GTFS-in-ArcGIS/UsersGuide.md)
* [GTFS specification](https://github.com/google/transit/blob/master/gtfs/spec/en/reference.md)

## Issues

Find a bug or want to request a new feature?  Please let us know by submitting an issue, or post a question in our [GeoNet group](https://community.esri.com/community/arcgis-for-public-transit).

## Contributing

Esri welcomes contributions from anyone and everyone. Please see our [guidelines for contributing](https://github.com/esri/contributing).

## Licensing
Copyright 2018 Esri

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

A copy of the license is available in the repository's [license.txt](../License.txt?raw=true) file.