-- WebStudio world: CMS pages / entries / change requests / scheduled releases,
-- design-token and component registry with consumers and pins, design-file
-- index, digital asset library with licence grants and vendor licence
-- requests, release checklist gates and performance budgets, CDN deploy lanes
-- with the window calendar, vendor quotes, approvals, and the collaboration
-- surfaces.

CREATE TABLE people (
  person_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  focus TEXT NOT NULL
);

CREATE TABLE pages (
  page_id TEXT PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  owner_team TEXT NOT NULL,
  owner_person_id TEXT REFERENCES people(person_id),
  markets_json TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE change_requests (
  cr_id TEXT PRIMARY KEY,
  page_id TEXT NOT NULL REFERENCES pages(page_id),
  title TEXT NOT NULL,
  kind TEXT NOT NULL,
  territories_json TEXT NOT NULL,
  entries_in_scope INTEGER NOT NULL,
  scope_note TEXT NOT NULL,
  deploy_minutes INTEGER NOT NULL,
  verify_minutes INTEGER NOT NULL,
  status TEXT NOT NULL,
  priority TEXT NOT NULL,
  duplicate_of TEXT,
  impact_consumers INTEGER,
  opened_at TEXT NOT NULL,
  requested_by TEXT NOT NULL REFERENCES people(person_id),
  note TEXT
);

CREATE TABLE entries (
  entry_id TEXT PRIMARY KEY,
  page_id TEXT NOT NULL REFERENCES pages(page_id),
  cr_id TEXT REFERENCES change_requests(cr_id),
  content_type TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  revision INTEGER NOT NULL,
  bound_token_id TEXT,
  bound_component_id TEXT,
  bound_asset_id TEXT,
  blocked_reason TEXT
);

CREATE TABLE token_sets (
  set_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  current_version TEXT NOT NULL
);

CREATE TABLE tokens (
  token_id TEXT PRIMARY KEY,
  set_id TEXT NOT NULL REFERENCES token_sets(set_id),
  name TEXT NOT NULL,
  kind TEXT NOT NULL
);

CREATE TABLE token_versions (
  token_id TEXT NOT NULL REFERENCES tokens(token_id),
  version TEXT NOT NULL,
  value TEXT NOT NULL,
  status TEXT NOT NULL,
  breaking INTEGER NOT NULL,
  released_on TEXT NOT NULL,
  note TEXT,
  PRIMARY KEY (token_id, version)
);

CREATE TABLE components (
  component_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  library TEXT NOT NULL,
  version TEXT NOT NULL,
  allowed_variants_json TEXT NOT NULL,
  status TEXT NOT NULL,
  deprecated INTEGER NOT NULL,
  breaking_change_pending INTEGER NOT NULL,
  note TEXT
);

CREATE TABLE consumers (
  consumer_id TEXT PRIMARY KEY,
  token_id TEXT REFERENCES tokens(token_id),
  component_id TEXT REFERENCES components(component_id),
  page_id TEXT NOT NULL REFERENCES pages(page_id),
  surface TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE token_pins (
  pin_id TEXT PRIMARY KEY,
  token_id TEXT NOT NULL REFERENCES tokens(token_id),
  version TEXT NOT NULL,
  cr_id TEXT NOT NULL REFERENCES change_requests(cr_id),
  consumer_count INTEGER NOT NULL,
  unit TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE design_files (
  file_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  page_id TEXT NOT NULL REFERENCES pages(page_id),
  version TEXT NOT NULL,
  status TEXT NOT NULL,
  superseded_by TEXT,
  review_status TEXT NOT NULL
);

CREATE TABLE design_frames (
  frame_id TEXT PRIMARY KEY,
  file_id TEXT NOT NULL REFERENCES design_files(file_id),
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  components_json TEXT NOT NULL,
  note TEXT
);

CREATE TABLE vendors (
  vendor_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  account_number TEXT NOT NULL
);

CREATE TABLE assets (
  asset_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  name TEXT NOT NULL,
  vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
  page_id TEXT NOT NULL REFERENCES pages(page_id),
  usage_count INTEGER NOT NULL,
  licence_required INTEGER NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE licences (
  licence_id TEXT PRIMARY KEY,
  asset_id TEXT NOT NULL REFERENCES assets(asset_id),
  vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
  reference TEXT NOT NULL,
  territories_json TEXT NOT NULL,
  territory_count INTEGER NOT NULL,
  usage_scope TEXT NOT NULL,
  expires_on TEXT NOT NULL,
  status TEXT NOT NULL,
  status_reason TEXT,
  reserved_for_cr TEXT
);

CREATE TABLE licence_quotes (
  quote_id TEXT PRIMARY KEY,
  vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
  asset_id TEXT NOT NULL,
  reference TEXT NOT NULL,
  kind TEXT NOT NULL,
  units_available INTEGER NOT NULL,
  standard_issue_date TEXT NOT NULL,
  expedited_issue_date TEXT NOT NULL,
  rush_fee_usd REAL NOT NULL,
  per_unit_fee_usd REAL NOT NULL,
  valid_until TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE licence_requests (
  request_id TEXT PRIMARY KEY,
  vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
  quote_id TEXT REFERENCES licence_quotes(quote_id),
  asset_id TEXT NOT NULL,
  territory_count INTEGER NOT NULL,
  unit TEXT NOT NULL,
  issuance_option TEXT NOT NULL,
  expected_licence_date TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE checklist_gates (
  gate_id TEXT PRIMARY KEY,
  cr_id TEXT NOT NULL REFERENCES change_requests(cr_id),
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  status TEXT NOT NULL,
  authority_role TEXT NOT NULL,
  measured TEXT,
  budget TEXT,
  note TEXT
);

CREATE TABLE perf_budgets (
  budget_id TEXT PRIMARY KEY,
  page_id TEXT NOT NULL REFERENCES pages(page_id),
  metric TEXT NOT NULL,
  budget_value REAL NOT NULL,
  measured_value REAL NOT NULL,
  unit TEXT NOT NULL,
  measured_at TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE waivers (
  waiver_id TEXT PRIMARY KEY,
  gate_id TEXT NOT NULL REFERENCES checklist_gates(gate_id),
  cr_id TEXT NOT NULL REFERENCES change_requests(cr_id),
  reason TEXT NOT NULL,
  approval_id TEXT,
  status TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE lanes (
  lane_id TEXT PRIMARY KEY,
  pool TEXT NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  rollback_capable INTEGER NOT NULL,
  status_note TEXT
);

CREATE TABLE deploy_windows (
  window_id TEXT PRIMARY KEY,
  lane_id TEXT NOT NULL REFERENCES lanes(lane_id),
  service_date TEXT NOT NULL,
  session TEXT NOT NULL,
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL,
  status TEXT NOT NULL,
  hold_reason TEXT,
  release_id TEXT
);

CREATE TABLE releases (
  release_id TEXT PRIMARY KEY,
  page_id TEXT NOT NULL REFERENCES pages(page_id),
  cr_id TEXT REFERENCES change_requests(cr_id),
  lane_id TEXT REFERENCES lanes(lane_id),
  start_time TEXT,
  end_time TEXT,
  status TEXT NOT NULL,
  description TEXT,
  entry_count INTEGER,
  revision INTEGER NOT NULL DEFAULT 1,
  last_updated TEXT NOT NULL
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
  related_change_request_id TEXT,
  related_page_id TEXT,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL
);
