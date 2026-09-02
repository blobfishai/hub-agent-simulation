# Margin backfill runbook (extract)

A margin partition reruns in at most 55 minutes on WH-STD at current volumes; plan 4 partitions per 4-hour window. A backfill reserves whole windows, holds staging locks for the reservation, and never spans clusters. Corrected vendor files must be validated (next batch day after delivery) before the rerun is scheduled.
