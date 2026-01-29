# Updated AI Document Processor with Intelligent Case Matching
# Uses the CaseMatcher to handle documents arriving in any order

import os
import hashlib
import uuid
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
import logging

from ai_document_parser import AIDocumentExtractor, CourtSessionData, PoliceReportData, InvestigationData, JudgmentData
from case_matcher import CaseReferences, SmartCaseProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ImprovedAIDocumentProcessor:
    """
    Enhanced document processor that uses intelligent case matching
    to handle documents arriving in any order
    """
    
    def __init__(self, anthropic_api_key: str, db_manager, storage_path: str):
        """
        Initialize processor
        
        Args:
            anthropic_api_key: Anthropic API key
            db_manager: DatabaseManager instance
            storage_path: Path for document storage
        """
        self.extractor = AIDocumentExtractor(api_key=anthropic_api_key)
        self.db = db_manager
        self.storage_path = Path(storage_path)
        self.case_processor = SmartCaseProcessor(db_manager)
        
        # Ensure storage path exists
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        logger.info("Improved AI Document Processor initialized")
    
    def process_document(self, file_path: str) -> Dict[str, Any]:
        """
        Process document with intelligent case matching
        
        Args:
            file_path: Path to document file
        
        Returns:
            Processing results
        """
        logger.info(f"Processing document: {file_path}")
        
        try:
            # Step 1: Load document text
            with open(file_path, 'r', encoding='utf-8') as f:
                document_text = f.read()
            
            logger.info(f"Document loaded: {len(document_text)} characters")
            
            # Step 2: AI classification and extraction
            result = self.extractor.classify_and_extract(document_text)
            doc_type = result['document_type']
            confidence = result['confidence']
            extracted_data = result['extracted_data']
            
            logger.info(f"Classified as {doc_type} (confidence: {confidence}%)")
            
            # Step 3: Extract case references from extracted data
            references = self._extract_references(extracted_data)
            
            logger.info(f"References found: {references.get_available_references()}")
            
            # Step 4: Prepare document metadata
            document_metadata = self._prepare_metadata(doc_type, extracted_data)
            
            # Step 5: Find or create case using intelligent matcher
            case_result = self.case_processor.process_document_intelligently(
                references=references,
                document_type=doc_type,
                document_data=extracted_data,
                document_metadata=document_metadata
            )
            
            case_id = case_result['case_id']
            
            logger.info(f"Case ID: {case_id} ({case_result['action']})")
            
            if not case_result['sequence_valid']:
                logger.warning("Document sequence validation failed - unusual order")
            
            # Step 6: Store document file
            stored_filename, file_hash = self._store_document_file(file_path)
            
            # Step 7: Create document record
            document_data = {
                'case_id': case_id,
                'document_type': doc_type,
                'document_category': result.get('category', doc_type),
                'original_filename': os.path.basename(file_path),
                'stored_filename': stored_filename,
                'file_path': str(self.storage_path / stored_filename),
                'file_hash': file_hash,
                'raw_text': document_text,
                'primary_language': 'ar',
                'processing_status': 'processed',
                'received_date': datetime.now(),
                'document_date': self._extract_document_date(extracted_data)
            }
            
            document_id = self._insert_document(document_data)
            
            logger.info(f"Document record created: {document_id}")
            
            # Step 8: Store extracted structured data
            self._store_extracted_data(case_id, document_id, doc_type, extracted_data)
            
            # Step 9: Get case completeness
            completeness = self.case_processor.get_case_completeness(case_id)
            
            # Step 10: Return comprehensive result
            return {
                'success': True,
                'case_id': case_id,
                'document_id': document_id,
                'document_type': doc_type,
                'confidence': confidence,
                'case_action': case_result['action'],  # 'found' or 'created'
                'sequence_valid': case_result['sequence_valid'],
                'completeness': completeness,
                'extracted_data': self._serialize_extracted_data(extracted_data)
            }
        
        except Exception as e:
            logger.error(f"Error processing document: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'file_path': file_path
            }
    
    def _extract_references(self, extracted_data: Any) -> CaseReferences:
        """Extract case references from extracted data"""
        
        references = CaseReferences()
        
        # Extract from case_references if it exists
        if hasattr(extracted_data, 'case_references'):
            refs = extracted_data.case_references
            references.court_case_number = refs.court_case_number
            references.prosecution_case_number = refs.prosecution_case_number
            references.police_report_number = refs.police_report_number
            references.internal_report_number = refs.internal_report_number
        
        return references
    
    def _prepare_metadata(self, doc_type: str, extracted_data: Any) -> Dict[str, Any]:
        """Prepare document metadata for case creation/update"""
        
        metadata = {}
        
        if doc_type == 'police_report' and isinstance(extracted_data, PoliceReportData):
            metadata['incident_date'] = extracted_data.incident_date
            metadata['report_date'] = extracted_data.report_date
            metadata['police_station'] = extracted_data.police_station
        
        elif doc_type == 'investigation' and isinstance(extracted_data, InvestigationData):
            metadata['prosecution_office'] = 'نيابة الشمال'  # Could extract this too
        
        return metadata
    
    def _extract_document_date(self, extracted_data: Any) -> str:
        """Extract primary date from document"""
        
        # Try different date fields depending on document type
        date_fields = ['judgment_date', 'session_date', 'investigation_date', 
                      'report_date', 'incident_date']
        
        for field in date_fields:
            if hasattr(extracted_data, field):
                date_val = getattr(extracted_data, field)
                if date_val:
                    return date_val
        
        return None
    
    def _store_document_file(self, file_path: str) -> tuple:
        """Store document file and return (filename, hash)"""
        
        # Calculate hash
        with open(file_path, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        
        # Generate unique filename
        ext = os.path.splitext(file_path)[1]
        stored_filename = f"{uuid.uuid4()}{ext}"
        
        # Copy to storage
        import shutil
        dest_path = self.storage_path / stored_filename
        shutil.copy2(file_path, dest_path)
        
        return stored_filename, file_hash
    
    def _insert_document(self, document_data: Dict[str, Any]) -> int:
        """Insert document record into database"""
        
        with self.db.connection.cursor() as cursor:
            fields = []
            values = []
            placeholders = []
            
            for key, value in document_data.items():
                if value is not None:
                    fields.append(key)
                    values.append(value)
                    placeholders.append('%s')
            
            sql = f"""
                INSERT INTO documents ({', '.join(fields)})
                VALUES ({', '.join(placeholders)})
                RETURNING document_id
            """
            
            cursor.execute(sql, values)
            self.db.connection.commit()
            return cursor.fetchone()['document_id']
    
    def _store_extracted_data(self, case_id: int, document_id: int, 
                              doc_type: str, data: Any):
        """Store extracted data in appropriate tables"""
        
        if doc_type == 'court_session' and isinstance(data, CourtSessionData):
            self._store_court_session(case_id, document_id, data)
        
        elif doc_type == 'police_report' and isinstance(data, PoliceReportData):
            self._store_police_report(case_id, document_id, data)
        
        elif doc_type == 'investigation' and isinstance(data, InvestigationData):
            self._store_investigation(case_id, document_id, data)
        
        elif doc_type == 'judgment' and isinstance(data, JudgmentData):
            self._store_judgment(case_id, document_id, data)
    
    def _store_court_session(self, case_id: int, document_id: int, data: CourtSessionData):
        """Store court session data"""
        
        # Insert session
        session_data = {
            'case_id': case_id,
            'session_date': data.session_date,
            'session_time': data.session_time,
            'decision_ar': data.decision_ar,
            'next_session_date': data.next_session_date,
            'accused_present': data.accused_present,
            'court_name': data.court_name,
            'circuit_name': data.circuit_name,
            'session_status': 'held'
        }
        
        session_id = self._insert_generic('court_sessions', session_data)
        
        # Link parties
        if data.judge_name:
            judge_id = self._get_or_create_party({'full_name_ar': data.judge_name})
            self._link_party_to_case(case_id, judge_id, 'judge')
        
        if data.prosecutor_name:
            prosecutor_id = self._get_or_create_party({'full_name_ar': data.prosecutor_name})
            self._link_party_to_case(case_id, prosecutor_id, 'prosecutor')
        
        if data.secretary_name:
            secretary_id = self._get_or_create_party({'full_name_ar': data.secretary_name})
            self._link_party_to_case(case_id, secretary_id, 'secretary')
        
        # Add event
        self._add_case_event(case_id, {
            'event_type': 'court_hearing',
            'event_date': data.session_date,
            'event_description_ar': f"جلسة محكمة: {data.decision_ar or ''}",
            'related_session_id': session_id,
            'related_document_id': document_id
        })
    
    def _store_police_report(self, case_id: int, document_id: int, data: PoliceReportData):
        """Store police report data"""
        
        # Link complainant
        if data.complainant:
            complainant_dict = {
                'full_name_ar': data.complainant.full_name_ar,
                'full_name_en': data.complainant.full_name_en,
                'personal_id': data.complainant.personal_id,
                'nationality': data.complainant.nationality,
                'age': data.complainant.age,
                'gender': data.complainant.gender,
                'occupation': data.complainant.occupation,
                'phone_mobile': data.complainant.phone
            }
            complainant_dict = {k: v for k, v in complainant_dict.items() if v}
            complainant_id = self._get_or_create_party(complainant_dict)
            self._link_party_to_case(case_id, complainant_id, 'complainant')
        
        # Link accused
        if data.accused:
            accused_dict = {
                'full_name_ar': data.accused.full_name_ar,
                'full_name_en': data.accused.full_name_en,
                'nationality': data.accused.nationality
            }
            accused_dict = {k: v for k, v in accused_dict.items() if v}
            accused_id = self._get_or_create_party(accused_dict)
            self._link_party_to_case(case_id, accused_id, 'accused')
        
        # Add incident event
        self._add_case_event(case_id, {
            'event_type': 'incident',
            'event_date': data.incident_date,
            'event_time': data.incident_time,
            'event_description_ar': data.incident_description_ar,
            'event_location': data.incident_location,
            'related_document_id': document_id
        })
        
        # Add report filed event
        self._add_case_event(case_id, {
            'event_type': 'report_filed',
            'event_date': data.report_date,
            'event_description_ar': f"تم تقديم بلاغ رقم {data.case_references.police_report_number or ''}",
            'related_document_id': document_id
        })
    
    def _store_investigation(self, case_id: int, document_id: int, data: InvestigationData):
        """Store investigation data"""
        
        # Link subject person
        if data.subject_person:
            subject_dict = {
                'full_name_ar': data.subject_person.full_name_ar,
                'personal_id': data.subject_person.personal_id,
                'nationality': data.subject_person.nationality,
                'age': data.subject_person.age,
                'occupation': data.subject_person.occupation,
                'religion': data.subject_person.religion
            }
            subject_dict = {k: v for k, v in subject_dict.items() if v}
            subject_id = self._get_or_create_party(subject_dict)
            
            # Store statement
            import json
            statement_data = {
                'case_id': case_id,
                'party_id': subject_id,
                'statement_type': 'interrogation',
                'statement_date': data.investigation_date,
                'statement_time': data.investigation_time,
                'oath_taken': data.oath_taken,
                'is_confession': data.confession_made,
                'document_id': document_id,
                'statement_text_ar': json.dumps(data.questions_answers, ensure_ascii=False) if data.questions_answers else None
            }
            self._insert_generic('statements', statement_data)
        
        # Store charges
        if data.charges_presented:
            for charge in data.charges_presented:
                charge_data = {
                    'case_id': case_id,
                    'charge_number': charge.charge_number,
                    'charge_description_ar': charge.charge_description_ar,
                    'article_number': charge.article_number,
                    'article_section': charge.article_section,
                    'law_name_ar': charge.law_name_ar,
                    'charge_status': 'pending'
                }
                self._insert_generic('charges', charge_data)
        
        # Add event
        self._add_case_event(case_id, {
            'event_type': 'investigation',
            'event_date': data.investigation_date,
            'event_description_ar': 'تحقيق النيابة العامة',
            'related_document_id': document_id
        })
    
    def _store_judgment(self, case_id: int, document_id: int, data: JudgmentData):
        """Store judgment data"""
        
        # Insert judgment
        judgment_data = {
            'case_id': case_id,
            'judgment_date': data.judgment_date,
            'presence_type': data.presence_type,
            'verdict': data.verdict,
            'is_final': True,
            'judgment_reasoning_ar': data.reasoning_summary_ar
        }
        
        judgment_id = self._insert_generic('judgments', judgment_data)
        
        # Insert sentences
        if data.sentences:
            for sentence in data.sentences:
                sentence['judgment_id'] = judgment_id
                self._insert_generic('sentences', sentence)
        
        # Update case status
        with self.db.connection.cursor() as cursor:
            cursor.execute("""
                UPDATE cases 
                SET current_status = 'closed',
                    case_closed_date = %s,
                    final_judgment_date = %s,
                    updated_at = NOW()
                WHERE case_id = %s
            """, (data.judgment_date, data.judgment_date, case_id))
            self.db.connection.commit()
        
        # Add event
        self._add_case_event(case_id, {
            'event_type': 'judgment',
            'event_date': data.judgment_date,
            'event_description_ar': 'صدور الحكم',
            'related_document_id': document_id
        })
    
    def _get_or_create_party(self, party_data: Dict[str, Any]) -> int:
        """Get or create party"""
        
        # Try to find by personal_id
        if party_data.get('personal_id'):
            with self.db.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT party_id FROM parties WHERE personal_id = %s LIMIT 1",
                    (party_data['personal_id'],)
                )
                result = cursor.fetchone()
                if result:
                    return result['party_id']
        
        # Try to find by name and nationality
        if party_data.get('full_name_ar') and party_data.get('nationality'):
            with self.db.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT party_id FROM parties WHERE full_name_ar = %s AND nationality = %s LIMIT 1",
                    (party_data['full_name_ar'], party_data['nationality'])
                )
                result = cursor.fetchone()
                if result:
                    return result['party_id']
        
        # Create new party
        return self._insert_generic('parties', party_data)
    
    def _link_party_to_case(self, case_id: int, party_id: int, role_type: str):
        """Link party to case with role"""
        
        with self.db.connection.cursor() as cursor:
            # Check if already linked
            cursor.execute("""
                SELECT case_party_id FROM case_parties 
                WHERE case_id = %s AND party_id = %s AND role_type = %s
            """, (case_id, party_id, role_type))
            
            if cursor.fetchone():
                return  # Already linked
            
            # Create link
            cursor.execute("""
                INSERT INTO case_parties (case_id, party_id, role_type, status, assigned_date)
                VALUES (%s, %s, %s, 'active', NOW())
            """, (case_id, party_id, role_type))
            self.db.connection.commit()
    
    def _add_case_event(self, case_id: int, event_data: Dict[str, Any]):
        """Add event to case timeline"""
        event_data['case_id'] = case_id
        self._insert_generic('case_events', event_data)
    
    def _insert_generic(self, table_name: str, data: Dict[str, Any]) -> int:
        """Generic insert that returns ID"""
        
        with self.db.connection.cursor() as cursor:
            fields = [k for k, v in data.items() if v is not None]
            values = [v for v in data.values() if v is not None]
            placeholders = ['%s'] * len(fields)
            
            sql = f"""
                INSERT INTO {table_name} ({', '.join(fields)})
                VALUES ({', '.join(placeholders)})
                RETURNING {table_name.rstrip('s')}_id
            """
            
            cursor.execute(sql, values)
            self.db.connection.commit()
            return cursor.fetchone()[f"{table_name.rstrip('s')}_id"]
    
    def _serialize_extracted_data(self, data: Any) -> Dict[str, Any]:
        """Convert extracted data to dictionary for JSON serialization"""
        
        if hasattr(data, '__dict__'):
            return {k: self._serialize_value(v) for k, v in data.__dict__.items()}
        return {}
    
    def _serialize_value(self, value: Any) -> Any:
        """Serialize a single value"""
        
        if hasattr(value, '__dict__'):
            return {k: self._serialize_value(v) for k, v in value.__dict__.items()}
        elif isinstance(value, list):
            return [self._serialize_value(v) for v in value]
        else:
            return value
