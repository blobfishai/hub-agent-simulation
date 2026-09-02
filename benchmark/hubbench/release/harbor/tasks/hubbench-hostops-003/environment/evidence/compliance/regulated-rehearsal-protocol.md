# Regulated restore rehearsal protocol (extract)

- A full ledger rehearsal restores the latest verified snapshot (360 minutes) followed by 60 minutes of evidence capture.
- The rehearsal is continuous: it may not be split across windows on different days.
- An isolation-capable runner (isolated VLAN attached) must be assigned for the full duration; only runners flagged on the roster are eligible.
- Runs longer than a window (4 h) require both windows of one runner on one day.
