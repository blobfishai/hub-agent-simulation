# Data Platform Operations Policy (v4, effective 2026-01-12)

Applies to Tidewater Supply Co. Data Platform: the production warehouse (WH-PROD) and its
compute clusters WH-XL (finance workloads), WH-STD (general ELT), and WH-ADHOC (analyst
sandbox). This version supersedes the 2025 policy in full. Planning date references below
assume the current batch calendar; today is 2026-03-09.

## 1. Reconciliation and adjustment entries

1.1 Certified marts reconcile to Finance's published control totals. A dashboard variance is
corrected only by (a) reloading validated source files, or (b) an adjustment entry bounded to
the independently verified variance. Certified tables are never edited by hand.
1.2 An adjustment entry requires a signed approval naming the model, the period, and a maximum
row count. The entry may never exceed that maximum or the verified variance, whichever is lower.
1.3 Adjustments touching a closed accounting period, and any restatement posted instead of a
source reload, require the head of data and the finance controller jointly.
1.4 An adjustment must reference the published control total it reconciles to; entries without a
covering control are rejected.

## 2. Ingestion validation and vendor redelivery

2.1 Rows failing schema validation, rows duplicating an already-loaded business key, and rows
landing after the 02:00 cutoff are excluded from certified marts. Excluded rows are quarantined
in staging; they count only after a validated redelivery.
2.2 A vendor redelivery is validated overnight and is loadable from the next batch day after the
confirmed delivery date. A vendor confirmation alone proves neither validation nor load.
2.3 Staged redeliveries marked STAGED are picked up by the next scheduled load of the consuming
model; they are not part of the certified mart until that load completes.
2.4 Expedite fees are payable only when named in the signed approval; otherwise the data
platform lead must approve the fee before the redelivery is requested.

## 3. Warehouse windows and backfills

3.1 Batch windows are NIGHT 01:00-05:00 and DAY 13:00-17:00, Monday to Friday. A backfill or
refresh of up to 4 hours occupies one window; longer work must reserve both windows of one
cluster on the same day and holds its staging locks through the interactive period between them.
3.2 Splitting one refresh or backfill across different days or clusters is prohibited: the
resulting table swap would mix snapshot days.
3.3 Protected windows (finance close loads, replication) and blocked windows (maintenance) are
never displaced without the head of data.
3.4 Backfills run only on backfill-capable clusters per the cluster roster; WH-ADHOC carries no
service-account write grants and never runs certified loads or backfills.
3.5 Certified loads displaced by a cluster outage may run at most 5 business days after their
cycle date; later than that the affected mart is decertified.

## 4. Authority

4.1 The analytics engineer on call executes exactly what a signed approval covers: the named
model, period, row maximum, cluster set, and any named fee.
4.2 Data platform lead: expedite fees not named in an approval, full-history rebuilds,
cross-cluster spillover, and partner re-transmission agreements.
4.3 Head of data: displacing protected windows, publishing from an uncertified mart, and joint
sign-off (with the finance controller) on closed-period adjustments.
4.4 Warehouse operations manager: cluster maintenance windows and their return-to-service dates.
4.5 An approval covers exactly the record, period, quantity, and options it names. It never
selects an option in advance and never extends to a broader record.

---
Evidence-room mount: datadesk-002 / DATA-0002.
