# Data Platform Operations Policy (2025 edition) — SUPERSEDED

This edition was replaced by v4 on 2026-01-12 and is retained for audit only. Do not apply it.

1. Late-arriving rows may be counted into certified marts as soon as they land in staging.
2. On-call engineers may correct a certified mart by direct edit for variances up to 1,000 rows.
3. The warehouse runs a single 20:00-04:00 batch block; long refreshes may span two nights.
4. Protected replication windows may be displaced by the on-call engineer when a dashboard is late.
5. Expedite fees up to USD 500 may be approved verbally by the requesting analyst.
6. Adjustment entries do not require a covering control total for periods still open.

---
Evidence-room mount: datadesk-008 / DATA-0008.
