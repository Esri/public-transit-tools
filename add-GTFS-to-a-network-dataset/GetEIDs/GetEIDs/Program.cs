//##############################################################################
//Copyright 2015 Esri
//   Licensed under the Apache License, Version 2.0 (the "License");
//   you may not use this file except in compliance with the License.
//   You may obtain a copy of the License at
//       http://www.apache.org/licenses/LICENSE-2.0
//   Unless required by applicable law or agreed to in writing, software
//   distributed under the License is distributed on an "AS IS" BASIS,
//   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//   See the License for the specific language governing permissions and
//   limitations under the License.
//##############################################################################

using System;
using System.Collections.Generic;
using System.Data.SQLite;
using ESRI.ArcGIS.esriSystem;
using ESRI.ArcGIS.Geodatabase;

namespace GetEIDs
{
    class Program
    {
        #region Get the network dataset
        public static INetworkDataset GetNetworkDatasetFromPath(string ndPath)
        {
            // The last entry is the ND name, the penultimate entry is the FD name
            string[] splitPath = ndPath.Split('\\');

            string ndName = splitPath[splitPath.Length - 1];
            string fdName = splitPath[splitPath.Length - 2];

            // trim off the nd and fd.
            string workspacePath = ndPath.Remove(ndPath.Length - fdName.Length - ndName.Length - 2);

           // Console.WriteLine("Opening feature workspace: " + workspacePath);
            IFeatureWorkspace featureWorkspace = GetFeatureWorkspace(workspacePath);

            //Console.WriteLine("Opening dataset container: " + fdName);
            IDatasetContainer2 datasetContainer = GetDatasetContainer(featureWorkspace, fdName);

            //Console.WriteLine("Opening network dataset: " + ndName);
            INetworkDataset networkDataset = GetNetworkDataset(datasetContainer, ndName);
            //Console.WriteLine("Opened");

            return networkDataset;
        }

        public static INetworkDataset GetNetworkDataset(IDatasetContainer2 datasetContainer, string ndName)
        {
            INetworkDataset networkDataset;
            try
            {
                networkDataset = datasetContainer.get_DatasetByName(esriDatasetType.esriDTNetworkDataset, ndName) as INetworkDataset;
            }
            catch (Exception e)
            {
                if (e.Message.Contains("0x80042603"))
                {
                    throw new Exception("Unable to read network dataset. Ensure that the installed version of the TransitEvaluator.dll matches the installed version of ArcGIS. GDB Exception: " + e.Message);
                }
                else
                {
                    throw e;
                }
            }
            
            if (networkDataset == null)
                throw new Exception("NATestNetworkDataset: networkDataset should not be null");

            return networkDataset;
        }

        public static IDatasetContainer3 GetDatasetContainer(IFeatureWorkspace featureWorkspace, string fdName)
        {
            IDatasetContainer3 datasetContainer = null;

            if (featureWorkspace is IWorkspace2)
            {
                IWorkspace2 workspace = featureWorkspace as IWorkspace2;
                bool fdExists = workspace.get_NameExists(esriDatasetType.esriDTFeatureDataset, fdName);
                if (!fdExists)
                    throw new Exception("Feature Dataset does not exist.");
            }

            IFeatureDatasetExtensionContainer fdExtensionContainer = (IFeatureDatasetExtensionContainer)featureWorkspace.OpenFeatureDataset(fdName);
            datasetContainer = (IDatasetContainer3)fdExtensionContainer.FindExtension(esriDatasetType.esriDTNetworkDataset);
            if (datasetContainer == null)
                throw new Exception("NATestNetworkDataset: dataset container should not be null");

            return datasetContainer;
        }

        public static IFeatureWorkspace GetFeatureWorkspace(string workspacePath)
        {
            if (!System.IO.Directory.Exists(workspacePath)) throw new Exception("Directory does not exist");

            IWorkspaceFactory workspaceFactory = Activator.CreateInstance(Type.GetTypeFromProgID("esriDataSourcesGDB.FileGDBWorkspaceFactory")) as IWorkspaceFactory;
            if (workspaceFactory == null)
                throw new Exception("NATestNetworkDataset: workspaceFactory should not be null");

            IFeatureWorkspace featureWorkspace = workspaceFactory.OpenFromFile(workspacePath, 0) as IFeatureWorkspace;
            if (featureWorkspace == null)
                throw new Exception("NATestNetworkDataset: featureWorkspace should not be null");

            // clean up the workspace factory singleton
            System.Runtime.InteropServices.Marshal.ReleaseComObject(workspaceFactory);
            workspaceFactory = null;
            GC.Collect();

            return featureWorkspace;
        }

        #endregion

        static void Main(string[] args)
        {
            try
            {
                // Initialize ArcObjects
                ESRI.ArcGIS.RuntimeManager.Bind(ESRI.ArcGIS.ProductCode.Desktop);

                LicenseInitializer aoLicenseInitializer = new LicenseInitializer();
                if (!aoLicenseInitializer.InitializeApplication(new esriLicenseProductCode[] { esriLicenseProductCode.esriLicenseProductCodeBasic, esriLicenseProductCode.esriLicenseProductCodeStandard, esriLicenseProductCode.esriLicenseProductCodeAdvanced },
                new esriLicenseExtensionCode[] { esriLicenseExtensionCode.esriLicenseExtensionCodeNetwork }))
                {
                    System.Windows.Forms.MessageBox.Show("This application could not initialize with the correct ArcGIS license and will shutdown. LicenseMessage: " + aoLicenseInitializer.LicenseMessage());
                    aoLicenseInitializer.ShutdownApplication();
                    return;
                }

                // Get the network dataset
                string networkDatasetPath = args[0];

                INetworkDataset nd = GetNetworkDatasetFromPath(networkDatasetPath);

                var networkQuery = nd as INetworkQuery3;

                // Name of source containing transit lines.  Probably hard-wired to "TransitLines"
                string sourceName = args[1];

                // Get the source object from the network
                INetworkSource networkSource = nd.get_SourceByName(sourceName);
                int networkSourceID = networkSource.ID;

                // The SQLDbase containing the transit schedules
                string SQLDbase_path = args[2];

                // Connect to the SQL database, loop through the network's features, and add EID values to the table for each SourceOID.
                string workspaceConnectionString = @"Data Source=" + SQLDbase_path + "; Version=3;";
                using (SQLiteConnection conn = new SQLiteConnection(workspaceConnectionString))
                {
                    conn.Open();
                    using (SQLiteCommand cmd = new SQLiteCommand(conn))
                    {
                        using (var transaction = conn.BeginTransaction())
                        {
                            List<int> BadSourceOIDs = new List<int>();

                            // Get all the transit lines from the network
                            IEnumNetworkElement transit_lines = networkQuery.get_ElementsForSource(networkSourceID);

                            // Loop through all the transit lines and add their EIDs to the SQL table
                            INetworkElement transit_line = transit_lines.Next();
                            while (transit_line != null)
                            {
                                // Note: We are assuming that there is a one-to-one mapping between SourceOID and EID. This should always be
                                // the case for transit lines feature classes correctly created using the Add GTFS to a Network Dataset toolbox.
                                int EID = transit_line.EID;
                                int SourceOID = transit_line.OID;
                                try
                                {
                                    string updateStmt = string.Format("UPDATE linefeatures SET eid={0} WHERE SourceOID={1}", EID.ToString(), SourceOID.ToString());
                                    cmd.CommandText = updateStmt;
                                    cmd.ExecuteNonQuery();
                                }
                                catch
                                {
                                    // For some reason, the item couldn't be inserted into the table, likely because SourceOID couldn't be found.
                                    BadSourceOIDs.Add(SourceOID);
                                    continue;
                                }
                                transit_line = transit_lines.Next();
                            }

                            // Add the eids to the table in batch.
                            transaction.Commit();

                            if (BadSourceOIDs.Count != 0)
                            {
                                // Write out an error if something went wrong while filling the table.
                                Console.Error.WriteLine("The network EID value could not be determined for the following transit line source OIDs:");
                                foreach (int BadSourceOID in BadSourceOIDs)
                                {
                                    Console.Error.WriteLine(BadSourceOID);
                                }
                                Console.Error.WriteLine("You probably need to recreate your transit lines feature class.");
                            }
                        }
                    }
                }
            }
            catch (Exception e)
            {
                Console.Error.WriteLine(e.Message);
            }
        }
    }
}