-- Create scheduled_jobs table
CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    user_id INTEGER NOT NULL,
    url VARCHAR(500) NOT NULL,
    frequency VARCHAR(20) NOT NULL, -- hourly, daily, weekly, monthly
    time VARCHAR(10) NOT NULL, -- HH:MM format
    day_of_week TINYINT, -- 0-6 (Sunday-Saturday)
    day_of_month TINYINT, -- 1-31
    scrape_type VARCHAR(20) NOT NULL, -- auto, static, dynamic
    export_format VARCHAR(10) NOT NULL, -- json, csv, xlsx
    status VARCHAR(20) NOT NULL, -- active, paused, completed, failed
    email_notification BOOLEAN DEFAULT 0,
    last_run DATETIME,
    next_run DATETIME,
    created_at DATETIME NOT NULL,
    modified_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Create a table for job execution history
CREATE TABLE IF NOT EXISTS job_executions (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    job_id INTEGER NOT NULL,
    execution_time DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL, -- success, failed
    result_id INTEGER, -- Link to the scrape_results table
    error_message TEXT,
    FOREIGN KEY (job_id) REFERENCES scheduled_jobs(id) ON DELETE CASCADE,
    FOREIGN KEY (result_id) REFERENCES scrape_results(id) ON DELETE SET NULL
);

-- Add index for faster job lookups
CREATE INDEX idx_jobs_user_id ON scheduled_jobs(user_id);
CREATE INDEX idx_jobs_status ON scheduled_jobs(status);
CREATE INDEX idx_job_executions_job_id ON job_executions(job_id); 