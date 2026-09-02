# Hotfix backport procedure (extract)

1. Only eligible commits ride a backport: status merged, not reverted, not embargoed for a named change, not docs-only.
2. Backports ride the 21:00 merge-queue run; the target branch is rebuilt and verified on the next business day after the scheduled date.
3. Commits the target branch already carries are never re-applied; backport only the commits it is missing.
4. Reverted or embargoed commits are never backported, whatever the requesting team's need.
