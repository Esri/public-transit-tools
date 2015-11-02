# display-gtfs-route-shapes

The Display GTFS Route Shapes tool converts the information from the GTFS routes.txt and shapes.txt files into an ArcGIS feature class, allowing you to view your transit lines on a map.  The output will contain one line feature for each unique shape in your GTFS data.  The attributes for each line contain all the information about the routes represented by the shape.

## Features
* Conversion - Convert GTFS shapes.txt data to an ArcGIS feature class
* ArcGIS toolbox - No coding is required to use this tool.  Just add the toolbox to ArcMap and use the tools like any other geoprocessing tools.

## Instructions

1. To simply use the tool, download the latest release and follow the included User's Guide.
2. If you want to play with the code, fork it and have fun.

## Requirements

* ArcGIS 10.0 or higher with a Desktop Basic (ArcView) license, or ArcGIS Pro.
* A valid GTFS dataset that contains the optional shapes.txt file.

## Resources

* [User's Guide](https://github.com/ArcGIS/public-transit-tools/blob/master/display-gtfs-route-shapes/UsersGuide.md)
* [GTFS specification](https://developers.google.com/transit/gtfs/reference)

## Issues

Find a bug or want to request a new feature?  Please let us know by submitting an issue.

## Contributing

Esri welcomes contributions from anyone and everyone. Please see our [guidelines for contributing](https://github.com/esri/contributing).

## Licensing
Copyright 2015 Esri

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

[](Esri Tags: ArcGIS GTFS shapes.txt public transit transport transportation routes shapes toolbox geoprocessing)
[](Esri Language: Python)​
