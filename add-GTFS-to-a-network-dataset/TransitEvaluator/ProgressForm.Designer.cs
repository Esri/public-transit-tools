namespace TransitEvaluator
{
  partial class ProgressForm
  {
    /// <summary>
    /// Required designer variable.
    /// </summary>
    private System.ComponentModel.IContainer components = null;

    /// <summary>
    /// Clean up any resources being used.
    /// </summary>
    /// <param name="disposing">true if managed resources should be disposed; otherwise, false.</param>
    protected override void Dispose(bool disposing)
    {
      if (disposing && (components != null))
      {
        components.Dispose();
      }
      base.Dispose(disposing);
    }

    #region Windows Form Designer generated code

    /// <summary>
    /// Required method for Designer support - do not modify
    /// the contents of this method with the code editor.
    /// </summary>
    private void InitializeComponent()
    {
        this.cachingProgressBar = new System.Windows.Forms.ProgressBar();
        this.label1 = new System.Windows.Forms.Label();
        this.lblCount = new System.Windows.Forms.Label();
        this.label2 = new System.Windows.Forms.Label();
        this.lblTimeRemaining = new System.Windows.Forms.Label();
        this.label4 = new System.Windows.Forms.Label();
        this.lblTotalRowCount = new System.Windows.Forms.Label();
        this.btnCancel = new System.Windows.Forms.Button();
        this.label3 = new System.Windows.Forms.Label();
        this.label5 = new System.Windows.Forms.Label();
        this.lblTableName = new System.Windows.Forms.Label();
        this.lvError = new System.Windows.Forms.ListView();
        this.SuspendLayout();
        // 
        // cachingProgressBar
        // 
        this.cachingProgressBar.Location = new System.Drawing.Point(15, 63);
        this.cachingProgressBar.Name = "cachingProgressBar";
        this.cachingProgressBar.Size = new System.Drawing.Size(248, 23);
        this.cachingProgressBar.Step = 1;
        this.cachingProgressBar.TabIndex = 0;
        // 
        // label1
        // 
        this.label1.AutoSize = true;
        this.label1.Location = new System.Drawing.Point(12, 9);
        this.label1.Name = "label1";
        this.label1.Size = new System.Drawing.Size(230, 13);
        this.label1.TabIndex = 1;
        this.label1.Text = "Please wait while transit schedules are cached.";
        this.label1.TextAlign = System.Drawing.ContentAlignment.TopCenter;
        // 
        // lblCount
        // 
        this.lblCount.AutoSize = true;
        this.lblCount.Location = new System.Drawing.Point(37, 115);
        this.lblCount.Name = "lblCount";
        this.lblCount.Size = new System.Drawing.Size(0, 13);
        this.lblCount.TabIndex = 2;
        // 
        // label2
        // 
        this.label2.AutoSize = true;
        this.label2.Location = new System.Drawing.Point(12, 149);
        this.label2.Name = "label2";
        this.label2.Size = new System.Drawing.Size(126, 13);
        this.label2.TabIndex = 3;
        this.label2.Text = "Estimated time remaining:";
        // 
        // lblTimeRemaining
        // 
        this.lblTimeRemaining.AutoSize = true;
        this.lblTimeRemaining.Location = new System.Drawing.Point(154, 149);
        this.lblTimeRemaining.Name = "lblTimeRemaining";
        this.lblTimeRemaining.Size = new System.Drawing.Size(13, 13);
        this.lblTimeRemaining.TabIndex = 4;
        this.lblTimeRemaining.Text = "0";
        // 
        // label4
        // 
        this.label4.AutoSize = true;
        this.label4.Location = new System.Drawing.Point(12, 128);
        this.label4.Name = "label4";
        this.label4.Size = new System.Drawing.Size(111, 13);
        this.label4.TabIndex = 5;
        this.label4.Text = "Total rows to process:";
        // 
        // lblTotalRowCount
        // 
        this.lblTotalRowCount.AutoSize = true;
        this.lblTotalRowCount.Location = new System.Drawing.Point(154, 128);
        this.lblTotalRowCount.Name = "lblTotalRowCount";
        this.lblTotalRowCount.Size = new System.Drawing.Size(13, 13);
        this.lblTotalRowCount.TabIndex = 6;
        this.lblTotalRowCount.Text = "0";
        // 
        // btnCancel
        // 
        this.btnCancel.Location = new System.Drawing.Point(95, 263);
        this.btnCancel.Name = "btnCancel";
        this.btnCancel.Size = new System.Drawing.Size(75, 23);
        this.btnCancel.TabIndex = 7;
        this.btnCancel.Text = "&Cancel";
        this.btnCancel.UseVisualStyleBackColor = true;
        this.btnCancel.Click += new System.EventHandler(this.btnCancel_Click);
        // 
        // label3
        // 
        this.label3.AutoSize = true;
        this.label3.Location = new System.Drawing.Point(12, 31);
        this.label3.Name = "label3";
        this.label3.Size = new System.Drawing.Size(255, 13);
        this.label3.TabIndex = 8;
        this.label3.Text = "If successful, caching only occurs once per process.";
        this.label3.TextAlign = System.Drawing.ContentAlignment.TopCenter;
        // 
        // label5
        // 
        this.label5.AutoSize = true;
        this.label5.Location = new System.Drawing.Point(12, 102);
        this.label5.Name = "label5";
        this.label5.Size = new System.Drawing.Size(88, 13);
        this.label5.TabIndex = 9;
        this.label5.Text = "Processing table:";
        // 
        // lblTableName
        // 
        this.lblTableName.AutoSize = true;
        this.lblTableName.Location = new System.Drawing.Point(154, 102);
        this.lblTableName.Name = "lblTableName";
        this.lblTableName.Size = new System.Drawing.Size(16, 13);
        this.lblTableName.TabIndex = 10;
        this.lblTableName.Text = "...";
        // 
        // lvError
        // 
        this.lvError.BackColor = System.Drawing.SystemColors.Control;
        this.lvError.BorderStyle = System.Windows.Forms.BorderStyle.None;
        this.lvError.HeaderStyle = System.Windows.Forms.ColumnHeaderStyle.None;
        this.lvError.Location = new System.Drawing.Point(15, 179);
        this.lvError.Name = "lvError";
        this.lvError.Size = new System.Drawing.Size(248, 78);
        this.lvError.TabIndex = 12;
        this.lvError.UseCompatibleStateImageBehavior = false;
        this.lvError.View = System.Windows.Forms.View.Details;
        // 
        // ProgressForm
        // 
        this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 13F);
        this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
        this.AutoSize = true;
        this.AutoValidate = System.Windows.Forms.AutoValidate.Disable;
        this.ClientSize = new System.Drawing.Size(275, 296);
        this.ControlBox = false;
        this.Controls.Add(this.lvError);
        this.Controls.Add(this.lblTableName);
        this.Controls.Add(this.label5);
        this.Controls.Add(this.label3);
        this.Controls.Add(this.btnCancel);
        this.Controls.Add(this.lblTotalRowCount);
        this.Controls.Add(this.label4);
        this.Controls.Add(this.lblTimeRemaining);
        this.Controls.Add(this.label2);
        this.Controls.Add(this.lblCount);
        this.Controls.Add(this.label1);
        this.Controls.Add(this.cachingProgressBar);
        this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedDialog;
        this.MaximizeBox = false;
        this.MinimizeBox = false;
        this.Name = "ProgressForm";
        this.SizeGripStyle = System.Windows.Forms.SizeGripStyle.Hide;
        this.Text = "Progress";
        this.Load += new System.EventHandler(this.ProgressForm_Load);
        this.ResumeLayout(false);
        this.PerformLayout();

    }

    #endregion

    private System.Windows.Forms.ProgressBar cachingProgressBar;
    private System.Windows.Forms.Label label1;
    private System.Windows.Forms.Label lblCount;
    private System.Windows.Forms.Label label2;
    private System.Windows.Forms.Label lblTimeRemaining;
    private System.Windows.Forms.Label label4;
    private System.Windows.Forms.Label lblTotalRowCount;
    private System.Windows.Forms.Button btnCancel;
    private System.Windows.Forms.Label label3;
    private System.Windows.Forms.Label label5;
    private System.Windows.Forms.Label lblTableName;
    private System.Windows.Forms.ListView lvError;
  }
}