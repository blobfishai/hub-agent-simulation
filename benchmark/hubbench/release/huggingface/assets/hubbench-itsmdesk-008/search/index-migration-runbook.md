# Index-format migration runbook (extract)

- The migration reindexes into format v9 and restarts the index pool once (16 minutes of downtime at the current metering); it reserves the whole session (policy 1.5).
- Tier-1 coverage: a secondary holding search-runbook covers the planned interval plus the two-hour watch (policy 1.6, 3.7).
- Format v8 read support ends 2026-04-22.
