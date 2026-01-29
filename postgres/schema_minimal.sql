-- ============================================================================
-- Minimal Legal Case Management Schema (Vector-Based Architecture)
-- PostgreSQL with FAISS for vector similarity (embeddings stored as JSONB)
-- ============================================================================

-- ============================================================================
-- 1. CASES Table - JSONB-based flexible case storage
-- ============================================================================
CREATE TABLE IF NOT EXISTS cases (
    case_id SERIAL PRIMARY KEY,
    
    -- Comprehensive JSONB columns for all case data
    case_numbers JSONB,              -- All case reference numbers and variations
    parties JSONB,                   -- All parties with full details (names, IDs, roles, demographics)
    key_dates JSONB,                 -- All important dates (incident, hearings, judgment, etc.)
    locations JSONB,                 -- Courts, police stations, prosecution offices, incident locations
    charges JSONB,                   -- All legal charges with articles and status
    judgments JSONB,                 -- Court decisions, verdicts, sentences
    financial JSONB,                 -- Fines, damages, bail amounts
    evidence JSONB,                  -- Evidence items and lab results
    case_status JSONB,               -- Current status, type, category, summary
    legal_references JSONB,          -- Laws and articles cited
    timeline JSONB,                  -- Chronological events and sessions
    
    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for JSONB queries
CREATE INDEX IF NOT EXISTS idx_cases_case_numbers ON cases USING gin (case_numbers);
CREATE INDEX IF NOT EXISTS idx_cases_parties ON cases USING gin (parties);
CREATE INDEX IF NOT EXISTS idx_cases_key_dates ON cases USING gin (key_dates);
CREATE INDEX IF NOT EXISTS idx_cases_case_status ON cases USING gin (case_status);

-- Index for case number lookups (common queries)
CREATE INDEX IF NOT EXISTS idx_cases_case_numbers_gin ON cases USING gin (case_numbers jsonb_path_ops);

-- ============================================================================
-- 2. DOCUMENTS Table - Document metadata with vector embeddings
-- ============================================================================
CREATE TABLE IF NOT EXISTS documents (
    document_id SERIAL PRIMARY KEY,
    case_id INTEGER REFERENCES cases(case_id) ON DELETE CASCADE,
    
    -- File Information
    file_path TEXT NOT NULL,
    file_hash TEXT,                  -- SHA-256 hash for deduplication
    original_filename TEXT,
    file_size_bytes BIGINT,
    mime_type TEXT,
    
    -- Document Metadata (JSONB)
    document_metadata JSONB,         -- Type, number, date, author, language
    
    -- Extracted Entities (JSONB)
    extracted_entities JSONB,        -- All entities extracted from document
    
    -- Vector Embedding for Similarity Search (stored as JSONB array)
    document_embedding JSONB,        -- 384-dimensional embedding array (paraphrase-multilingual-MiniLM-L12-v2)
    
    -- Processing Info
    confidence_score FLOAT,          -- How confident we are in case linking
    processing_status TEXT,          -- 'pending', 'processed', 'error'
    error_message TEXT,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP
);

-- Index for embedding JSONB (for FAISS-based similarity search)
CREATE INDEX IF NOT EXISTS idx_documents_embedding ON documents USING gin (document_embedding);

-- Indexes for JSONB queries
CREATE INDEX IF NOT EXISTS idx_documents_metadata ON documents USING gin (document_metadata);
CREATE INDEX IF NOT EXISTS idx_documents_entities ON documents USING gin (extracted_entities);
CREATE INDEX IF NOT EXISTS idx_documents_case_id ON documents (case_id);
CREATE INDEX IF NOT EXISTS idx_documents_file_hash ON documents (file_hash);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents (processing_status);

-- ============================================================================
-- 3. PROCESSING_LOG Table - Track processing history
-- ============================================================================
CREATE TABLE IF NOT EXISTS processing_log (
    log_id SERIAL PRIMARY KEY,
    file_path TEXT NOT NULL,
    case_id INTEGER REFERENCES cases(case_id) ON DELETE SET NULL,
    document_id INTEGER REFERENCES documents(document_id) ON DELETE SET NULL,
    
    -- Processing Status
    processing_status TEXT NOT NULL,  -- 'success', 'failed', 'duplicate', 'skipped'
    error_message TEXT,
    
    -- Processing Metrics
    processing_time_ms INTEGER,      -- Processing time in milliseconds
    entities_extracted INTEGER,      -- Number of entities extracted
    confidence_score FLOAT,
    
    -- Timestamps
    processing_time TIMESTAMP DEFAULT NOW()
);

-- Indexes for processing log
CREATE INDEX IF NOT EXISTS idx_processing_log_file_path ON processing_log (file_path);
CREATE INDEX IF NOT EXISTS idx_processing_log_case_id ON processing_log (case_id);
CREATE INDEX IF NOT EXISTS idx_processing_log_status ON processing_log (processing_status);
CREATE INDEX IF NOT EXISTS idx_processing_log_time ON processing_log (processing_time);

-- ============================================================================
-- Helper Functions for JSONB Operations
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update updated_at on cases
DROP TRIGGER IF EXISTS trigger_update_cases_updated_at ON cases;
CREATE TRIGGER trigger_update_cases_updated_at
    BEFORE UPDATE ON cases
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Comments
-- ============================================================================
COMMENT ON TABLE cases IS 'Main case records with comprehensive JSONB data storage';
COMMENT ON TABLE documents IS 'Document metadata with vector embeddings for similarity search';
COMMENT ON TABLE processing_log IS 'Processing history and audit trail';

COMMENT ON COLUMN cases.case_numbers IS 'JSONB: All case reference numbers (court, prosecution, police, internal) and variations';
COMMENT ON COLUMN cases.parties IS 'JSONB: All parties with entity IDs, relationships, and full details';
COMMENT ON COLUMN cases.charges IS 'JSONB: All charges with entity IDs, relationships, and status evolution';
COMMENT ON COLUMN cases.timeline IS 'JSONB: Chronological events with entity relationships';

COMMENT ON COLUMN documents.document_embedding IS 'Vector embedding stored as JSONB array (384 dimensions) - similarity search handled by FAISS';
COMMENT ON COLUMN documents.extracted_entities IS 'JSONB: All entities extracted from this document';
COMMENT ON COLUMN documents.confidence_score IS 'Confidence score (0-1) for case linking accuracy';

-- ============================================================================
-- 4. NORMALIZED ENTITY TABLES (Medium-term scaling)
--    Goal: avoid unbounded JSONB arrays in cases.parties/cases.charges/cases.evidence
-- ============================================================================

-- -------------------------
-- PARTIES (unique entity)
-- -------------------------
CREATE TABLE IF NOT EXISTS parties (
    party_id SERIAL PRIMARY KEY,
    signature TEXT UNIQUE NOT NULL,          -- stable key: id:<personal_id> OR ar:<normalized_name> OR en:<normalized_name>
    personal_id TEXT,
    name_ar TEXT,
    name_en TEXT,
    nationality TEXT,
    age INTEGER,
    gender TEXT,
    occupation TEXT,
    phone TEXT,
    address TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_parties_personal_id ON parties (personal_id);
CREATE INDEX IF NOT EXISTS idx_parties_name_ar ON parties (name_ar);
CREATE INDEX IF NOT EXISTS idx_parties_signature ON parties (signature);

-- Link parties to cases (many-to-many with roles)
CREATE TABLE IF NOT EXISTS case_parties (
    case_id INTEGER NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    party_id INTEGER NOT NULL REFERENCES parties(party_id) ON DELETE CASCADE,
    role_type TEXT,                          -- accused|victim|complainant|witness|...
    source_document_id INTEGER REFERENCES documents(document_id) ON DELETE SET NULL,
    confidence_score FLOAT,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (case_id, party_id, role_type)
);

CREATE INDEX IF NOT EXISTS idx_case_parties_case_id ON case_parties (case_id);
CREATE INDEX IF NOT EXISTS idx_case_parties_role_type ON case_parties (role_type);

-- -------------------------
-- CHARGES (unique entity)
-- -------------------------
CREATE TABLE IF NOT EXISTS charges (
    charge_id SERIAL PRIMARY KEY,
    signature TEXT UNIQUE NOT NULL,          -- stable key: art:<article> OR ar:<normalized_desc> OR en:<normalized_desc>
    charge_number TEXT,
    article_number TEXT,
    description_ar TEXT,
    description_en TEXT,
    law_name_ar TEXT,
    law_name_en TEXT,
    law_year TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_charges_article_number ON charges (article_number);
CREATE INDEX IF NOT EXISTS idx_charges_signature ON charges (signature);

CREATE TABLE IF NOT EXISTS case_charges (
    case_id INTEGER NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    charge_id INTEGER NOT NULL REFERENCES charges(charge_id) ON DELETE CASCADE,
    status TEXT,                              -- pending|dismissed|acquitted|convicted
    source_document_id INTEGER REFERENCES documents(document_id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (case_id, charge_id)
);

CREATE INDEX IF NOT EXISTS idx_case_charges_case_id ON case_charges (case_id);

-- -------------------------
-- EVIDENCE (unique entity)
-- -------------------------
CREATE TABLE IF NOT EXISTS evidence_items (
    evidence_id SERIAL PRIMARY KEY,
    signature TEXT UNIQUE NOT NULL,          -- stable key: <type>:<normalized_desc>
    evidence_type TEXT,
    description_ar TEXT,
    description_en TEXT,
    collected_date TEXT,
    location TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evidence_items_signature ON evidence_items (signature);
CREATE INDEX IF NOT EXISTS idx_evidence_items_type ON evidence_items (evidence_type);

CREATE TABLE IF NOT EXISTS case_evidence (
    case_id INTEGER NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    evidence_id INTEGER NOT NULL REFERENCES evidence_items(evidence_id) ON DELETE CASCADE,
    source_document_id INTEGER REFERENCES documents(document_id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (case_id, evidence_id)
);

CREATE INDEX IF NOT EXISTS idx_case_evidence_case_id ON case_evidence (case_id);

