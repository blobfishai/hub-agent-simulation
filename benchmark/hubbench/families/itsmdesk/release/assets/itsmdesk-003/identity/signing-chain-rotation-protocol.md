# Signing-chain rotation protocol (extract)

- A gateway rotation loads the new intermediate chain, restarts the pool, verifies OCSP, and restarts once more: two restarts at the current RESTART-MIN metering plus 6 minutes of validation.
- The rotation reserves the whole session; no other change shares it (policy 1.5).
- The lane must be certified for tier-1 and a secondary holding identity-runbook must cover the interval plus the two-hour watch.
- The chain-2024 certificate expires 2026-04-27 23:59; the rotation must complete before then.
