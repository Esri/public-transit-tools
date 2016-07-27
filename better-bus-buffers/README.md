# better-bus-buffers

BetterBusBuffers is a toolset to help you quantitatively measure access to public transit in your city. The tools use GTFS public transit data and ArcGIS to count the number of transit trips available during a time window for areas within your city, point locations within your city, or at the transit stops themselves.

## Features
* Create service areas (ie, walksheds, or network buffers) around transit stops.
* Count trips at stops, for areas of town, or for points of interest.
* ArcGIS toolbox - No coding is required to use this tool.  Just add the toolbox to ArcMap and use the tools like any other geoprocessing tools.

## Instructions

1. To simply use the tool, download the latest release and follow the included User's Guide.
2. If you want to play with the code, fork it and have fun.

## Requirements

* ArcGIS 10.0 or higher with a Desktop Basic (ArcView) license, or ArcGIS Pro 1.2 or higher. The *Count Trips at Points Online* tool cannot be run with ArcGIS 10.0.
* Network Analyst extension. (You can run the *Count Trips at Stops* and *Count Trips at Points Online* tools even if you do not have Network Analyst.)
* For the *Count Trips at Points Online*, an ArcGIS Online account with routing privileges and sufficient credits for your analysis.
* You need the Desktop Advanced (ArcInfo) license in order to run the *Count Trips in Polygon Buffers around Stops* tool.
* A valid GTFS dataset. Your GTFS dataset must contain a calendar.txt file.  If your GTFS dataset has blank values for arrival_time and departure_time in stop_times.txt, you will not be able to run this tool.
* For some functionality, a network dataset with street data for your area of interest.
* For the *Count Trips at Points* and *Count Trips at Points Online* tools, a feature class of your points of interest.

## Resources

* [User's Guide](https://github.com/ArcGIS/public-transit-tools/blob/master/better-bus-buffers/UsersGuide.md)
* [GTFS specification](https://developers.google.com/transit/gtfs/reference)

## Issues

Find a bug or want to request a new feature?  Please let us know by submitting an issue.

## Contributing

Esri welcomes contributions from anyone and everyone. Please see our [guidelines for contributing](https://github.com/esri/contributing).

## Licensing
Copyright 2016 Esri

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

[](Esri Tags: ArcGIS GTFS public transit transport transportation routes walkshed service area frequency Title VI buffer isochrone coverage trips toolbox geoprocessing)
[](Esri Language: Python)​
