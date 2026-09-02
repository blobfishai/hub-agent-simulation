-- PolicyDesk world: an access-governance desk. Policy library with numbered
-- clauses and versions, an access-request queue, an entitlement/grant store
-- with segregation-of-duties rules, an exceptions register, an approver
-- directory with authority tiers and availability, training/attestation
-- records, an audit-finding tracker, an approver review-session calendar, an
-- external screening/certification vendor, approvals, and the collaboration
-- surfaces. Everything is clean-room synthetic.

CREATE TABLE departments (
  department_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  cost_centre TEXT NOT NULL
);

CREATE TABLE people (
  person_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  title TEXT NOT NULL,
  department_id TEXT REFERENCES departments(department_id),
  employment_type TEXT NOT NULL,
  manager_id TEXT
);

CREATE TABLE resources (
  resource_id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  system TEXT NOT NULL,
  sensitivity_tier TEXT NOT NULL,
  sod_domain TEXT NOT NULL,
  owner_id TEXT REFERENCES people(person_id)
);

CREATE TABLE policies (
  policy_id TEXT PRIMARY KEY,
  code TEXT NOT NULL,
  title TEXT NOT NULL,
  version TEXT NOT NULL,
  effective_date TEXT NOT NULL,
  status TEXT NOT NULL,
  supersedes TEXT
);

CREATE TABLE policy_clauses (
  clause_id TEXT PRIMARY KEY,
  policy_id TEXT NOT NULL REFERENCES policies(policy_id),
  number TEXT NOT NULL,
  topic TEXT NOT NULL,
  sensitivity_tier TEXT NOT NULL,
  max_grant_days INTEGER NOT NULL,
  requires_tier INTEGER NOT NULL,
  requires_training TEXT,
  allowed_control TEXT,
  text TEXT NOT NULL
);

CREATE TABLE access_requests (
  request_id TEXT PRIMARY KEY,
  requester_id TEXT NOT NULL REFERENCES people(person_id),
  resource_id TEXT NOT NULL REFERENCES resources(resource_id),
  requested_role TEXT NOT NULL,
  duration_days INTEGER NOT NULL,
  justification TEXT NOT NULL,
  manager_attested INTEGER NOT NULL,
  sensitivity_tier TEXT NOT NULL,
  disposition_basis TEXT NOT NULL,
  duplicate_of TEXT,
  submitted_at TEXT NOT NULL,
  status TEXT NOT NULL,
  decision TEXT,
  decided_days INTEGER,
  note TEXT
);

CREATE TABLE grants (
  grant_id TEXT PRIMARY KEY,
  resource_id TEXT NOT NULL REFERENCES resources(resource_id),
  request_id TEXT,
  role TEXT NOT NULL,
  sod_domain TEXT NOT NULL,
  covers_request_count INTEGER NOT NULL,
  granted_on TEXT NOT NULL,
  expires_on TEXT NOT NULL,
  status TEXT NOT NULL,
  status_reason TEXT,
  approval_id TEXT,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE sod_rules (
  rule_id TEXT PRIMARY KEY,
  domain_a TEXT NOT NULL,
  domain_b TEXT NOT NULL,
  severity TEXT NOT NULL,
  rule_text TEXT NOT NULL
);

CREATE TABLE exceptions_register (
  exception_id TEXT PRIMARY KEY,
  resource_id TEXT NOT NULL REFERENCES resources(resource_id),
  request_id TEXT,
  reason TEXT NOT NULL,
  compensating_control TEXT NOT NULL,
  approver_tier INTEGER NOT NULL,
  covers_request_count INTEGER NOT NULL,
  granted_on TEXT NOT NULL,
  expires_on TEXT NOT NULL,
  status TEXT NOT NULL,
  approval_id TEXT,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE approvers (
  approver_id TEXT PRIMARY KEY,
  person_id TEXT REFERENCES people(person_id),
  name TEXT NOT NULL,
  authority_tier INTEGER NOT NULL,
  max_sensitivity_tier TEXT NOT NULL,
  status TEXT NOT NULL,
  available_from TEXT,
  status_note TEXT
);

CREATE TABLE training_records (
  record_id TEXT PRIMARY KEY,
  person_id TEXT NOT NULL REFERENCES people(person_id),
  training_code TEXT NOT NULL,
  completed_on TEXT,
  expires_on TEXT,
  status TEXT NOT NULL
);

CREATE TABLE audit_findings (
  finding_id TEXT PRIMARY KEY,
  resource_id TEXT REFERENCES resources(resource_id),
  severity TEXT NOT NULL,
  title TEXT NOT NULL,
  blocks_grant INTEGER NOT NULL,
  status TEXT NOT NULL,
  opened_on TEXT NOT NULL,
  remediation_due TEXT
);

CREATE TABLE review_windows (
  window_id TEXT PRIMARY KEY,
  approver_id TEXT NOT NULL REFERENCES approvers(approver_id),
  service_date TEXT NOT NULL,
  session TEXT NOT NULL,
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL,
  status TEXT NOT NULL,
  hold_reason TEXT,
  session_id TEXT
);

CREATE TABLE review_sessions (
  session_id TEXT PRIMARY KEY,
  request_id TEXT,
  resource_id TEXT REFERENCES resources(resource_id),
  approver_id TEXT REFERENCES approvers(approver_id),
  start_time TEXT,
  end_time TEXT,
  status TEXT NOT NULL,
  description TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  last_updated TEXT NOT NULL
);

CREATE TABLE screening_vendors (
  vendor_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  account_number TEXT NOT NULL
);

CREATE TABLE screening_confirmations (
  confirmation_id TEXT PRIMARY KEY,
  vendor_id TEXT NOT NULL REFERENCES screening_vendors(vendor_id),
  credential TEXT NOT NULL,
  reference TEXT NOT NULL,
  slots_available INTEGER NOT NULL,
  standard_ready_date TEXT NOT NULL,
  expedited_ready_date TEXT NOT NULL,
  expedite_fee_usd REAL NOT NULL,
  per_slot_fee_usd REAL NOT NULL,
  valid_until TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT
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
  related_request_id TEXT,
  related_resource_id TEXT,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL
);
