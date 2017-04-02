#Transit Analysis Tools User's Guide

Created by Melinda Morang, Esri  
Contact: <mmorang@esri.com>

Copyright 2016 Esri  
Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License.  You may obtain a copy of the License at <http://www.apache.org/licenses/LICENSE-2.0>.  Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  See the License for the specific language governing permissions and limitations under the License.

##What are the Transit Analysis Tools?
These instructions explain how to use the supplemental Transit Analysis Tools with the transit network dataset you created using Add GTFS to a Network Dataset.  These tools are designed to help you explore your data and understand the results of network analysis using transit.
- [Copy Traversed Source Features (with Transit)](#CopyTraversed)
- [Transit Identify](#TransitIdentify)

##<a name="CopyTraversed"></a>Copy Traversed Source Features (with Transit)
The ArcGIS Network Analyst tool *Copy Traversed Source Features* produces feature classes showing the network edges, junctions, and turns that were traversed when solving a network analysis layer.  It shows the actual network features that were used.  The *Copy Traversed Source Features (with Transit)* tool is an extension of the ArcGIS tool designed for use with transit network datasets.  It adds GTFS transit information to the traversal result produced by the ArcGIS *Copy Traversed Source Features* tool.  GTFS stop information is added to the output Junctions. GTFS route information, trip_id, arrive and depart time and stop names, and the transit time and wait time are added to the output Edges for each transit leg.  An additional feature class is produced containing only the transit edges.

Learn more about the original [Copy Traversed Source Features](http://desktop.arcgis.com/en/desktop/latest/tools/network-analyst-toolbox/copy-traversed-source-features.htm) tool and the [output](http://desktop.arcgis.com/en/desktop/latest/tools/network-analyst-toolbox/copy-traversed-source-features-output.htm) from that tool in the ArcGIS documentation.

![Screenshot of tool dialog](./images/Screenshot_CopyTraversedSourceFeaturesWithTransit_Dialog.png)

###Inputs
* **Input Network Analysis Layer**: The network analysis layer created using your transit network dataset for which you want to produce the traversal result. At this time, only network analysis layers of type Route and Closest Facility are supported.
* **Output Location**: A file geodatabase where the output feature classes will be written.
* **Edge Feature Class Name**: The name for the output Edge feature class.  This feature class will show the network edges (streets, connector lines, transit lines, etc.) that were traversed and will include GTFS information for all transit lines.
* **Junction Feature Class Name**: The name for the output Junctions feature class.  This feature class will show the network junctions (including GTFS stops) that were traversed and will include GTFS stop information.
* **Turn Table Name**: The name for the output Turns table. This table will show any network Turns that were traversed.
* **Transit Edge Feature Class Name**: The name for the output Transit Edge feature class.  This feature class will show the transit edges that were traversed and will include GTFS information for all the transit lines.

###Outputs
All output will be created in the file geodatabase you specified in the tool inputs.
* **[Edge Feature Class Name]**: This feature class shows the network edges (streets, connector lines, transit lines, etc.) that were traversed in the Route.  GTFS information for all transit lines is included.  The edges are sorted in the order traversed.
* **[Junction Feature Class Name]**: This feature class shows the network junctions (including GTFS stops) that were traversed.  GTFS stop information is included for all GTFS stops.
* **[Turn Table Name]**: This table shows any network Turns that were traversed.  If your network did not use Turns, this table will be empty.
* **[Transit Edge Feature Class Name]**: This feature class is a subset of the Edge feature class and contains only the transit edges lines that were traversed, including the GTFS information

###Notes about the Edge output
* The edges are sorted first by the Network Analyst RouteID (if there is more than one Route in your input layer), and second by the order traversed.
* The wait_time and transit_time fields are given in units of minutes and rounded to two decimal places.
* The trip_id, agency_id, route_id, from_stop_id, and to_stop_id fields have the GTFS data folder name prepended to the original ID values.  This is in order to distinguish the IDs when multiple GTFS datasets have been used in the network dataset.
* When Network Analyst solves a Route, the network edge features traversed by that Route can be determined.  However, this traversal result does not contain any information about the actual GTFS trip associated with the transit line that was traversed.  The *Copy Traversed Source Features (with Transit)* tool first calculates the traversal result and then subsequently adds the GTFS information based on the ID of the edge and the time of day it was traversed.  It is conceivable, though unlikely, that there may be more than one trip that traverses the same edge at the same time.  In these cases, both trips will be written to the Edges feature class, even though in reality the passenger could have only used one of the trips.
* If you are calculating the traversal result from a Closest Facility layer and you are using the time of day as an end time rather than a start time, a wait time will be shown for the last transit leg in each set of transit legs rather than at the beginning.  The solver essentially searches the network in reverse to find the optimal path so the traveler can arrive at the destination at exactly the time you specify, and it assumes they leave their origin at exactly the right time.  Consequently, there is no wait time at the beginning of the transit leg, but a wait time may be applied at the end so they reach their destination at the correct time.
* If your Network Analysis layer was solved using "Today" as the Day of Week instead of a specific weekday, you might not get correct transit information if you run this tool on a different day of the week from the day of week when your layer was solved.  The tool will output a warning.


##<a name="TransitIdentify"></a>Transit Identify
The *Transit Identify* tool is a network debugging utility that will print the transit schedule for the selected transit line in the network.  If you make a selection on the TransitLines feature class that participates in your network dataset, the *Transit Identify* tool will print a list of the times of day and days of week the selected line feature is traveled across.

You can use this information when testing that your network is working correctly.  For instance, if you suspect that the transit lines are ever being used in your analysis and you want to make sure your network connectivity is correct, you can use this tool to help you check the behavior of your network.

###Debugging procedure
* Select any transit line.
* Create a Route layer.
* Place two stops on the street features on either end of the selected transit line.
* Run Transit Identify to find a time of day and day of week when the selected transit line is used.
* Set your Route's time of day to correspond with the time of day when you know the transit line is used.  You should set the time of day to a minute or two before the transit trip starts to account for a small amount of walking time from the origin point to the transit stop.
* Solve the Route layer.  If the resulting route uses the transit line as expected, your network is working correctly. 

This tool is *not* meant to be used to extract schedule information from the entire network; consequently, the tool will only run if the number of selected features is 5 or fewer.

![Screenshot of tool dialog](./images/Screenshot_TransitIdentify_Dialog.png)

###Inputs
* **TransitLines (with selected features)**: The only valid input for this tool is a feature layer of your TransitLines feature class with 1-5 transit line features selected.  In other words, you should add your TransitLines feature class to the map, select up to five transit lines manually or using Select by Attributes or Select by Location, and use the TransitLines map layer as the input.
* **Save schedule info to this text file (optional)**: The schedule information for the selected transit lines will be printed to the ArcMap geoprocessing dialog.  If you would like to additionally save that information to a text file for easier reading or future reference, you may optionally indicate a text file path here.

###Outputs
* **\[Text file\] (optional)**: A text file containing the schedule information for the selected transit line(s).
