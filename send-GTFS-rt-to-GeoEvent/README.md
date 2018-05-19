# send-GTFS-rt-to-GeoEvent

This simple script provides a fast and easy way to consume GTFS-rt feeds and send the data to the ArcGIS GeoEvent Extension for Server via TCP.

## Features
* View GTFS-rt realtime transit data in ArcGIS using ArcGIS GeoEvent

## Instructions

Edit the hostname and port in the script to match your environment, i.e. the hostname would be the server on which GeoEvent is running and the port would be the port you configured for the TCP input.


## Requirements

- ArcGIS for Server with the GeoEvent Extension
- GeoEvent TCP input 
- Access to a GTFS-rt feed (e.g. http://www.cttransit.com/about/developers/gtfsdata/)
- Python runtime
- Python GTFS bindings 

## Resources

* [GTFS specification](https://developers.google.com/transit/gtfs/reference)

## Issues

Find a bug or want to request a new feature?  Please let us know by submitting an issue, or post a question in our [GeoNet group](https://community.esri.com/community/arcgis-for-public-transit).

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
