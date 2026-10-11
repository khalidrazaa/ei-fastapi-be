-- Apply through the documented deployment migration process, not at application startup.
BEGIN;
CREATE TABLE content_audit (
	id SERIAL NOT NULL, 
	topic_id VARCHAR(40) NOT NULL, 
	actor VARCHAR(100) NOT NULL, 
	action VARCHAR(60) NOT NULL, 
	details JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_content_audit_topic_id ON content_audit (topic_id);

CREATE TABLE content_topic_identifiers (
	id SERIAL NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE content_topics (
	topic_id VARCHAR(40) NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	reader_question TEXT NOT NULL, 
	track VARCHAR(120) NOT NULL, 
	priority INTEGER NOT NULL, 
	notes TEXT NOT NULL, 
	status VARCHAR(40) NOT NULL, 
	archived BOOLEAN NOT NULL, 
	version INTEGER NOT NULL, 
	brief JSON NOT NULL, 
	brief_version INTEGER NOT NULL, 
	article_id INTEGER, 
	saved_version_id INTEGER, 
	review_date VARCHAR(10), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (topic_id), 
	UNIQUE (article_id), 
	FOREIGN KEY(article_id) REFERENCES articles (id) ON DELETE SET NULL
);

CREATE TABLE content_runs (
	id VARCHAR(36) NOT NULL, 
	topic_id VARCHAR(40) NOT NULL, 
	stage VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	request_key VARCHAR(100) NOT NULL, 
	inputs JSON NOT NULL, 
	result JSON, 
	error TEXT, 
	attempts INTEGER NOT NULL, 
	lease_token VARCHAR(36), 
	lease_until TIMESTAMP WITH TIME ZONE, 
	cancel_requested BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(topic_id) REFERENCES content_topics (topic_id), 
	UNIQUE (request_key)
);

CREATE UNIQUE INDEX uq_content_active_topic ON content_runs (topic_id) WHERE status IN ('queued', 'running');

CREATE INDEX ix_content_runs_topic_id ON content_runs (topic_id);

CREATE TABLE content_versions (
	id SERIAL NOT NULL, 
	topic_id VARCHAR(40) NOT NULL, 
	run_id VARCHAR(36), 
	research_id VARCHAR(36), 
	brief_version INTEGER NOT NULL, 
	payload JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(topic_id) REFERENCES content_topics (topic_id), 
	UNIQUE (run_id), 
	FOREIGN KEY(run_id) REFERENCES content_runs (id), 
	FOREIGN KEY(research_id) REFERENCES content_runs (id)
);

CREATE INDEX ix_content_versions_topic_id ON content_versions (topic_id);

CREATE TABLE content_qa_reports (
	id SERIAL NOT NULL, 
	version_id INTEGER NOT NULL, 
	report JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(version_id) REFERENCES content_versions (id)
);

CREATE INDEX ix_content_qa_reports_version_id ON content_qa_reports (version_id);
COMMIT;
