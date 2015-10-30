#Add GTFS to a Network Dataset Troubleshooting Guide

Created by Melinda Morang, Esri  
Contact: <mmorang@esri.com>

Copyright 2015 Esri  
Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License.  You may obtain a copy of the License at <http://www.apache.org/licenses/LICENSE-2.0>.  Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  See the License for the specific language governing permissions and limitations under the License.


##Common problems
This document describes some common problems encountered by users of *Add GTFS to a Network Dataset*, and how to solve them.
- [I can't register/install the transit evaluator](#Registration)
- [I got an FDO error when I tried to open my network dataset or add it to the map](#FDO)
- [I tried to run one of the tools in the Add GTFS to a Network Dataset toolbox, but it said it was missing a script reference.](#MissingScript)
- [When I'm setting up the evaluators for my transit travel time cost attribute, "TransitEvaluator" doesn't appear in the drop-down list of evaluator types](#DropDown)
- [My analysis never uses the transit lines. It only uses the streets.](#NoTransitLines)
- [My Service Areas have ugly spikes around the transit lines](#Exclude)
- [The Get Network EIDs tool failed with a message saying "Error obtaining network EIDs. Exception from HRESULT: 0x80040216".](#HRESULT)
- [The Network Identify tool always shows a cost of -1 for TransitLines edges in my network](#NetworkIdentify)


##<a name="Registration"></a>I can't register/install the transit evaluator
There are several reasons why registering the transit evaluator might fail.  These reasons are usually specific to your computer and have to do with installation paths or security settings.  You might need to talk to your system administrator for help if none of the suggestions below solve your problem.

**Don't try to register the transit evaluator on a network drive**
Make sure the Add GTFS to a Network Dataset files and folders are all on a local drive on your machine.

**Check your ArcGIS install path**
Open the Install.bat file (right-click it and click Edit).  Make sure the path on your computer to the file called ESRIRegAsm.exe matches what's written in the file.  If it doesn't, modify the file, try running Install.bat again, and see if that makes it work.

**If you get the error message "Registration failed. Could not load file or assembly…Operation is not supported."**
Your computer might have blocked the TransitEvaluator.dll file as a security risk because it came from another computer.  In the EvaluatorFiles folder, right click TransitEvaluator.dll and click Properties.  If there is an Unblock button at the bottom click it, and then try running Install.bat again.

**If you get an error saying "Registration failed. Could not write to disk"**
You probably need to run the .bat file as an administrator.  Right click on Install.bat and choose "Run as Administrator".  If it fails again and says it can't find the specified path to the .dll file, open the .bat file for editing and change the "%CD%" in the .dll path to the correct path on your machine.


##<a name="FDO"></a>I got an FDO error when I tried to open my network dataset
This means that the transit evaluator is not currently registered on the machine you are using.  You need to register the transit evaluator as described in the User's Guide.  You will have to register the transit evaluator on any machine where you intend to use your transit network dataset.

If you try to open or delete your transit network datasets on a machine without the GTFS transit evaluator registered, you will get an error message saying "Failed to edit the selected object(s). The item does not have a definition. FDO error -2147212634".


##<a name="MissingScript"></a>I tried to run one of the tools in the Add GTFS to a Network Dataset toolbox, but it said it was missing a script reference.
The *Add GTFS to a Network Dataset* toolbox files (with the .tbx extensions and the red toolbox icon) have associated python script files (with the .py extensions in the scripts folder).  If you move the toolbox files without moving the associated scripts folder with them, then they will no longer be able to find the scripts, and the tools won't work.  Make sure if you want to move the Add GTFS to a Network Dataset files to a new location that you move the entire folder together and don't separate the files.  Additionally, make sure to uninstall the transit evaluator before you move it, and reinstall it in its new location.

##<a name="DropDown"></a>When I'm setting up the evaluators for my transit travel time cost attribute, "TransitEvaluator" doesn't appear in the drop-down list of evaluator types
First, make sure your cost attribute has units of Minutes.  TransitEvaluator will only appear in the list of choices if the attribute has units of Minutes.

If your cost attribute units are correct, then the transit evaluator probably didn't register (install) correctly on your machine.  Make sure you followed the instructions in the user's guide exactly for registering transitevaluator.dll on your system.  If you have problems registering it, please consult the [I can't register/install the transit evaluator](#Registration) section of this Troubleshooting Guide.

If ArcMap is open when you register the transit evaluator, you will need to close and re-open it in order to refresh it.


##<a name="NoTransitLines"></a>My analysis never uses the transit lines. It only uses the streets.
There are many reasons why the results of your analysis might fail to use the transit lines and only use the streets.

**You forgot to set a time of day and day of week / date for your analysis**
The transit lines will only be used if you set a time of day and day of week or date for your analysis.

**You set an incorrect day of week or date for your analysis**
There are two valid ways to construct GTFS schedules.  Transit agencies can use the calendar.txt file to indicate a date range that service is available and designate which service_ids run on each day of the week.  They can use the calendar_dates.txt file to indicate special exceptions to the regular schedule, such as for holidays.  Alternatively, transit authority can exclusively use the calendar_dates.txt file, treating service as a special "exception" for every day.

If your transit agency uses this second method, you cannot select a generic weekday for your analysis.  You will have to enter a specific date, and that date must be a date during the time period your GTFS data covers.  Additionally, your network's travel time attribute must have a parameter called "Use Specific Dates", and that parameter must be set to True.  See the User's Guide for further instructions.

If, on the other hand, your transit agency uses the calendar.txt file and you still wish to use specific dates rather than generic weekdays for your analysis, you must still select a date that falls within the ranges listed in the calendar.txt file, and you must still have a parameter called "Use Specific Dates" that is set to True.

**Your network connectivity is incorrect**
Make sure your network connectivity is set up according to the instructions in the User's Guide.  The most common mistake is to forget to switch the Stops_Snapped2Streets source to a connectivity policy of "Override".  If it is still set to "End Point", then your connector lines will not actually be connected to the street features, and it will be impossible for travelers to actually access the transit lines from the streets.  If this was your problem, make sure to rebuild the network dataset after switching your connectivity to Override.  Then, rerun the *Get Network EIDs* tool to refresh the EIDs (which may change during the rebuild).

![Screenshot of correct network dataset connectivity policy](https://github.com/ArcGIS/public-transit-tools/blob/master/add-GTFS-to-a-network-dataset/images/Screenshot_NDCreation_ConnectivityGroups_Override.png.png)

It's easy to check whether your network features are correctly connected to one another.  Zoom in to one of your transit lines. Use the Network Identify tool (on the Network Analyst toolbar) to click on the connector line (Connectors_Stops2Streets) that connects the street with the transit line.  When you use Network Identify, it will give you a list of the other edges that are connected to it.  When you click on the items in this list, it should highlight them in the map.  Make sure the adjacent street feature shows up as connected to your connector line.

**Your cost attribute incorrectly calculates the travel time on your streets**
If you set up the travel time attribute incorrectly for your streets, it may just appear to be drastically more efficient to travel on the streets than on the transit lines.  For instance, you may have accidentally set the impedance along all your street features to 0.  Or, you may have used the wrong units of measurement when converting your street lengths to a walking time.  If your street features are in units of feet, you need to convert your desired miles per hour walk speed to feet per minute and divide the street length by this number.

**None of the above**
Here is a technique for debugging your transit network in detail.  The idea is to try to force a Route to use a transit line and in doing so reveal any underlying issues with the network or your analysis settings.
- Pick a transit line feature in your network.  Any transit line feature will do.
- Create a Route layer and drop two stops on the streets on either end of the transit line
- Use the Select tool to select the transit line feature you're working with.
- Use the *Transit Identify* tool (in the Transit Analysis Tools toolbox) to find the times of day and days of week your chosen transit line has service.  See the Transit Analysis Tools User's Guide for instructions on using the *Transit Identify* tool.
- In your Route analysis settings, set the time of day and day of week to be just before one of the times when the line has service so that the transit line ought to be the quickest way to travel between your two points.
- Solve the Route and see if it uses the transit line.  If not, adjust the time by a minute or two and try again.  If it doesn't, something is still wrong with your network or your analysis settings, and you should revisit the suggestions above or contact me for help.


##<a name="Exclude"></a>My Service Areas have ugly spikes around the transit lines
If you are solving a Service Area analysis, you need to prevent service areas from being drawn around transit lines.  The service area polygons should only be drawn around streets since pedestrians can't exit the transit vehicle partway between stops.  To do this, open the layer properties and go to the Polygon Generation tab.  In the bottom left corner, click to exclude TransitLines and Connectors_Stops2Streets (or whatever is most appropriate for your network).

![Screenshot of tool dialog](https://github.com/ArcGIS/public-transit-tools/blob/master/add-GTFS-to-a-network-dataset/images/Screenshot_AnalysisSettings_ExcludedSources.png.png)

##<a name="HRESULT"></a>The Get Network EIDs tool failed with a message saying "Error obtaining network EIDs. Exception from HRESULT: 0x80040216".
This means that your network dataset or one of the associated files has a schema lock on it, likely because you added it to the map or tried to edit it.  Try closing ArcMap, reopening a blank map, and running the tool again prior to adding any layers to the map.  Alternatively, you can run the tool from ArcCatalog.

Note: Try this solution if you receive any HRESULT code.  Other HRESULT numbers might be indicative of the same problem.

##<a name="NetworkIdentify"></a>The Network Identify tool always shows a cost of -1 for TransitLines edges in my network
This is the correct behavior.  Because TransitEvaluator is a custom evaluator, the Network Identify tool does not know how to use it to determine the impedance of your TransitLines edges.  Furthermore, the impedance of those edges is not static; the time it takes to traverse them depends on the time of day and the transit schedules.  The Network Identify tool is not time-aware.  Because of these limitations, the Network Identify tool always lists -1 as the impedance for the TransitLines edges in your network.  It does not mean that your network is broken.

If you are concerned that your transit lines are never being used or that your analysis results are incorrect, please consult the [My analysis never uses the transit lines. It only uses the streets.](#NoTransitLines) section of this Troubleshooting Guide.
