-- RepoDesk world: repository + issue tracker + CI evidence register + deploy
-- pipeline (lanes, windows, change records, flags) + customer commitments +
-- certification partners + reviewer availability, approvals, and the
-- collaboration surfaces.

CREATE TABLE repositories (
  repo_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  default_branch TEXT NOT NULL,
  visibility TEXT NOT NULL
);

CREATE TABLE environments (
  environment_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  cluster TEXT NOT NULL
);

CREATE TABLE engineers (
  engineer_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  focus TEXT NOT NULL
);

CREATE TABLE components (
  component_id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  tier TEXT NOT NULL,
  owner_team TEXT NOT NULL,
  repo_id TEXT NOT NULL REFERENCES repositories(repo_id),
  primary_engineer_id TEXT REFERENCES engineers(engineer_id)
);

CREATE TABLE impact_reports (
  report_id TEXT PRIMARY KEY,
  component_id TEXT NOT NULL REFERENCES components(component_id),
  metric TEXT NOT NULL,
  value REAL NOT NULL,
  unit TEXT NOT NULL,
  generated_at TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE verification_classes (
  verification_class TEXT PRIMARY KEY,
  display TEXT NOT NULL,
  runs_per_module INTEGER NOT NULL,
  required_checks_json TEXT NOT NULL,
  evidence_tier TEXT NOT NULL,
  minimum_validity_days INTEGER NOT NULL,
  release_eligible INTEGER NOT NULL,
  interchangeable_with TEXT
);

CREATE TABLE modules (
  module_id TEXT PRIMARY KEY,
  repo_id TEXT NOT NULL REFERENCES repositories(repo_id),
  path TEXT NOT NULL,
  component_id TEXT NOT NULL REFERENCES components(component_id),
  owner_team TEXT NOT NULL,
  codeowner_id TEXT REFERENCES engineers(engineer_id),
  verification_class TEXT NOT NULL REFERENCES verification_classes(verification_class),
  gate TEXT,
  gate_note TEXT
);

CREATE TABLE commits (
  sha TEXT PRIMARY KEY,
  repo_id TEXT NOT NULL REFERENCES repositories(repo_id),
  branch TEXT NOT NULL,
  authored_at TEXT NOT NULL,
  author_id TEXT REFERENCES engineers(engineer_id),
  message TEXT NOT NULL,
  pr_number INTEGER,
  status TEXT NOT NULL,
  backported_to TEXT,
  fix_for TEXT
);

CREATE TABLE commit_modules (
  sha TEXT NOT NULL REFERENCES commits(sha),
  module_id TEXT NOT NULL REFERENCES modules(module_id),
  PRIMARY KEY (sha, module_id)
);

CREATE TABLE pull_requests (
  pr_id TEXT PRIMARY KEY,
  repo_id TEXT NOT NULL REFERENCES repositories(repo_id),
  number INTEGER NOT NULL,
  title TEXT NOT NULL,
  head_sha TEXT NOT NULL,
  base_branch TEXT NOT NULL,
  status TEXT NOT NULL,
  issue_key TEXT,
  author_id TEXT REFERENCES engineers(engineer_id),
  opened_at TEXT NOT NULL,
  superseded_by TEXT
);

CREATE TABLE reviews (
  review_id TEXT PRIMARY KEY,
  pr_id TEXT NOT NULL REFERENCES pull_requests(pr_id),
  reviewer_id TEXT NOT NULL REFERENCES engineers(engineer_id),
  state TEXT NOT NULL,
  submitted_at TEXT NOT NULL
);

CREATE TABLE branch_rules (
  rule_id TEXT PRIMARY KEY,
  repo_id TEXT NOT NULL REFERENCES repositories(repo_id),
  branch TEXT NOT NULL,
  required_checks_json TEXT NOT NULL,
  required_approvals INTEGER NOT NULL,
  codeowner_review_required INTEGER NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE customers (
  customer_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  tier TEXT NOT NULL,
  environment_id TEXT NOT NULL REFERENCES environments(environment_id),
  account_owner TEXT NOT NULL
);

CREATE TABLE issues (
  issue_key TEXT PRIMARY KEY,
  component_id TEXT NOT NULL REFERENCES components(component_id),
  title TEXT NOT NULL,
  verification_class TEXT NOT NULL REFERENCES verification_classes(verification_class),
  basis TEXT NOT NULL,
  fixed_modules INTEGER,
  gated_modules INTEGER NOT NULL,
  environments_in_scope INTEGER NOT NULL,
  scope_note TEXT NOT NULL,
  build_minutes INTEGER NOT NULL,
  bake_minutes INTEGER NOT NULL,
  status TEXT NOT NULL,
  severity TEXT NOT NULL,
  kind TEXT NOT NULL,
  customer_id TEXT REFERENCES customers(customer_id),
  commitment_id TEXT,
  regression_from TEXT,
  regression_to TEXT,
  opened_at TEXT NOT NULL,
  requested_by TEXT NOT NULL REFERENCES engineers(engineer_id),
  duplicate_of TEXT,
  fix_version TEXT,
  note TEXT
);

CREATE TABLE commitments (
  commitment_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(customer_id),
  issue_key TEXT NOT NULL,
  kind TEXT NOT NULL,
  cutover_date TEXT NOT NULL,
  penalty_usd REAL NOT NULL,
  contract_ref TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE result_sources (
  source_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL
);

CREATE TABLE verification_results (
  result_id TEXT PRIMARY KEY,
  verification_class TEXT NOT NULL REFERENCES verification_classes(verification_class),
  result_label TEXT NOT NULL,
  source_id TEXT NOT NULL REFERENCES result_sources(source_id),
  run_count INTEGER NOT NULL,
  valid_until TEXT NOT NULL,
  status TEXT NOT NULL,
  status_reason TEXT,
  held_for_issue TEXT
);

CREATE TABLE flaky_tests (
  flaky_id TEXT PRIMARY KEY,
  check_name TEXT NOT NULL,
  module_id TEXT NOT NULL REFERENCES modules(module_id),
  quarantined_since TEXT NOT NULL,
  retry_minutes INTEGER NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE coverage_reports (
  report_id TEXT PRIMARY KEY,
  module_id TEXT NOT NULL REFERENCES modules(module_id),
  build_sha TEXT NOT NULL,
  line_coverage REAL NOT NULL,
  threshold REAL NOT NULL,
  generated_at TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE runner_pools (
  pool_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  capacity INTEGER NOT NULL,
  queue_minutes INTEGER NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE pipelines (
  pipeline_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  repo_id TEXT NOT NULL REFERENCES repositories(repo_id),
  component_id TEXT REFERENCES components(component_id),
  kind TEXT NOT NULL,
  trigger TEXT NOT NULL,
  base_minutes INTEGER NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE pipeline_runs (
  run_id TEXT PRIMARY KEY,
  pipeline_id TEXT NOT NULL REFERENCES pipelines(pipeline_id),
  head_sha TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL,
  status TEXT NOT NULL,
  exit_code INTEGER NOT NULL,
  summary TEXT NOT NULL
);

CREATE TABLE lanes (
  lane_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  cluster TEXT NOT NULL,
  status TEXT NOT NULL,
  isolation_capable INTEGER NOT NULL,
  status_note TEXT
);

CREATE TABLE release_windows (
  window_id TEXT PRIMARY KEY,
  lane_id TEXT NOT NULL REFERENCES lanes(lane_id),
  service_date TEXT NOT NULL,
  session TEXT NOT NULL,
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL,
  status TEXT NOT NULL,
  hold_reason TEXT,
  change_id TEXT
);

CREATE TABLE change_records (
  change_id TEXT PRIMARY KEY,
  component_id TEXT NOT NULL REFERENCES components(component_id),
  issue_key TEXT REFERENCES issues(issue_key),
  lane_id TEXT REFERENCES lanes(lane_id),
  start_time TEXT,
  end_time TEXT,
  status TEXT NOT NULL,
  description TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  last_updated TEXT NOT NULL
);

CREATE TABLE feature_flags (
  flag_key TEXT NOT NULL,
  environment_id TEXT NOT NULL REFERENCES environments(environment_id),
  state TEXT NOT NULL,
  scope TEXT NOT NULL,
  note TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  last_updated TEXT NOT NULL,
  PRIMARY KEY (flag_key, environment_id)
);

CREATE TABLE partners (
  partner_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  account_number TEXT NOT NULL
);

CREATE TABLE partner_confirmations (
  confirmation_id TEXT PRIMARY KEY,
  partner_id TEXT NOT NULL REFERENCES partners(partner_id),
  verification_class TEXT NOT NULL REFERENCES verification_classes(verification_class),
  reference TEXT NOT NULL,
  runs_available INTEGER NOT NULL,
  standard_ready_date TEXT NOT NULL,
  expedited_ready_date TEXT NOT NULL,
  expedite_fee_usd REAL NOT NULL,
  per_run_fee_usd REAL NOT NULL,
  valid_until TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE certification_orders (
  order_id TEXT PRIMARY KEY,
  partner_id TEXT NOT NULL REFERENCES partners(partner_id),
  confirmation_id TEXT REFERENCES partner_confirmations(confirmation_id),
  verification_class TEXT NOT NULL,
  run_count INTEGER NOT NULL,
  unit TEXT NOT NULL,
  service_option TEXT NOT NULL,
  expected_ready_date TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE backport_requests (
  backport_id TEXT PRIMARY KEY,
  repo_id TEXT NOT NULL REFERENCES repositories(repo_id),
  from_ref TEXT NOT NULL,
  to_ref TEXT NOT NULL,
  commit_count INTEGER NOT NULL,
  unit TEXT NOT NULL,
  scheduled_date TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE reviewer_availability (
  availability_id TEXT PRIMARY KEY,
  engineer_id TEXT NOT NULL REFERENCES engineers(engineer_id),
  service_date TEXT NOT NULL,
  session TEXT NOT NULL,
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
  related_issue_key TEXT,
  related_component_id TEXT,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL
);
