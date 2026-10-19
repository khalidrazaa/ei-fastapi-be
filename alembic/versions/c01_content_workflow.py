"""Add inventory workspace and durable research jobs (additive)."""
from alembic import op
revision = "c01_content_workflow"
down_revision = 'b6f3e94d2a10'
branch_labels = None
depends_on = None

STATEMENTS = ['CREATE TABLE content_audit (\n\tid SERIAL NOT NULL, \n\ttopic_id VARCHAR(40) NOT NULL, \n\tactor VARCHAR(100) NOT NULL, \n\taction VARCHAR(60) NOT NULL, \n\tdetails JSON NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id)\n)', 'CREATE INDEX ix_content_audit_topic_id ON content_audit (topic_id)', 'CREATE TABLE content_topic_identifiers (\n\tid SERIAL NOT NULL, \n\tPRIMARY KEY (id)\n)', 'CREATE TABLE content_topics (\n\ttopic_id VARCHAR(40) NOT NULL, \n\ttitle VARCHAR(300) NOT NULL, \n\treader_question TEXT NOT NULL, \n\ttrack VARCHAR(120) NOT NULL, \n\tpriority INTEGER NOT NULL, \n\tnotes TEXT NOT NULL, \n\tstatus VARCHAR(40) NOT NULL, \n\tarchived BOOLEAN NOT NULL, \n\tversion INTEGER NOT NULL, \n\tbrief JSON NOT NULL, \n\tbrief_version INTEGER NOT NULL, \n\tarticle_id INTEGER, \n\tsaved_version_id INTEGER, \n\treview_date VARCHAR(10), \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (topic_id), \n\tUNIQUE (article_id), \n\tFOREIGN KEY(article_id) REFERENCES articles (id) ON DELETE SET NULL\n)', 'CREATE TABLE content_runs (\n\tid VARCHAR(36) NOT NULL, \n\ttopic_id VARCHAR(40) NOT NULL, \n\tstage VARCHAR(20) NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\trequest_key VARCHAR(100) NOT NULL, \n\tinputs JSON NOT NULL, \n\tresult JSON, \n\terror TEXT, \n\tattempts INTEGER NOT NULL, \n\tlease_token VARCHAR(36), \n\tlease_until TIMESTAMP WITH TIME ZONE, \n\tcancel_requested BOOLEAN NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tfinished_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(topic_id) REFERENCES content_topics (topic_id), \n\tUNIQUE (request_key)\n)', "CREATE UNIQUE INDEX uq_content_active_topic ON content_runs (topic_id) WHERE status IN ('queued', 'running')", 'CREATE INDEX ix_content_runs_topic_id ON content_runs (topic_id)', 'CREATE TABLE content_versions (\n\tid SERIAL NOT NULL, \n\ttopic_id VARCHAR(40) NOT NULL, \n\trun_id VARCHAR(36), \n\tresearch_id VARCHAR(36), \n\tbrief_version INTEGER NOT NULL, \n\tpayload JSON NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(topic_id) REFERENCES content_topics (topic_id), \n\tUNIQUE (run_id), \n\tFOREIGN KEY(run_id) REFERENCES content_runs (id), \n\tFOREIGN KEY(research_id) REFERENCES content_runs (id)\n)', 'CREATE INDEX ix_content_versions_topic_id ON content_versions (topic_id)', 'CREATE TABLE content_qa_reports (\n\tid SERIAL NOT NULL, \n\tversion_id INTEGER NOT NULL, \n\treport JSON NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(version_id) REFERENCES content_versions (id)\n)', 'CREATE INDEX ix_content_qa_reports_version_id ON content_qa_reports (version_id)']

def upgrade():
    for statement in STATEMENTS:
        op.execute(statement)

def downgrade():
    op.drop_table('content_qa_reports')
    op.drop_table('content_versions')
    op.drop_table('content_runs')
    op.drop_table('content_topics')
    op.drop_table('content_topic_identifiers')
    op.drop_table('content_audit')
