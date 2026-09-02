-- ClinicOps world: FHIR-shaped EHR, infusion scheduling, pharmacy inventory,
-- supplier confirmations, approvals, and the collaboration surfaces.

CREATE TABLE locations (
  location_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL
);

CREATE TABLE practitioners (
  practitioner_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  specialty TEXT NOT NULL
);

CREATE TABLE patients (
  patient_id TEXT PRIMARY KEY,
  mrn TEXT NOT NULL UNIQUE,
  family_name TEXT NOT NULL,
  given_name TEXT NOT NULL,
  birth_date TEXT NOT NULL,
  sex TEXT NOT NULL,
  primary_practitioner_id TEXT REFERENCES practitioners(practitioner_id)
);

CREATE TABLE observations (
  observation_id TEXT PRIMARY KEY,
  patient_id TEXT NOT NULL REFERENCES patients(patient_id),
  code TEXT NOT NULL,
  display TEXT NOT NULL,
  value REAL NOT NULL,
  unit TEXT NOT NULL,
  effective_date TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE medications (
  medication_code TEXT PRIMARY KEY,
  display TEXT NOT NULL,
  vial_strength_value REAL NOT NULL,
  vial_strength_unit TEXT NOT NULL,
  route TEXT NOT NULL,
  storage TEXT NOT NULL,
  minimum_dating_days INTEGER NOT NULL,
  interchangeable_with TEXT
);

CREATE TABLE medication_requests (
  request_id TEXT PRIMARY KEY,
  patient_id TEXT NOT NULL REFERENCES patients(patient_id),
  medication_code TEXT NOT NULL REFERENCES medications(medication_code),
  dose_value REAL NOT NULL,
  dose_unit TEXT NOT NULL,
  regimen TEXT NOT NULL,
  doses_in_scope INTEGER NOT NULL,
  infusion_minutes INTEGER NOT NULL,
  observation_minutes INTEGER NOT NULL,
  status TEXT NOT NULL,
  intent TEXT NOT NULL,
  priority TEXT NOT NULL,
  authored_on TEXT NOT NULL,
  requester_id TEXT NOT NULL REFERENCES practitioners(practitioner_id),
  note TEXT
);

CREATE TABLE inventory_lots (
  lot_id TEXT PRIMARY KEY,
  medication_code TEXT NOT NULL REFERENCES medications(medication_code),
  lot_number TEXT NOT NULL,
  location_id TEXT NOT NULL REFERENCES locations(location_id),
  quantity_on_hand INTEGER NOT NULL,
  expiry_date TEXT NOT NULL,
  status TEXT NOT NULL,
  status_reason TEXT,
  reserved_for_patient_id TEXT
);

CREATE TABLE chairs (
  chair_id TEXT PRIMARY KEY,
  location_id TEXT NOT NULL REFERENCES locations(location_id),
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  first_dose_capable INTEGER NOT NULL,
  status_note TEXT
);

CREATE TABLE slots (
  slot_id TEXT PRIMARY KEY,
  chair_id TEXT NOT NULL REFERENCES chairs(chair_id),
  service_date TEXT NOT NULL,
  session TEXT NOT NULL,
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL,
  status TEXT NOT NULL,
  hold_reason TEXT,
  appointment_id TEXT
);

CREATE TABLE appointments (
  appointment_id TEXT PRIMARY KEY,
  patient_id TEXT NOT NULL REFERENCES patients(patient_id),
  request_id TEXT REFERENCES medication_requests(request_id),
  chair_id TEXT REFERENCES chairs(chair_id),
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

CREATE TABLE supplier_confirmations (
  confirmation_id TEXT PRIMARY KEY,
  supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
  medication_code TEXT NOT NULL REFERENCES medications(medication_code),
  reference TEXT NOT NULL,
  quantity_available INTEGER NOT NULL,
  standard_delivery_date TEXT NOT NULL,
  expedited_delivery_date TEXT NOT NULL,
  expedite_fee_usd REAL NOT NULL,
  unit_price_usd REAL NOT NULL,
  valid_until TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE purchase_orders (
  po_id TEXT PRIMARY KEY,
  supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
  confirmation_id TEXT REFERENCES supplier_confirmations(confirmation_id),
  medication_code TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  unit TEXT NOT NULL,
  delivery_option TEXT NOT NULL,
  expected_delivery_date TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE stock_transfers (
  transfer_id TEXT PRIMARY KEY,
  medication_code TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  from_location_id TEXT NOT NULL REFERENCES locations(location_id),
  to_location_id TEXT NOT NULL REFERENCES locations(location_id),
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
  related_request_id TEXT,
  related_patient_id TEXT,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL
);
