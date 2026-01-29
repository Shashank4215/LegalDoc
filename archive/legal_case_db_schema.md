# Legal Case Management System - Database Schema & Document Parsing Strategy

## Document Analysis Summary

Based on the uploaded documents for Case 2552/2025, the system contains:

### Document Types Identified:
1. **Court Session Minutes** (محضر الجلسة) - Court proceedings records
2. **Police Reports** (بلاغ) - Initial incident reports
3. **Party Statements** (افادة طرف) - Statements from involved parties
4. **Investigation Records** (محضر تحقيق) - Formal investigation transcripts
5. **Court Judgments** (حكم) - Final court decisions
6. **Case Transfer Orders** (أمر إحالة) - Prosecution to court transfers
7. **Notification Documents** (إعلان) - Legal summons/notifications
8. **Detention Orders** (حبس احتياطي) - Custody orders
9. **Lab Results** (نتيجة فحص) - Forensic test results
10. **Waiver Documents** (تنازل) - Complaint withdrawals
11. **Correspondence** (مخاطبات) - Inter-department communications

### Key Entities in Documents:
- Cases with multiple reference numbers (court, prosecution, police)
- Multiple parties (accused, complainants, witnesses, lawyers, judges, prosecutors)
- Legal charges with article references
- Timeline of events and hearings
- Evidence items
- Court decisions and sentences

---

## Database Schema Design

### Core Principles:
1. **Multi-reference support** - Cases have court, prosecution, and police reference numbers
2. **Document versioning** - Track all document versions and amendments
3. **Temporal tracking** - Complete audit trail of all events
4. **Bilingual support** - Arabic and English field names
5. **Flexible structure** - Support various document types and party roles
6. **AI-queryable** - Optimized for natural language to SQL conversion

---

## Schema Tables

### 1. CASES Table
Primary case tracking with all reference numbers.

```sql
CREATE TABLE cases (
    case_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    
    -- Reference Numbers (all cases have multiple references)
    court_case_number VARCHAR(100) UNIQUE NOT NULL,  -- e.g., "2552/2025/جنح متنوعة/ابتدائي"
    prosecution_case_number VARCHAR(100),             -- e.g., "303/2025"
    police_report_number VARCHAR(100),                -- e.g., "2590/2025"
    internal_report_number VARCHAR(100),              -- e.g., "4308/2025"
    
    -- Case Classification
    case_type VARCHAR(50) NOT NULL,                   -- 'criminal', 'civil', 'commercial', etc.
    case_category VARCHAR(100),                       -- 'misdemeanor', 'felony', 'traffic', etc.
    case_subcategory VARCHAR(100),                    -- Specific category
    
    -- Court Information
    court_name VARCHAR(200),                          -- e.g., "محكمة الجنح الابتدائية"
    court_name_en VARCHAR(200),                       -- "Court of First Instance - Misdemeanor"
    circuit_number VARCHAR(50),                       -- e.g., "الدائرة السادسة"
    circuit_name VARCHAR(200),
    
    -- Location & Jurisdiction
    police_station VARCHAR(200),                      -- e.g., "قسم شرطة أم صلال"
    police_station_en VARCHAR(200),                   -- "Um Slal Police Station"
    security_department VARCHAR(200),                 -- e.g., "ادارة أمن الشمال"
    prosecution_office VARCHAR(200),                  -- e.g., "نيابة الشمال"
    
    -- Key Dates
    incident_date DATETIME,                           -- When the incident occurred
    report_date DATETIME,                             -- When reported to police
    case_opened_date DATETIME,                        -- When case officially opened
    case_closed_date DATETIME,                        -- When case closed
    final_judgment_date DATETIME,                     -- Date of final judgment
    
    -- Status
    current_status VARCHAR(50) NOT NULL,              -- 'open', 'under_investigation', 'in_trial', 'closed', etc.
    status_date DATETIME NOT NULL,
    
    -- Summary
    case_summary_ar TEXT,                             -- Brief Arabic description
    case_summary_en TEXT,                             -- Brief English description
    
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
);
```

### 2. PARTIES Table
All individuals and entities involved in cases.

```sql
CREATE TABLE parties (
    party_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    
    -- Personal Information
    personal_id VARCHAR(50),                          -- رقم شخصي
    full_name_ar VARCHAR(200),                        -- Arabic name
    full_name_en VARCHAR(200),                        -- English name
    latin_name VARCHAR(200),                          -- Latin transliteration
    
    -- Demographics
    date_of_birth DATE,
    age INT,
    gender VARCHAR(20),                               -- 'male', 'female'
    nationality VARCHAR(100),
    religion VARCHAR(100),
    
    -- Contact Information
    phone_mobile VARCHAR(50),
    phone_landline VARCHAR(50),
    email VARCHAR(200),
    
    -- Address
    area VARCHAR(200),                                -- منطقة
    compound VARCHAR(200),                            -- مجمع
    building_number VARCHAR(100),
    apartment_number VARCHAR(100),
    street VARCHAR(200),
    po_box VARCHAR(50),
    electricity_number VARCHAR(100),
    unit_number VARCHAR(50),
    
    -- Employment/Sponsorship
    occupation VARCHAR(200),
    sponsor_type VARCHAR(50),                         -- 'individual', 'establishment', etc.
    sponsor_name VARCHAR(200),
    sponsor_id VARCHAR(100),
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_personal_id (personal_id),
    INDEX idx_full_name_ar (full_name_ar),
    INDEX idx_nationality (nationality),
    INDEX idx_sponsor (sponsor_name)
);
```

### 3. CASE_PARTIES Table
Links parties to cases with their specific roles.

```sql
CREATE TABLE case_parties (
    case_party_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    party_id BIGINT NOT NULL,
    
    -- Role Information
    role_type VARCHAR(50) NOT NULL,                   -- 'accused', 'complainant', 'victim', 'witness', 'lawyer', 'judge', 'prosecutor', 'translator', 'officer'
    role_subtype VARCHAR(100),                        -- e.g., 'defense_lawyer', 'prosecution_lawyer', 'expert_witness'
    role_description_ar TEXT,
    role_description_en TEXT,
    
    -- Role-specific Details
    badge_number VARCHAR(50),                         -- For officers
    license_number VARCHAR(50),                       -- For lawyers
    rank VARCHAR(100),                                -- Military/police rank
    
    -- Status in this role
    status VARCHAR(50),                               -- 'active', 'removed', 'replaced'
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
);
```

### 4. DOCUMENTS Table
All documents associated with cases.

```sql
CREATE TABLE documents (
    document_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    
    -- Document Classification
    document_type VARCHAR(100) NOT NULL,              -- 'police_report', 'statement', 'investigation', 'court_session', 'judgment', 'notification', etc.
    document_subtype VARCHAR(100),
    document_category VARCHAR(100),
    
    -- Document Identifiers
    document_number VARCHAR(200),                     -- Official document reference number
    internal_reference VARCHAR(200),
    
    -- File Information
    original_filename VARCHAR(500),
    stored_filename VARCHAR(500) UNIQUE NOT NULL,     -- UUID-based filename
    file_path VARCHAR(1000),
    file_size_bytes BIGINT,
    file_hash VARCHAR(100),                           -- SHA-256 hash for integrity
    mime_type VARCHAR(100),
    
    -- Language & Content
    primary_language VARCHAR(20),                     -- 'ar', 'en', 'both'
    extracted_text_ar TEXT,                           -- Parsed Arabic text
    extracted_text_en TEXT,                           -- Parsed English text
    raw_text TEXT,                                    -- Complete raw text
    
    -- Document Metadata
    document_date DATETIME,                           -- Date mentioned in document
    creation_date DATETIME,                           -- When document was created
    received_date DATETIME,                           -- When received by system
    
    -- Status
    processing_status VARCHAR(50),                    -- 'pending', 'processed', 'error', 'archived'
    is_official BOOLEAN DEFAULT TRUE,
    is_confidential BOOLEAN DEFAULT FALSE,
    is_redacted BOOLEAN DEFAULT FALSE,
    
    -- Authoring Information
    author_party_id BIGINT,                           -- Link to parties table
    author_name VARCHAR(200),
    author_title VARCHAR(200),
    author_organization VARCHAR(200),
    
    -- Processing Info
    parser_version VARCHAR(50),
    parsed_at TIMESTAMP,
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
);
```

### 5. CHARGES Table
Legal charges in each case.

```sql
CREATE TABLE charges (
    charge_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    
    -- Charge Details
    charge_number INT,                                -- Sequence number (التهمة الأولى، الثانية)
    charge_description_ar TEXT NOT NULL,
    charge_description_en TEXT,
    
    -- Legal References
    law_name_ar VARCHAR(500),                         -- e.g., "قانون العقوبات"
    law_name_en VARCHAR(500),
    article_number VARCHAR(100),                      -- e.g., "270", "44"
    article_section VARCHAR(100),                     -- e.g., "/2"
    law_year VARCHAR(20),                             -- e.g., "1999", "2004"
    law_number VARCHAR(50),                           -- e.g., "14 لسنة 1999"
    
    -- Classification
    charge_category VARCHAR(100),                     -- 'misdemeanor', 'felony', etc.
    charge_severity VARCHAR(50),                      -- 'minor', 'moderate', 'major', 'severe'
    
    -- Status
    charge_status VARCHAR(50),                        -- 'pending', 'convicted', 'acquitted', 'dropped', 'amended'
    status_date DATETIME,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE,
    
    INDEX idx_case_charges (case_id),
    INDEX idx_article (article_number),
    INDEX idx_charge_status (charge_status)
);
```

### 6. COURT_SESSIONS Table
Court hearing records.

```sql
CREATE TABLE court_sessions (
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
    session_type VARCHAR(100),                        -- 'hearing', 'judgment', 'investigation', 'procedural'
    session_purpose_ar TEXT,
    session_purpose_en TEXT,
    
    -- Attendance
    judge_present BOOLEAN,
    prosecutor_present BOOLEAN,
    accused_present BOOLEAN,
    lawyer_present BOOLEAN,
    
    -- Session Outcome
    session_status VARCHAR(50),                       -- 'held', 'postponed', 'cancelled', 'judgment_issued'
    next_session_date DATETIME,
    
    -- Decision
    decision_ar TEXT,                                 -- القرار
    decision_en TEXT,
    decision_type VARCHAR(100),                       -- 'adjournment', 'judgment', 'continuation', etc.
    
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
);
```

### 7. SESSION_ATTENDEES Table
Links parties to specific court sessions.

```sql
CREATE TABLE session_attendees (
    attendee_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    session_id BIGINT NOT NULL,
    party_id BIGINT NOT NULL,
    
    -- Attendance Details
    role_in_session VARCHAR(100),                     -- 'judge', 'prosecutor', 'accused', 'lawyer', 'witness', 'secretary'
    attendance_status VARCHAR(50),                    -- 'present', 'absent', 'excused', 'represented'
    arrival_time TIME,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (session_id) REFERENCES court_sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (party_id) REFERENCES parties(party_id) ON DELETE CASCADE,
    
    INDEX idx_session_party (session_id, party_id),
    
    UNIQUE KEY unique_session_party (session_id, party_id, role_in_session)
);
```

### 8. JUDGMENTS Table
Court decisions and verdicts.

```sql
CREATE TABLE judgments (
    judgment_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    session_id BIGINT,                                -- Link to session where judgment was issued
    
    -- Judgment Details
    judgment_number VARCHAR(200),
    judgment_date DATETIME NOT NULL,
    judgment_type VARCHAR(100),                       -- 'conviction', 'acquittal', 'dismissal', 'procedural'
    
    -- Verdict
    verdict VARCHAR(50),                              -- 'guilty', 'not_guilty', 'partially_guilty'
    verdict_description_ar TEXT,
    verdict_description_en TEXT,
    
    -- Presence Type
    presence_type VARCHAR(50),                        -- 'in_presence' (حضوري), 'in_absentia' (غيابي), 'deemed_presence' (حضوري اعتباري)
    
    -- Reasoning
    judgment_reasoning_ar TEXT,                       -- Full judgment text
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
);
```

### 9. SENTENCES Table
Punishments imposed by court.

```sql
CREATE TABLE sentences (
    sentence_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    judgment_id BIGINT NOT NULL,
    charge_id BIGINT,                                 -- Link to specific charge if applicable
    
    -- Sentence Details
    sentence_number INT,                              -- Order in judgment (first, second, etc.)
    sentence_type VARCHAR(100),                       -- 'fine', 'imprisonment', 'confiscation', 'deportation', 'community_service', etc.
    
    -- Fine Details
    fine_amount DECIMAL(15,2),
    fine_currency VARCHAR(10) DEFAULT 'QAR',
    
    -- Imprisonment Details
    imprisonment_duration_days INT,
    imprisonment_type VARCHAR(50),                    -- 'actual', 'suspended', 'community_service'
    
    -- Confiscation
    confiscation_items TEXT,                          -- Description of confiscated items
    
    -- Other Penalties
    deportation_ordered BOOLEAN DEFAULT FALSE,
    license_suspended BOOLEAN DEFAULT FALSE,
    license_suspension_duration_days INT,
    
    -- Description
    sentence_description_ar TEXT,
    sentence_description_en TEXT,
    
    -- Execution Status
    execution_status VARCHAR(50),                     -- 'pending', 'partially_executed', 'fully_executed', 'suspended', 'appealed'
    execution_date DATE,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (judgment_id) REFERENCES judgments(judgment_id) ON DELETE CASCADE,
    FOREIGN KEY (charge_id) REFERENCES charges(charge_id) ON DELETE SET NULL,
    
    INDEX idx_judgment_sentence (judgment_id),
    INDEX idx_sentence_type (sentence_type),
    INDEX idx_execution_status (execution_status)
);
```

### 10. EVIDENCE Table
Physical and documentary evidence.

```sql
CREATE TABLE evidence (
    evidence_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    
    -- Evidence Classification
    evidence_type VARCHAR(100),                       -- 'physical', 'documentary', 'digital', 'testimonial', 'forensic'
    evidence_category VARCHAR(100),                   -- 'weapon', 'substance', 'tool', 'clothing', 'recording', etc.
    
    -- Description
    evidence_description_ar TEXT,
    evidence_description_en TEXT,
    evidence_number VARCHAR(200),                     -- Official evidence tag/number
    
    -- Physical Details
    quantity INT,
    unit VARCHAR(50),                                 -- 'piece', 'gram', 'liter', etc.
    condition_description TEXT,
    
    -- Chain of Custody
    collected_by_party_id BIGINT,
    collected_date DATETIME,
    collected_location VARCHAR(500),
    
    -- Storage
    storage_location VARCHAR(500),
    storage_status VARCHAR(50),                       -- 'in_custody', 'released', 'destroyed', 'confiscated'
    
    -- Lab Analysis
    lab_analysis_requested BOOLEAN DEFAULT FALSE,
    lab_result_summary TEXT,
    
    -- Court Decision
    court_decision VARCHAR(100),                      -- 'confiscated', 'returned', 'destroyed'
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
);
```

### 11. LAB_RESULTS Table
Forensic and laboratory test results.

```sql
CREATE TABLE lab_results (
    result_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    evidence_id BIGINT,                               -- Related evidence if applicable
    subject_party_id BIGINT,                          -- Person tested (if applicable)
    
    -- Test Details
    test_type VARCHAR(200),                           -- 'alcohol', 'drug', 'DNA', 'fingerprint', 'ballistics', etc.
    test_number VARCHAR(200),
    test_date DATETIME,
    
    -- Laboratory
    lab_name VARCHAR(200),
    lab_department VARCHAR(200),
    analyst_name VARCHAR(200),
    
    -- Results
    result_summary_ar TEXT,
    result_summary_en TEXT,
    result_value VARCHAR(500),                        -- Numeric/categorical result
    result_unit VARCHAR(100),
    
    -- Interpretation
    interpretation VARCHAR(100),                      -- 'positive', 'negative', 'inconclusive'
    detailed_findings TEXT,
    
    -- Report
    report_document_id BIGINT,                        -- Link to documents table
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
);
```

### 12. STATEMENTS Table
Recorded statements from parties.

```sql
CREATE TABLE statements (
    statement_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    party_id BIGINT NOT NULL,
    document_id BIGINT,                               -- Link to source document
    
    -- Statement Context
    statement_type VARCHAR(100),                      -- 'complaint', 'testimony', 'interrogation', 'defense', 'waiver'
    statement_date DATETIME NOT NULL,
    statement_time TIME,
    statement_location VARCHAR(500),
    
    -- Recording Details
    recorded_by_party_id BIGINT,                      -- Officer/prosecutor who recorded
    translator_party_id BIGINT,                       -- If translation was involved
    
    -- Statement Content
    statement_text_ar TEXT,
    statement_text_en TEXT,
    
    -- Key Points (structured data extracted from statement)
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
);
```

### 13. DETENTION_RECORDS Table
Custody and detention tracking.

```sql
CREATE TABLE detention_records (
    detention_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    party_id BIGINT NOT NULL,                         -- Detained person
    
    -- Detention Order
    order_number VARCHAR(200),
    order_date DATETIME NOT NULL,
    ordered_by_party_id BIGINT,                       -- Judge/prosecutor who ordered
    
    -- Detention Details
    detention_type VARCHAR(100),                      -- 'pre_trial', 'post_trial', 'investigative', 'protective'
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
    release_type VARCHAR(100),                        -- 'bail', 'bond', 'personal_guarantee', 'order', 'sentence_complete'
    release_conditions TEXT,
    bail_amount DECIMAL(15,2),
    guarantor_party_id BIGINT,
    
    -- Extensions
    extension_count INT DEFAULT 0,
    
    -- Status
    detention_status VARCHAR(50),                     -- 'active', 'released', 'transferred', 'escaped'
    
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
);
```

### 14. NOTIFICATIONS Table
Legal notifications and summons.

```sql
CREATE TABLE notifications (
    notification_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    recipient_party_id BIGINT NOT NULL,
    
    -- Notification Details
    notification_number VARCHAR(200),
    notification_type VARCHAR(100),                   -- 'summons', 'judgment_notice', 'hearing_notice', 'order_notice'
    notification_purpose_ar TEXT,
    notification_purpose_en TEXT,
    
    -- Content
    session_date DATETIME,                            -- If notification is for a session
    session_id BIGINT,
    judgment_id BIGINT,                               -- If notifying about a judgment
    
    -- Delivery
    issue_date DATETIME NOT NULL,
    delivery_method VARCHAR(100),                     -- 'personal', 'residence', 'workplace', 'registered_mail', 'publication'
    delivery_location VARCHAR(500),
    delivery_date DATETIME,
    delivered_to_party_id BIGINT,                     -- Person who received (if not recipient)
    delivered_to_name VARCHAR(200),
    delivered_to_relationship VARCHAR(100),
    
    -- Status
    delivery_status VARCHAR(50),                      -- 'pending', 'delivered', 'refused', 'not_found', 'returned'
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
);
```

### 15. CASE_EVENTS Table
Timeline of all case events.

```sql
CREATE TABLE case_events (
    event_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    
    -- Event Details
    event_type VARCHAR(100) NOT NULL,                 -- 'incident', 'report_filed', 'arrest', 'investigation', 'hearing', 'judgment', 'appeal', etc.
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
);
```

### 16. DOCUMENT_ENTITIES Table
Structured data extracted from documents (NER).

```sql
CREATE TABLE document_entities (
    entity_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    document_id BIGINT NOT NULL,
    
    -- Entity Details
    entity_type VARCHAR(100),                         -- 'person', 'date', 'location', 'organization', 'law_article', 'amount', etc.
    entity_value TEXT,
    entity_value_normalized VARCHAR(500),             -- Standardized format
    
    -- Context
    context_snippet TEXT,                             -- Surrounding text
    confidence_score DECIMAL(5,4),                    -- 0.0000 to 1.0000
    
    -- Position in Document
    start_position INT,
    end_position INT,
    page_number INT,
    
    -- Linking
    linked_party_id BIGINT,                           -- If entity is a person
    linked_case_id BIGINT,                            -- If entity references another case
    
    -- Metadata
    extraction_method VARCHAR(100),                   -- 'regex', 'nlp', 'manual', 'ai_model'
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE,
    FOREIGN KEY (linked_party_id) REFERENCES parties(party_id) ON DELETE SET NULL,
    FOREIGN KEY (linked_case_id) REFERENCES cases(case_id) ON DELETE SET NULL,
    
    INDEX idx_document_entities (document_id, entity_type),
    INDEX idx_entity_type (entity_type),
    INDEX idx_entity_value (entity_value_normalized)
);
```

### 17. WAIVERS Table
Complaint withdrawals and settlements.

```sql
CREATE TABLE waivers (
    waiver_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT NOT NULL,
    complainant_party_id BIGINT NOT NULL,
    
    -- Waiver Details
    waiver_date DATETIME NOT NULL,
    waiver_location VARCHAR(500),
    waiver_type VARCHAR(100),                         -- 'full', 'partial', 'conditional'
    
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
    case_status_after VARCHAR(50),                    -- 'continued', 'dismissed', 'modified'
    charges_affected TEXT,                            -- Which charges were waived
    
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
);
```

### 18. CORRESPONDENCE Table
Inter-department communications.

```sql
CREATE TABLE correspondence (
    correspondence_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id BIGINT,                                   -- May not always be case-specific
    
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
    correspondence_type VARCHAR(100),                 -- 'request', 'response', 'notification', 'report', 'order'
    priority VARCHAR(50),                             -- 'routine', 'urgent', 'confidential'
    
    -- Related Records
    document_id BIGINT,
    in_response_to_id BIGINT,                         -- Link to previous correspondence
    
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
);
```

### 19. PARSING_METADATA Table
Track document parsing history and quality.

```sql
CREATE TABLE parsing_metadata (
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
    parsing_errors TEXT,                              -- JSON array of errors
    validation_warnings TEXT,                         -- JSON array of warnings
    
    -- Raw Output
    raw_parsing_output LONGTEXT,                      -- Full parser output for debugging
    
    -- Status
    parsing_status VARCHAR(50),                       -- 'success', 'partial', 'failed'
    manual_review_required BOOLEAN DEFAULT FALSE,
    reviewed_by VARCHAR(100),
    reviewed_at TIMESTAMP,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE,
    
    INDEX idx_document_parsing (document_id, parsing_date),
    INDEX idx_parser (parser_name, parser_version),
    INDEX idx_status (parsing_status)
);
```

### 20. CRIMINAL_RECORDS Table
Prior criminal history references.

```sql
CREATE TABLE criminal_records (
    record_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    party_id BIGINT NOT NULL,
    
    -- Record Details
    record_number VARCHAR(200),
    record_type VARCHAR(100),                         -- 'prior_conviction', 'pending_case', 'acquittal', 'dismissed'
    
    -- Case Information
    prior_case_number VARCHAR(200),
    prior_case_date DATETIME,
    prior_court_name VARCHAR(200),
    
    -- Offense
    offense_description_ar TEXT,
    offense_description_en TEXT,
    offense_category VARCHAR(100),
    
    -- Outcome
    outcome VARCHAR(100),                             -- 'convicted', 'acquitted', 'dismissed', 'pending'
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
);
```

---

## Document Parsing Strategy

### Phase 1: Document Classification
```python
# Identify document type based on:
# 1. Filename patterns
# 2. Header text patterns
# 3. Document structure
# 4. Key phrases

DOCUMENT_TYPE_PATTERNS = {
    'court_session': ['محضر الجلسة', 'محضر جلسة'],
    'police_report': ['بلاغ داخلي', 'بلاغ رقم'],
    'party_statement': ['افادة طرف', 'افادة أولية'],
    'investigation': ['محضر تحقيق', 'التحقيق'],
    'judgment': ['حُكم', 'صَادِرْ بِإِسْم'],
    'case_transfer': ['أمر إحالة', 'إحالة'],
    'notification': ['إعلان', 'تكليف'],
    'detention_order': ['حبس احتياطي'],
    'lab_result': ['نتيجة فحص', 'تقرير الطب الشرعي'],
    'waiver': ['تنازل'],
    'correspondence': ['مخاطبة', 'السيد', 'المحترم']
}
```

### Phase 2: Extract Core Identifiers
```python
# Extract case reference numbers using regex
PATTERNS = {
    'court_case_number': r'رقم الدعوى:\s*([0-9]+/[0-9]+/[^/\n]+)',
    'prosecution_case_number': r'النيابة:\s*([0-9]+/[0-9]+)',
    'police_report_number': r'البلاغ:\s*([0-9]+/[0-9]+)',
    'personal_id': r'الرقم الشخصي:\s*([0-9]+)',
    'date': r'([0-9]{4}/[0-9]{2}/[0-9]{2})',
    'article_number': r'المادة\s*[:(]?\s*([0-9]+)'
}
```

### Phase 3: Extract Structured Data
For each document type, extract specific fields:

#### Court Session Document:
- Session date and time
- Judge, prosecutor, secretary names
- Attendees and their presence status
- Decision/ruling
- Next session date

#### Police Report:
- Report number and date
- Complainant details
- Accused details
- Incident description
- Location and time of incident
- Witnesses

#### Investigation Record:
- Investigation date
- Prosecutor conducting investigation
- Translator (if any)
- Q&A pairs (questions and answers)
- Confession details
- Charges presented

#### Judgment:
- Judgment date
- Presence type (حضوري/غيابي/حضوري اعتباري)
- Verdict for each charge
- Sentence details (fine amounts, imprisonment, confiscation)
- Legal reasoning

### Phase 4: Entity Linking
- Match extracted names to parties table
- Link personal IDs to party records
- Create case_parties relationships
- Link evidence mentions to evidence table
- Connect dates to case_events timeline

### Phase 5: Relationship Building
- Create timeline entries in case_events
- Link documents to appropriate tables (sessions, judgments, etc.)
- Build detention history
- Track charge evolution
- Map correspondence chains

---

## Parsing Implementation Example

```python
class LegalDocumentParser:
    def __init__(self, db_connection):
        self.db = db_connection
        self.extractors = {
            'court_session': CourtSessionExtractor(),
            'police_report': PoliceReportExtractor(),
            'investigation': InvestigationExtractor(),
            'judgment': JudgmentExtractor(),
            # ... other extractors
        }
    
    def parse_document(self, file_path):
        # 1. Load document
        raw_text = self.load_document(file_path)
        
        # 2. Classify document type
        doc_type = self.classify_document(raw_text)
        
        # 3. Extract case identifiers
        case_refs = self.extract_case_references(raw_text)
        
        # 4. Get or create case
        case_id = self.get_or_create_case(case_refs)
        
        # 5. Store document record
        document_id = self.store_document(case_id, file_path, raw_text, doc_type)
        
        # 6. Extract structured data using appropriate extractor
        extractor = self.extractors[doc_type]
        structured_data = extractor.extract(raw_text)
        
        # 7. Store extracted data in appropriate tables
        self.store_structured_data(case_id, document_id, doc_type, structured_data)
        
        # 8. Perform entity recognition and linking
        entities = self.extract_entities(raw_text)
        self.link_entities(document_id, entities)
        
        # 9. Update case timeline
        self.update_case_timeline(case_id, document_id, structured_data)
        
        # 10. Update parsing metadata
        self.store_parsing_metadata(document_id, extractor.metrics)
        
        return {
            'case_id': case_id,
            'document_id': document_id,
            'doc_type': doc_type,
            'status': 'success'
        }
```

---

## AI Agent Query Examples

With this schema, an AI agent can handle natural language queries:

### Example Queries:

**Query 1:** "What charges does Ashok face?"
```sql
SELECT 
    c.charge_description_ar,
    c.article_number,
    c.law_name_ar,
    c.charge_status
FROM charges c
JOIN cases ca ON c.case_id = ca.case_id
JOIN case_parties cp ON ca.case_id = cp.case_id
JOIN parties p ON cp.party_id = p.party_id
WHERE p.full_name_en = 'Ashok' 
AND cp.role_type = 'accused';
```

**Query 2:** "Show me the timeline of case 2552/2025"
```sql
SELECT 
    event_date,
    event_type,
    event_description_ar
FROM case_events
WHERE case_id = (
    SELECT case_id 
    FROM cases 
    WHERE court_case_number = '2552/2025/جنح متنوعة/ابتدائي'
)
ORDER BY event_date ASC;
```

**Query 3:** "What was the final sentence?"
```sql
SELECT 
    s.sentence_type,
    s.fine_amount,
    s.sentence_description_ar,
    j.judgment_date,
    j.presence_type
FROM sentences s
JOIN judgments j ON s.judgment_id = j.judgment_id
JOIN cases c ON j.case_id = c.case_id
WHERE c.court_case_number = '2552/2025/جنح متنوعة/ابتدائي';
```

**Query 4:** "Did the complainant withdraw the complaint?"
```sql
SELECT 
    w.waiver_date,
    w.waiver_statement_ar,
    w.case_status_after
FROM waivers w
JOIN cases c ON w.case_id = c.case_id
WHERE c.court_case_number = '2552/2025/جنح متنوعة/ابتدائي';
```

**Query 5:** "List all court sessions with their outcomes"
```sql
SELECT 
    cs.session_date,
    cs.session_type,
    cs.accused_present,
    cs.decision_ar,
    cs.next_session_date
FROM court_sessions cs
JOIN cases c ON cs.case_id = c.case_id
WHERE c.court_case_number = '2552/2025/جنح متنوعة/ابتدائي'
ORDER BY cs.session_date ASC;
```

---

## Best Practices for Implementation

### 1. Data Quality
- Implement validation rules at database level
- Use CHECK constraints for enums
- Validate date ranges (end_date > start_date)
- Ensure referential integrity

### 2. Performance
- Create appropriate indexes on frequently queried fields
- Use FULLTEXT indexes for Arabic text search
- Partition large tables by date if needed
- Implement caching for frequently accessed case data

### 3. Security
- Row-level security for multi-tenant scenarios
- Audit logging for all changes
- Encryption for sensitive fields (personal IDs, contact info)
- Role-based access control

### 4. Scalability
- Consider sharding by year or court jurisdiction
- Archive old closed cases to separate database
- Implement document storage in object storage (S3/MinIO) with references in DB
- Use read replicas for reporting queries

### 5. Data Consistency
- Use transactions for multi-table operations
- Implement soft deletes where audit trail is needed
- Maintain data lineage for corrections
- Version control for document parsing rules

### 6. AI/ML Integration
- Store model predictions with confidence scores
- Track model performance metrics
- Allow human override of AI decisions
- Implement feedback loop for continuous improvement

---

## Next Steps

1. **Create database migration scripts** for each table
2. **Develop parsing library** with type-specific extractors
3. **Build API layer** for CRUD operations
4. **Implement document upload pipeline** with validation
5. **Create AI agent** with SQL generation capability
6. **Build dashboards** for case management
7. **Implement search** with Arabic language support
8. **Add document versioning** and change tracking
9. **Create reporting module** for statistics and analytics
10. **Implement notifications** for case updates

This schema provides a solid foundation for a comprehensive legal case management system that can handle the complexity of Arabic legal documents while being queryable by AI agents.
