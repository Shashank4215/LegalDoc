-- Migration: Make Reference Numbers Nullable
-- Reason: Documents arrive in different order; police reports don't have court case numbers yet
-- PostgreSQL compatible - can be run multiple times safely

-- Step 1: Make court_case_number nullable (it's created later in the process)
DO $$
BEGIN
    -- Drop NOT NULL constraint if it exists
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'cases' 
        AND column_name = 'court_case_number' 
        AND is_nullable = 'NO'
    ) THEN
        ALTER TABLE cases ALTER COLUMN court_case_number DROP NOT NULL;
    END IF;
END $$;

-- Step 2: Add unique constraint that only applies when value is not null
-- This ensures no duplicate court case numbers when they DO exist
DROP INDEX IF EXISTS idx_unique_court_case_number;
CREATE UNIQUE INDEX idx_unique_court_case_number 
    ON cases(court_case_number) 
    WHERE court_case_number IS NOT NULL;

-- Step 3: Add similar constraints for other reference numbers
DROP INDEX IF EXISTS idx_unique_prosecution_case_number;
CREATE UNIQUE INDEX idx_unique_prosecution_case_number 
    ON cases(prosecution_case_number) 
    WHERE prosecution_case_number IS NOT NULL;

DROP INDEX IF EXISTS idx_unique_police_report_number;
CREATE UNIQUE INDEX idx_unique_police_report_number 
    ON cases(police_report_number) 
    WHERE police_report_number IS NOT NULL;

-- Step 4: Add composite index for efficient case matching by any reference
DROP INDEX IF EXISTS idx_case_references;
CREATE INDEX IF NOT EXISTS idx_case_references 
    ON cases(court_case_number, prosecution_case_number, police_report_number, internal_report_number);

-- Step 5: Add a check constraint to ensure at least ONE reference exists
-- This prevents completely orphaned cases
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'chk_at_least_one_reference'
    ) THEN
        ALTER TABLE cases 
        ADD CONSTRAINT chk_at_least_one_reference 
        CHECK (
            court_case_number IS NOT NULL OR 
            prosecution_case_number IS NOT NULL OR 
            police_report_number IS NOT NULL OR 
            internal_report_number IS NOT NULL
        );
    END IF;
END $$;

-- Step 6: Add case_reference_completeness computed column for easy querying
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'cases' 
        AND column_name = 'reference_completeness'
    ) THEN
        ALTER TABLE cases 
        ADD COLUMN reference_completeness INTEGER GENERATED ALWAYS AS (
            (CASE WHEN court_case_number IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN prosecution_case_number IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN police_report_number IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN internal_report_number IS NOT NULL THEN 1 ELSE 0 END)
        ) STORED;
    END IF;
END $$;

-- Step 7: Add index on completeness for queries like "find incomplete cases"
DROP INDEX IF EXISTS idx_case_reference_completeness;
CREATE INDEX IF NOT EXISTS idx_case_reference_completeness ON cases(reference_completeness);

-- Step 8: Add case merge audit trail
CREATE TABLE IF NOT EXISTS case_merge_history (
    merge_id BIGSERIAL PRIMARY KEY,
    case_id BIGINT NOT NULL REFERENCES cases(case_id),
    reference_type VARCHAR(50) NOT NULL,  -- 'court_case_number', 'prosecution_case_number', etc.
    reference_value VARCHAR(200) NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    added_by_document_id BIGINT REFERENCES documents(document_id),
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_merge_history_case ON case_merge_history(case_id);

-- Step 9: Add document linking audit trail
CREATE TABLE IF NOT EXISTS document_case_links (
    link_id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(document_id),
    case_id BIGINT NOT NULL REFERENCES cases(case_id),
    linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    linked_by_reference VARCHAR(50),  -- Which reference was used to link
    confidence_score DECIMAL(5,2),    -- How confident we are about this link
    
    UNIQUE(document_id, case_id)
);

CREATE INDEX IF NOT EXISTS idx_doc_case_links_document ON document_case_links(document_id);
CREATE INDEX IF NOT EXISTS idx_doc_case_links_case ON document_case_links(case_id);

-- Step 10: Create view for easy case overview
CREATE OR REPLACE VIEW v_case_overview AS
SELECT 
    c.case_id,
    c.court_case_number,
    c.prosecution_case_number,
    c.police_report_number,
    c.internal_report_number,
    c.reference_completeness,
    c.current_status,
    c.incident_date,
    c.case_opened_date,
    c.case_closed_date,
    COUNT(DISTINCT d.document_id) as total_documents,
    COUNT(DISTINCT d.document_type) as document_types_count,
    MIN(d.document_date) as first_document_date,
    MAX(d.document_date) as latest_document_date,
    STRING_AGG(DISTINCT d.document_type, ', ') as document_types
FROM cases c
LEFT JOIN documents d ON c.case_id = d.case_id
GROUP BY 
    c.case_id,
    c.court_case_number,
    c.prosecution_case_number,
    c.police_report_number,
    c.internal_report_number,
    c.reference_completeness,
    c.current_status,
    c.incident_date,
    c.case_opened_date,
    c.case_closed_date;

-- Step 11: Create function to find case by any reference
CREATE OR REPLACE FUNCTION find_case_by_reference(
    p_court_case VARCHAR DEFAULT NULL,
    p_prosecution_case VARCHAR DEFAULT NULL,
    p_police_report VARCHAR DEFAULT NULL,
    p_internal_report VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    case_id BIGINT,
    match_type VARCHAR,
    match_value VARCHAR
) AS $$
BEGIN
    -- Try court case number first (highest priority)
    IF p_court_case IS NOT NULL THEN
        RETURN QUERY
        SELECT c.case_id, 'court_case_number'::VARCHAR, p_court_case
        FROM cases c
        WHERE c.court_case_number = p_court_case
        LIMIT 1;
        
        IF FOUND THEN RETURN; END IF;
    END IF;
    
    -- Try prosecution number
    IF p_prosecution_case IS NOT NULL THEN
        RETURN QUERY
        SELECT c.case_id, 'prosecution_case_number'::VARCHAR, p_prosecution_case
        FROM cases c
        WHERE c.prosecution_case_number = p_prosecution_case
        LIMIT 1;
        
        IF FOUND THEN RETURN; END IF;
    END IF;
    
    -- Try police report number
    IF p_police_report IS NOT NULL THEN
        RETURN QUERY
        SELECT c.case_id, 'police_report_number'::VARCHAR, p_police_report
        FROM cases c
        WHERE c.police_report_number = p_police_report
        LIMIT 1;
        
        IF FOUND THEN RETURN; END IF;
    END IF;
    
    -- Try internal report number
    IF p_internal_report IS NOT NULL THEN
        RETURN QUERY
        SELECT c.case_id, 'internal_report_number'::VARCHAR, p_internal_report
        FROM cases c
        WHERE c.internal_report_number = p_internal_report
        LIMIT 1;
        
        IF FOUND THEN RETURN; END IF;
    END IF;
    
    -- No match found
    RETURN;
END;
$$ LANGUAGE plpgsql;

-- Step 12: Create trigger to log reference additions
CREATE OR REPLACE FUNCTION log_reference_addition()
RETURNS TRIGGER AS $$
BEGIN
    -- Log court case number addition
    IF NEW.court_case_number IS NOT NULL AND 
       (OLD.court_case_number IS NULL OR OLD.court_case_number != NEW.court_case_number) THEN
        INSERT INTO case_merge_history (case_id, reference_type, reference_value, notes)
        VALUES (NEW.case_id, 'court_case_number', NEW.court_case_number, 'Reference added/updated');
    END IF;
    
    -- Log prosecution number addition
    IF NEW.prosecution_case_number IS NOT NULL AND 
       (OLD.prosecution_case_number IS NULL OR OLD.prosecution_case_number != NEW.prosecution_case_number) THEN
        INSERT INTO case_merge_history (case_id, reference_type, reference_value, notes)
        VALUES (NEW.case_id, 'prosecution_case_number', NEW.prosecution_case_number, 'Reference added/updated');
    END IF;
    
    -- Log police report number addition
    IF NEW.police_report_number IS NOT NULL AND 
       (OLD.police_report_number IS NULL OR OLD.police_report_number != NEW.police_report_number) THEN
        INSERT INTO case_merge_history (case_id, reference_type, reference_value, notes)
        VALUES (NEW.case_id, 'police_report_number', NEW.police_report_number, 'Reference added/updated');
    END IF;
    
    -- Log internal report number addition
    IF NEW.internal_report_number IS NOT NULL AND 
       (OLD.internal_report_number IS NULL OR OLD.internal_report_number != NEW.internal_report_number) THEN
        INSERT INTO case_merge_history (case_id, reference_type, reference_value, notes)
        VALUES (NEW.case_id, 'internal_report_number', NEW.internal_report_number, 'Reference added/updated');
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_log_reference_addition ON cases;
CREATE TRIGGER trg_log_reference_addition
    AFTER UPDATE ON cases
    FOR EACH ROW
    EXECUTE FUNCTION log_reference_addition();

-- Step 13: Create helpful queries for monitoring

-- Query 1: Find cases with incomplete references
CREATE OR REPLACE VIEW v_incomplete_cases AS
SELECT 
    case_id,
    court_case_number,
    prosecution_case_number,
    police_report_number,
    internal_report_number,
    reference_completeness,
    current_status,
    CASE 
        WHEN court_case_number IS NULL THEN 'Missing court case number'
        WHEN prosecution_case_number IS NULL THEN 'Missing prosecution number'
        WHEN police_report_number IS NULL THEN 'Missing police report number'
        ELSE 'Complete'
    END as missing_reference
FROM cases
WHERE reference_completeness < 3  -- Less than 3 references
ORDER BY case_opened_date DESC;

-- Query 2: Find potential duplicate cases (same reference values)
CREATE OR REPLACE VIEW v_potential_duplicates AS
SELECT 
    'court_case_number' as reference_type,
    court_case_number as reference_value,
    COUNT(*) as case_count,
    STRING_AGG(case_id::TEXT, ', ') as case_ids
FROM cases
WHERE court_case_number IS NOT NULL
GROUP BY court_case_number
HAVING COUNT(*) > 1

UNION ALL

SELECT 
    'prosecution_case_number' as reference_type,
    prosecution_case_number as reference_value,
    COUNT(*) as case_count,
    STRING_AGG(case_id::TEXT, ', ') as case_ids
FROM cases
WHERE prosecution_case_number IS NOT NULL
GROUP BY prosecution_case_number
HAVING COUNT(*) > 1

UNION ALL

SELECT 
    'police_report_number' as reference_type,
    police_report_number as reference_value,
    COUNT(*) as case_count,
    STRING_AGG(case_id::TEXT, ', ') as case_ids
FROM cases
WHERE police_report_number IS NOT NULL
GROUP BY police_report_number
HAVING COUNT(*) > 1;

-- Query 3: Case reference completeness statistics
CREATE OR REPLACE VIEW v_reference_stats AS
SELECT 
    reference_completeness,
    COUNT(*) as case_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage
FROM cases
GROUP BY reference_completeness
ORDER BY reference_completeness;

COMMENT ON VIEW v_case_overview IS 'Overview of all cases with document counts';
COMMENT ON VIEW v_incomplete_cases IS 'Cases missing one or more reference numbers';
COMMENT ON VIEW v_potential_duplicates IS 'Potential duplicate cases sharing reference numbers';
COMMENT ON VIEW v_reference_stats IS 'Statistics on reference completeness across all cases';

COMMENT ON FUNCTION find_case_by_reference IS 'Find case by any available reference number';
COMMENT ON TABLE case_merge_history IS 'Audit trail of reference number additions to cases';
COMMENT ON TABLE document_case_links IS 'Tracks which reference was used to link each document';
