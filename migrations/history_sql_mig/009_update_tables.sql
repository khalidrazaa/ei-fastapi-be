
CREATE TABLE leads (
	id SERIAL NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	email VARCHAR(254) NOT NULL, 
	phone VARCHAR(16), 
	subject VARCHAR(200), 
	message TEXT NOT NULL, 
	host_site VARCHAR(120) NOT NULL, 
	landing_page VARCHAR(2048), 
	referrer VARCHAR(2048), 
	utm_source VARCHAR(200), 
	utm_medium VARCHAR(200), 
	utm_campaign VARCHAR(200), 
	utm_term VARCHAR(200), 
	utm_content VARCHAR(200), 
	status VARCHAR(20) DEFAULT 'new' NOT NULL, 
	internal_notes TEXT DEFAULT '' NOT NULL, 
	submitted_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_leads_status CHECK (status IN ('new','contacted','qualified','proposal','won','lost','spam'))
)

;


CREATE TABLE lead_notification_outbox (
	id SERIAL NOT NULL, 
	lead_id INTEGER NOT NULL, 
	state VARCHAR(20) DEFAULT 'pending' NOT NULL, 
	attempts INTEGER DEFAULT '0' NOT NULL, 
	available_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	lease_until TIMESTAMP WITH TIME ZONE, 
	lease_token VARCHAR(36), 
	last_error VARCHAR(80), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	sent_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_lead_notification_state CHECK (state IN ('pending','processing','sent','failed')), 
	CONSTRAINT ck_lead_notification_attempts CHECK (attempts >= 0), 
	UNIQUE (lead_id), 
	FOREIGN KEY(lead_id) REFERENCES leads (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_leads_submitted_at ON leads (submitted_at);
CREATE INDEX ix_leads_utm_source ON leads (utm_source);
CREATE INDEX ix_leads_status_submitted_at ON leads (status, submitted_at);
CREATE INDEX ix_leads_email_submitted_at ON leads (email, submitted_at);
CREATE INDEX ix_lead_notification_ready ON lead_notification_outbox (state, available_at);
CREATE INDEX ix_lead_notification_lease ON lead_notification_outbox (state, lease_until);
