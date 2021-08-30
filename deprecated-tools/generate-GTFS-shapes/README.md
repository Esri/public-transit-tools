# generate-GTFS-shapes

The Generate GTFS Shapes toolbox produces a shapes.txt file for your GTFS dataset.  You give the tool a valid, existing GTFS dataset, and the tool creates a new shape.txt file and updates the shape_id field in trips.txt and the shape_dist_traveled field in stop_times.txt.  Alternatively, if you already have a shapes.txt file, you can use this toolbox to edit one or more of the existing shapes.

## Features
* Create a shapes.txt file for your GTFS dataset.
* Edit one or more shapes in your existing shapes.txt file.
* Start from a reasonable estimate of the shapes and use the editing tools in ArcGIS to make them perfect.
* ArcGIS toolbox - No coding is required to use this tool.  Just add the toolbox to ArcMap and use the tools like any other geoprocessing tools.

## Instructions

1. To simply use the tool, download the latest release and follow the included User's Guide.
2. If you want to play with the code, fork it and have fun.

## Requirements

* ArcGIS 10.3 or higher with a Desktop Basic (ArcView) license, or ArcGIS Pro 1.2 or higher.
* If you want to generate on-street route shapes (as opposed to straight lines connecting stops), you will need either a Network Analyst extension and a network dataset or an ArcGIS Online account with routing privileges and sufficient credits for your analysis.  Learn more in the [User's Guide](https://github.com/ArcGIS/public-transit-tools/blob/master/generate-GTFS-shapes/UsersGuide.md).

## Resources

* [User's Guide](https://github.com/ArcGIS/public-transit-tools/blob/master/generate-GTFS-shapes/UsersGuide.md)
* [GTFS specification](https://github.com/google/transit/blob/master/gtfs/spec/en/reference.md)

## Issues

Find a bug or want to request a new feature?  Please let us know by submitting an issue, or post a question in the [Esri Community forums](https://community.esri.com/t5/public-transit-questions/bd-p/public-transit-questions).

## Contributing

Esri welcomes contributions from anyone and everyone. Please see our [guidelines for contributing](https://github.com/esri/contributing).

## Licensing
Copyright 2019 Esri

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