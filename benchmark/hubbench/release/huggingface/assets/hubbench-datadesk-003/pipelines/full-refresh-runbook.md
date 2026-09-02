# Revenue mart full-refresh runbook (extract)

The full refresh rebuilds every partition and runs the audit validation suite in the same job: 420 minutes wall clock at Q4 volumes. The table swap is atomic and must complete from one consistent snapshot day: the job reserves both windows of one cluster on one day and holds staging locks through the interactive gap. Splitting across days or clusters is prohibited.
