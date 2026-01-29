-- ============================================================================
-- Migration: Fix Orphan Cases - READY FOR PGADMIN4
-- Database: PostgreSQL
-- Purpose: Allow documents without reference numbers
-- ============================================================================
-- PASTE THIS ENTIRE FILE INTO PGADMIN4 QUERY TOOL AND PRESS F5
-- ============================================================================

BEGIN;

-- Drop dependent views first
DROP VIEW IF EXISTS v_reference_stats CASCADE;
DROP VIEW IF EXISTS v_incomplete_cases CASCADE;
DROP VIEW IF EXISTS v_case_overview CASCADE;
DROP VIEW IF EXISTS v_orphan_cases CASCADE;
DROP VIEW IF EXISTS v_orphan_case_details CASCADE;

-- Remove the strict constraint
ALTER TABLE cases DROP CONSTRAINT IF EXISTS chk_at_least_one_reference;

-- Add is_orphan flag
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'cases' AND column_name = 'is_orphan') THEN
        ALTER TABLE cases ADD COLUMN is_orphan BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

-- Add synthetic reference
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'cases' AND column_name = 'synthetic_reference') THEN
        ALTER TABLE cases ADD COLUMN synthetic_reference VARCHAR(100);
    END IF;
END $$;

-- Add unique constraint
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_synthetic_reference') THEN
        ALTER TABLE cases ADD CONSTRAINT uq_synthetic_reference UNIQUE (synthetic_reference);
    END IF;
END $$;

-- Add index
CREATE INDEX IF NOT EXISTS idx_cases_orphan ON cases(is_orphan) WHERE is_orphan = TRUE;

-- Create sequence
CREATE SEQUENCE IF NOT EXISTS seq_orphan_case_number START 1;

-- Drop and recreate reference_completeness
ALTER TABLE cases DROP COLUMN IF EXISTS reference_completeness;

ALTER TABLE cases 
ADD COLUMN reference_completeness INTEGER GENERATED ALWAYS AS (
    CASE 
        WHEN court_case_number IS NULL AND prosecution_case_number IS NULL AND police_report_number IS NULL AND internal_report_number IS NULL 
        THEN -1
        ELSE
            (CASE WHEN court_case_number IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN prosecution_case_number IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN police_report_number IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN internal_report_number IS NOT NULL THEN 1 ELSE 0 END)
    END
) STORED;

CREATE INDEX IF NOT EXISTS idx_case_reference_completeness ON cases(reference_completeness);

-- Create trigger function
CREATE OR REPLACE FUNCTION generate_synthetic_reference()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.court_case_number IS NULL AND NEW.prosecution_case_number IS NULL AND NEW.police_report_number IS NULL AND NEW.internal_report_number IS NULL THEN
        NEW.is_orphan := TRUE;
        IF NEW.synthetic_reference IS NULL THEN
            NEW.synthetic_reference := 'ORPHAN-' || TO_CHAR(CURRENT_DATE, 'YYYY') || '-' || LPAD(nextval('seq_orphan_case_number')::TEXT, 6, '0');
        END IF;
    ELSE
        NEW.is_orphan := FALSE;
        NEW.synthetic_reference := NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger
DROP TRIGGER IF EXISTS trg_generate_synthetic_reference ON cases;
CREATE TRIGGER trg_generate_synthetic_reference BEFORE INSERT OR UPDATE ON cases FOR EACH ROW EXECUTE FUNCTION generate_synthetic_reference();

-- Update existing orphan cases
-- Mark orphan cases
UPDATE cases 
SET is_orphan = TRUE 
WHERE court_case_number IS NULL 
  AND prosecution_case_number IS NULL 
  AND police_report_number IS NULL 
  AND internal_report_number IS NULL 
  AND (is_orphan IS NULL OR is_orphan = FALSE);

-- Generate synthetic references for orphan cases (using a subquery to avoid sequence issues)
DO $$
DECLARE
    v_case_record RECORD;
    v_counter INTEGER := 0;
BEGIN
    -- Reset sequence to max existing value + 1 if there are existing synthetic references
    SELECT COALESCE(MAX(CAST(SUBSTRING(synthetic_reference FROM '[0-9]+$') AS INTEGER)), 0) + 1
    INTO v_counter
    FROM cases
    WHERE synthetic_reference IS NOT NULL 
      AND synthetic_reference ~ '^ORPHAN-';
    
    -- Set sequence to the correct value
    IF v_counter > 1 THEN
        PERFORM setval('seq_orphan_case_number', v_counter);
    END IF;
    
    -- Generate synthetic references for orphan cases that don't have one
    FOR v_case_record IN 
        SELECT case_id 
        FROM cases 
        WHERE is_orphan = TRUE 
          AND synthetic_reference IS NULL
        ORDER BY case_id
    LOOP
        UPDATE cases 
        SET synthetic_reference = 'ORPHAN-' || TO_CHAR(CURRENT_DATE, 'YYYY') || '-' || LPAD(nextval('seq_orphan_case_number')::TEXT, 6, '0')
        WHERE case_id = v_case_record.case_id;
    END LOOP;
END $$;

-- Recreate views
CREATE VIEW v_incomplete_cases AS
SELECT c.case_id, c.court_case_number, c.prosecution_case_number, c.police_report_number, c.internal_report_number, c.synthetic_reference, c.is_orphan, c.reference_completeness, c.current_status, c.created_at,
CASE WHEN c.is_orphan THEN 'Orphan case' WHEN c.court_case_number IS NULL THEN 'Missing court' WHEN c.prosecution_case_number IS NULL THEN 'Missing prosecution' WHEN c.police_report_number IS NULL THEN 'Missing police' ELSE 'Complete' END as missing_reference,
COUNT(d.document_id) as document_count
FROM cases c LEFT JOIN documents d ON c.case_id = d.case_id
WHERE c.reference_completeness < 3 OR c.is_orphan = TRUE
GROUP BY c.case_id, c.court_case_number, c.prosecution_case_number, c.police_report_number, c.internal_report_number, c.synthetic_reference, c.is_orphan, c.reference_completeness, c.current_status, c.created_at
ORDER BY c.created_at DESC;

CREATE VIEW v_case_overview AS
SELECT c.case_id, c.court_case_number, c.prosecution_case_number, c.police_report_number, c.internal_report_number, c.synthetic_reference, c.is_orphan, c.reference_completeness, c.current_status, c.incident_date, c.case_opened_date, c.case_closed_date,
COUNT(DISTINCT d.document_id) as total_documents, COUNT(DISTINCT d.document_type) as document_types_count, MIN(d.document_date) as first_document_date, MAX(d.document_date) as latest_document_date,
STRING_AGG(DISTINCT d.document_type, ', ' ORDER BY d.document_type) as document_types
FROM cases c LEFT JOIN documents d ON c.case_id = d.case_id
GROUP BY c.case_id, c.court_case_number, c.prosecution_case_number, c.police_report_number, c.internal_report_number, c.synthetic_reference, c.is_orphan, c.reference_completeness, c.current_status, c.incident_date, c.case_opened_date, c.case_closed_date;

CREATE VIEW v_orphan_cases AS
SELECT c.case_id, c.synthetic_reference, c.current_status, c.case_opened_date, c.created_at, COUNT(d.document_id) as document_count,
STRING_AGG(DISTINCT d.document_type, ', ' ORDER BY d.document_type) as document_types, MIN(d.document_date) as first_document_date, MAX(d.document_date) as latest_document_date
FROM cases c LEFT JOIN documents d ON c.case_id = d.case_id WHERE c.is_orphan = TRUE
GROUP BY c.case_id, c.synthetic_reference, c.current_status, c.case_opened_date, c.created_at ORDER BY c.created_at DESC;

CREATE VIEW v_orphan_case_details AS
SELECT c.case_id, c.synthetic_reference, c.current_status, c.created_at, d.document_id, d.document_type, d.document_date, d.original_filename, d.document_category
FROM cases c JOIN documents d ON c.case_id = d.case_id WHERE c.is_orphan = TRUE ORDER BY c.case_id, d.document_date;

CREATE VIEW v_reference_stats AS
SELECT CASE WHEN reference_completeness = -1 THEN 'Orphan Cases' WHEN reference_completeness = 0 THEN 'No refs' WHEN reference_completeness = 1 THEN 'One ref' WHEN reference_completeness = 2 THEN 'Two refs' WHEN reference_completeness = 3 THEN 'Three refs' WHEN reference_completeness = 4 THEN 'All refs' ELSE 'Unknown' END as category,
reference_completeness, COUNT(*) as case_count, ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage
FROM cases GROUP BY reference_completeness ORDER BY reference_completeness;

-- Create helper functions
CREATE OR REPLACE FUNCTION find_case_by_reference(
    p_court_case VARCHAR DEFAULT NULL, 
    p_prosecution_case VARCHAR DEFAULT NULL, 
    p_police_report VARCHAR DEFAULT NULL, 
    p_internal_report VARCHAR DEFAULT NULL, 
    p_synthetic_ref VARCHAR DEFAULT NULL
)
RETURNS TABLE (case_id BIGINT, match_type VARCHAR, match_value VARCHAR) AS $$
BEGIN
    -- Try synthetic reference first (lowest priority)
    IF p_synthetic_ref IS NOT NULL THEN
        RETURN QUERY 
        SELECT c.case_id, 'synthetic_reference'::VARCHAR, p_synthetic_ref 
        FROM cases c 
        WHERE c.synthetic_reference = p_synthetic_ref 
        LIMIT 1;
        IF FOUND THEN RETURN; END IF;
    END IF;
    
    -- Try court case number (highest priority)
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
    
    RETURN;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION link_orphan_to_case(
    p_orphan_case_id BIGINT, 
    p_target_case_id BIGINT
)
RETURNS BOOLEAN AS $$
DECLARE 
    v_is_orphan BOOLEAN;
    v_orphan_exists BOOLEAN;
    v_target_exists BOOLEAN;
BEGIN
    -- Check if orphan case exists
    SELECT EXISTS(SELECT 1 FROM cases WHERE case_id = p_orphan_case_id) INTO v_orphan_exists;
    IF NOT v_orphan_exists THEN 
        RAISE EXCEPTION 'Orphan case % does not exist', p_orphan_case_id; 
    END IF;
    
    -- Check if target case exists
    SELECT EXISTS(SELECT 1 FROM cases WHERE case_id = p_target_case_id) INTO v_target_exists;
    IF NOT v_target_exists THEN 
        RAISE EXCEPTION 'Target case % does not exist', p_target_case_id; 
    END IF;
    
    -- Check if it's actually an orphan case
    SELECT is_orphan INTO v_is_orphan FROM cases WHERE case_id = p_orphan_case_id;
    IF v_is_orphan IS NULL OR v_is_orphan = FALSE THEN 
        RAISE EXCEPTION 'Case % is not an orphan case', p_orphan_case_id; 
    END IF;
    
    -- Prevent linking to itself
    IF p_orphan_case_id = p_target_case_id THEN
        RAISE EXCEPTION 'Cannot link case to itself';
    END IF;
    
    -- Move documents to target case
    UPDATE documents 
    SET case_id = p_target_case_id 
    WHERE case_id = p_orphan_case_id;
    
    -- Move parties to target case (avoid duplicates)
    UPDATE case_parties 
    SET case_id = p_target_case_id 
    WHERE case_id = p_orphan_case_id 
      AND NOT EXISTS (
          SELECT 1 
          FROM case_parties cp 
          WHERE cp.case_id = p_target_case_id 
            AND cp.party_id = case_parties.party_id 
            AND cp.role_type = case_parties.role_type
      );
    
    -- Delete orphan case
    DELETE FROM cases WHERE case_id = p_orphan_case_id;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

COMMIT;

-- ============================================================================
-- MIGRATION COMPLETE! Check for "COMMIT" in Messages tab = SUCCESS!
-- Verify with: SELECT * FROM v_orphan_cases;
-- ============================================================================