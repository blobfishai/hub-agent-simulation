# Dedicated-tenant cutover rehearsal protocol (extract)

- A full ledger rehearsal replays the latest verified migration (360 minutes) followed by 60 minutes of evidence capture.
- The rehearsal is continuous: it may not be split across windows on different days.
- A tenant-isolation-capable lane must carry the run for the full duration; only lanes flagged on the roster are eligible.
- Runs longer than a window (4 h) require both windows of one lane on one day.
