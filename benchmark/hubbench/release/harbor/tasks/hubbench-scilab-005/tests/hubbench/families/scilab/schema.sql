-- SciLab world: LIMS (assays, protocols with versions, sample batches, run
-- requests, assay runs, QC results), instrument schedule (analysers,
-- calibration certificates, window calendar, bookings), reagent inventory
-- (reagents, lots, transfers), supplier portal (shipment confirmations,
-- orders), ELN method notes, approvals, and the collaboration surfaces.

CREATE TABLE sites (
  site_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL
);

CREATE TABLE scientists (
  scientist_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  focus TEXT NOT NULL
);

CREATE TABLE assays (
  assay_id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  owner_lab TEXT NOT NULL,
  principal_scientist_id TEXT REFERENCES scientists(scientist_id)
);

CREATE TABLE sample_batches (
  batch_id TEXT PRIMARY KEY,
  assay_id TEXT NOT NULL REFERENCES assays(assay_id),
  metric TEXT NOT NULL,
  value INTEGER NOT NULL,
  unit TEXT NOT NULL,
  counted_at TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE protocols (
  protocol_id TEXT PRIMARY KEY,
  code TEXT NOT NULL,
  version TEXT NOT NULL,
  status TEXT NOT NULL,
  samples_per_plate INTEGER NOT NULL,
  control_vials_per_plate INTEGER NOT NULL,
  control_rule TEXT NOT NULL,
  effective_from TEXT NOT NULL,
  superseded_by TEXT
);

CREATE TABLE reagents (
  reagent_code TEXT PRIMARY KEY,
  display TEXT NOT NULL,
  vial_format TEXT NOT NULL,
  storage TEXT NOT NULL,
  minimum_dating_days INTEGER NOT NULL,
  validated INTEGER NOT NULL,
  interchangeable_with TEXT
);

CREATE TABLE run_requests (
  request_id TEXT PRIMARY KEY,
  assay_id TEXT NOT NULL REFERENCES assays(assay_id),
  reagent_code TEXT NOT NULL REFERENCES reagents(reagent_code),
  protocol_id TEXT NOT NULL REFERENCES protocols(protocol_id),
  unit_kind TEXT NOT NULL,
  unit_basis TEXT NOT NULL,
  samples INTEGER,
  units_in_scope INTEGER NOT NULL,
  scope_note TEXT NOT NULL,
  run_minutes INTEGER NOT NULL,
  read_minutes INTEGER NOT NULL,
  status TEXT NOT NULL,
  kind TEXT NOT NULL,
  priority TEXT NOT NULL,
  opened_at TEXT NOT NULL,
  requested_by TEXT NOT NULL REFERENCES scientists(scientist_id),
  note TEXT
);

CREATE TABLE reagent_lots (
  lot_id TEXT PRIMARY KEY,
  reagent_code TEXT NOT NULL REFERENCES reagents(reagent_code),
  lot_number TEXT NOT NULL,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  vials_on_hand INTEGER NOT NULL,
  expiry_date TEXT NOT NULL,
  status TEXT NOT NULL,
  status_reason TEXT,
  reserved_for_request TEXT
);

CREATE TABLE instruments (
  instrument_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  name TEXT NOT NULL,
  model TEXT NOT NULL,
  status TEXT NOT NULL,
  validation_capable INTEGER NOT NULL,
  status_note TEXT
);

CREATE TABLE calibration_certificates (
  cert_id TEXT PRIMARY KEY,
  instrument_id TEXT NOT NULL REFERENCES instruments(instrument_id),
  issued_on TEXT NOT NULL,
  expires_on TEXT NOT NULL,
  status TEXT NOT NULL,
  issuer TEXT NOT NULL,
  note TEXT
);

CREATE TABLE assay_runs (
  run_id TEXT PRIMARY KEY,
  assay_id TEXT REFERENCES assays(assay_id),
  protocol_id TEXT REFERENCES protocols(protocol_id),
  instrument_id TEXT NOT NULL REFERENCES instruments(instrument_id),
  kind TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL,
  status TEXT NOT NULL,
  plates INTEGER NOT NULL,
  summary TEXT NOT NULL
);

CREATE TABLE qc_results (
  result_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES assay_runs(run_id),
  control_level TEXT NOT NULL,
  lot_id TEXT,
  value REAL NOT NULL,
  unit TEXT NOT NULL,
  low_limit REAL NOT NULL,
  high_limit REAL NOT NULL,
  valid INTEGER NOT NULL,
  note TEXT
);

CREATE TABLE instrument_windows (
  window_id TEXT PRIMARY KEY,
  instrument_id TEXT NOT NULL REFERENCES instruments(instrument_id),
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
  assay_id TEXT NOT NULL REFERENCES assays(assay_id),
  request_id TEXT REFERENCES run_requests(request_id),
  instrument_id TEXT REFERENCES instruments(instrument_id),
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
  account_number TEXT NOT NULL
);

CREATE TABLE shipment_confirmations (
  confirmation_id TEXT PRIMARY KEY,
  supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
  reagent_code TEXT NOT NULL REFERENCES reagents(reagent_code),
  reference TEXT NOT NULL,
  vials_available INTEGER NOT NULL,
  standard_delivery_date TEXT NOT NULL,
  expedited_delivery_date TEXT NOT NULL,
  expedite_fee_usd REAL NOT NULL,
  unit_price_usd REAL NOT NULL,
  valid_until TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE reagent_orders (
  order_id TEXT PRIMARY KEY,
  supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
  confirmation_id TEXT REFERENCES shipment_confirmations(confirmation_id),
  reagent_code TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  unit TEXT NOT NULL,
  delivery_option TEXT NOT NULL,
  expected_delivery_date TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE lot_transfers (
  transfer_id TEXT PRIMARY KEY,
  reagent_code TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  from_site_id TEXT NOT NULL REFERENCES sites(site_id),
  to_site_id TEXT NOT NULL REFERENCES sites(site_id),
  scheduled_date TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE method_notes (
  note_id TEXT PRIMARY KEY,
  protocol_code TEXT NOT NULL,
  version TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  content TEXT NOT NULL,
  updated_at TEXT NOT NULL
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
  related_assay_id TEXT,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL
);
