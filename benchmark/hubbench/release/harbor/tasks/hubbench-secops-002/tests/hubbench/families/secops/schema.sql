-- SecOps world: SIEM alerts and correlated events with versioned detection
-- rules, an EDR host and detection inventory, an IAM identity register with
-- sessions, MFA factors, credential-object grants and inventory snapshots, a
-- cloud IAM key register, a security ticket queue, containment-tier playbooks,
-- a responder on-call window calendar with incident bridges, identity-provider
-- vendor invalidation confirmations and orders, tenant revocation records,
-- approvals, and the collaboration surfaces.  Defensive operations only:
-- every record describes triage, containment, or revocation of a synthetic
-- organisation's own credentials.

CREATE TABLE analysts (
  analyst_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  focus TEXT NOT NULL
);

CREATE TABLE identities (
  identity_id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  kind TEXT NOT NULL,
  tier TEXT NOT NULL,
  owner_team TEXT NOT NULL,
  owner_analyst_id TEXT REFERENCES analysts(analyst_id)
);

CREATE TABLE grant_inventory (
  inventory_id TEXT PRIMARY KEY,
  identity_id TEXT NOT NULL REFERENCES identities(identity_id),
  metric TEXT NOT NULL,
  value INTEGER NOT NULL,
  unit TEXT NOT NULL,
  measured_at TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE credential_classes (
  credential_class TEXT PRIMARY KEY,
  display TEXT NOT NULL,
  object_kind TEXT NOT NULL,
  revocation_channel TEXT NOT NULL,
  privileged INTEGER NOT NULL,
  interchangeable_with TEXT
);

CREATE TABLE containment_tiers (
  tier_code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  immediate_revocation_allowed INTEGER NOT NULL,
  owner_confirmation_required INTEGER NOT NULL,
  authority_level TEXT NOT NULL,
  sla_hours INTEGER NOT NULL,
  note TEXT
);

CREATE TABLE tickets (
  ticket_id TEXT PRIMARY KEY,
  identity_id TEXT NOT NULL REFERENCES identities(identity_id),
  alert_id TEXT,
  tier_code TEXT NOT NULL REFERENCES containment_tiers(tier_code),
  credential_class TEXT NOT NULL REFERENCES credential_classes(credential_class),
  unit_kind TEXT NOT NULL,
  unit_basis TEXT NOT NULL,
  unit_objects INTEGER,
  units_in_scope INTEGER NOT NULL,
  scope_note TEXT NOT NULL,
  triage_minutes INTEGER NOT NULL,
  confirm_minutes INTEGER NOT NULL,
  status TEXT NOT NULL,
  kind TEXT NOT NULL,
  priority TEXT NOT NULL,
  opened_at TEXT NOT NULL,
  requested_by TEXT NOT NULL REFERENCES analysts(analyst_id),
  note TEXT
);

CREATE TABLE grant_sets (
  grant_id TEXT PRIMARY KEY,
  credential_class TEXT NOT NULL REFERENCES credential_classes(credential_class),
  grant_label TEXT NOT NULL,
  identity_id TEXT NOT NULL REFERENCES identities(identity_id),
  system TEXT NOT NULL,
  object_count INTEGER NOT NULL,
  expires_on TEXT NOT NULL,
  status TEXT NOT NULL,
  status_reason TEXT,
  deferred_for_ticket TEXT,
  register_flag TEXT
);

CREATE TABLE detection_rules (
  rule_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE alerts (
  alert_id TEXT PRIMARY KEY,
  rule_id TEXT NOT NULL REFERENCES detection_rules(rule_id),
  identity_id TEXT REFERENCES identities(identity_id),
  severity TEXT NOT NULL,
  status TEXT NOT NULL,
  kind TEXT NOT NULL,
  opened_at TEXT NOT NULL,
  summary TEXT NOT NULL
);

CREATE TABLE alert_events (
  event_id TEXT PRIMARY KEY,
  alert_id TEXT NOT NULL REFERENCES alerts(alert_id),
  ts TEXT NOT NULL,
  kind TEXT NOT NULL,
  source_ip TEXT NOT NULL,
  detail TEXT NOT NULL
);

CREATE TABLE hosts (
  host_id TEXT PRIMARY KEY,
  hostname TEXT NOT NULL,
  identity_id TEXT REFERENCES identities(identity_id),
  role TEXT NOT NULL,
  isolation_state TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE detections (
  detection_id TEXT PRIMARY KEY,
  host_id TEXT NOT NULL REFERENCES hosts(host_id),
  tactic TEXT NOT NULL,
  severity TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE sessions (
  session_id TEXT PRIMARY KEY,
  identity_id TEXT NOT NULL REFERENCES identities(identity_id),
  source_ip TEXT NOT NULL,
  geo TEXT NOT NULL,
  device TEXT NOT NULL,
  started_at TEXT NOT NULL,
  risk TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE mfa_factors (
  factor_id TEXT PRIMARY KEY,
  identity_id TEXT NOT NULL REFERENCES identities(identity_id),
  factor_type TEXT NOT NULL,
  status TEXT NOT NULL,
  enrolled_at TEXT NOT NULL,
  last_used TEXT NOT NULL
);

CREATE TABLE responders (
  responder_id TEXT PRIMARY KEY,
  pool TEXT NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  tier2_capable INTEGER NOT NULL,
  status_note TEXT
);

CREATE TABLE oncall_windows (
  window_id TEXT PRIMARY KEY,
  responder_id TEXT NOT NULL REFERENCES responders(responder_id),
  service_date TEXT NOT NULL,
  session TEXT NOT NULL,
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL,
  status TEXT NOT NULL,
  hold_reason TEXT,
  bridge_id TEXT
);

CREATE TABLE bridges (
  bridge_id TEXT PRIMARY KEY,
  identity_id TEXT NOT NULL REFERENCES identities(identity_id),
  ticket_id TEXT REFERENCES tickets(ticket_id),
  responder_id TEXT REFERENCES responders(responder_id),
  start_time TEXT,
  end_time TEXT,
  status TEXT NOT NULL,
  description TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  last_updated TEXT NOT NULL
);

CREATE TABLE idp_vendors (
  vendor_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  account_number TEXT NOT NULL
);

CREATE TABLE invalidation_confirmations (
  confirmation_id TEXT PRIMARY KEY,
  vendor_id TEXT NOT NULL REFERENCES idp_vendors(vendor_id),
  credential_class TEXT NOT NULL REFERENCES credential_classes(credential_class),
  reference TEXT NOT NULL,
  objects_available INTEGER NOT NULL,
  standard_ready_date TEXT NOT NULL,
  expedited_ready_date TEXT NOT NULL,
  expedite_fee_usd REAL NOT NULL,
  per_object_fee_usd REAL NOT NULL,
  valid_until TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE invalidation_orders (
  order_id TEXT PRIMARY KEY,
  vendor_id TEXT NOT NULL REFERENCES idp_vendors(vendor_id),
  confirmation_id TEXT REFERENCES invalidation_confirmations(confirmation_id),
  credential_class TEXT NOT NULL,
  object_count INTEGER NOT NULL,
  unit TEXT NOT NULL,
  service_option TEXT NOT NULL,
  expected_ready_date TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE revocations (
  revocation_id TEXT PRIMARY KEY,
  credential_class TEXT NOT NULL,
  object_count INTEGER NOT NULL,
  identity_id TEXT NOT NULL REFERENCES identities(identity_id),
  system TEXT NOT NULL,
  effective_date TEXT NOT NULL,
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
  related_identity_id TEXT,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL
);
