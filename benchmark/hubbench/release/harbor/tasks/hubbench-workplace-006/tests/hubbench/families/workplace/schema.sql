-- Workplace world: helpdesk (customers, tickets, escalations, SLA policies),
-- delivery tracker (issues, sprints, capacity reports), wiki pages, staff
-- calendar (blocks, leave, on-call, bookings), HRIS roster and skills,
-- contract register (agreements, commitments, credit ledger, billing runs),
-- counterparty confirmations, approvals, and the collaboration surfaces.

CREATE TABLE customers (
  customer_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  tier TEXT NOT NULL,
  region TEXT NOT NULL,
  industry TEXT NOT NULL,
  account_owner_user_id TEXT NOT NULL REFERENCES users(user_id)
);

CREATE TABLE sla_policies (
  sla_policy_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  version INTEGER NOT NULL,
  status TEXT NOT NULL,
  effective_from TEXT NOT NULL,
  note TEXT
);

CREATE TABLE sla_targets (
  target_id TEXT PRIMARY KEY,
  sla_policy_id TEXT NOT NULL REFERENCES sla_policies(sla_policy_id),
  priority TEXT NOT NULL,
  response_hours REAL NOT NULL,
  resolution_hours REAL NOT NULL,
  in_scope INTEGER NOT NULL
);

CREATE TABLE agreements (
  agreement_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(customer_id),
  plan TEXT NOT NULL,
  monthly_fee_usd INTEGER NOT NULL,
  sla_policy_id TEXT NOT NULL REFERENCES sla_policies(sla_policy_id),
  credit_pct_per_breach INTEGER NOT NULL,
  credit_cap_pct INTEGER NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE commitments (
  commitment_id TEXT PRIMARY KEY,
  agreement_id TEXT NOT NULL REFERENCES agreements(agreement_id),
  description TEXT NOT NULL,
  committed_date TEXT NOT NULL,
  penalty_usd_per_week INTEGER NOT NULL,
  status TEXT NOT NULL,
  accepted_on TEXT,
  guards_escalation_id TEXT,
  note TEXT
);

CREATE TABLE tickets (
  ticket_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(customer_id),
  subject TEXT NOT NULL,
  priority TEXT NOT NULL,
  status TEXT NOT NULL,
  opened_at TEXT NOT NULL,
  first_response_at TEXT,
  resolved_at TEXT,
  channel TEXT NOT NULL,
  requester TEXT NOT NULL,
  duplicate_of TEXT REFERENCES tickets(ticket_id),
  escalation_id TEXT,
  exempt_reason TEXT,
  note TEXT
);

CREATE TABLE escalations (
  escalation_id TEXT PRIMARY KEY,
  ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id),
  customer_id TEXT NOT NULL REFERENCES customers(customer_id),
  level INTEGER NOT NULL,
  status TEXT NOT NULL,
  opened_at TEXT NOT NULL,
  owner_user_id TEXT NOT NULL REFERENCES users(user_id),
  summary TEXT NOT NULL,
  required_skill TEXT NOT NULL,
  hands_on_minutes INTEGER NOT NULL,
  verification_minutes INTEGER NOT NULL,
  claim_ticket_ids_json TEXT NOT NULL,
  claim_basis TEXT,
  target_date TEXT,
  sprint_id TEXT,
  resolution_plan TEXT,
  note TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  last_updated TEXT NOT NULL
);

CREATE TABLE sprints (
  sprint_id TEXT PRIMARY KEY,
  board TEXT NOT NULL,
  name TEXT NOT NULL,
  state TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  goal TEXT NOT NULL
);

CREATE TABLE employees (
  employee_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  title TEXT NOT NULL,
  team TEXT NOT NULL,
  timezone TEXT NOT NULL,
  email TEXT NOT NULL,
  status TEXT NOT NULL,
  engagement_from TEXT,
  note TEXT
);

CREATE TABLE skills (
  skill_id TEXT PRIMARY KEY,
  employee_id TEXT NOT NULL REFERENCES employees(employee_id),
  skill_code TEXT NOT NULL,
  level INTEGER NOT NULL,
  certified_on TEXT NOT NULL
);

CREATE TABLE issues (
  issue_key TEXT PRIMARY KEY,
  project TEXT NOT NULL,
  summary TEXT NOT NULL,
  type TEXT NOT NULL,
  status TEXT NOT NULL,
  story_points INTEGER NOT NULL,
  priority TEXT NOT NULL,
  required_skill TEXT NOT NULL,
  escalation_id TEXT REFERENCES escalations(escalation_id),
  sprint_id TEXT REFERENCES sprints(sprint_id),
  assignee_id TEXT REFERENCES employees(employee_id),
  note TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL
);

CREATE TABLE sprint_capacity (
  capacity_id TEXT PRIMARY KEY,
  sprint_id TEXT NOT NULL REFERENCES sprints(sprint_id),
  employee_id TEXT NOT NULL REFERENCES employees(employee_id),
  capacity_points INTEGER NOT NULL,
  committed_points INTEGER NOT NULL,
  report_date TEXT NOT NULL
);

CREATE TABLE timeoff (
  timeoff_id TEXT PRIMARY KEY,
  employee_id TEXT NOT NULL REFERENCES employees(employee_id),
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  approved_on TEXT NOT NULL
);

CREATE TABLE oncall_shifts (
  shift_id TEXT PRIMARY KEY,
  employee_id TEXT NOT NULL REFERENCES employees(employee_id),
  rota TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL
);

CREATE TABLE calendar_blocks (
  block_id TEXT PRIMARY KEY,
  employee_id TEXT NOT NULL REFERENCES employees(employee_id),
  service_date TEXT NOT NULL,
  session TEXT NOT NULL,
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL,
  status TEXT NOT NULL,
  hold_reason TEXT,
  booking_id TEXT
);

CREATE TABLE bookings (
  booking_id TEXT PRIMARY KEY,
  employee_id TEXT REFERENCES employees(employee_id),
  escalation_id TEXT REFERENCES escalations(escalation_id),
  issue_key TEXT,
  start_time TEXT,
  end_time TEXT,
  status TEXT NOT NULL,
  description TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  last_updated TEXT NOT NULL
);

CREATE TABLE credits (
  credit_id TEXT PRIMARY KEY,
  agreement_id TEXT NOT NULL REFERENCES agreements(agreement_id),
  customer_id TEXT NOT NULL REFERENCES customers(customer_id),
  escalation_id TEXT REFERENCES escalations(escalation_id),
  amount_usd INTEGER NOT NULL,
  basis TEXT NOT NULL,
  status TEXT NOT NULL,
  issued_on TEXT NOT NULL,
  billing_option TEXT,
  confirmation_id TEXT,
  expected_application_date TEXT,
  note TEXT,
  requested_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE billing_runs (
  run_id TEXT PRIMARY KEY,
  run_date TEXT NOT NULL,
  cutoff_date TEXT NOT NULL,
  kind TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE confirmations (
  confirmation_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(customer_id),
  kind TEXT NOT NULL,
  counterparty TEXT NOT NULL,
  reference TEXT NOT NULL,
  standard_date TEXT NOT NULL,
  expedited_date TEXT NOT NULL,
  expedite_fee_usd INTEGER NOT NULL,
  valid_until TEXT NOT NULL,
  status TEXT NOT NULL,
  capacity_points INTEGER,
  skill_code TEXT,
  note TEXT
);

CREATE TABLE wiki_pages (
  page_id TEXT PRIMARY KEY,
  root_page_id TEXT NOT NULL,
  space TEXT NOT NULL,
  title TEXT NOT NULL,
  version INTEGER NOT NULL,
  status TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  body TEXT NOT NULL
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
  related_escalation_id TEXT,
  related_customer_id TEXT,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL
);
