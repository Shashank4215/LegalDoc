"""
Document Type Schemas
Defines extraction schemas for each document type in the Qatar legal system
"""

from typing import Dict, List, Any

# Document type schemas with Arabic names and field requirements
DOCUMENT_TYPE_SCHEMAS: Dict[str, Dict[str, Any]] = {
    'police_complaint': {
        'ar_name': 'افادة طرف',
        'en_name': 'Police Complaint Report',
        'required_fields': ['parties', 'incident_date', 'charges', 'locations', 'case_numbers'],
        # Comprehensive optional fields that can realistically appear in a police complaint
        'optional_fields': [
            # Incident narrative/details
            'incident_time', 'incident_location', 'incident_description_ar', 'incident_description_en',
            'cause_ar', 'cause_en', 'motive_ar', 'motive_en', 'consequences_ar', 'consequences_en',
            # Medical/hospital/injuries (often mentioned in complaints)
            'injuries', 'injury_details_ar', 'injury_type', 'hospital', 'hospital_name',
            'hospital_reason_ar', 'hospital_reason_en', 'transfer_reason_ar', 'transfer_reason_en',
            # Weapons/threats
            'weapon', 'tool_used', 'threat_with_weapon', 'weapon_description_ar', 'weapon_description_en',
            # Evidence & witnesses & statements
            'evidence', 'witnesses', 'statements',
            # Procedural/police actions
            'police_actions_ar', 'police_actions_en', 'actions_taken_ar', 'actions_taken_en',
            'police_station', 'report_date', 'report_time', 'report_number',
            # Parties/relationships extras
            'relationships', 'vehicles', 'phones', 'addresses',
            # Legal refs/metadata/status
            'legal_references', 'document_metadata', 'case_status'
        ],
        'description': 'Initial police complaint filed by a party'
    },
    'police_statement': {
        'ar_name': 'افادة أولية',
        'en_name': 'Police Statement',
        'required_fields': ['parties', 'statement_date', 'statement_type', 'case_numbers'],
        'optional_fields': [
            # Statement content
            'statements', 'oath_taken', 'statement_time', 'statement_location',
            # Context (incident may be described within statement)
            'incident_date', 'incident_time', 'incident_location',
            'incident_description_ar', 'incident_description_en',
            'cause_ar', 'cause_en',
            # Medical/hospital/injuries
            'injuries', 'injury_details_ar', 'hospital', 'hospital_name',
            'hospital_reason_ar', 'transfer_reason_ar',
            # Weapons/threats
            'weapon', 'tool_used', 'threat_with_weapon',
            # Charges/locations/evidence
            'charges', 'locations', 'evidence', 'witnesses',
            # Confession/denial cues (often present in statements)
            'confession', 'admission', 'denial', 'denied_charges',
            # Metadata/status
            'document_metadata', 'case_status', 'dates', 'locations'
        ],
        'description': 'Initial police statement or testimony'
    },
    'investigation_record': {
        'ar_name': 'محضر تحقيق',
        'en_name': 'Investigation Record',
        'required_fields': ['parties', 'investigation_date', 'charges', 'locations'],
        'optional_fields': [
            # Investigation details
            'investigation_time', 'interrogation_details', 'questions_answers', 'investigating_officer',
            # Statements/confession/denial
            'statements', 'confession', 'admission', 'denial', 'denied_charges',
            # Incident context
            'incident_date', 'incident_time', 'incident_location',
            'incident_description_ar', 'incident_description_en', 'cause_ar', 'cause_en',
            # Evidence/witnesses/weapons
            'evidence', 'witnesses', 'weapon', 'tool_used', 'threat_with_weapon',
            # Medical/hospital/injuries
            'injuries', 'injury_details_ar', 'hospital', 'hospital_name',
            'hospital_reason_ar', 'transfer_reason_ar',
            # References/metadata/status
            'case_numbers', 'legal_references', 'document_metadata', 'case_status', 'dates'
        ],
        'description': 'Record of investigation proceedings'
    },
    'detention_order': {
        'ar_name': 'حبس احتياطي',
        'en_name': 'Detention Order',
        'required_fields': ['parties', 'order_date', 'detention_type', 'duration_days', 'case_numbers'],
        'optional_fields': [
            'facility', 'facility_name', 'facility_location',
            'charges', 'reasoning_ar', 'reasoning_en',
            'previous_orders', 'bail_amount', 'conditions_ar', 'conditions_en',
            'locations', 'dates', 'document_metadata', 'case_status'
        ],
        'description': 'Order for preventive detention'
    },
    'detention_renewal': {
        'ar_name': 'محضر تجديد حبس',
        'en_name': 'Detention Renewal',
        'required_fields': ['parties', 'renewal_date', 'previous_order_date', 'new_duration', 'case_numbers'],
        'optional_fields': [
            'facility', 'facility_name', 'facility_location',
            'charges', 'reasoning_ar', 'reasoning_en',
            'previous_orders', 'conditions_ar', 'conditions_en',
            'locations', 'dates', 'document_metadata', 'case_status'
        ],
        'description': 'Renewal of detention order'
    },
    'case_transfer_order': {
        'ar_name': 'أمر إحالة',
        'en_name': 'Case Transfer Order',
        'required_fields': ['case_numbers', 'transfer_date', 'from_court', 'to_court', 'parties'],
        'optional_fields': [
            'charges', 'reasoning_ar', 'reasoning_en',
            'transfer_reason_ar', 'transfer_reason_en',
            'locations', 'dates', 'document_metadata', 'case_status'
        ],
        'description': 'Order transferring case between courts'
    },
    'court_session': {
        'ar_name': 'محضر الجلسة',
        'en_name': 'Court Session Minutes',
        'required_fields': ['session_date', 'judge_name', 'parties', 'case_numbers', 'decisions'],
        'optional_fields': [
            'next_session', 'accused_present', 'prosecutor_name', 'secretary_name',
            'courtroom', 'panel', 'attendees', 'requests', 'pleas',
            'evidence', 'witnesses', 'statements',
            'charges', 'locations', 'dates',
            'document_metadata', 'case_status'
        ],
        'description': 'Minutes of court hearing session'
    },
    'court_judgment': {
        'ar_name': 'حكم',
        'en_name': 'Court Judgment',
        'required_fields': ['judgment_date', 'verdict', 'sentences', 'case_numbers', 'parties'],
        'optional_fields': [
            'reasoning_ar', 'reasoning_en',
            'appeal_deadline', 'judge_name', 'court_name',
            'charges', 'legal_references',
            'financial', 'fines', 'damages', 'compensation',
            'evidence', 'witnesses', 'statements',
            'locations', 'dates', 'document_metadata', 'case_status'
        ],
        'description': 'Final court judgment/verdict'
    },
    'court_summons': {
        'ar_name': 'إعلان',
        'en_name': 'Court Summons/Notification',
        'required_fields': ['notification_date', 'recipient_party', 'session_date', 'case_numbers'],
        'optional_fields': [
            'notification_type', 'delivery_status', 'recipient_role',
            'delivery_method', 'delivery_attempts', 'served_by',
            'locations', 'dates', 'document_metadata', 'case_status'
        ],
        'description': 'Court summons or notification to parties'
    },
    'waiver': {
        'ar_name': 'تنازل',
        'en_name': 'Waiver Document',
        'required_fields': ['waiver_date', 'complainant_party', 'case_numbers'],
        'optional_fields': [
            'waiver_type', 'reasoning_ar', 'reasoning_en',
            'waiver_scope', 'waiver_conditions', 'recipient_party',
            'locations', 'dates', 'document_metadata', 'case_status'
        ],
        'description': 'Document waiving rights or complaint'
    },
    'lab_test_results': {
        'ar_name': 'نتيجة فحص الكحول',
        'en_name': 'Lab Test Results',
        'required_fields': ['test_date', 'test_type', 'result', 'subject_party', 'lab_name'],
        'optional_fields': [
            'test_number', 'case_numbers',
            'sample_type', 'sample_collected_at', 'sample_received_at',
            'units', 'reference_range', 'method', 'technician_name',
            'notes_ar', 'notes_en',
            'locations', 'dates', 'document_metadata', 'case_status'
        ],
        'description': 'Laboratory test results (e.g., alcohol test)'
    },
    'forensic_medical_report': {
        'ar_name': 'تقرير الطب الشرعي',
        'en_name': 'Forensic Medical Report',
        'required_fields': ['report_date', 'subject_party', 'medical_findings_ar', 'case_numbers'],
        'optional_fields': [
            'doctor_name', 'examination_type', 'conclusions_ar',
            'medical_findings_en', 'injury_details_ar', 'injury_type',
            'hospital', 'hospital_name',
            'imaging_results', 'lab_results', 'treatment_given',
            'notes_ar', 'notes_en',
            'locations', 'dates', 'document_metadata', 'case_status'
        ],
        'description': 'Forensic medical examination report'
    },
    'enforcement_order': {
        'ar_name': 'تنفيذ الأحكام',
        'en_name': 'Enforcement Order',
        'required_fields': ['enforcement_date', 'case_numbers', 'judgment_reference', 'parties'],
        'optional_fields': [
            'enforcement_type', 'amount', 'status',
            'payment_schedule', 'seizure_details', 'execution_actions_ar', 'execution_actions_en',
            'locations', 'dates', 'document_metadata', 'case_status'
        ],
        'description': 'Order for enforcement of court judgment'
    },
    'criminal_record_request': {
        'ar_name': 'طلب صحيفة الحالة الجنائية',
        'en_name': 'Criminal Record Request',
        'required_fields': ['request_date', 'requested_party', 'case_numbers'],
        'optional_fields': [
            'requesting_authority', 'purpose',
            'request_number', 'response_deadline',
            'locations', 'dates', 'document_metadata', 'case_status'
        ],
        'description': 'Request for criminal record certificate'
    },
    'administrative_correspondence': {
        'ar_name': 'مخاطبة إدارية',
        'en_name': 'Administrative Correspondence',
        'required_fields': ['correspondence_date', 'from_organization', 'to_organization', 'subject_ar'],
        'optional_fields': [
            'correspondence_number', 'case_numbers', 'body_summary_ar', 'body_summary_en',
            'attachments', 'requested_actions_ar', 'requested_actions_en',
            'locations', 'dates', 'document_metadata', 'case_status'
        ],
        'description': 'Administrative correspondence between organizations'
    },
    'release_order': {
        'ar_name': 'أمر إخلاء سبيل',
        'en_name': 'Release Order',
        'required_fields': ['release_date', 'parties', 'case_numbers', 'release_type'],
        'optional_fields': [
            'bail_amount', 'conditions_ar', 'conditions_en', 'charges',
            'release_reason_ar', 'release_reason_en',
            'facility', 'facility_name',
            'locations', 'dates', 'document_metadata', 'case_status'
        ],
        'description': 'Order for release from detention'
    }
}


def get_document_type_schema(doc_type: str) -> Dict[str, Any]:
    """
    Get schema for a specific document type
    
    Args:
        doc_type: Document type identifier
        
    Returns:
        Schema dictionary or empty dict if not found
    """
    return DOCUMENT_TYPE_SCHEMAS.get(doc_type, {})


def get_all_document_types() -> List[str]:
    """Get list of all supported document types"""
    return list(DOCUMENT_TYPE_SCHEMAS.keys())


def get_required_fields(doc_type: str) -> List[str]:
    """Get required fields for a document type"""
    schema = get_document_type_schema(doc_type)
    return schema.get('required_fields', [])


def get_optional_fields(doc_type: str) -> List[str]:
    """Get optional fields for a document type"""
    schema = get_document_type_schema(doc_type)
    return schema.get('optional_fields', [])

