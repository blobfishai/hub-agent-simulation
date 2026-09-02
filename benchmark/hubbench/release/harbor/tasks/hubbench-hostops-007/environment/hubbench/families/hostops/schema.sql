-- HostOps world: Linux host + service inventory, release tickets, scheduler,
-- backup catalog with retention and vendor retrievals, release build farm,
-- approvals, and the collaboration surfaces.

CREATE TABLE stores (
  store_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL
);

CREATE TABLE engineers (
  engineer_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  focus TEXT NOT NULL
);

CREATE TABLE services (
  service_id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  tier TEXT NOT NULL,
  owner_team TEXT NOT NULL,
  primary_engineer_id TEXT REFERENCES engineers(engineer_id)
);

CREATE TABLE hosts (
  host_id TEXT PRIMARY KEY,
  hostname TEXT NOT NULL,
  role TEXT NOT NULL,
  os_release TEXT NOT NULL,
  status TEXT NOT NULL,
  service_id TEXT REFERENCES services(service_id)
);

CREATE TABLE meterings (
  metering_id TEXT PRIMARY KEY,
  service_id TEXT NOT NULL REFERENCES services(service_id),
  metric TEXT NOT NULL,
  value REAL NOT NULL,
  unit TEXT NOT NULL,
  measured_at TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE artifact_classes (
  artifact_class TEXT PRIMARY KEY,
  display TEXT NOT NULL,
  segment_size_gb REAL NOT NULL,
  segment_unit TEXT NOT NULL,
  storage_tier TEXT NOT NULL,
  minimum_retention_days INTEGER NOT NULL,
  signed INTEGER NOT NULL,
  interchangeable_with TEXT
);

CREATE TABLE tickets (
  ticket_id TEXT PRIMARY KEY,
  service_id TEXT NOT NULL REFERENCES services(service_id),
  artifact_class TEXT NOT NULL REFERENCES artifact_classes(artifact_class),
  unit_kind TEXT NOT NULL,
  unit_basis TEXT NOT NULL,
  unit_gb REAL,
  units_in_scope INTEGER NOT NULL,
  scope_note TEXT NOT NULL,
  build_minutes INTEGER NOT NULL,
  verify_minutes INTEGER NOT NULL,
  status TEXT NOT NULL,
  kind TEXT NOT NULL,
  priority TEXT NOT NULL,
  opened_at TEXT NOT NULL,
  requested_by TEXT NOT NULL REFERENCES engineers(engineer_id),
  note TEXT
);

CREATE TABLE backup_sets (
  set_id TEXT PRIMARY KEY,
  artifact_class TEXT NOT NULL REFERENCES artifact_classes(artifact_class),
  set_label TEXT NOT NULL,
  store_id TEXT NOT NULL REFERENCES stores(store_id),
  segment_count INTEGER NOT NULL,
  retention_expiry TEXT NOT NULL,
  status TEXT NOT NULL,
  status_reason TEXT,
  reserved_for_ticket TEXT
);

CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  service_id TEXT REFERENCES services(service_id),
  kind TEXT NOT NULL,
  schedule TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE job_runs (
  run_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(job_id),
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL,
  status TEXT NOT NULL,
  exit_code INTEGER NOT NULL,
  summary TEXT NOT NULL
);

CREATE TABLE runners (
  runner_id TEXT PRIMARY KEY,
  pool TEXT NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  isolation_capable INTEGER NOT NULL,
  status_note TEXT
);

CREATE TABLE farm_windows (
  window_id TEXT PRIMARY KEY,
  runner_id TEXT NOT NULL REFERENCES runners(runner_id),
  service_date TEXT NOT NULL,
  session TEXT NOT NULL,
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL,
  status TEXT NOT NULL,
  hold_reason TEXT,
  reservation_id TEXT
);

CREATE TABLE reservations (
  reservation_id TEXT PRIMARY KEY,
  service_id TEXT NOT NULL REFERENCES services(service_id),
  ticket_id TEXT REFERENCES tickets(ticket_id),
  runner_id TEXT REFERENCES runners(runner_id),
  start_time TEXT,
  end_time TEXT,
  status TEXT NOT NULL,
  description TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  last_updated TEXT NOT NULL
);

CREATE TABLE vendors (
  vendor_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  account_number TEXT NOT NULL
);

CREATE TABLE retrieval_confirmations (
  confirmation_id TEXT PRIMARY KEY,
  vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
  artifact_class TEXT NOT NULL REFERENCES artifact_classes(artifact_class),
  reference TEXT NOT NULL,
  segments_available INTEGER NOT NULL,
  standard_ready_date TEXT NOT NULL,
  expedited_ready_date TEXT NOT NULL,
  expedite_fee_usd REAL NOT NULL,
  per_segment_fee_usd REAL NOT NULL,
  valid_until TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE restore_jobs (
  restore_id TEXT PRIMARY KEY,
  vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
  confirmation_id TEXT REFERENCES retrieval_confirmations(confirmation_id),
  artifact_class TEXT NOT NULL,
  segment_count INTEGER NOT NULL,
  unit TEXT NOT NULL,
  retrieval_option TEXT NOT NULL,
  expected_ready_date TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE store_copies (
  copy_id TEXT PRIMARY KEY,
  artifact_class TEXT NOT NULL,
  segment_count INTEGER NOT NULL,
  from_store_id TEXT NOT NULL REFERENCES stores(store_id),
  to_store_id TEXT NOT NULL REFERENCES stores(store_id),
  scheduled_date TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_by TEXT NOT NULL,
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
  related_ticket_id TEXT,
  related_service_id TEXT,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL
);
