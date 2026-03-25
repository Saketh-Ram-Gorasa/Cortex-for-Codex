-- Create tables
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    workspace_folder VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    deleted_at TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_user_projects ON projects(user_id, deleted_at);

CREATE TABLE IF NOT EXISTS snapshots (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    user_id UUID NOT NULL,
    
    active_file VARCHAR(255),
    language_id VARCHAR(50),
    git_branch VARCHAR(100),
    timestamp TIMESTAMPTZ NOT NULL,
    
    shadow_graph TEXT,
    summary VARCHAR(1000),
    entities JSONB,
    relations JSONB,
    
    embedding BYTEA,
    metadata_for_search JSONB,
    
    sync_status VARCHAR(20) DEFAULT 'PENDING' CHECK (sync_status IN ('PENDING', 'SYNCED', 'FAILED')),
    ingestion_error TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_project_snapshots ON snapshots(project_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_user_project_time ON snapshots(user_id, project_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_sync_status ON snapshots(project_id, sync_status);
CREATE INDEX IF NOT EXISTS idx_project_latest ON snapshots(project_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_user_all_snapshots ON snapshots(user_id, timestamp DESC);
