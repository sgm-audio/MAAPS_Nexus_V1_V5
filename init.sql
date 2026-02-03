-- MAAPS Nexus Database Schema

-- Leads table (V2: Ghost Outbound Engine)
CREATE TABLE IF NOT EXISTS leads (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(50),
    company VARCHAR(255),
    source VARCHAR(100),
    bio TEXT,
    status VARCHAR(50) DEFAULT 'new',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Audio jobs table (V3: Sub-Sonic Mastering)
CREATE TABLE IF NOT EXISTS audio_jobs (
    id SERIAL PRIMARY KEY,
    job_type VARCHAR(50) NOT NULL,  -- 'demucs_split', 'heartmula_generate', 'rvc_clone', 'lufs_normalize'
    input_path TEXT,
    output_path TEXT,
    status VARCHAR(50) DEFAULT 'pending',  -- pending, processing, complete, failed
    params JSONB,
    result JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Deployments table (V1: CI/CD Umbilical)
CREATE TABLE IF NOT EXISTS deployments (
    id SERIAL PRIMARY KEY,
    commit_sha VARCHAR(64),
    branch VARCHAR(100),
    status VARCHAR(50) DEFAULT 'pending',
    logs TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Outbound campaigns (V2: Ghost Engine)
CREATE TABLE IF NOT EXISTS campaigns (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    template TEXT,
    voice_model_id VARCHAR(100),
    status VARCHAR(50) DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sent messages (V2: Tracking)
CREATE TABLE IF NOT EXISTS outbound_messages (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER REFERENCES campaigns(id),
    lead_id INTEGER REFERENCES leads(id),
    audio_path TEXT,
    email_sent BOOLEAN DEFAULT FALSE,
    opened BOOLEAN DEFAULT FALSE,
    replied BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_audio_jobs_status ON audio_jobs(status);
CREATE INDEX IF NOT EXISTS idx_deployments_status ON deployments(status);
