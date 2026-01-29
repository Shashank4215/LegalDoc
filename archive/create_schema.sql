-- Legal Case Management System - Database Schema
-- MySQL 8.0+ with InnoDB Engine
-- Character Set: utf8mb4 for Arabic support

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================================
-- 1. CASES Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS cases (
    case_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    
    -- Reference Numbers (all cases have multiple references)
    court_case_number VARCHAR(100) UNIQUE NOT NULL,
    prosecution_case_number VARCHAR(100),
    police_report_number VARCHAR(100),
    internal_report_number VARCHAR(100),
    
    -- Case Classification
    case_type VARCHAR(50) NOT NULL,
    case_category VARCHAR(100),
    case_subcategory VARCHAR(100),
    
    -- Court Information
    court_name VARCHAR(200),
    court_name_en VARCHAR(200),
    circuit_number VARCHAR(50),
    circuit_name VARCHAR(200),
    
    -- Location & Jurisdiction
    police_station VARCHAR(200),
    police_station_en VARCHAR(200),
    security_department VARCHAR(200),
    prosecution_office VARCHAR(200),
    
    -- Key Dates
    incident_date DATETIME,
    report_date DATETIME,
    case_opened_date DATETIME,
    case_closed_date DATETIME,
    final_judgment_date DATETIME,
    
    -- Status
    current_status VARCHAR(50) NOT NULL,
    status_date DATETIME NOT NULL,
    
    -- Summary
    case_summary_ar TEXT,
    case_summary_en TEXT,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    
    INDEX idx_court_case (court_case_number),
    INDEX idx_prosecution_case (prosecution_case_number),
    INDEX idx_police_report (police_report_number),
    INDEX idx_status (current_status),
    INDEX idx_incident_date (incident_date),
    INDEX idx_case_type (case_type, case_category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 2. PARTIES Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS parties (
    party_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    
    -- Personal Information
    personal_id VARCHAR(50),
    full_name_ar VARCHAR(200),
    full_name_en VARCHAR(200),
    latin_name VARCHAR(200),
    
    -- Demographics
    date_of_birth DATE,
    age INT,
    gender VARCHAR(20),
    nationality VARCHAR(100),
    religion VARCHAR(100),
    
    -- Contact Information
    phone_mobile VARCHAR(50),
    phone_landline VARCHAR(50),
    email VARCHAR(200),
    
    -- Address
    area VARCHAR(200),
    compound VARCHAR(200),
    building_number VARCHAR(100),
    apartment_number VARCHAR(100),
    street VARCHAR(200),
    po_box VARCHAR(50),
    electricity_number VARCHAR(100),
    unit_number VARCHAR(50),
    
    -- Employment/Sponsorship
    occupation VARCHAR(200),
    sponsor_type VARCHAR(50),
    sponsor_name VARCHAR(200),
    sponsor_id VARCHAR(100),
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_personal_id (personal_id),
    INDEX idx_full_name_ar (full_name_ar),
    INDEX idx_nationality (nationality),
    INDEX idx_sponsor (sponsor_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 3. CASE_PARTIES Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS case_parties (
    case_party_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    party_id BIGINT NOT NULL,
    
    -- Role Information
    role_type VARCHAR(50) NOT NULL,
    role_subtype VARCHAR(100),
    role_description_ar TEXT,
    role_description_en TEXT,
    
    -- Role-specific Details
    badge_number VARCHAR(50),
    license_number VARCHAR(50),
    rank VARCHAR(100),
    
    -- Status in this role
    status VARCHAR(50),
    assigned_date DATETIME,
    removed_date DATETIME,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY (party_id) REFERENCES parties(party_id) ON DELETE RESTRICT,
    
    INDEX idx_case_role (case_id, role_type),
    INDEX idx_party_role (party_id, role_type),
    
    UNIQUE KEY unique_case_party_role (case_id, party_id, role_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 4. DOCUMENTS Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS documents (
    document_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    
    -- Document Classification
    document_type VARCHAR(100) NOT NULL,
    document_subtype VARCHAR(100),
    document_category VARCHAR(100),
    
    -- Document Identifiers
    document_number VARCHAR(200),
    internal_reference VARCHAR(200),
    
    -- File Information
    original_filename VARCHAR(500),
    stored_filename VARCHAR(500) UNIQUE NOT NULL,
    file_path VARCHAR(1000),
    file_size_bytes BIGINT,
    file_hash VARCHAR(100),
    mime_type VARCHAR(100),
    
    -- Language & Content
    primary_language VARCHAR(20),
    extracted_text_ar TEXT,
    extracted_text_en TEXT,
    raw_text TEXT,
    
    -- Document Metadata
    document_date DATETIME,
    creation_date DATETIME,
    received_date DATETIME,
    
    -- Status
    processing_status VARCHAR(50),
    is_official BOOLEAN DEFAULT TRUE,
    is_confidential BOOLEAN DEFAULT FALSE,
    is_redacted BOOLEAN DEFAULT FALSE,
    
    -- Authoring Information
    author_party_id BIGINT,
    author_name VARCHAR(200),
    author_title VARCHAR(200),
    author_organization VARCHAR(200),
    
    -- Processing Info
    parser_version VARCHAR(50),
    parsed_at TIMESTAMP NULL,
    validation_status VARCHAR(50),
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY (author_party_id) REFERENCES parties(party_id) ON DELETE SET NULL,
    
    INDEX idx_case_docs (case_id, document_date),
    INDEX idx_doc_type (document_type, document_date),
    INDEX idx_processing (processing_status),
    INDEX idx_document_number (document_number),
    FULLTEXT INDEX ft_extracted_text_ar (extracted_text_ar),
    FULLTEXT INDEX ft_extracted_text_en (extracted_text_en)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 5. CHARGES Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS charges (
    charge_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    
    -- Charge Details
    charge_number INT,
    charge_description_ar TEXT NOT NULL,
    charge_description_en TEXT,
    
    -- Legal References
    law_name_ar VARCHAR(500),
    law_name_en VARCHAR(500),
    article_number VARCHAR(100),
    article_section VARCHAR(100),
    law_year VARCHAR(20),
    law_number VARCHAR(50),
    
    -- Classification
    charge_category VARCHAR(100),
    charge_severity VARCHAR(50),
    
    -- Status
    charge_status VARCHAR(50),
    status_date DATETIME,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
    
    INDEX idx_case_charges (case_id),
    INDEX idx_article (article_number),
    INDEX idx_charge_status (charge_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 6. COURT_SESSIONS Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS court_sessions (
    session_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    
    -- Session Details
    session_number INT,
    session_date DATETIME NOT NULL,
    session_time TIME,
    
    -- Location
    court_name VARCHAR(200),
    courtroom VARCHAR(100),
    circuit_name VARCHAR(200),
    
    -- Session Type
    session_type VARCHAR(100),
    session_purpose_ar TEXT,
    session_purpose_en TEXT,
    
    -- Attendance
    judge_present BOOLEAN,
    prosecutor_present BOOLEAN,
    accused_present BOOLEAN,
    lawyer_present BOOLEAN,
    
    -- Session Outcome
    session_status VARCHAR(50),
    next_session_date DATETIME,
    
    -- Decision
    decision_ar TEXT,
    decision_en TEXT,
    decision_type VARCHAR(100),
    
    -- Notes
    session_notes_ar TEXT,
    session_notes_en TEXT,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
    
    INDEX idx_case_sessions (case_id, session_date),
    INDEX idx_session_date (session_date),
    INDEX idx_next_session (next_session_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 7. SESSION_ATTENDEES Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS session_attendees (
    attendee_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    session_id BIGINT NOT NULL,
    party_id BIGINT NOT NULL,
    
    -- Attendance Details
    role_in_session VARCHAR(100),
    attendance_status VARCHAR(50),
    arrival_time TIME,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (session_id) REFERENCES court_sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (party_id) REFERENCES parties(party_id) ON DELETE CASCADE,
    
    INDEX idx_session_party (session_id, party_id),
    
    UNIQUE KEY unique_session_party (session_id, party_id, role_in_session)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 8. JUDGMENTS Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS judgments (
    judgment_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    session_id BIGINT,
    
    -- Judgment Details
    judgment_number VARCHAR(200),
    judgment_date DATETIME NOT NULL,
    judgment_type VARCHAR(100),
    
    -- Verdict
    verdict VARCHAR(50),
    verdict_description_ar TEXT,
    verdict_description_en TEXT,
    
    -- Presence Type
    presence_type VARCHAR(50),
    
    -- Reasoning
    judgment_reasoning_ar TEXT,
    judgment_reasoning_en TEXT,
    
    -- Status
    is_final BOOLEAN DEFAULT FALSE,
    appeal_deadline_date DATE,
    is_appealed BOOLEAN DEFAULT FALSE,
    appeal_case_number VARCHAR(200),
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES court_sessions(session_id) ON DELETE SET NULL,
    
    INDEX idx_case_judgment (case_id),
    INDEX idx_judgment_date (judgment_date),
    INDEX idx_verdict (verdict)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 9. SENTENCES Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS sentences (
    sentence_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    judgment_id BIGINT NOT NULL,
    charge_id BIGINT,
    
    -- Sentence Details
    sentence_number INT,
    sentence_type VARCHAR(100),
    
    -- Fine Details
    fine_amount DECIMAL(15,2),
    fine_currency VARCHAR(10) DEFAULT 'QAR',
    
    -- Imprisonment Details
    imprisonment_duration_days INT,
    imprisonment_type VARCHAR(50),
    
    -- Confiscation
    confiscation_items TEXT,
    
    -- Other Penalties
    deportation_ordered BOOLEAN DEFAULT FALSE,
    license_suspended BOOLEAN DEFAULT FALSE,
    license_suspension_duration_days INT,
    
    -- Description
    sentence_description_ar TEXT,
    sentence_description_en TEXT,
    
    -- Execution Status
    execution_status VARCHAR(50),
    execution_date DATE,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (judgment_id) REFERENCES judgments(judgment_id) ON DELETE CASCADE,
    FOREIGN KEY (charge_id) REFERENCES charges(charge_id) ON DELETE SET NULL,
    
    INDEX idx_judgment_sentence (judgment_id),
    INDEX idx_sentence_type (sentence_type),
    INDEX idx_execution_status (execution_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 10. EVIDENCE Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    
    -- Evidence Classification
    evidence_type VARCHAR(100),
    evidence_category VARCHAR(100),
    
    -- Description
    evidence_description_ar TEXT,
    evidence_description_en TEXT,
    evidence_number VARCHAR(200),
    
    -- Physical Details
    quantity INT,
    unit VARCHAR(50),
    condition_description TEXT,
    
    -- Chain of Custody
    collected_by_party_id BIGINT,
    collected_date DATETIME,
    collected_location VARCHAR(500),
    
    -- Storage
    storage_location VARCHAR(500),
    storage_status VARCHAR(50),
    
    -- Lab Analysis
    lab_analysis_requested BOOLEAN DEFAULT FALSE,
    lab_result_summary TEXT,
    
    -- Court Decision
    court_decision VARCHAR(100),
    confiscation_judgment_id BIGINT,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY (collected_by_party_id) REFERENCES parties(party_id) ON DELETE SET NULL,
    FOREIGN KEY (confiscation_judgment_id) REFERENCES judgments(judgment_id) ON DELETE SET NULL,
    
    INDEX idx_case_evidence (case_id),
    INDEX idx_evidence_type (evidence_type),
    INDEX idx_storage_status (storage_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 11. LAB_RESULTS Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS lab_results (
    result_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    evidence_id BIGINT,
    subject_party_id BIGINT,
    
    -- Test Details
    test_type VARCHAR(200),
    test_number VARCHAR(200),
    test_date DATETIME,
    
    -- Laboratory
    lab_name VARCHAR(200),
    lab_department VARCHAR(200),
    analyst_name VARCHAR(200),
    
    -- Results
    result_summary_ar TEXT,
    result_summary_en TEXT,
    result_value VARCHAR(500),
    result_unit VARCHAR(100),
    
    -- Interpretation
    interpretation VARCHAR(100),
    detailed_findings TEXT,
    
    -- Report
    report_document_id BIGINT,
    report_date DATETIME,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY (evidence_id) REFERENCES evidence(evidence_id) ON DELETE SET NULL,
    FOREIGN KEY (subject_party_id) REFERENCES parties(party_id) ON DELETE SET NULL,
    FOREIGN KEY (report_document_id) REFERENCES documents(document_id) ON DELETE SET NULL,
    
    INDEX idx_case_results (case_id),
    INDEX idx_test_type (test_type),
    INDEX idx_test_date (test_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 12. STATEMENTS Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS statements (
    statement_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    party_id BIGINT NOT NULL,
    document_id BIGINT,
    
    -- Statement Context
    statement_type VARCHAR(100),
    statement_date DATETIME NOT NULL,
    statement_time TIME,
    statement_location VARCHAR(500),
    
    -- Recording Details
    recorded_by_party_id BIGINT,
    translator_party_id BIGINT,
    
    -- Statement Content
    statement_text_ar TEXT,
    statement_text_en TEXT,
    
    -- Key Points
    incident_description TEXT,
    injuries_claimed TEXT,
    damages_claimed TEXT,
    witnesses_mentioned TEXT,
    
    -- Legal Status
    oath_taken BOOLEAN DEFAULT FALSE,
    is_confession BOOLEAN DEFAULT FALSE,
    is_retracted BOOLEAN DEFAULT FALSE,
    retraction_date DATETIME,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY (party_id) REFERENCES parties(party_id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE SET NULL,
    FOREIGN KEY (recorded_by_party_id) REFERENCES parties(party_id) ON DELETE SET NULL,
    FOREIGN KEY (translator_party_id) REFERENCES parties(party_id) ON DELETE SET NULL,
    
    INDEX idx_case_statements (case_id, statement_date),
    INDEX idx_party_statements (party_id, statement_date),
    INDEX idx_statement_type (statement_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 13. DETENTION_RECORDS Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS detention_records (
    detention_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    party_id BIGINT NOT NULL,
    
    -- Detention Order
    order_number VARCHAR(200),
    order_date DATETIME NOT NULL,
    ordered_by_party_id BIGINT,
    
    -- Detention Details
    detention_type VARCHAR(100),
    detention_reason_ar TEXT,
    detention_reason_en TEXT,
    
    -- Duration
    start_date DATETIME NOT NULL,
    scheduled_end_date DATETIME,
    actual_end_date DATETIME,
    duration_days INT,
    
    -- Location
    detention_facility VARCHAR(200),
    
    -- Release Details
    release_type VARCHAR(100),
    release_conditions TEXT,
    bail_amount DECIMAL(15,2),
    guarantor_party_id BIGINT,
    
    -- Extensions
    extension_count INT DEFAULT 0,
    
    -- Status
    detention_status VARCHAR(50),
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY (party_id) REFERENCES parties(party_id) ON DELETE CASCADE,
    FOREIGN KEY (ordered_by_party_id) REFERENCES parties(party_id) ON DELETE SET NULL,
    FOREIGN KEY (guarantor_party_id) REFERENCES parties(party_id) ON DELETE SET NULL,
    
    INDEX idx_case_detention (case_id),
    INDEX idx_party_detention (party_id),
    INDEX idx_detention_status (detention_status),
    INDEX idx_detention_dates (start_date, actual_end_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 14. NOTIFICATIONS Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS notifications (
    notification_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    recipient_party_id BIGINT NOT NULL,
    
    -- Notification Details
    notification_number VARCHAR(200),
    notification_type VARCHAR(100),
    notification_purpose_ar TEXT,
    notification_purpose_en TEXT,
    
    -- Content
    session_date DATETIME,
    session_id BIGINT,
    judgment_id BIGINT,
    
    -- Delivery
    issue_date DATETIME NOT NULL,
    delivery_method VARCHAR(100),
    delivery_location VARCHAR(500),
    delivery_date DATETIME,
    delivered_to_party_id BIGINT,
    delivered_to_name VARCHAR(200),
    delivered_to_relationship VARCHAR(100),
    
    -- Status
    delivery_status VARCHAR(50),
    delivery_attempts INT DEFAULT 0,
    
    -- Official Details
    serving_officer_party_id BIGINT,
    serving_officer_signature BOOLEAN DEFAULT FALSE,
    recipient_signature BOOLEAN DEFAULT FALSE,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY (recipient_party_id) REFERENCES parties(party_id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES court_sessions(session_id) ON DELETE SET NULL,
    FOREIGN KEY (judgment_id) REFERENCES judgments(judgment_id) ON DELETE SET NULL,
    FOREIGN KEY (delivered_to_party_id) REFERENCES parties(party_id) ON DELETE SET NULL,
    FOREIGN KEY (serving_officer_party_id) REFERENCES parties(party_id) ON DELETE SET NULL,
    
    INDEX idx_case_notifications (case_id),
    INDEX idx_recipient (recipient_party_id, delivery_status),
    INDEX idx_delivery_date (delivery_date),
    INDEX idx_session_notification (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 15. CASE_EVENTS Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS case_events (
    event_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    
    -- Event Details
    event_type VARCHAR(100) NOT NULL,
    event_category VARCHAR(100),
    event_date DATETIME NOT NULL,
    event_time TIME,
    
    -- Description
    event_description_ar TEXT,
    event_description_en TEXT,
    event_location VARCHAR(500),
    
    -- Related Records
    related_document_id BIGINT,
    related_session_id BIGINT,
    related_party_id BIGINT,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY (related_document_id) REFERENCES documents(document_id) ON DELETE SET NULL,
    FOREIGN KEY (related_session_id) REFERENCES court_sessions(session_id) ON DELETE SET NULL,
    FOREIGN KEY (related_party_id) REFERENCES parties(party_id) ON DELETE SET NULL,
    
    INDEX idx_case_timeline (case_id, event_date),
    INDEX idx_event_type (event_type, event_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 16. DOCUMENT_ENTITIES Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS document_entities (
    entity_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    document_id BIGINT NOT NULL,
    
    -- Entity Details
    entity_type VARCHAR(100),
    entity_value TEXT,
    entity_value_normalized VARCHAR(500),
    
    -- Context
    context_snippet TEXT,
    confidence_score DECIMAL(5,4),
    
    -- Position in Document
    start_position INT,
    end_position INT,
    page_number INT,
    
    -- Linking
    linked_party_id BIGINT,
    linked_case_id BIGINT,
    
    -- Metadata
    extraction_method VARCHAR(100),
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE,
    FOREIGN KEY (linked_party_id) REFERENCES parties(party_id) ON DELETE SET NULL,
    FOREIGN KEY (linked_case_id) REFERENCES cases(case_id) ON DELETE SET NULL,
    
    INDEX idx_document_entities (document_id, entity_type),
    INDEX idx_entity_type (entity_type),
    INDEX idx_entity_value (entity_value_normalized)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 17. WAIVERS Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS waivers (
    waiver_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    complainant_party_id BIGINT NOT NULL,
    
    -- Waiver Details
    waiver_date DATETIME NOT NULL,
    waiver_location VARCHAR(500),
    waiver_type VARCHAR(100),
    
    -- Content
    waiver_statement_ar TEXT,
    waiver_statement_en TEXT,
    waiver_conditions TEXT,
    
    -- Verification
    witnessed_by_party_id BIGINT,
    is_voluntary BOOLEAN DEFAULT TRUE,
    under_duress BOOLEAN DEFAULT FALSE,
    
    -- Document
    document_id BIGINT,
    
    -- Effect on Case
    case_status_after VARCHAR(50),
    charges_affected TEXT,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY (complainant_party_id) REFERENCES parties(party_id) ON DELETE CASCADE,
    FOREIGN KEY (witnessed_by_party_id) REFERENCES parties(party_id) ON DELETE SET NULL,
    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE SET NULL,
    
    INDEX idx_case_waiver (case_id),
    INDEX idx_complainant_waiver (complainant_party_id),
    INDEX idx_waiver_date (waiver_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 18. CORRESPONDENCE Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS correspondence (
    correspondence_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT,
    
    -- Letter Details
    correspondence_number VARCHAR(200),
    correspondence_date DATETIME NOT NULL,
    
    -- Parties
    from_organization VARCHAR(200),
    from_department VARCHAR(200),
    from_person VARCHAR(200),
    to_organization VARCHAR(200),
    to_department VARCHAR(200),
    to_person VARCHAR(200),
    
    -- Content
    subject_ar TEXT,
    subject_en TEXT,
    body_ar TEXT,
    body_en TEXT,
    
    -- Classification
    correspondence_type VARCHAR(100),
    priority VARCHAR(50),
    
    -- Related Records
    document_id BIGINT,
    in_response_to_id BIGINT,
    
    -- Attachments
    attachments_count INT DEFAULT 0,
    attachments_description TEXT,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE SET NULL,
    FOREIGN KEY (in_response_to_id) REFERENCES correspondence(correspondence_id) ON DELETE SET NULL,
    
    INDEX idx_case_correspondence (case_id, correspondence_date),
    INDEX idx_from_org (from_organization),
    INDEX idx_to_org (to_organization),
    INDEX idx_correspondence_date (correspondence_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 19. PARSING_METADATA Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS parsing_metadata (
    parsing_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    document_id BIGINT NOT NULL,
    
    -- Parsing Details
    parser_name VARCHAR(100),
    parser_version VARCHAR(50),
    parsing_date TIMESTAMP NOT NULL,
    parsing_duration_ms INT,
    
    -- Quality Metrics
    confidence_score DECIMAL(5,4),
    fields_extracted INT,
    fields_failed INT,
    validation_errors INT,
    
    -- Issues
    parsing_errors TEXT,
    validation_warnings TEXT,
    
    -- Raw Output
    raw_parsing_output LONGTEXT,
    
    -- Status
    parsing_status VARCHAR(50),
    manual_review_required BOOLEAN DEFAULT FALSE,
    reviewed_by VARCHAR(100),
    reviewed_at TIMESTAMP NULL,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE,
    
    INDEX idx_document_parsing (document_id, parsing_date),
    INDEX idx_parser (parser_name, parser_version),
    INDEX idx_status (parsing_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 20. CRIMINAL_RECORDS Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS criminal_records (
    record_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    party_id BIGINT NOT NULL,
    
    -- Record Details
    record_number VARCHAR(200),
    record_type VARCHAR(100),
    
    -- Case Information
    prior_case_number VARCHAR(200),
    prior_case_date DATETIME,
    prior_court_name VARCHAR(200),
    
    -- Offense
    offense_description_ar TEXT,
    offense_description_en TEXT,
    offense_category VARCHAR(100),
    
    -- Outcome
    outcome VARCHAR(100),
    sentence_description TEXT,
    
    -- Verification
    verification_date DATE,
    verified_by VARCHAR(200),
    record_source VARCHAR(200),
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (party_id) REFERENCES parties(party_id) ON DELETE CASCADE,
    
    INDEX idx_party_records (party_id),
    INDEX idx_record_type (record_type),
    INDEX idx_prior_case (prior_case_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;
