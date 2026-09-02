-- DeskOps world: the office applications a GUI benchmark drives through
-- pixels, exposed as stateful tables — people directory and offices, calendar
-- events with attendees and free/busy blocks, in-house rooms, venue portal
-- (venues, weekly availability, quotes, holds), corporate travel desk
-- (policy versions, bookings, group-ticketing confirmations, booking
-- changes), budget system (lines, adjustments), spreadsheet workbooks with
-- versions, documents with revisions, approvals, and the collaboration
-- surfaces.

CREATE TABLE offices (
  office_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  city TEXT NOT NULL,
  country TEXT NOT NULL,
  timezone TEXT NOT NULL,
  region TEXT NOT NULL
);

CREATE TABLE people (
  person_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  title TEXT NOT NULL,
  team TEXT NOT NULL,
  office_id TEXT NOT NULL REFERENCES offices(office_id),
  employment TEXT NOT NULL
);

CREATE TABLE rooms (
  room_id TEXT PRIMARY KEY,
  office_id TEXT NOT NULL REFERENCES offices(office_id),
  name TEXT NOT NULL,
  capacity INTEGER NOT NULL,
  bookable INTEGER NOT NULL,
  note TEXT
);

CREATE TABLE venues (
  venue_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  city TEXT NOT NULL,
  country TEXT NOT NULL,
  local_office_id TEXT REFERENCES offices(office_id),
  capacity INTEGER NOT NULL,
  hold_business_days INTEGER NOT NULL,
  deposit_pct INTEGER NOT NULL,
  events_director TEXT NOT NULL,
  note TEXT
);

CREATE TABLE budget_lines (
  line_id TEXT PRIMARY KEY,
  cost_center TEXT NOT NULL,
  name TEXT NOT NULL,
  fiscal_period TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  approved_usd REAL NOT NULL,
  committed_usd REAL NOT NULL,
  reserved_usd REAL NOT NULL,
  adjustment_ceiling_usd REAL NOT NULL,
  status TEXT NOT NULL,
  note TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  last_updated TEXT NOT NULL
);

CREATE TABLE documents (
  doc_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  folder TEXT NOT NULL,
  current_revision INTEGER NOT NULL,
  modified_time TEXT NOT NULL
);

CREATE TABLE document_revisions (
  revision_id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL REFERENCES documents(doc_id),
  revision INTEGER NOT NULL,
  status TEXT NOT NULL,
  modified_time TEXT NOT NULL,
  modified_by TEXT NOT NULL,
  body TEXT NOT NULL,
  metadata_json TEXT NOT NULL
);

CREATE TABLE events (
  event_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  organizer_id TEXT NOT NULL REFERENCES people(person_id),
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  session_days INTEGER NOT NULL,
  venue_id TEXT REFERENCES venues(venue_id),
  location TEXT,
  status TEXT NOT NULL,
  agenda_doc_id TEXT REFERENCES documents(doc_id),
  budget_line_id TEXT REFERENCES budget_lines(line_id),
  cost_center TEXT,
  description TEXT,
  revision INTEGER NOT NULL DEFAULT 1,
  last_updated TEXT NOT NULL
);

CREATE TABLE event_attendees (
  attendee_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(event_id),
  person_id TEXT NOT NULL REFERENCES people(person_id),
  required INTEGER NOT NULL,
  response TEXT NOT NULL,
  note TEXT
);

CREATE TABLE busy_blocks (
  block_id TEXT PRIMARY KEY,
  person_id TEXT NOT NULL REFERENCES people(person_id),
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  transparency TEXT NOT NULL
);

CREATE TABLE venue_weeks (
  week_id TEXT PRIMARY KEY,
  venue_id TEXT NOT NULL REFERENCES venues(venue_id),
  week_start TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT,
  hold_id TEXT
);

CREATE TABLE venue_quotes (
  quote_id TEXT PRIMARY KEY,
  venue_id TEXT NOT NULL REFERENCES venues(venue_id),
  event_id TEXT REFERENCES events(event_id),
  reference TEXT NOT NULL,
  week_start TEXT NOT NULL,
  days INTEGER NOT NULL,
  total_usd REAL NOT NULL,
  deposit_usd REAL NOT NULL,
  issued_on TEXT NOT NULL,
  valid_until TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE venue_holds (
  hold_id TEXT PRIMARY KEY,
  venue_id TEXT NOT NULL REFERENCES venues(venue_id),
  event_id TEXT NOT NULL REFERENCES events(event_id),
  quote_id TEXT REFERENCES venue_quotes(quote_id),
  week_start TEXT NOT NULL,
  deposit_usd REAL NOT NULL,
  expires_on TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE travel_policies (
  policy_id TEXT PRIMARY KEY,
  code TEXT NOT NULL,
  version TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  effective_from TEXT NOT NULL,
  superseded_by TEXT,
  parameters_json TEXT NOT NULL
);

CREATE TABLE tmcs (
  tmc_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  account_number TEXT NOT NULL
);

CREATE TABLE bookings (
  booking_id TEXT PRIMARY KEY,
  person_id TEXT NOT NULL REFERENCES people(person_id),
  event_id TEXT NOT NULL REFERENCES events(event_id),
  kind TEXT NOT NULL,
  tmc_id TEXT NOT NULL REFERENCES tmcs(tmc_id),
  record_locator TEXT NOT NULL,
  origin_office_id TEXT REFERENCES offices(office_id),
  destination_city TEXT NOT NULL,
  travel_date TEXT NOT NULL,
  return_date TEXT NOT NULL,
  fare_class TEXT NOT NULL,
  fare_usd REAL NOT NULL,
  changeable INTEGER NOT NULL,
  change_fee_usd REAL NOT NULL,
  refundable INTEGER NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE ticketing_confirmations (
  confirmation_id TEXT PRIMARY KEY,
  tmc_id TEXT NOT NULL REFERENCES tmcs(tmc_id),
  event_id TEXT NOT NULL REFERENCES events(event_id),
  reference TEXT NOT NULL,
  seats_available INTEGER NOT NULL,
  group_fare_usd REAL NOT NULL,
  standard_ticketing_date TEXT NOT NULL,
  rush_ticketing_date TEXT NOT NULL,
  rush_fee_usd REAL NOT NULL,
  valid_until TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT
);

CREATE TABLE booking_changes (
  change_id TEXT PRIMARY KEY,
  confirmation_id TEXT REFERENCES ticketing_confirmations(confirmation_id),
  event_id TEXT NOT NULL REFERENCES events(event_id),
  booking_ids_json TEXT NOT NULL,
  booking_count INTEGER NOT NULL,
  new_travel_date TEXT NOT NULL,
  ticketing_option TEXT NOT NULL,
  change_fees_usd REAL NOT NULL,
  rush_fee_usd REAL NOT NULL,
  expected_ticketing_date TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE budget_adjustments (
  adjustment_id TEXT PRIMARY KEY,
  line_id TEXT NOT NULL REFERENCES budget_lines(line_id),
  amount_usd REAL NOT NULL,
  reason TEXT NOT NULL,
  related_event_id TEXT REFERENCES events(event_id),
  status TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE spreadsheets (
  spreadsheet_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  folder TEXT NOT NULL,
  current_version INTEGER NOT NULL,
  modified_time TEXT NOT NULL
);

CREATE TABLE spreadsheet_versions (
  version_id TEXT PRIMARY KEY,
  spreadsheet_id TEXT NOT NULL REFERENCES spreadsheets(spreadsheet_id),
  version INTEGER NOT NULL,
  status TEXT NOT NULL,
  modified_time TEXT NOT NULL,
  modified_by TEXT NOT NULL,
  rows_json TEXT NOT NULL
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
  related_event_id TEXT,
  related_line_id TEXT,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL
);
