using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using System.Windows.Forms;

namespace TransitEvaluator
{
     public partial class ProgressForm : Form
    {

        #region member variables

        // Callback used to update the UI while running a background thread
        private delegate void IncrementProgressBarCallback();
        private delegate void SetTotalRowCountCallback();
        private delegate void DisplayTimeCallback();
        private delegate void DisplayTableNameCallback();
        private delegate void DisplayErrorCallback();

        // A timer will track how much time is remaining
        static private System.Windows.Forms.Timer m_timer = new System.Windows.Forms.Timer();
        static private long m_total_seconds_remaining;
        private int m_total_row_count = 0;
        private string m_current_table_name = "";
        int m_one_percent = 0;

        private string m_workspace_path;
        private Thread m_thread;

        private string m_caching_message;
        public string CachingMessage
        { get { return m_caching_message; } }

        private bool m_caching_complete = false;
        public bool CachingComplete
        { get { return m_caching_complete; } }

        // A hash of trips keyed with trip_id: <trip_id, Trip>
        private Dictionary<string, Trip> m_trips = new Dictionary<string, Trip>();
        public Dictionary<string, Trip> Trips
        {
            get { return m_trips; }
        }

        // A hash of eids with trip instances <eid, List<trip_instance>>
        private Dictionary<long, List<trip_instance>> m_eids = new Dictionary<long, List<trip_instance>>();
        public Dictionary<long, List<trip_instance>> eids
        {
            get { return m_eids; }
        }

        // A hash of eids with trip instances <eid, List<trip_instance>>
        private Dictionary<long, long> m_linefeatures = new Dictionary<long, long>();
        public Dictionary<long, long> linefeatures
        {
            get { return m_linefeatures; }
        }

        // A hash of calendars
        private Dictionary<string, Calendar> m_calendars = new Dictionary<string, Calendar>();
        public Dictionary<string, Calendar> Calendars
        {
            get { return m_calendars; }
        }

        // A hash of calendar exceptions
        private Dictionary<string, Dictionary<DateTime, CalendarExceptionType>> m_calExceptions = new Dictionary<string, Dictionary<DateTime, CalendarExceptionType>>();
        public Dictionary<string, Dictionary<DateTime, CalendarExceptionType>> Cal_Exceptions
        {
            get { return m_calExceptions; }
        }

        public int ProgressValue
        {
            get { return cachingProgressBar.Value; }
            set { cachingProgressBar.Value = value; }
        }

        #endregion

        #region manage the form

        public ProgressForm(string workspace_path)
        {
            InitializeComponent();
            m_workspace_path = workspace_path;

            m_thread = new Thread(new ThreadStart(CacheSchedules));
            m_thread.SetApartmentState(ApartmentState.STA);

            m_timer.Tick += new EventHandler(TimerTick);
            m_timer.Interval = 1000; // Timer goes off each second
        }

        // The entry point for the form
        private void ProgressForm_Load(object sender, EventArgs e)
        {
            // Begin processing and start the countdown to completion
            m_thread.Start();
            m_total_seconds_remaining = 80; // assume a start time
            m_timer.Start();
        }

        private void btnCancel_Click(object sender, EventArgs e)
        {
            Cancel();
        }

        private void Cancel()
        {
            m_trips.Clear();
            m_calendars.Clear();
            m_calExceptions.Clear();
            m_caching_complete = false;
            m_timer.Stop();
            m_timer.Dispose();

            this.DialogResult = System.Windows.Forms.DialogResult.Cancel;
        }

        #endregion

        #region UI update callbacks

        private void IncrementProgressBar()
        {
            // InvokeRequired required compares the thread ID of the
            // calling thread to the thread ID of the creating thread.
            // If these threads are different, it returns true.
            if (this.cachingProgressBar.InvokeRequired)
            {
                //call itself on the main thread
                IncrementProgressBarCallback d = new IncrementProgressBarCallback(IncrementProgressBar);
                this.Invoke(d);
            }
            else
            {
                this.cachingProgressBar.Increment(1);
            }
        }

        private void TimerTick(System.Object myObject, EventArgs myEventArgs)
        {
            // count off a second, then update the timer in the UI
            if (m_total_seconds_remaining > 0)
                --m_total_seconds_remaining;
            DisplayTime();
        }

        private void DisplayTableName()
        {
            // InvokeRequired required compares the thread ID of the
            // calling thread to the thread ID of the creating thread.
            // If these threads are different, it returns true.
            if (this.lblTableName.InvokeRequired)
            {
                //call itself on the main thread
                DisplayTableNameCallback d = new DisplayTableNameCallback(DisplayTableName);
                this.Invoke(d);
            }
            else
            {
                this.lblTableName.Text = m_current_table_name;
            }
        }

        private void DisplayError()
        {
            // InvokeRequired required compares the thread ID of the
            // calling thread to the thread ID of the creating thread.
            // If these threads are different, it returns true.
            if (this.lvError.InvokeRequired)
            {
                //call itself on the main thread
                DisplayErrorCallback d = new DisplayErrorCallback(DisplayError);
                this.Invoke(d);
            }
            else
            {
                this.lvError.Items.Clear();
                this.lvError.View = View.Details;
                this.lvError.Columns.Add("Text");
                this.lvError.Columns[0].Width = this.lvError.Width - 4;
                this.lvError.HeaderStyle = ColumnHeaderStyle.None;
                this.lvError.ShowItemToolTips = true;

                // break up the text into 40 characters or so, because the view truncates it
                string[] split_message = m_caching_message.Split(' ');
                string current_text = "";
                for (int split_index = 0; split_index < split_message.Length; ++split_index)
                {
                    string split_part = split_message[split_index];

                    if ((40 < current_text.Length + split_part.Length)) 
                    {
                        AddError(current_text);
                        current_text = split_part;
                    }
                    else
                    {
                        if (current_text.Trim() != "") current_text += " ";

                        current_text += split_part;
                    }

                    // If the current part is the last part, just display it.
                    if (split_index == split_message.Length - 1)
                        AddError(current_text);
                }
            }
        }

        private void AddError(string error_message)
        {
            ListViewItem lvItem = new ListViewItem(new string[] { error_message, "INVISIBLE" });
            //lvItem.Text = m_caching_message;
            //lvItem.BackColor = System.Drawing.Color.Red;
            lvItem.ForeColor = System.Drawing.Color.Red;
            lvItem.Font = new System.Drawing.Font(lvItem.Font, System.Drawing.FontStyle.Bold);
            lvItem.ToolTipText = m_caching_message;
            this.lvError.Items.Add(lvItem);
        }

        private void DisplayTime()
        {
            // InvokeRequired required compares the thread ID of the
            // calling thread to the thread ID of the creating thread.
            // If these threads are different, it returns true.
            if (this.lblTimeRemaining.InvokeRequired)
            {
                //call itself on the main thread
                DisplayTimeCallback d = new DisplayTimeCallback(DisplayTime);
                this.Invoke(d);
            }
            else
            {
                long minutesRemaining = m_total_seconds_remaining / 60;
                long secondsRemaining = m_total_seconds_remaining % 60;
                this.lblTimeRemaining.Text = String.Format("{0:00}:{1:00}", minutesRemaining, secondsRemaining);
            }
        }

        private void UpdateTimeUI(int processedRowCount, Stopwatch timeSoFar)
        {
            // increment the progress bar every 1 percent
            if ((processedRowCount % m_one_percent) == 0)
            {
                IncrementProgressBar();
            }

            // update the remaining time every 10 percent
            if ((processedRowCount % (m_one_percent * 10)) == 0)
            {
                // rowsToGo / rowsProcessedSoFar = timeToGo / timeSoFar
                // Therefor: timeToGo = (rowsToGo * timeSoFar) / rowsProcessed
                long secondsSoFar = timeSoFar.ElapsedMilliseconds / 1000;
                long rowsToGo = m_total_row_count - processedRowCount;
                if (processedRowCount > 0)
                    m_total_seconds_remaining = (rowsToGo * secondsSoFar) / processedRowCount;
                DisplayTime();
            }
        }

        private void SetTotalRowCount()
        {
            // InvokeRequired required compares the thread ID of the
            // calling thread to the thread ID of the creating thread.
            // If these threads are different, it returns true.
            if (this.lblTotalRowCount.InvokeRequired)
            {
                //call itself on the main thread
                SetTotalRowCountCallback d = new SetTotalRowCountCallback(SetTotalRowCount);
                this.Invoke(d);
            }
            else
            {
                this.lblTotalRowCount.Text = this.m_total_row_count.ToString();
            }
        }

        #endregion

        private void CacheSchedules()
        {
            TransitScheduleCacher.CacheSchedules(ref m_caching_complete, m_workspace_path,
                ref m_total_row_count, SetTotalRowCount, ref m_one_percent,
                ref m_caching_message, ref m_current_table_name, DisplayTableName,
                UpdateTimeUI, ref m_calExceptions, ref m_calendars, ref m_trips, ref m_eids, ref m_linefeatures);

            if (m_caching_complete)
            {
                this.DialogResult = System.Windows.Forms.DialogResult.OK;
            }
            else
            {
                //btnCancel.Text = "&Close";
                DisplayError();
                m_total_seconds_remaining = 0;
            }
        }
    }
}
