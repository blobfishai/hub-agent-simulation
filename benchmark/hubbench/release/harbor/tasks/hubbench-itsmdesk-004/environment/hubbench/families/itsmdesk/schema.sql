-- ITSMDesk world: ServiceNow-shaped ITSM (CIs, nodes, incidents, problems,
-- change requests, change tasks, planned outages), Grafana/Prometheus-shaped
-- telemetry (SLOs, burn samples, alerts), a change calendar with lanes,
-- freeze windows and maintenance windows, a PagerDuty-shaped on-call plane
-- (schedules, shifts, escalation policies, overrides), a vendor patch portal
-- (advisories), approvals, and the collaboration surfaces.

CREATE TABLE engineers (
  engineer_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  team TEXT NOT NULL,
  certifications TEXT NOT NULL
);

CREATE TABLE vendors (
  vendor_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  account_number TEXT NOT NULL
);

CREATE TABLE change_lanes (
  lane_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  weekday_policy TEXT NOT NULL,
  tier1_capable INTEGER NOT NULL,
  status TEXT NOT NULL,
  status_note TEXT
);

CREATE TABLE services (
  service_id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  tier TEXT NOT NULL,
  owner_team TEXT NOT NULL,
  lane_id TEXT NOT NULL REFERENCES change_lanes(lane_id),
  primary_engineer_id TEXT REFERENCES engineers(engineer_id),
  runtime TEXT NOT NULL,
  version TEXT NOT NULL,
  required_certification TEXT,
  validation_minutes INTEGER NOT NULL,
  rollback_minutes INTEGER NOT NULL
);

CREATE TABLE nodes (
  node_id TEXT PRIMARY KEY,
  service_id TEXT NOT NULL REFERENCES services(service_id),
  pool TEXT NOT NULL,
  region TEXT NOT NULL,
  lane_id TEXT NOT NULL REFERENCES change_lanes(lane_id),
  version TEXT NOT NULL,
  status TEXT NOT NULL,
  staged_build TEXT,
  build_status TEXT,
  pinned_for TEXT
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

CREATE TABLE slos (
  slo_id TEXT PRIMARY KEY,
  service_id TEXT NOT NULL REFERENCES services(service_id),
  name TEXT NOT NULL,
  sli TEXT NOT NULL,
  objective_pct REAL NOT NULL,
  window_days INTEGER NOT NULL,
  budget_minutes INTEGER NOT NULL,
  reserve_minutes INTEGER NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE burn_samples (
  sample_id TEXT PRIMARY KEY,
  slo_id TEXT NOT NULL REFERENCES slos(slo_id),
  sampled_at TEXT NOT NULL,
  burn_rate_1h REAL NOT NULL,
  burn_rate_6h REAL NOT NULL,
  raw_consumed_minutes REAL NOT NULL
);

CREATE TABLE problems (
  problem_id TEXT PRIMARY KEY,
  service_id TEXT NOT NULL REFERENCES services(service_id),
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  review_note TEXT NOT NULL
);

CREATE TABLE incidents (
  incident_id TEXT PRIMARY KEY,
  service_id TEXT NOT NULL REFERENCES services(service_id),
  opened_at TEXT NOT NULL,
  resolved_at TEXT NOT NULL,
  severity TEXT NOT NULL,
  impact_minutes INTEGER NOT NULL,
  slo_charged INTEGER NOT NULL,
  problem_id TEXT REFERENCES problems(problem_id),
  summary TEXT NOT NULL
);

CREATE TABLE alerts (
  alert_id TEXT PRIMARY KEY,
  service_id TEXT NOT NULL REFERENCES services(service_id),
  rule TEXT NOT NULL,
  severity TEXT NOT NULL,
  fired_at TEXT NOT NULL,
  resolved_at TEXT NOT NULL,
  incident_id TEXT
);

CREATE TABLE vendor_advisories (
  advisory_id TEXT PRIMARY KEY,
  vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
  reference TEXT NOT NULL,
  product TEXT NOT NULL,
  severity TEXT NOT NULL,
  published_on TEXT NOT NULL,
  remediation_sla_days INTEGER NOT NULL,
  affected_versions TEXT NOT NULL,
  fixed_version TEXT NOT NULL,
  restarts_required INTEGER NOT NULL,
  vendor_estimate_minutes INTEGER NOT NULL,
  standard_release_date TEXT NOT NULL,
  expedited_release_date TEXT NOT NULL,
  expedite_fee_usd REAL NOT NULL,
  valid_until TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE freeze_windows (
  freeze_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  lanes TEXT NOT NULL,
  authority TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE maintenance_windows (
  window_id TEXT PRIMARY KEY,
  lane_id TEXT NOT NULL REFERENCES change_lanes(lane_id),
  service_date TEXT NOT NULL,
  session TEXT NOT NULL,
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL,
  status TEXT NOT NULL,
  hold_reason TEXT,
  change_id TEXT
);

CREATE TABLE change_requests (
  change_id TEXT PRIMARY KEY,
  service_id TEXT NOT NULL REFERENCES services(service_id),
  advisory_id TEXT REFERENCES vendor_advisories(advisory_id),
  change_type TEXT NOT NULL,
  state TEXT NOT NULL,
  lane_id TEXT REFERENCES change_lanes(lane_id),
  window_id TEXT,
  planned_start TEXT,
  planned_end TEXT,
  downtime_minutes INTEGER NOT NULL,
  restarts INTEGER NOT NULL,
  risk TEXT NOT NULL,
  requested_by TEXT NOT NULL REFERENCES engineers(engineer_id),
  summary TEXT NOT NULL,
  opened_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  last_updated TEXT NOT NULL
);

CREATE TABLE change_tasks (
  task_id TEXT PRIMARY KEY,
  change_id TEXT NOT NULL REFERENCES change_requests(change_id),
  kind TEXT NOT NULL,
  node_count INTEGER NOT NULL,
  window_id TEXT,
  planned_start TEXT NOT NULL,
  planned_end TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE planned_outages (
  outage_id TEXT PRIMARY KEY,
  service_id TEXT NOT NULL REFERENCES services(service_id),
  change_id TEXT NOT NULL REFERENCES change_requests(change_id),
  window_id TEXT,
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL,
  duration_minutes INTEGER NOT NULL,
  downtime_minutes INTEGER NOT NULL,
  status TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE oncall_schedules (
  schedule_id TEXT PRIMARY KEY,
  service_id TEXT NOT NULL REFERENCES services(service_id),
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  required_certification TEXT
);

CREATE TABLE oncall_shifts (
  shift_id TEXT PRIMARY KEY,
  schedule_id TEXT NOT NULL REFERENCES oncall_schedules(schedule_id),
  engineer_id TEXT NOT NULL REFERENCES engineers(engineer_id),
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL,
  source TEXT NOT NULL
);

CREATE TABLE escalation_policies (
  policy_id TEXT PRIMARY KEY,
  service_id TEXT NOT NULL REFERENCES services(service_id),
  name TEXT NOT NULL,
  levels_json TEXT NOT NULL
);

CREATE TABLE oncall_overrides (
  override_id TEXT PRIMARY KEY,
  schedule_id TEXT NOT NULL REFERENCES oncall_schedules(schedule_id),
  engineer_id TEXT NOT NULL REFERENCES engineers(engineer_id),
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL,
  hours INTEGER NOT NULL,
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
  related_change_id TEXT,
  related_service_id TEXT,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL
);
