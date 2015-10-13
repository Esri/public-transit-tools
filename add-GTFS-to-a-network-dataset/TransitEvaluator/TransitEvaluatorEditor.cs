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
using System.Runtime.InteropServices;
using ESRI.ArcGIS.ADF.CATIDs;
using ESRI.ArcGIS.CatalogUI;
using ESRI.ArcGIS.esriSystem;

namespace TransitEvaluator
{
	[ClassInterface(ClassInterfaceType.None)]
    [Guid("3AB7BC00-E283-49DC-B068-511A06F2B604")]
    public class TransitEvaluatorEditor : IEvaluatorEditor
	{
		#region Component Category Registration

		[ComRegisterFunction()]
		[ComVisible(false)]
		static void RegisterFunction(Type registerType)
		{
			string regKey = string.Format("HKEY_CLASSES_ROOT\\CLSID\\{{{0}}}", registerType.GUID);
			NetworkEvaluatorEditor.Register(regKey);
		}

		[ComUnregisterFunction()]
		[ComVisible(false)]
		static void UnregisterFunction(Type registerType)
		{
			string regKey = string.Format("HKEY_CLASSES_ROOT\\CLSID\\{{{0}}}", registerType.GUID);
			NetworkEvaluatorEditor.Unregister(regKey);
		}

		#endregion

		#region IEvaluatorEditor Members

		public bool ContextSupportsEditDescriptors
		{
			// The descriptor text is the single line of text in the Evaluators dialog that appears under the Value column.
			//  This property indicates whether the descriptor text can be directly edited in the dialog by the user.
			//  Since this evaluator editor does not make use of descriptors, it returns false
			get { return false; }
		}

		public bool ContextSupportsEditProperties
		{
			// This property indicates whether the ArcCatalog user is able to bring up a dialog by 
      //  clicking the Properties button (or pressing F12) in order to specify settings for the evaluator.
			get { return false; }
		}

		public void EditDescriptors(string value)
		{
			// This evaluator editor does not make use of descriptors.
		}

        private IEditEvaluators m_EditEvaluators;
        public IEditEvaluators EditEvaluators
        {
            // This property is used by ArcCatalog to set a reference to its EditEvaluators object 
            //  on each registered EvaluatorEditor. This allows each EvaluatorEditor to access the 
            //  current state of ArcCatalog's Evaluators dialog, such as how many evaluators are listed 
            //  and which evaluators are currently selected.
            get { return m_EditEvaluators; }
            set { m_EditEvaluators = value; }
        }

		public bool EditProperties(int parentWindow)
		{
			return true;
		}

		public UID EvaluatorCLSID
		{
			get
			{
                // This property returns the GUID of this EvaluatorEditor's associated INetworkEvaluator.
				UID uid = new UIDClass();
                uid.Value = "{5DC6A0FF-EC95-47A4-9169-783FB4474E51}";
				return uid;
			}
		}

		public void SetDefaultProperties(int index)
		{
			// This method is called when the ArcCatalog user selects this evaluator 
            //  under the Type column of the Evaluators dialog. This method can be used to 
            //  initialize any dialogs that the evaluator editor uses.
		}

		public int ValueChoice
		{
			// This evaluator editor does not support value choices.
			set { }
		}

		public int ValueChoiceCount
		{
			// This evaluator editor has no value choices.
			get { return 0; }
		}

		public string get_Descriptor(int index)
		{
			// This evaluator editor does not make use of descriptors.
			return string.Empty;
		}

		public string get_FullDescription(int index)
		{
			// This property is the text representation of all of the settings made on this evaluator.
			// This evaluator editor does not make any settings changes, so it returns an empty string.
			return string.Empty;
		}

		public string get_ValueChoiceDescriptor(int choice)
		{
			// This evaluator editor does not make use of value choices.
			return string.Empty;
		}

		#endregion
	}
}
