# add-GTFS-to-a-network-dataset

*Add GTFS to a Network Dataset* allows you to put GTFS public transit data into an ArcGIS network dataset so you can run schedule-aware analyses using the Network Analyst tools, like Service Area, OD Cost Matrix, and Location-Allocation.

## Features
* Use schedule-based transit data with the ArcGIS Network Analyst tools.
* Create transit service areas (transitsheds).
* Study accessibility of destinations by transit.
* Make location decisions based on access by transit.
* ArcGIS toolbox - No coding is required to use this tool.  Just add the toolbox to ArcMap and use the tools like any other geoprocessing tools.

## Instructions

1. To simply use the tool, download the latest release and follow the included User's Guide. 
2. If you want to play with the code, fork it and have fun.

## Requirements

* ArcGIS 10.1 or higher with a Desktop Standard (ArcEditor) license. (You can still use it if you have a Desktop Basic license, but you will have to find an alternate method for one of the pre-processing tools.) This tool does not work in ArcGIS Pro yet.
* Network Analyst extension.
* Street data for the area covered by your transit system, preferably data including pedestrian attributes.
* A valid GTFS dataset. If your GTFS dataset has blank values for arrival_time and departure_time in stop_times.txt, you will not be able to run this tool.
* The necessary privileges to install something on your computer.

## Resources

* [User's Guide](https://github.com/ArcGIS/public-transit-tools/blob/master/add-GTFS-to-a-network-dataset/UsersGuide.md)
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

A copy of the license is available in the repository's [license.txt](https://github.com/mmorang/add-GTFS-to-a-network-dataset/blob/master/License.txt) file.

[](Esri Tags: ArcGIS GTFS public transit transport transportation transitshed service area isochrone origin destination cost matrix schedule Network Analyst accessibility planning toolbox geoprocessing C-Sharp ArcObjects)
[](Esri Language: Python)​
