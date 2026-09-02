-- DataDesk world: dbt-style model catalog and lineage, pipeline run history,
-- run schedules and backfill jobs, source feeds with vendor delivery
-- confirmations, freshness SLAs, finance reconciliation controls and
-- adjustment entries, warehouse window calendar, and collaboration surfaces.

CREATE TABLE clusters (
  cluster_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  backfill_capable INTEGER NOT NULL,
  status_note TEXT
);

CREATE TABLE models (
  model_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  layer TEXT NOT NULL,
  schema_name TEXT NOT NULL,
  materialization TEXT NOT NULL,
  owner TEXT NOT NULL,
  status TEXT NOT NULL,
  description TEXT
);

CREATE TABLE model_lineage (
  parent_model_id TEXT NOT NULL REFERENCES models(model_id),
  child_model_id TEXT NOT NULL REFERENCES models(model_id),
  relationship TEXT NOT NULL,
  PRIMARY KEY (parent_model_id, child_model_id)
);

CREATE TABLE sla_targets (
  sla_id TEXT PRIMARY KEY,
  model_id TEXT NOT NULL REFERENCES models(model_id),
  max_staleness_hours INTEGER NOT NULL,
  refresh_deadline TEXT NOT NULL,
  breach_escalation TEXT NOT NULL,
  business_reference TEXT NOT NULL,
  effective_from TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE pipeline_runs (
  run_id TEXT PRIMARY KEY,
  model_id TEXT NOT NULL REFERENCES models(model_id),
  partition_date TEXT NOT NULL,
  started_at TEXT NOT NULL,
  duration_minutes INTEGER NOT NULL,
  status TEXT NOT NULL,
  rows_processed INTEGER NOT NULL,
  trigger TEXT NOT NULL,
  source_version TEXT,
  note TEXT
);

CREATE TABLE run_schedules (
  schedule_id TEXT PRIMARY KEY,
  model_id TEXT NOT NULL REFERENCES models(model_id),
  description TEXT NOT NULL,
  duration_minutes INTEGER NOT NULL,
  cluster_id TEXT REFERENCES clusters(cluster_id),
  start_time TEXT,
  end_time TEXT,
  status TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  last_updated TEXT NOT NULL
);

CREATE TABLE backfill_jobs (
  job_id TEXT PRIMARY KEY,
  model_id TEXT NOT NULL REFERENCES models(model_id),
  partition_start TEXT NOT NULL,
  partition_end TEXT NOT NULL,
  partitions INTEGER NOT NULL,
  cluster_id TEXT REFERENCES clusters(cluster_id),
  start_time TEXT,
  end_time TEXT,
  status TEXT NOT NULL,
  description TEXT,
  requested_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE warehouse_slots (
  slot_id TEXT PRIMARY KEY,
  cluster_id TEXT NOT NULL REFERENCES clusters(cluster_id),
  service_date TEXT NOT NULL,
  window_name TEXT NOT NULL,
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL,
  status TEXT NOT NULL,
  hold_reason TEXT,
  job_id TEXT
);

CREATE TABLE vendors (
  vendor_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  account_number TEXT NOT NULL
);

CREATE TABLE feeds (
  feed_id TEXT PRIMARY KEY,
  vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
  name TEXT NOT NULL,
  dataset TEXT NOT NULL,
  cadence TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE feed_deliveries (
  delivery_id TEXT PRIMARY KEY,
  feed_id TEXT NOT NULL REFERENCES feeds(feed_id),
  business_date TEXT NOT NULL,
  files_expected INTEGER NOT NULL,
  files_received INTEGER NOT NULL,
  rows_received INTEGER NOT NULL,
  rows_invalid INTEGER NOT NULL,
  rows_duplicate INTEGER NOT NULL,
  rows_late INTEGER NOT NULL,
  status TEXT NOT NULL,
  received_at TEXT NOT NULL,
  note TEXT
);

CREATE TABLE vendor_confirmations (
  confirmation_id TEXT PRIMARY KEY,
  vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
  feed_id TEXT NOT NULL REFERENCES feeds(feed_id),
  reference TEXT NOT NULL,
  scope_note TEXT NOT NULL,
  standard_redelivery_date TEXT NOT NULL,
  expedited_redelivery_date TEXT NOT NULL,
  expedite_fee_usd REAL NOT NULL,
  valid_until TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE recon_controls (
  control_id TEXT PRIMARY KEY,
  model_id TEXT NOT NULL REFERENCES models(model_id),
  metric TEXT NOT NULL,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  control_total_rows INTEGER NOT NULL,
  source TEXT NOT NULL,
  published_at TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE adjustment_entries (
  entry_id TEXT PRIMARY KEY,
  model_id TEXT NOT NULL REFERENCES models(model_id),
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  direction TEXT NOT NULL,
  rows INTEGER NOT NULL,
  reason TEXT NOT NULL,
  approval_id TEXT,
  status TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE approvals (
  approval_id TEXT PRIMARY KEY,
  subject TEXT NOT NULL,
  approver_id TEXT NOT NULL,
  approver_role TEXT NOT NULL,
  status TEXT NOT NULL,
  granted_on TEXT NOT NULL,
  scope_json TEXT NOT NULL
);

CREATE TABLE messages (
  message_id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  sender TEXT NOT NULL,
  recipients TEXT NOT NULL,
  subject TEXT NOT NULL,
  sent_at TEXT NOT NULL,
  body TEXT NOT NULL,
  attachments_json TEXT NOT NULL,
  labels TEXT NOT NULL
);

CREATE TABLE chat_threads (
  thread_id TEXT PRIMARY KEY,
  channel TEXT NOT NULL,
  title TEXT NOT NULL,
  messages_json TEXT NOT NULL
);

CREATE TABLE drive_files (
  file_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  modified_time TEXT NOT NULL,
  folder TEXT NOT NULL,
  content TEXT NOT NULL,
  sha256 TEXT NOT NULL
);

CREATE TABLE note_drafts (
  draft_id TEXT PRIMARY KEY,
  recipient TEXT NOT NULL,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  related_model_id TEXT,
  related_case TEXT,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL
);
