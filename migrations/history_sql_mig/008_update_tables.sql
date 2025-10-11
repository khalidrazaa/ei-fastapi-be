


CREATE TABLE trend_items (
	id SERIAL NOT NULL, 
	trend VARCHAR(255) NOT NULL, 
	search_volume INTEGER, 
	started TIMESTAMP WITH TIME ZONE, 
	ended TIMESTAMP WITH TIME ZONE, 
	trend_breakdown TEXT, 
	explore_link TEXT, 
	is_growing BOOLEAN, 
	category VARCHAR(100), 
	subcategory VARCHAR(100), 
	status VARCHAR(100), 
	draft_id VARCHAR(255), 
	last_updated TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (trend)
)

;


CREATE TABLE volume_points (
	id SERIAL NOT NULL, 
	trend_id INTEGER NOT NULL, 
	ts TIMESTAMP WITH TIME ZONE, 
	value INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_trend_volume_ts UNIQUE (trend_id, ts), 
	FOREIGN KEY(trend_id) REFERENCES trend_items (id) ON DELETE CASCADE
)

;