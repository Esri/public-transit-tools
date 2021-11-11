# Defines
!define APPNAME "Add GTFS to a Network Dataset"
!define COMPANYNAME "Environmental Systems Research Institute, Inc."
!define DESCRIPTION "Add GTFS to a Network Dataset allows you to put GTFS public transit data into an ArcGIS network dataset so you can run schedule-aware analyses using the Network Analyst tools, like Service Area, OD Cost Matrix, and Location-Allocation."
!define HELPURL "http://transit.melindamorang.com/UsersGuides/AddGTFStoaNetworkDataset/AddGTFStoND_UsersGuide.html"
#!define UPDATEURL "Product Updates" link
!define ABOUTURL https://github.com/Esri/public-transit-tools/tree/master/add-GTFS-to-a-network-dataset # "Publisher" link
!define VERSIONMAJOR 1
!define VERSIONMINOR 0
!define VERSIONBUILD 0
!define INSTALLSIZE 3608

Var ArcMapInstallDir
Var DocShortcutInstallDir
Var ToolboxesDir

!include LogicLib.nsh

!macro VerifyUserIsAdmin
UserInfo::GetAccountType
pop $0
${If} $0 != "admin" ;Require admin rights on NT4+
        messageBox mb_iconstop "Administrator rights required!"
        setErrorLevel 740 ;ERROR_ELEVATION_REQUIRED
        quit
${EndIf}
!macroend

function .onInit
	setShellVarContext all
	!insertmacro VerifyUserIsAdmin
functionEnd

# installer name
Name "Add GTFS to a Network Dataset"
OutFile "AddGTFStoaNetworkDataset_Installer.exe"

# default installation folder
InstallDir "$EXEDIR\AddGTFStoaNetworkDataset"

Section Install
DetailPrint "Searching the registry for ArcMap installation folder..."
ReadRegStr $0 HKLM Software\WOW6432Node\ESRI\Desktop10.7 "InstallDir"
IfErrors +1 Success
ReadRegStr $0 HKLM Software\WOW6432Node\ESRI\Desktop10.6 "InstallDir"
IfErrors +1 Success
ReadRegStr $0 HKLM Software\WOW6432Node\ESRI\Desktop10.5 "InstallDir"
IfErrors +1 Success
ReadRegStr $0 HKLM Software\WOW6432Node\ESRI\Desktop10.4 "InstallDir"
IfErrors +1 Success
ReadRegStr $0 HKLM Software\WOW6432Node\ESRI\Desktop10.3 "InstallDir"
IfErrors +1 Success
ReadRegStr $0 HKLM Software\WOW6432Node\ESRI\Desktop10.2 "InstallDir"
IfErrors +1 Success
ReadRegStr $0 HKLM Software\WOW6432Node\ESRI\Desktop10.1 "InstallDir"
IfErrors Failure Success
Success: StrCpy $ArcMapInstallDir "$0"
StrCpy $ToolboxesDir "$0ArcToolbox\Toolboxes"
DetailPrint "ArcMap installation found at: $0"
Goto +2
Failure: Abort "ArcMap was not found on this computer.  Installation aborted."

# Copy and register TransitEvaluator.dll.
DetailPrint "Installing TransitEvaluator.dll and dependencies to: $ToolboxesDir\EvaluatorFiles "
SetOutpath "$ToolboxesDir\EvaluatorFiles"
File "EvaluatorFiles\ESRI.ArcGIS.ADF.Local.dll"
File "EvaluatorFiles\ESRI.ArcGIS.CatalogUI.dll"
File "EvaluatorFiles\ESRI.ArcGIS.Geodatabase.dll"
File "EvaluatorFiles\ESRI.ArcGIS.NetworkAnalyst.dll"
File "EvaluatorFiles\ESRI.ArcGIS.System.dll"
File "EvaluatorFiles\ESRI.ArcGIS.Version.dll"
File "EvaluatorFiles\TransitEvaluator.dll"
ExecWait '"$COMMONFILES\ArcGIS\bin\ESRIRegAsm.exe" "$ToolboxesDir\EvaluatorFiles\TransitEvaluator.dll" /p:Desktop /s' $0
# Determine whether the registration succeeded.  Cleanup and abort installation if registration fails.
StrCmp $0 "0" 0 +3
DetailPrint "Registration of TransitEvaluator.dll with ArcMap succeeded."
Goto +14
DetailPrint "Registration of TransitEvaluator.dll was not successful."
MessageBox MB_ICONEXCLAMATION "Registration of TransitEvaluator.dll failed.  Installation aborted."
Delete "$ToolboxesDir\EvaluatorFiles\ESRI.ArcGIS.ADF.Local.dll"
Delete "$ToolboxesDir\EvaluatorFiles\ESRI.ArcGIS.CatalogUI.dll"
Delete "$ToolboxesDir\EvaluatorFiles\ESRI.ArcGIS.Geodatabase.dll"
Delete "$ToolboxesDir\EvaluatorFiles\ESRI.ArcGIS.NetworkAnalyst.dll"
Delete "$ToolboxesDir\EvaluatorFiles\ESRI.ArcGIS.System.dll"
Delete "$ToolboxesDir\EvaluatorFiles\ESRI.ArcGIS.Version.dll"
Delete "$ToolboxesDir\EvaluatorFiles\TransitEvaluator.dll"
SetOutpath "$ToolboxesDir"
rmDir "$ToolboxesDir\EvaluatorFiles"
DetailPrint "Installation aborted."
Abort

# Copy additional binaries.
DetailPrint "Installing additional binaries to: $ToolboxesDir\EvaluatorFiles"
File "EvaluatorFiles\System.Data.SQLite.dll"
File "EvaluatorFiles\GetEIDs.exe"
# SQLite interop DLL's
SetOutpath "$ToolboxesDir\EvaluatorFiles\x64"
File "EvaluatorFiles\x64\SQLite.Interop.dll"
SetOutpath "$ToolboxesDir\EvaluatorFiles\x86"
File "EvaluatorFiles\x86\SQLite.Interop.dll"

# Registry information for add/remove programs
DetailPrint "Writing uninstallation information to the registry..."
WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "ToolboxesDir" "$ToolboxesDir"
WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME}"
WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" "$\"$INSTDIR\AddGTFStoaNetworkDataset_Uninstall.exe$\""
WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "QuietUninstallString" "$\"$INSTDIR\AddGTFStoaNetworkDataset_Uninstall.exe$\" /S"
WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "InstallLocation" "$\"$INSTDIR$\""
WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "Publisher" "${COMPANYNAME}"
WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "URLInfoAbout" "${ABOUTURL}"
WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayVersion" "${VERSIONMAJOR}.${VERSIONMINOR}.${VERSIONBUILD}"
WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "VersionMajor" ${VERSIONMAJOR}
WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "VersionMinor" ${VERSIONMINOR}
WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "NoModify" 1
WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "NoRepair" 1
WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "EstimatedSize" ${INSTALLSIZE}

# install the documentation and template
DetailPrint "Installing documentation..."
SetOutPath "$INSTDIR"
File "TroubleshootingGuide.html"
File "AddGTFStoND_UsersGuide.html"
File "TransitNetworkTemplate.xml"
SetOutpath "$INSTDIR\images"
File "images\ConnectivityDiagram.png"
File "images\Screenshot_AnalysisSettings_ExcludedSources.png"
File "images\Screenshot_AnalysisSettings_ExcludeRoutes.png"
File "images\Screenshot_AnalysisSettings_NetworkLocations.png"
File "images\Screenshot_AnalysisSettings_SpecificDatesParameter.png"
File "images\Screenshot_AnalysisSettings_TimeOfDay.png"
File "images\Screenshot_Caching_Popup.png"
File "images\Screenshot_CopyTraversedSourceFeaturesWithTransit_Dialog.png"
File "images\Screenshot_GenerateStopStreetConnectors_Dialog.png"
File "images\Screenshot_GenerateTransitLinesAndStops_Dialog.png"
File "images\Screenshot_GetEIDs_Dialog.png"
File "images\Screenshot_NDCreation_ConnectivityGroups.png"
File "images\Screenshot_NDCreation_ConnectivityGroups_Override.png"
File "images\Screenshot_NDCreation_Evaluators.png"
File "images\Screenshot_NDCreation_NewAttribute.png"
File "images\Screenshot_NDCreation_RestrictionFieldEvaluator.png"
File "images\Screenshot_NDCreation_SourceFCs.png"
File "images\Screenshot_Registration_Popup.png"
File "images\Screenshot_TransitIdentify_Dialog.png"

# Create shortcuts to the documentation
DetailPrint "Installing doc shortcuts to: $SMPROGRAMS\ArcGIS\TransitTools"
CreateDirectory "$SMPROGRAMS\ArcGIS\TransitTools"
createShortCut "$SMPROGRAMS\ArcGIS\TransitTools\Public Transit Tools - Troubleshooting Guide.lnk" "$INSTDIR\TroubleshootingGuide.html" "Troubleshooting Guide"
createShortCut "$SMPROGRAMS\ArcGIS\TransitTools\Public Transit Tools - Add GTFS to Network Dataset Users Guide.lnk" "$INSTDIR\AddGTFStoND_UsersGuide.html" "Add GTFS To Network Dataset User Guide"
DetailPrint "Writing registry key for DocShortcutLocation:  $SMPROGRAMS\ArcGIS\TransitTools"
WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DocShortcutLocation" '$SMPROGRAMS\ArcGIS\TransitTools'

# Install the tools
# Toolboxes
DetailPrint "Installing toolboxes and scripts to: $ToolboxesDir"
SetOutpath "$ToolboxesDir"
File "Add GTFS to network dataset.tbx"
# Scripts
SetOutpath "$ToolboxesDir\scripts"
File "scripts\CopyTraversedSourceFeatures_wTransit.py"
File "scripts\GenerateStop2StreetConnectors.py"
File "scripts\GenerateStopPairs.py"
File "scripts\GetEIDs.py"
File "scripts\hms.py"
File "scripts\sqlize_csv.py"
File "scripts\TransitIdentify.py"

# Write the uninstaller
DetailPrint "Writing uninstaller..."
WriteUninstaller "$INSTDIR\AddGTFStoaNetworkDataset_Uninstall.exe"
SectionEnd


Section Uninstall
# Get the current ArcMap install directory from the registry
ReadRegStr $0 HKLM Software\WOW6432Node\ESRI\Desktop10.7 "InstallDir"
IfErrors +1 Success
ReadRegStr $0 HKLM Software\WOW6432Node\ESRI\Desktop10.6 "InstallDir"
IfErrors +1 Success
ReadRegStr $0 HKLM Software\WOW6432Node\ESRI\Desktop10.5 "InstallDir"
IfErrors +1 Success
ReadRegStr $0 HKLM Software\WOW6432Node\ESRI\Desktop10.4 "InstallDir"
IfErrors +1 Success
ReadRegStr $0 HKLM Software\WOW6432Node\ESRI\Desktop10.3 "InstallDir"
IfErrors +1 Success
ReadRegStr $0 HKLM Software\WOW6432Node\ESRI\Desktop10.2 "InstallDir"
IfErrors +1 Success
ReadRegStr $0 HKLM Software\WOW6432Node\ESRI\Desktop10.1 "InstallDir"
IfErrors Failure Success
Success: StrCpy $ArcMapInstallDir $0
Goto +3
Failure:  MessageBox MB_ICONSTOP "ArcMap must be installed on this computer in order to un-install the ArcGIS Public Transit Tools.  Please reinstall ArcMap and try again."
Abort "ArcMap must be installed on this computer in order to un-install the ArcGIS Public Transit Tools.  Please reinstall ArcMap and try again."

#ReadRegStr $0 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "ArcMapInstallLocation"
#IfErrors Failure2 Success2
#Failure2: MessageBox MB_ICONSTOP "ArcMap must be installed on this computer in order to un-install the ArcGIS Public Transit Tools.  Please reinstall ArcMap and try again."
#DetailPrint "Un-installation aborted.  Please reinstall ArcMap and try again."
#Abort
#Success2: StrCpy $ArcMapInstallDir $0
#
# Get the Toolboxes directory where the tools, dlls, and scripts were installed from the registry.
ReadRegStr $0 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "ToolboxesDir"
IfErrors Failure3 Success3
Failure3: MessageBox MB_ICONSTOP "Uninstallation aborted due to missing registry key: HKLM Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME} ${APPNAME} ToolboxesDir"
DetailPrint "Uninstallation aborted due to missing registry key: HKLM Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME} ToolboxesDir"
Success3: StrCpy $ToolboxesDir $0
#
# Un-register TransitEvaluator.dll
ExecWait '"$COMMONFILES\ArcGIS\bin\ESRIRegAsm.exe" "$ToolboxesDir\EvaluatorFiles\TransitEvaluator.dll" /p:Desktop /u /s' $0
StrCmp $0 "0" 0 +3
DetailPrint "Un-registration ofTransitEvaluator.dll with ArcMap was successful."
Goto +2
DetailPrint "Un-registration of TransitEvaluator.dll  with ArcMap was not successful."

# Delete help documentation files in the install directory
Delete "$INSTDIR\AddGTFStoND_UsersGuide.html"
Delete "$INSTDIR\TroubleshootingGuide.html"
Delete "$INSTDIR\TransitNetworkTemplate.xml"
Delete "$INSTDIR\images\ConnectivityDiagram.png"
Delete "$INSTDIR\images\Screenshot_AnalysisSettings_ExcludedSources.png"
Delete "$INSTDIR\images\Screenshot_AnalysisSettings_ExcludeRoutes.png"
Delete "$INSTDIR\images\Screenshot_AnalysisSettings_NetworkLocations.png"
Delete "$INSTDIR\images\Screenshot_AnalysisSettings_SpecificDatesParameter.png"
Delete "$INSTDIR\images\Screenshot_AnalysisSettings_TimeOfDay.png"
Delete "$INSTDIR\images\Screenshot_Caching_Popup.png"
Delete "$INSTDIR\images\Screenshot_CopyTraversedSourceFeaturesWithTransit_Dialog.png"
Delete "$INSTDIR\images\Screenshot_GenerateStopStreetConnectors_Dialog.png"
Delete "$INSTDIR\images\Screenshot_GenerateTransitLinesAndStops_Dialog.png"
Delete "$INSTDIR\images\Screenshot_GetEIDs_Dialog.png"
Delete "$INSTDIR\images\Screenshot_NDCreation_ConnectivityGroups.png"
Delete "$INSTDIR\images\Screenshot_NDCreation_ConnectivityGroups_Override.png"
Delete "$INSTDIR\images\Screenshot_NDCreation_Evaluators.png"
Delete "$INSTDIR\images\Screenshot_NDCreation_NewAttribute.png"
Delete "$INSTDIR\images\Screenshot_NDCreation_RestrictionFieldEvaluator.png"
Delete "$INSTDIR\images\Screenshot_NDCreation_SourceFCs.png"
Delete "$INSTDIR\images\Screenshot_Registration_Popup.png"
Delete "$INSTDIR\images\Screenshot_TransitIdentify_Dialog.png"
rmDir "$INSTDIR\images"

# Delete the tools
Delete "$ToolboxesDir\Add GTFS to network dataset.tbx"
Delete "$ToolboxesDir\EvaluatorFiles\GetEIDs.exe"
Delete "$ToolboxesDir\EvaluatorFiles\System.Data.SQLite.dll"
Delete "$ToolboxesDir\EvaluatorFiles\TransitEvaluator.dll"
Delete "$ToolboxesDir\EvaluatorFiles\ESRI.ArcGIS.ADF.Local.dll"
Delete "$ToolboxesDir\EvaluatorFiles\ESRI.ArcGIS.CatalogUI.dll"
Delete "$ToolboxesDir\EvaluatorFiles\ESRI.ArcGIS.Geodatabase.dll"
Delete "$ToolboxesDir\EvaluatorFiles\ESRI.ArcGIS.NetworkAnalyst.dll"
Delete "$ToolboxesDir\EvaluatorFiles\ESRI.ArcGIS.System.dll"
Delete "$ToolboxesDir\EvaluatorFiles\ESRI.ArcGIS.Version.dll"
Delete "$ToolboxesDir\EvaluatorFiles\x64\SQLite.Interop.dll"
Delete "$ToolboxesDir\EvaluatorFiles\x86\SQLite.Interop.dll"
Delete "$ToolboxesDir\scripts\CopyTraversedSourceFeatures_wTransit.py"
Delete "$ToolboxesDir\scripts\GenerateStop2StreetConnectors.py"
Delete "$ToolboxesDir\scripts\GenerateStopPairs.py"
Delete "$ToolboxesDir\scripts\GetEIDs.py"
Delete "$ToolboxesDir\scripts\hms.py"
Delete "$ToolboxesDir\scripts\TransitIdentify.py"
Delete "$ToolboxesDir\scripts\sqlize_csv.py"

# Get the documentation shortcut directory from the registry
ReadRegStr $0 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DocShortcutLocation"
IfErrors Failure1 Success1
# Delete the documentation shortcuts
Success1: StrCpy $DocShortcutInstallDir $0
Delete '$DocShortcutInstallDir\Public Transit Tools - Troubleshooting Guide.lnk'
Delete '$DocShortcutInstallDir\Public Transit Tools - Users Guide.lnk'
Delete '$DocShortcutInstallDir\Public Transit Tools - Add GTFS to Network Dataset Users Guide.lnk'
rmDir "$DocShortcutInstallDir"
Goto +6
Failure1: MessageBox MB_ICONEXCLAMATION "Unable to identify the location of the documentation shortcuts from the registry.  Click 'Details' for more information."
DetailPrint "The following links will have to be manually deleted from the Start Menu folder:"
DetailPrint " - Public Transit Tools - Add GTFS to Network Dataset Users Guide.lnk"
DetailPrint " - Public Transit Tools - Troubleshooting Guide.lnk"

# Delete the uninstaller
Delete $INSTDIR\AddGTFStoaNetworkDataset_Uninstall.exe

# Try to remove the install directories - this will only happen if they are empty
DetailPrint "$ToolboxesDir\EvaluatorFiles"
rmDir "$ToolboxesDir\EvaluatorFiles\x64"
rmDir "$ToolboxesDir\EvaluatorFiles\x86"
rmDir "$ToolboxesDir\EvaluatorFiles\"
rmDir "$ToolboxesDir\scripts"
rmDir '$INSTDIR'

# Remove uninstaller information from the registry
DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
SectionEnd
