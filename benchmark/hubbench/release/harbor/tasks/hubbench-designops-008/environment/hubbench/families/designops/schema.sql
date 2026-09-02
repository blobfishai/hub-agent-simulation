-- DesignOps world: PLM parts / revisions / CAD documents with check-in history,
-- engineering change orders with affected items, multi-level BOM lines,
-- certification register, tooling (fixture) register with calibration state,
-- supplier portal quotes and orders, production release calendar, approvals,
-- and the collaboration surfaces.

CREATE TABLE plants (
  plant_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL
);

CREATE TABLE engineers (
  engineer_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  focus TEXT NOT NULL
);

CREATE TABLE parts (
  part_id TEXT PRIMARY KEY,
  number TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  part_type TEXT NOT NULL,
  owner_team TEXT NOT NULL,
  current_revision TEXT NOT NULL,
  primary_engineer_id TEXT REFERENCES engineers(engineer_id)
);

CREATE TABLE part_revisions (
  revision_id TEXT PRIMARY KEY,
  part_id TEXT NOT NULL REFERENCES parts(part_id),
  revision TEXT NOT NULL,
  status TEXT NOT NULL,
  released_on TEXT,
  superseded_on TEXT,
  note TEXT
);

CREATE TABLE cad_documents (
  document_id TEXT PRIMARY KEY,
  part_id TEXT NOT NULL REFERENCES parts(part_id),
  kind TEXT NOT NULL,
  number TEXT NOT NULL,
  version INTEGER NOT NULL,
  revision TEXT NOT NULL,
  status TEXT NOT NULL,
  checked_in_at TEXT NOT NULL,
  checked_in_by TEXT NOT NULL,
  note TEXT
);

CREATE TABLE checkins (
  checkin_id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES cad_documents(document_id),
  version INTEGER NOT NULL,
  checked_in_at TEXT NOT NULL,
  check_kind TEXT NOT NULL,
  status TEXT NOT NULL,
  summary TEXT NOT NULL
);

CREATE TABLE change_orders (
  change_id TEXT PRIMARY KEY,
  part_id TEXT NOT NULL REFERENCES parts(part_id),
  from_revision TEXT NOT NULL,
  to_revision TEXT NOT NULL,
  change_class TEXT NOT NULL,
  title TEXT NOT NULL,
  reason TEXT NOT NULL,
  state TEXT NOT NULL,
  effectivity_basis TEXT NOT NULL,
  effectivity_date TEXT,
  fixture_family TEXT,
  fai_minutes INTEGER NOT NULL,
  changeover_minutes INTEGER NOT NULL,
  required_by TEXT,
  requested_by TEXT NOT NULL REFERENCES engineers(engineer_id),
  opened_at TEXT NOT NULL,
  note TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  last_updated TEXT NOT NULL
);

CREATE TABLE affected_items (
  item_id TEXT PRIMARY KEY,
  change_id TEXT NOT NULL REFERENCES change_orders(change_id),
  assembly_part_id TEXT NOT NULL REFERENCES parts(part_id),
  assembly_revision TEXT NOT NULL,
  disposition TEXT NOT NULL,
  in_scope INTEGER NOT NULL,
  note TEXT
);

CREATE TABLE bom_lines (
  line_id TEXT PRIMARY KEY,
  parent_part_id TEXT NOT NULL REFERENCES parts(part_id),
  parent_revision TEXT NOT NULL,
  component_part_id TEXT NOT NULL REFERENCES parts(part_id),
  find_number INTEGER NOT NULL,
  qty_per INTEGER NOT NULL,
  line_kind TEXT NOT NULL,
  effectivity_end TEXT,
  note TEXT
);

CREATE TABLE certifications (
  cert_id TEXT PRIMARY KEY,
  assembly_part_id TEXT NOT NULL REFERENCES parts(part_id),
  assembly_revision TEXT NOT NULL,
  program TEXT NOT NULL,
  status TEXT NOT NULL,
  issued_on TEXT NOT NULL,
  expires_on TEXT NOT NULL,
  covered_components_json TEXT NOT NULL,
  recert_lead_days INTEGER NOT NULL,
  recert_test_fee_usd REAL NOT NULL,
  note TEXT
);

CREATE TABLE fixture_families (
  family_code TEXT PRIMARY KEY,
  display TEXT NOT NULL,
  sets_per_station INTEGER NOT NULL,
  calibration_interval_days INTEGER NOT NULL,
  minimum_remaining_calibration_days INTEGER NOT NULL,
  revision_specific INTEGER NOT NULL,
  interchangeable_with TEXT
);

CREATE TABLE fixture_sets (
  set_id TEXT PRIMARY KEY,
  family_code TEXT NOT NULL REFERENCES fixture_families(family_code),
  set_label TEXT NOT NULL,
  plant_id TEXT NOT NULL REFERENCES plants(plant_id),
  set_count INTEGER NOT NULL,
  calibration_due TEXT NOT NULL,
  status TEXT NOT NULL,
  status_reason TEXT,
  reserved_for_change TEXT
);

CREATE TABLE lines (
  line_id TEXT PRIMARY KEY,
  plant_id TEXT NOT NULL REFERENCES plants(plant_id),
  name TEXT NOT NULL,
  stations INTEGER NOT NULL,
  status TEXT NOT NULL,
  fai_capable INTEGER NOT NULL,
  status_note TEXT
);

CREATE TABLE release_windows (
  window_id TEXT PRIMARY KEY,
  line_id TEXT NOT NULL REFERENCES lines(line_id),
  service_date TEXT NOT NULL,
  session TEXT NOT NULL,
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL,
  status TEXT NOT NULL,
  hold_reason TEXT,
  reservation_id TEXT
);

CREATE TABLE cutin_reservations (
  reservation_id TEXT PRIMARY KEY,
  assembly_part_id TEXT NOT NULL REFERENCES parts(part_id),
  change_id TEXT REFERENCES change_orders(change_id),
  line_id TEXT REFERENCES lines(line_id),
  start_time TEXT,
  end_time TEXT,
  status TEXT NOT NULL,
  description TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  last_updated TEXT NOT NULL
);

CREATE TABLE suppliers (
  supplier_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  account_number TEXT NOT NULL
);

CREATE TABLE supplier_quotes (
  quote_id TEXT PRIMARY KEY,
  supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
  item_code TEXT NOT NULL,
  reference TEXT NOT NULL,
  quantity_available INTEGER NOT NULL,
  standard_ready_date TEXT NOT NULL,
  expedited_ready_date TEXT NOT NULL,
  expedite_fee_usd REAL NOT NULL,
  unit_price_usd REAL NOT NULL,
  valid_until TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE supplier_orders (
  order_id TEXT PRIMARY KEY,
  supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
  quote_id TEXT REFERENCES supplier_quotes(quote_id),
  item_code TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  unit TEXT NOT NULL,
  service_option TEXT NOT NULL,
  expected_ready_date TEXT NOT NULL,
  total_cost_usd REAL NOT NULL,
  status TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE fixture_transfers (
  transfer_id TEXT PRIMARY KEY,
  family_code TEXT NOT NULL,
  set_count INTEGER NOT NULL,
  from_plant_id TEXT NOT NULL REFERENCES plants(plant_id),
  to_plant_id TEXT NOT NULL REFERENCES plants(plant_id),
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
  related_change_id TEXT,
  related_part_id TEXT,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL
);
