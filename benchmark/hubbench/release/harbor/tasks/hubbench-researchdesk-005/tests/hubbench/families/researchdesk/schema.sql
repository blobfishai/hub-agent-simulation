-- ResearchDesk domain state. Every task gets a fresh copy plus HubBench core.sql.

CREATE TABLE knowledge_articles (
  article_id TEXT PRIMARY KEY,
  slug TEXT NOT NULL,
  title TEXT NOT NULL,
  owner TEXT NOT NULL,
  status TEXT NOT NULL,
  current_revision TEXT NOT NULL,
  summary TEXT NOT NULL
);

CREATE TABLE knowledge_revisions (
  revision_id TEXT PRIMARY KEY,
  article_id TEXT NOT NULL,
  revision TEXT NOT NULL,
  effective_from TEXT NOT NULL,
  status TEXT NOT NULL,
  definition_id TEXT NOT NULL,
  body TEXT NOT NULL,
  FOREIGN KEY (article_id) REFERENCES knowledge_articles(article_id)
);

CREATE TABLE metric_definitions (
  definition_id TEXT PRIMARY KEY,
  metric_key TEXT NOT NULL,
  name TEXT NOT NULL,
  unit TEXT NOT NULL,
  numerator TEXT NOT NULL,
  denominator TEXT NOT NULL,
  exclusions TEXT NOT NULL,
  effective_from TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE metric_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  metric_key TEXT NOT NULL,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  definition_id TEXT NOT NULL,
  gross_value INTEGER NOT NULL,
  excluded_value INTEGER NOT NULL,
  supported_value INTEGER NOT NULL,
  unit TEXT NOT NULL,
  source_set_id TEXT NOT NULL,
  status TEXT NOT NULL,
  published_at TEXT NOT NULL,
  FOREIGN KEY (definition_id) REFERENCES metric_definitions(definition_id)
);

CREATE TABLE source_sets (
  source_set_id TEXT PRIMARY KEY,
  description TEXT NOT NULL,
  required_sources INTEGER NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE source_records (
  source_id TEXT PRIMARY KEY,
  source_set_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_name TEXT NOT NULL,
  captured_at TEXT NOT NULL,
  value INTEGER NOT NULL,
  unit TEXT NOT NULL,
  status TEXT NOT NULL,
  reliability TEXT NOT NULL,
  note TEXT,
  FOREIGN KEY (source_set_id) REFERENCES source_sets(source_set_id)
);

CREATE TABLE search_indexes (
  index_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  revision TEXT NOT NULL,
  last_refreshed TEXT NOT NULL
);

CREATE TABLE search_hits (
  hit_id TEXT PRIMARY KEY,
  index_id TEXT NOT NULL,
  query_key TEXT NOT NULL,
  article_id TEXT,
  source_id TEXT,
  rank INTEGER NOT NULL,
  snippet TEXT NOT NULL,
  status TEXT NOT NULL,
  FOREIGN KEY (index_id) REFERENCES search_indexes(index_id)
);

CREATE TABLE review_slots (
  slot_id TEXT PRIMARY KEY,
  review_date TEXT NOT NULL,
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL,
  duration_minutes INTEGER NOT NULL,
  reviewer_id TEXT NOT NULL,
  expertise TEXT NOT NULL,
  status TEXT NOT NULL,
  hold_reason TEXT,
  reservation_id TEXT
);

CREATE TABLE approvals (
  approval_id TEXT PRIMARY KEY,
  subject TEXT NOT NULL,
  approver_id TEXT NOT NULL,
  approver_role TEXT NOT NULL,
  status TEXT NOT NULL,
  granted_on TEXT NOT NULL,
  valid_until TEXT NOT NULL,
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

CREATE TABLE research_claims (
  claim_id TEXT PRIMARY KEY,
  article_id TEXT NOT NULL,
  metric_key TEXT NOT NULL,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  value INTEGER NOT NULL,
  unit TEXT NOT NULL,
  definition_id TEXT NOT NULL,
  source_set_id TEXT NOT NULL,
  approval_id TEXT NOT NULL,
  note TEXT NOT NULL,
  status TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL,
  FOREIGN KEY (article_id) REFERENCES knowledge_articles(article_id),
  FOREIGN KEY (definition_id) REFERENCES metric_definitions(definition_id),
  FOREIGN KEY (source_set_id) REFERENCES source_sets(source_set_id),
  FOREIGN KEY (approval_id) REFERENCES approvals(approval_id)
);

CREATE TABLE evidence_packets (
  packet_id TEXT PRIMARY KEY,
  article_id TEXT NOT NULL,
  metric_key TEXT NOT NULL,
  source_set_id TEXT NOT NULL,
  included_sources_json TEXT NOT NULL,
  excluded_sources_json TEXT NOT NULL,
  approval_id TEXT NOT NULL,
  summary TEXT NOT NULL,
  status TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL,
  FOREIGN KEY (article_id) REFERENCES knowledge_articles(article_id),
  FOREIGN KEY (source_set_id) REFERENCES source_sets(source_set_id),
  FOREIGN KEY (approval_id) REFERENCES approvals(approval_id)
);

CREATE TABLE review_reservations (
  reservation_id TEXT PRIMARY KEY,
  article_id TEXT NOT NULL,
  metric_key TEXT NOT NULL,
  slot_id TEXT NOT NULL,
  reviewer_id TEXT NOT NULL,
  minutes INTEGER NOT NULL,
  approval_id TEXT NOT NULL,
  purpose TEXT NOT NULL,
  status TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revision INTEGER NOT NULL,
  FOREIGN KEY (article_id) REFERENCES knowledge_articles(article_id),
  FOREIGN KEY (slot_id) REFERENCES review_slots(slot_id),
  FOREIGN KEY (approval_id) REFERENCES approvals(approval_id)
);

CREATE TABLE note_drafts (
  draft_id TEXT PRIMARY KEY,
  recipient TEXT NOT NULL,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  related_article_id TEXT,
  related_case TEXT,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL
);
