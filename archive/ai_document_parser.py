# AI-Powered Legal Document Parser
# Uses Claude/GPT for intelligent extraction instead of regex patterns

import json
import anthropic
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# STRUCTURED OUTPUT SCHEMAS (Pydantic-style)
# ============================================================================

@dataclass
class PersonInfo:
    """Structured person information"""
    full_name_ar: Optional[str] = None
    full_name_en: Optional[str] = None
    personal_id: Optional[str] = None
    nationality: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    occupation: Optional[str] = None
    phone: Optional[str] = None
    religion: Optional[str] = None
    area: Optional[str] = None  # منطقة (area/location)


@dataclass
class CaseReference:
    """Case reference numbers"""
    court_case_number: Optional[str] = None
    prosecution_case_number: Optional[str] = None
    police_report_number: Optional[str] = None
    internal_report_number: Optional[str] = None


@dataclass
class ChargeInfo:
    """Criminal charge information"""
    charge_number: int
    charge_description_ar: str
    charge_description_en: Optional[str] = None
    article_number: Optional[str] = None
    article_section: Optional[str] = None
    law_name_ar: Optional[str] = None
    law_year: Optional[str] = None


@dataclass
class CorrespondenceData:
    """Extracted correspondence data"""
    case_references: CaseReference
    correspondence_number: Optional[str] = None
    correspondence_date: Optional[str] = None
    sender_name: Optional[str] = None
    sender_organization: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_organization: Optional[str] = None
    subject_ar: Optional[str] = None
    correspondence_type: Optional[str] = None
    content_summary_ar: Optional[str] = None
    mentioned_case_numbers: Optional[List[str]] = None
    mentioned_dates: Optional[List[str]] = None


@dataclass
class DetentionOrderData:
    """Extracted detention order data"""
    case_references: CaseReference
    detention_order_number: Optional[str] = None
    order_date: Optional[str] = None
    detention_type: Optional[str] = None  # 'pre_trial', 'post_trial', 'investigative', 'protective'
    detention_reason_ar: Optional[str] = None
    detention_reason_en: Optional[str] = None
    start_date: Optional[str] = None
    expected_end_date: Optional[str] = None
    detention_duration_days: Optional[int] = None
    detention_facility: Optional[str] = None
    detention_status: Optional[str] = None  # 'active', 'released', 'transferred'
    judge_name: Optional[str] = None
    prosecutor_name: Optional[str] = None
    detained_person: Optional[PersonInfo] = None
    court_name: Optional[str] = None
    circuit_name: Optional[str] = None
    mentioned_case_numbers: Optional[List[str]] = None


@dataclass
class WaiverData:
    """Extracted waiver data"""
    case_references: CaseReference
    waiver_date: Optional[str] = None
    waiver_location: Optional[str] = None
    waiver_type: Optional[str] = None  # 'full', 'partial', 'conditional'
    waiver_statement_ar: Optional[str] = None
    waiver_statement_en: Optional[str] = None
    waiver_conditions: Optional[str] = None
    complainant: Optional[PersonInfo] = None
    accused_person: Optional[PersonInfo] = None
    witnessed_by_name: Optional[str] = None
    is_voluntary: bool = True
    under_duress: bool = False
    case_status_after: Optional[str] = None
    charges_affected: Optional[List[str]] = None


@dataclass
class NotificationData:
    """Extracted notification data"""
    case_references: CaseReference
    notification_number: Optional[str] = None
    notification_type: Optional[str] = None  # 'summons', 'judgment_notice', 'hearing_notice', 'order_notice'
    notification_purpose_ar: Optional[str] = None
    notification_purpose_en: Optional[str] = None
    issue_date: Optional[str] = None
    session_date: Optional[str] = None
    session_time: Optional[str] = None
    recipient: Optional[PersonInfo] = None  # Person being notified
    delivered_to_name: Optional[str] = None  # If delivered to someone else
    delivered_to_relationship: Optional[str] = None
    delivery_method: Optional[str] = None  # 'personal', 'residence', 'workplace'
    delivery_location: Optional[str] = None
    delivery_date: Optional[str] = None
    delivery_status: Optional[str] = None  # 'delivered', 'refused', 'not_found'
    serving_officer_name: Optional[str] = None
    recipient_signature: bool = False
    court_name: Optional[str] = None
    circuit_name: Optional[str] = None
    charges_mentioned: Optional[List[str]] = None


@dataclass
class CaseTransferData:
    """Extracted case transfer order data"""
    case_references: CaseReference
    transfer_order_number: Optional[str] = None
    transfer_date: Optional[str] = None
    prosecutor_name: Optional[str] = None
    prosecutor_title: Optional[str] = None
    prosecution_office: Optional[str] = None
    accused_person: Optional[PersonInfo] = None
    charges: Optional[List[ChargeInfo]] = None
    transfer_reason_ar: Optional[str] = None
    transfer_reason_en: Optional[str] = None
    target_court_name: Optional[str] = None
    target_circuit_name: Optional[str] = None
    transfer_instructions_ar: Optional[str] = None
    transfer_instructions_en: Optional[str] = None
    mentioned_case_numbers: Optional[List[str]] = None
    mentioned_dates: Optional[List[str]] = None


@dataclass
class CourtSessionData:
    """Extracted court session data"""
    case_references: CaseReference
    session_date: Optional[str] = None
    session_time: Optional[str] = None
    judge_name: Optional[str] = None
    prosecutor_name: Optional[str] = None
    secretary_name: Optional[str] = None
    accused_present: bool = False
    decision_ar: Optional[str] = None
    decision_type: Optional[str] = None  # 'adjournment', 'judgment', etc.
    next_session_date: Optional[str] = None
    court_name: Optional[str] = None
    circuit_name: Optional[str] = None


@dataclass
class PoliceReportData:
    """Extracted police report data"""
    case_references: CaseReference
    report_date: Optional[str] = None
    report_time: Optional[str] = None
    police_station: Optional[str] = None
    complainant: Optional[PersonInfo] = None
    accused: Optional[PersonInfo] = None
    incident_date: Optional[str] = None
    incident_time: Optional[str] = None
    incident_location: Optional[str] = None
    incident_description_ar: Optional[str] = None
    recording_officer_name: Optional[str] = None
    recording_officer_rank: Optional[str] = None


@dataclass
class InvestigationData:
    """Extracted investigation record data"""
    case_references: CaseReference
    investigation_date: Optional[str] = None
    investigation_time: Optional[str] = None
    prosecutor_name: Optional[str] = None
    translator_name: Optional[str] = None
    subject_person: Optional[PersonInfo] = None
    questions_answers: List[Dict[str, str]] = None
    charges_presented: List[ChargeInfo] = None
    confession_made: bool = False
    oath_taken: bool = False


@dataclass
class JudgmentData:
    """Extracted judgment data"""
    case_references: CaseReference
    judgment_date: Optional[str] = None
    judge_name: Optional[str] = None
    prosecutor_name: Optional[str] = None
    presence_type: Optional[str] = None  # 'in_presence', 'in_absentia', 'deemed_presence'
    verdict: Optional[str] = None  # 'guilty', 'not_guilty'
    charges: List[ChargeInfo] = None
    sentences: List[Dict[str, Any]] = None
    reasoning_summary_ar: Optional[str] = None


# ============================================================================
# AI-POWERED EXTRACTOR
# ============================================================================

class AIDocumentExtractor:
    """Uses Claude AI to extract structured data from legal documents"""
    
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        """
        Initialize AI extractor
        
        Args:
            api_key: Anthropic API key
            model: Claude model to use
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        logger.info(f"AI Extractor initialized with model: {model}")
    
    def extract_court_session(self, document_text: str) -> CourtSessionData:
        """Extract structured data from court session document"""
        
        system_prompt = """You are an expert at extracting structured information from Arabic legal documents, specifically Qatari court session minutes (محضر الجلسة).

Your task is to extract all relevant information and return it as valid JSON following the exact schema provided.

Key information to extract:
- Case reference numbers (court case number, prosecution number, police report number)
- Session date and time
- Names of judge, prosecutor, and secretary
- Whether the accused was present
- The decision made (القرار)
- Next session date if mentioned
- Court name and circuit

Be precise with dates (format: YYYY-MM-DD) and names. If information is not present, use null."""

        user_prompt = f"""Extract structured information from this court session document:

{document_text}

Return ONLY valid JSON with this exact structure:
{{
  "case_references": {{
    "court_case_number": "string or null",
    "prosecution_case_number": "string or null",
    "police_report_number": "string or null"
  }},
  "session_date": "YYYY-MM-DD or null",
  "session_time": "HH:MM or null",
  "judge_name": "string or null",
  "prosecutor_name": "string or null",
  "secretary_name": "string or null",
  "accused_present": true or false,
  "decision_ar": "string or null",
  "decision_type": "adjournment|judgment|continuation|null",
  "next_session_date": "YYYY-MM-DD or null",
  "court_name": "string or null",
  "circuit_name": "string or null"
}}"""

        response = self._call_claude(system_prompt, user_prompt)
        data = self._parse_json_response(response)
        
        # Convert to dataclass
        return CourtSessionData(
            case_references=CaseReference(**data.get('case_references', {})),
            **{k: v for k, v in data.items() if k != 'case_references'}
        )
    
    def extract_police_report(self, document_text: str) -> PoliceReportData:
        """Extract structured data from police report"""
        
        system_prompt = """You are an expert at extracting structured information from Arabic legal documents, specifically Qatari police reports (بلاغ).

Your task is to extract all relevant information about the incident, complainant, accused, and investigation details.

Key information to extract:
- Report numbers and references
- Complainant details (name, personal ID, nationality, etc.)
- Accused details (name, nationality, etc.)
- Incident date, time, and location
- Incident description
- Recording officer details

Be thorough and precise. Extract all personal information found in the document."""

        user_prompt = f"""Extract structured information from this police report:

{document_text}

Return ONLY valid JSON with this exact structure:
{{
  "case_references": {{
    "court_case_number": "string or null",
    "prosecution_case_number": "string or null",
    "police_report_number": "string or null",
    "internal_report_number": "string or null"
  }},
  "report_date": "YYYY-MM-DD or null",
  "report_time": "HH:MM or null",
  "police_station": "string or null",
  "complainant": {{
    "full_name_ar": "string or null",
    "full_name_en": "string or null",
    "personal_id": "string or null",
    "nationality": "string or null",
    "age": number or null,
    "gender": "male|female|null",
    "occupation": "string or null",
    "phone": "string or null"
  }},
  "accused": {{
    "full_name_ar": "string or null",
    "full_name_en": "string or null",
    "nationality": "string or null"
  }},
  "incident_date": "YYYY-MM-DD or null",
  "incident_time": "HH:MM or null",
  "incident_location": "string or null",
  "incident_description_ar": "string or null",
  "recording_officer_name": "string or null",
  "recording_officer_rank": "string or null"
}}"""

        response = self._call_claude(system_prompt, user_prompt)
        data = self._parse_json_response(response)
        
        # Convert to dataclass
        return PoliceReportData(
            case_references=CaseReference(**data.get('case_references', {})),
            complainant=PersonInfo(**data.get('complainant', {})) if data.get('complainant') else None,
            accused=PersonInfo(**data.get('accused', {})) if data.get('accused') else None,
            **{k: v for k, v in data.items() if k not in ['case_references', 'complainant', 'accused']}
        )
    
    def extract_investigation(self, document_text: str) -> InvestigationData:
        """Extract structured data from investigation record"""
        
        system_prompt = """You are an expert at extracting structured information from Arabic legal documents, specifically Qatari prosecution investigation records (محضر تحقيق).

These documents contain:
- Case reference numbers (may be mentioned anywhere in the text):
  * Court case numbers (رقم القضية)
  * Prosecution case numbers (رقم النيابة, رقم المحضر)
  * Police report numbers (رقم البلاغ, في البلاغ رقم)
- Investigation details (date, prosecutor, translator)
- Subject person information (the person being questioned)
- Question and answer pairs (س/ and ج/)
- Charges being investigated
- Whether the person confessed

Be thorough in finding case references - they may be mentioned in the header, body, or within the Q&A text. Extract all Q&A pairs in sequence, maintaining the exact wording of questions and answers."""

        user_prompt = f"""Extract structured information from this investigation record:

{document_text}

Return ONLY valid JSON with this exact structure:
{{
  "case_references": {{
    "court_case_number": "string or null (extract if mentioned anywhere)",
    "prosecution_case_number": "string or null (extract if mentioned - may be in format like '2025-016-10-4593' or 'رقم النيابة')",
    "police_report_number": "string or null (extract if mentioned - may be in format like '2590/2025' or 'في البلاغ رقم 2590/2025')",
    "internal_report_number": "string or null"
  }},
  "investigation_date": "YYYY-MM-DD or null",
  "investigation_time": "HH:MM or null",
  "prosecutor_name": "string or null",
  "translator_name": "string or null",
  "subject_person": {{
    "full_name_ar": "string or null",
    "personal_id": "string or null",
    "nationality": "string or null",
    "age": number or null,
    "occupation": "string or null",
    "religion": "string or null"
  }},
  "questions_answers": [
    {{"question": "string", "answer": "string"}},
    ...
  ],
  "charges_presented": [
    {{
      "charge_number": number,
      "charge_description_ar": "string",
      "article_number": "string or null",
      "law_name_ar": "string or null"
    }},
    ...
  ],
  "confession_made": true or false,
  "oath_taken": true or false
}}

For questions_answers, extract ALL Q&A pairs found in the document (marked with س/ and ج/)."""

        response = self._call_claude(system_prompt, user_prompt)
        data = self._parse_json_response(response)
        
        # Convert to dataclass
        return InvestigationData(
            case_references=CaseReference(**data.get('case_references', {})),
            subject_person=PersonInfo(**data.get('subject_person', {})) if data.get('subject_person') else None,
            questions_answers=data.get('questions_answers', []),
            charges_presented=[ChargeInfo(**c) for c in data.get('charges_presented', [])],
            confession_made=data.get('confession_made', False),
            oath_taken=data.get('oath_taken', False),
            **{k: v for k, v in data.items() if k not in ['case_references', 'subject_person', 'questions_answers', 'charges_presented', 'confession_made', 'oath_taken']}
        )
    
    def extract_judgment(self, document_text: str) -> JudgmentData:
        """Extract structured data from court judgment"""
        
        system_prompt = """You are an expert at extracting structured information from Arabic legal documents, specifically Qatari court judgments (حكم).

These documents contain:
- Judgment date and court information
- Judge and prosecutor names
- Presence type (حضوري، غيابي، حضوري اعتباري)
- Charges and their verdicts
- Sentences (fines, imprisonment, confiscation)
- Legal reasoning

Extract all charges mentioned and their corresponding sentences. Be precise with amounts and legal article numbers."""

        user_prompt = f"""Extract structured information from this court judgment:

{document_text}

Return ONLY valid JSON with this exact structure:
{{
  "case_references": {{
    "court_case_number": "string or null",
    "prosecution_case_number": "string or null",
    "police_report_number": "string or null"
  }},
  "judgment_date": "YYYY-MM-DD or null",
  "judge_name": "string or null",
  "prosecutor_name": "string or null",
  "presence_type": "in_presence|in_absentia|deemed_presence|null",
  "verdict": "guilty|not_guilty|partially_guilty|null",
  "charges": [
    {{
      "charge_number": number,
      "charge_description_ar": "string",
      "article_number": "string or null",
      "law_name_ar": "string or null"
    }},
    ...
  ],
  "sentences": [
    {{
      "sentence_type": "fine|imprisonment|confiscation|deportation",
      "fine_amount": number or null,
      "fine_currency": "QAR",
      "imprisonment_days": number or null,
      "confiscation_items": "string or null",
      "charge_reference": "string (which charge this applies to)"
    }},
    ...
  ],
  "reasoning_summary_ar": "string (brief summary of legal reasoning)"
}}"""

        response = self._call_claude(system_prompt, user_prompt)
        data = self._parse_json_response(response)
        
        # Convert to dataclass
        return JudgmentData(
            case_references=CaseReference(**data.get('case_references', {})),
            charges=[ChargeInfo(**c) for c in data.get('charges', [])] if data.get('charges') else None,
            sentences=data.get('sentences', []),
            **{k: v for k, v in data.items() if k not in ['case_references', 'charges', 'sentences']}
        )
    
    def extract_correspondence(self, document_text: str) -> CorrespondenceData:
        """Extract structured data from correspondence document"""
        
        system_prompt = """You are an expert at extracting information from Arabic legal correspondence (مخاطبة) from Qatar.

Your task is to extract all relevant information, especially:
- Case reference numbers mentioned in the correspondence:
  * Court case numbers (رقم القضية, رقم الدعوى, القضية رقم)
  * Prosecution case numbers (رقم النيابة, النيابة رقم)
  * Police report numbers (رقم البلاغ, البلاغ رقم)
  * Internal reference numbers (رقم داخلي)
- Correspondence details:
  * Correspondence number (رقم المخاطبة)
  * Date (تاريخ)
  * Sender and recipient (المرسل, المرسل إليه)
  * Subject/purpose (الموضوع)
  * Any mentioned dates, names, or case details

Be thorough in finding case references - they may be mentioned anywhere in the text, including in the body, header, or footer."""

        user_prompt = f"""Extract structured information from this correspondence document:

{document_text}

Return ONLY valid JSON with this exact structure:
{{
  "case_references": {{
    "court_case_number": "string or null (extract if mentioned anywhere in text - may be in format like '2025/2552' or 'رقم القضية 2025/2552')",
    "prosecution_case_number": "string or null (extract if mentioned - may be in format like '2025-016-10-4593' or 'رقم النيابة')",
    "police_report_number": "string or null (extract if mentioned - may be in format like '2590/2025' or 'في البلاغ رقم 2590/2025' or 'بلاغ رقم 2590/2025')",
    "internal_report_number": "string or null (extract if mentioned - may be in format like '4308/2025' or 'بلاغ داخلي رقم 4308/2025')"
  }},
  "mentioned_case_numbers": ["array of any case numbers found anywhere in the text"],
  "correspondence_number": "string or null",
  "correspondence_date": "YYYY-MM-DD or null",
  "sender_name": "string or null",
  "sender_organization": "string or null",
  "recipient_name": "string or null",
  "recipient_organization": "string or null",
  "subject_ar": "string or null",
  "correspondence_type": "request|response|notification|report|order|null",
  "content_summary_ar": "string or null",
  "mentioned_case_numbers": ["array of any case numbers found in text"],
  "mentioned_dates": ["array of dates mentioned"]
}}"""

        response = self._call_claude(system_prompt, user_prompt)
        data = self._parse_json_response(response)
        
        # Convert to dataclass
        return CorrespondenceData(
            case_references=CaseReference(**data.get('case_references', {})),
            **{k: v for k, v in data.items() if k != 'case_references'}
        )
    
    def extract_detention_order(self, document_text: str) -> DetentionOrderData:
        """Extract structured data from detention order document"""
        
        system_prompt = """You are an expert at extracting information from Arabic detention orders (أمر حبس احتياطي) from Qatar.

Your task is to extract all relevant information, especially:
- Case reference numbers mentioned in the detention order (may be mentioned anywhere in the text):
  * Court case numbers (رقم القضية, رقم الدعوى, القضية رقم)
  * Prosecution case numbers (رقم النيابة, النيابة رقم)
  * Police report numbers (رقم البلاغ, البلاغ رقم, في البلاغ رقم)
  * Internal reference numbers (رقم داخلي)
- Detention order details:
  * Detention order number (رقم الأمر)
  * Order date (تاريخ الأمر)
  * Detention type (نوع الحبس: احتياطي, بعد المحاكمة, تحقيقي, وقائي)
  * Detention reason (سبب الحبس)
  * Start date and expected end date
  * Detention facility (مكان الحبس)
  * Judge and prosecutor names
  * Detained person information (name, ID, nationality, etc.)
  * Court and circuit information

Be thorough in finding case references - they may be mentioned anywhere in the text, including in the header, body, footer, or within the detention order details. They are critical for linking this detention order to the correct case."""

        user_prompt = f"""Extract structured information from this detention order document:

{document_text}

Return ONLY valid JSON with this exact structure:
{{
  "case_references": {{
    "court_case_number": "string or null (extract if mentioned)",
    "prosecution_case_number": "string or null (extract if mentioned)",
    "police_report_number": "string or null (extract if mentioned)",
    "internal_report_number": "string or null (extract if mentioned)"
  }},
  "detention_order_number": "string or null",
  "order_date": "YYYY-MM-DD or null",
  "detention_type": "pre_trial|post_trial|investigative|protective|null",
  "detention_reason_ar": "string or null",
  "detention_reason_en": "string or null",
  "start_date": "YYYY-MM-DD or null",
  "expected_end_date": "YYYY-MM-DD or null",
  "detention_duration_days": number or null,
  "detention_facility": "string or null",
  "detention_status": "active|released|transferred|null",
  "judge_name": "string or null",
  "prosecutor_name": "string or null",
  "detained_person": {{
    "full_name_ar": "string or null",
    "full_name_en": "string or null",
    "personal_id": "string or null",
    "nationality": "string or null",
    "age": number or null,
    "gender": "string or null"
  }},
  "court_name": "string or null",
  "circuit_name": "string or null",
  "mentioned_case_numbers": ["array of any case numbers found anywhere in the text"]
}}"""

        response = self._call_claude(system_prompt, user_prompt)
        data = self._parse_json_response(response)
        
        # Convert detained_person dict to PersonInfo if present
        detained_person = None
        if data.get('detained_person'):
            detained_person = PersonInfo(**data['detained_person'])
        
        # Convert to dataclass
        return DetentionOrderData(
            case_references=CaseReference(**data.get('case_references', {})),
            detained_person=detained_person,
            **{k: v for k, v in data.items() if k not in ['case_references', 'detained_person']}
        )
    
    def extract_waiver(self, document_text: str) -> WaiverData:
        """Extract structured data from waiver document"""
        
        system_prompt = """You are an expert at extracting information from Arabic waiver documents (تنازل) from Qatar.

Your task is to extract all relevant information, especially:
- Case reference numbers mentioned in the waiver:
  * Court case numbers (رقم القضية, رقم الدعوى)
  * Prosecution case numbers (رقم النيابة)
  * Police report numbers (رقم البلاغ, الرقم)
- Waiver details:
  * Waiver date (تاريخ التنازل)
  * Waiver location (مكان التنازل)
  * Waiver type (نوع التنازل: كامل, جزئي, مشروط)
  * Waiver statement (نص التنازل)
  * Conditions (شروط التنازل)
- Person information:
  * Complainant (الشاكي, المتنازل, المشتكي)
  * Accused person (المتهم, المدعو)
  * Witness (الشاهد)
- Verification:
  * Whether voluntary (طوعي, دون ضغط)
  * Whether under duress (تحت ضغط, أكراه)
- Effect on case:
  * Case status after waiver
  * Charges affected

Be thorough in finding case references - they may be mentioned as "الرقم" or "رقم البلاغ" or similar."""

        user_prompt = f"""Extract structured information from this waiver document:

{document_text}

Return ONLY valid JSON with this exact structure:
{{
  "case_references": {{
    "court_case_number": "string or null (extract if mentioned)",
    "prosecution_case_number": "string or null (extract if mentioned)",
    "police_report_number": "string or null (extract if mentioned - may be mentioned as 'الرقم' or 'رقم البلاغ')",
    "internal_report_number": "string or null (extract if mentioned)"
  }},
  "waiver_date": "YYYY-MM-DD or null",
  "waiver_location": "string or null",
  "waiver_type": "full|partial|conditional|null",
  "waiver_statement_ar": "string or null (full text of waiver statement)",
  "waiver_statement_en": "string or null",
  "waiver_conditions": "string or null",
  "complainant": {{
    "full_name_ar": "string or null",
    "full_name_en": "string or null",
    "personal_id": "string or null",
    "nationality": "string or null",
    "age": number or null,
    "gender": "string or null"
  }},
  "accused_person": {{
    "full_name_ar": "string or null",
    "full_name_en": "string or null",
    "personal_id": "string or null",
    "nationality": "string or null"
  }},
  "witnessed_by_name": "string or null",
  "is_voluntary": true or false,
  "under_duress": true or false,
  "case_status_after": "string or null",
  "charges_affected": ["array of charge descriptions affected by waiver"]
}}"""

        response = self._call_claude(system_prompt, user_prompt)
        data = self._parse_json_response(response)
        
        # Convert person dicts to PersonInfo if present
        complainant = None
        if data.get('complainant'):
            complainant = PersonInfo(**data['complainant'])
        
        accused_person = None
        if data.get('accused_person'):
            accused_person = PersonInfo(**data['accused_person'])
        
        # Convert to dataclass
        return WaiverData(
            case_references=CaseReference(**data.get('case_references', {})),
            complainant=complainant,
            accused_person=accused_person,
            **{k: v for k, v in data.items() if k not in ['case_references', 'complainant', 'accused_person']}
        )
    
    def extract_notification(self, document_text: str) -> NotificationData:
        """Extract structured data from notification document"""
        
        system_prompt = """You are an expert at extracting information from Arabic legal notification documents (إعلان) from Qatar.

Your task is to extract all relevant information, especially:
- Case reference numbers mentioned in the notification:
  * Court case numbers (رقم القضية)
  * Prosecution case numbers (رقم النيابة)
  * Police report numbers (رقم البلاغ, بيانات البلاغ)
- Notification details:
  * Notification number (رقم الإعلان)
  * Notification type (نوع الإعلان: تكليف, إعلان حكم, إعلان جلسة)
  * Issue date (تاريخ الإصدار)
  * Session date and time if applicable (تاريخ الجلسة, وقت الجلسة)
- Recipient information:
  * Person being notified (المتهم, المحكوم عليه, الشاكي)
  * Delivery details (مكان التسليم, طريقة التسليم)
  * Delivery status (تم التسليم, رفض الاستلام, لم يوجد)
- Court information:
  * Court name (المحكمة)
  * Circuit name (الدائرة)
- Charges mentioned
- Serving officer information

Be thorough in finding case references - they are critical for linking this notification to the correct case."""

        user_prompt = f"""Extract structured information from this notification document:

{document_text}

Return ONLY valid JSON with this exact structure:
{{
  "case_references": {{
    "court_case_number": "string or null (extract if mentioned - may be in format like '2025/2552')",
    "prosecution_case_number": "string or null (extract if mentioned)",
    "police_report_number": "string or null (extract if mentioned - may be in 'بيانات البلاغ' field)",
    "internal_report_number": "string or null (extract if mentioned)"
  }},
  "notification_number": "string or null",
  "notification_type": "summons|judgment_notice|hearing_notice|order_notice|null",
  "notification_purpose_ar": "string or null",
  "notification_purpose_en": "string or null",
  "issue_date": "YYYY-MM-DD or null",
  "session_date": "YYYY-MM-DD or null",
  "session_time": "HH:MM or null",
  "recipient": {{
    "full_name_ar": "string or null",
    "full_name_en": "string or null",
    "personal_id": "string or null",
    "nationality": "string or null",
    "age": number or null,
    "gender": "string or null"
  }},
  "delivered_to_name": "string or null (if delivered to someone other than recipient)",
  "delivered_to_relationship": "string or null",
  "delivery_method": "personal|residence|workplace|null",
  "delivery_location": "string or null",
  "delivery_date": "YYYY-MM-DD or null",
  "delivery_status": "delivered|refused|not_found|null",
  "serving_officer_name": "string or null",
  "recipient_signature": true or false,
  "court_name": "string or null",
  "circuit_name": "string or null",
  "charges_mentioned": ["array of charge descriptions mentioned"]
}}"""

        response = self._call_claude(system_prompt, user_prompt)
        data = self._parse_json_response(response)
        
        # Convert recipient dict to PersonInfo if present
        recipient = None
        if data.get('recipient'):
            recipient = PersonInfo(**data['recipient'])
        
        # Convert to dataclass
        return NotificationData(
            case_references=CaseReference(**data.get('case_references', {})),
            recipient=recipient,
            **{k: v for k, v in data.items() if k not in ['case_references', 'recipient']}
        )
    
    def extract_case_transfer(self, document_text: str) -> CaseTransferData:
        """Extract structured data from case transfer order document"""
        
        system_prompt = """You are an expert at extracting information from Arabic case transfer orders (أمر إحالة) from Qatar.

Your task is to extract all relevant information, especially:
- Case reference numbers mentioned in the transfer order (may be mentioned anywhere in the text):
  * Court case numbers (رقم القضية, رقم الدعوى, المقيد برقم)
  * Prosecution case numbers (رقم النيابة, المقيد برقم, سجل الجنح)
  * Police report numbers (رقم البلاغ, في البلاغ رقم, البلاغ رقم)
  * Internal reference numbers (رقم داخلي)
- Transfer order details:
  * Transfer order number (رقم الأمر)
  * Transfer date (تاريخ الأمر)
  * Prosecutor information (وكيل النيابة)
  * Prosecution office (نيابة)
- Accused person information:
  * Name, personal ID, nationality, age, etc.
- Charges being transferred:
  * Charge descriptions
  * Article numbers
  * Law references
- Transfer details:
  * Target court name (المحكمة المختصة)
  * Circuit information
  * Transfer instructions

Be thorough in finding case references - they may be mentioned anywhere in the text, including in the header, body, or within the transfer order details. They are critical for linking this transfer order to the correct case."""

        user_prompt = f"""Extract structured information from this case transfer order document:

{document_text}

Return ONLY valid JSON with this exact structure:
{{
  "case_references": {{
    "court_case_number": "string or null (extract if mentioned anywhere - may be in format like '2025/2552' or 'المقيد برقم 2025/2552')",
    "prosecution_case_number": "string or null (extract if mentioned - may be in format like '303/2025' or 'برقم 303 لسنة 2025م سجل الجنح')",
    "police_report_number": "string or null (extract if mentioned - may be in format like '2590/2025' or 'في البلاغ رقم 2590 لسنة 2025م')",
    "internal_report_number": "string or null (extract if mentioned)"
  }},
  "transfer_order_number": "string or null",
  "transfer_date": "YYYY-MM-DD or null",
  "prosecutor_name": "string or null",
  "prosecutor_title": "string or null",
  "prosecution_office": "string or null",
  "accused_person": {{
    "full_name_ar": "string or null",
    "full_name_en": "string or null",
    "personal_id": "string or null",
    "nationality": "string or null",
    "age": number or null,
    "gender": "string or null",
    "religion": "string or null",
    "occupation": "string or null",
    "area": "string or null"
  }},
  "charges": [
    {{
      "charge_number": number,
      "charge_description_ar": "string",
      "article_number": "string or null",
      "law_name_ar": "string or null",
      "law_year": "string or null"
    }}
  ],
  "transfer_reason_ar": "string or null",
  "transfer_reason_en": "string or null",
  "target_court_name": "string or null",
  "target_circuit_name": "string or null",
  "transfer_instructions_ar": "string or null",
  "transfer_instructions_en": "string or null",
  "mentioned_case_numbers": ["array of any case numbers found anywhere in the text"],
  "mentioned_dates": ["array of dates mentioned"]
}}"""

        response = self._call_claude(system_prompt, user_prompt)
        data = self._parse_json_response(response)
        
        # Convert accused_person dict to PersonInfo if present
        accused_person = None
        if data.get('accused_person'):
            accused_person = PersonInfo(**data['accused_person'])
        
        # Convert charges to ChargeInfo if present
        charges = None
        if data.get('charges'):
            charges = [ChargeInfo(**c) for c in data['charges']]
        
        # Convert to dataclass
        return CaseTransferData(
            case_references=CaseReference(**data.get('case_references', {})),
            accused_person=accused_person,
            charges=charges,
            **{k: v for k, v in data.items() if k not in ['case_references', 'accused_person', 'charges']}
        )
    
    def classify_and_extract(self, document_text: str) -> Dict[str, Any]:
        """
        First classify the document type, then extract appropriate data
        This is a two-step process for better accuracy
        """
        
        # Step 1: Classify document type
        classification_prompt = """You are an expert at classifying Arabic legal documents from Qatar.

Analyze the document and determine its type from these options:
1. court_session - محضر جلسة (Court session minutes)
2. police_report - بلاغ (Police report)
3. investigation - محضر تحقيق (Investigation record)
4. judgment - حكم (Court judgment)
5. case_transfer - أمر إحالة (Case transfer order)
6. notification - إعلان (Legal notification)
7. detention_order - حبس احتياطي (Detention order)
8. waiver - تنازل (Complaint waiver)
9. lab_result - نتيجة فحص (Lab result)
10. correspondence - مخاطبة (Correspondence)

Return ONLY the type ID (e.g., "court_session") and a confidence score (0-100).

Document to classify:
{text}

Return format: {{"type": "document_type", "confidence": 95}}"""

        classification_response = self._call_claude(
            "You are a document classifier.",
            classification_prompt.format(text=document_text[:2000])  # First 2000 chars for classification
        )
        
        classification = self._parse_json_response(classification_response)
        doc_type = classification.get('type')
        confidence = classification.get('confidence', 0)
        
        logger.info(f"Document classified as: {doc_type} (confidence: {confidence}%)")
        
        # Step 2: Extract based on type
        if doc_type == 'court_session':
            extracted_data = self.extract_court_session(document_text)
        elif doc_type == 'police_report':
            extracted_data = self.extract_police_report(document_text)
        elif doc_type == 'investigation':
            extracted_data = self.extract_investigation(document_text)
        elif doc_type == 'judgment':
            extracted_data = self.extract_judgment(document_text)
        elif doc_type == 'correspondence':
            extracted_data = self.extract_correspondence(document_text)
        elif doc_type == 'detention_order':
            extracted_data = self.extract_detention_order(document_text)
        elif doc_type == 'waiver':
            extracted_data = self.extract_waiver(document_text)
        elif doc_type == 'notification':
            extracted_data = self.extract_notification(document_text)
        elif doc_type == 'case_transfer':
            extracted_data = self.extract_case_transfer(document_text)
        else:
            # Generic extraction for other types
            extracted_data = self._generic_extract(document_text, doc_type)
        
        return {
            'document_type': doc_type,
            'confidence': confidence,
            'extracted_data': extracted_data
        }
    
    def _call_claude(self, system_prompt: str, user_prompt: str) -> str:
        """Make API call to Claude"""
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": user_prompt
                }]
            )
            return message.content[0].text
        except Exception as e:
            logger.error(f"Error calling Claude API: {str(e)}")
            raise
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON from Claude's response"""
        try:
            # Remove markdown code blocks if present
            if '```json' in response:
                response = response.split('```json')[1].split('```')[0]
            elif '```' in response:
                response = response.split('```')[1].split('```')[0]
            
            return json.loads(response.strip())
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {str(e)}")
            logger.error(f"Response was: {response}")
            raise
    
    def _generic_extract(self, document_text: str, doc_type: str) -> Dict[str, Any]:
        """Generic extraction for document types without specific handlers"""
        
        system_prompt = f"""You are an expert at extracting information from Arabic legal documents.
This document is of type: {doc_type}.

Extract as much structured information as possible, focusing on:
- Case reference numbers
- Dates and times
- Person names and roles
- Key facts and decisions
- Legal references"""

        user_prompt = f"""Extract all relevant information from this document:

{document_text}

Return as JSON with appropriate fields based on the document content."""

        response = self._call_claude(system_prompt, user_prompt)
        return self._parse_json_response(response)


# ============================================================================
# INTEGRATED PIPELINE WITH AI EXTRACTION
# ============================================================================

class AIDocumentProcessor:
    """Document processor using AI extraction with intelligent case matching"""
    
    def __init__(self, anthropic_api_key: str, db_config: Dict[str, str], storage_path: str):
        """
        Initialize AI-powered document processor
        
        Args:
            anthropic_api_key: Anthropic API key for Claude
            db_config: Database configuration
            storage_path: Path for document storage
        """
        self.extractor = AIDocumentExtractor(api_key=anthropic_api_key)
        self.db_config = db_config
        self.storage_path = Path(storage_path) if isinstance(storage_path, str) else storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        logger.info("AI Document Processor initialized")
    
    def process_document(self, file_path: str) -> Dict[str, Any]:
        """
        Process document using AI extraction
        
        Args:
            file_path: Path to document file
        
        Returns:
            Processing results with extracted data
        """
        logger.info(f"Processing document with AI: {file_path}")
        
        try:
            # Load document
            with open(file_path, 'r', encoding='utf-8') as f:
                document_text = f.read()
            
            # AI extraction
            result = self.extractor.classify_and_extract(document_text)
            
            logger.info(f"Extraction complete: {result['document_type']} (confidence: {result['confidence']}%)")
            
            # Store in database (using intelligent case matching)
            from database_manager import DatabaseManager
            from case_matcher import CaseReferences, SmartCaseProcessor
            
            with DatabaseManager(**self.db_config) as db:
                # Extract case references from extracted data
                extracted = result['extracted_data']
                references = CaseReferences()
                
                # Handle both dataclass and dict formats
                if hasattr(extracted, 'case_references'):
                    # Dataclass format (court_session, police_report, investigation, judgment, correspondence)
                    refs = extracted.case_references
                    references.court_case_number = refs.court_case_number
                    references.prosecution_case_number = refs.prosecution_case_number
                    references.police_report_number = refs.police_report_number
                    references.internal_report_number = refs.internal_report_number if hasattr(refs, 'internal_report_number') else None
                elif isinstance(extracted, dict) and 'case_references' in extracted:
                    # Dict format from generic extraction
                    refs = extracted['case_references']
                    references.court_case_number = refs.get('court_case_number')
                    references.prosecution_case_number = refs.get('prosecution_case_number')
                    references.police_report_number = refs.get('police_report_number')
                    references.internal_report_number = refs.get('internal_report_number')
                elif isinstance(extracted, dict):
                    # Try to find case references at top level (fallback)
                    references.court_case_number = extracted.get('court_case_number')
                    references.prosecution_case_number = extracted.get('prosecution_case_number')
                    references.police_report_number = extracted.get('police_report_number')
                    references.internal_report_number = extracted.get('internal_report_number')
                    
                    # Also check mentioned_case_numbers for correspondence, detention_order, etc.
                    if 'mentioned_case_numbers' in extracted and extracted['mentioned_case_numbers']:
                        logger.info(f"Found mentioned case numbers: {extracted['mentioned_case_numbers']}")
                        # Try to extract from mentioned numbers if no direct references found
                        if not references.has_any_reference():
                            for mentioned in extracted['mentioned_case_numbers']:
                                # Try to identify type by pattern
                                if 'قضية' in mentioned or 'دعوى' in mentioned:
                                    references.court_case_number = mentioned
                                elif 'نيابة' in mentioned:
                                    references.prosecution_case_number = mentioned
                                elif 'بلاغ' in mentioned:
                                    references.police_report_number = mentioned
                                elif 'داخلي' in mentioned:
                                    references.internal_report_number = mentioned
                
                # Prepare document metadata
                document_metadata = self._prepare_metadata(result['document_type'], extracted)
                
                # Use intelligent case matcher
                case_processor = SmartCaseProcessor(db)
                
                # Log references being searched
                available_refs = references.get_available_references()
                logger.info(f"Searching for case with references: {available_refs}")
                
                case_result = case_processor.process_document_intelligently(
                    references=references,
                    document_type=result['document_type'],
                    document_data=extracted,
                    document_metadata=document_metadata
                )
                
                case_id = case_result['case_id']
                
                # Ensure transaction is committed so next document can find this case
                db.commit()
                
                logger.info(f"Case ID determined: {case_id} (action: {case_result.get('action', 'unknown')})")
                
                if not case_result['sequence_valid']:
                    logger.warning("Document sequence validation failed - unusual order detected")
                
                # Store document file
                import os
                import hashlib
                import uuid
                import shutil
                
                # Calculate file hash
                with open(file_path, 'rb') as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()
                
                # Generate unique filename and copy to storage
                ext = os.path.splitext(file_path)[1]
                stored_filename = f"{uuid.uuid4()}{ext}"
                dest_path = self.storage_path / stored_filename
                shutil.copy2(file_path, dest_path)
                
                # Extract document date
                document_date = self._extract_document_date(extracted)
                
                # Store document record
                document_data = {
                    'case_id': case_id,
                    'document_type': result['document_type'],
                    'original_filename': os.path.basename(file_path),
                    'stored_filename': stored_filename,
                    'file_path': str(dest_path),
                    'file_hash': file_hash,
                    'raw_text': document_text,
                    'primary_language': 'ar',
                    'processing_status': 'processed',
                    'received_date': datetime.now(),
                    'document_date': document_date
                }
                
                document_id = db.insert_document(document_data)
                
                # Store extracted structured data
                self._store_structured_data(db, case_id, document_id, result)
                
                # Get case completeness
                completeness = case_processor.get_case_completeness(case_id)
                
                return {
                    'success': True,
                    'case_id': case_id,
                    'document_id': document_id,
                    'document_type': result['document_type'],
                    'confidence': result['confidence'],
                    'case_action': case_result['action'],  # 'found' or 'created'
                    'sequence_valid': case_result['sequence_valid'],
                    'completeness': completeness,
                    'extracted_data': asdict(extracted) if hasattr(extracted, '__dataclass_fields__') else extracted
                }
        
        except Exception as e:
            logger.error(f"Error processing document: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def _prepare_metadata(self, doc_type: str, extracted_data: Any) -> Dict[str, Any]:
        """Prepare document metadata for case creation/update and alternative matching"""
        metadata = {}
        
        if doc_type == 'police_report' and isinstance(extracted_data, PoliceReportData):
            metadata['incident_date'] = extracted_data.incident_date
            metadata['report_date'] = extracted_data.report_date
            metadata['police_station'] = extracted_data.police_station
            # Add person info for alternative matching
            if extracted_data.complainant:
                metadata['complainant'] = asdict(extracted_data.complainant)
            if extracted_data.accused:
                metadata['accused_person'] = asdict(extracted_data.accused)
        
        elif doc_type == 'investigation' and isinstance(extracted_data, InvestigationData):
            metadata['prosecution_office'] = 'نيابة الشمال'  # Could extract this too
            metadata['investigation_date'] = extracted_data.investigation_date
            # Add person info for alternative matching
            if extracted_data.subject_person:
                metadata['subject_person'] = asdict(extracted_data.subject_person)
        
        elif doc_type == 'correspondence' and isinstance(extracted_data, CorrespondenceData):
            # Correspondence might have dates but usually doesn't set case dates
            # The case references are what matter for linking
            metadata['correspondence_date'] = extracted_data.correspondence_date
        
        elif doc_type == 'detention_order' and isinstance(extracted_data, DetentionOrderData):
            # Detention orders might have dates that could update case metadata
            if extracted_data.start_date:
                metadata['case_opened_date'] = extracted_data.start_date
            if extracted_data.order_date:
                metadata['incident_date'] = extracted_data.order_date  # Use order date as fallback
            # Add person info for alternative matching
            if extracted_data.detained_person:
                metadata['detained_person'] = asdict(extracted_data.detained_person)
        
        elif doc_type == 'waiver' and isinstance(extracted_data, WaiverData):
            metadata['waiver_date'] = extracted_data.waiver_date
            # Add person info for alternative matching
            if extracted_data.complainant:
                metadata['complainant'] = asdict(extracted_data.complainant)
            if extracted_data.accused_person:
                metadata['accused_person'] = asdict(extracted_data.accused_person)
        
        elif doc_type == 'notification' and isinstance(extracted_data, NotificationData):
            metadata['issue_date'] = extracted_data.issue_date
            # Add person info for alternative matching
            if extracted_data.recipient:
                metadata['accused_person'] = asdict(extracted_data.recipient)  # Usually accused
        
        elif doc_type == 'case_transfer' and isinstance(extracted_data, CaseTransferData):
            metadata['transfer_date'] = extracted_data.transfer_date
            metadata['prosecution_office'] = extracted_data.prosecution_office
            # Add person info for alternative matching
            if extracted_data.accused_person:
                metadata['accused_person'] = asdict(extracted_data.accused_person)
        
        elif doc_type == 'court_session' and isinstance(extracted_data, CourtSessionData):
            metadata['session_date'] = extracted_data.session_date
        
        elif doc_type == 'judgment' and isinstance(extracted_data, JudgmentData):
            metadata['judgment_date'] = extracted_data.judgment_date
        
        return metadata
    
    def _extract_document_date(self, extracted_data: Any) -> Optional[str]:
        """Extract primary date from document"""
        date_fields = ['judgment_date', 'session_date', 'investigation_date', 
                      'report_date', 'incident_date', 'correspondence_date', 
                      'order_date', 'start_date', 'waiver_date', 'issue_date', 
                      'transfer_date']
        
        for field in date_fields:
            if hasattr(extracted_data, field):
                date_val = getattr(extracted_data, field)
                if date_val:
                    return date_val
            elif isinstance(extracted_data, dict) and field in extracted_data:
                date_val = extracted_data[field]
                if date_val:
                    return date_val
        return None
    
    def _store_structured_data(self, db, case_id: int, document_id: int, result: Dict[str, Any]):
        """Store AI-extracted data in database"""
        
        doc_type = result['document_type']
        data = result['extracted_data']
        
        if doc_type == 'court_session' and isinstance(data, CourtSessionData):
            self._store_court_session(db, case_id, document_id, data)
        
        elif doc_type == 'police_report' and isinstance(data, PoliceReportData):
            self._store_police_report(db, case_id, document_id, data)
        
        elif doc_type == 'investigation' and isinstance(data, InvestigationData):
            self._store_investigation(db, case_id, document_id, data)
        
        elif doc_type == 'judgment' and isinstance(data, JudgmentData):
            self._store_judgment(db, case_id, document_id, data)
        
        elif doc_type == 'correspondence' and isinstance(data, CorrespondenceData):
            self._store_correspondence(db, case_id, document_id, data)
        
        elif doc_type == 'detention_order' and isinstance(data, DetentionOrderData):
            self._store_detention_order(db, case_id, document_id, data)
        
        elif doc_type == 'waiver' and isinstance(data, WaiverData):
            self._store_waiver(db, case_id, document_id, data)
        
        elif doc_type == 'notification' and isinstance(data, NotificationData):
            self._store_notification(db, case_id, document_id, data)
        
        elif doc_type == 'case_transfer' and isinstance(data, CaseTransferData):
            self._store_case_transfer(db, case_id, document_id, data)
    
    def _store_court_session(self, db, case_id: int, document_id: int, data: CourtSessionData):
        """Store court session data"""
        session_data = {
            'session_date': data.session_date,
            'session_time': data.session_time,
            'decision_ar': data.decision_ar,
            'decision_type': data.decision_type,
            'next_session_date': data.next_session_date,
            'accused_present': data.accused_present,
            'court_name': data.court_name,
            'circuit_name': data.circuit_name,
            'session_status': 'held'
        }
        
        session_id = db.insert_court_session(case_id, session_data)
        
        # Link parties
        if data.judge_name:
            judge_id = db.get_or_create_party({'full_name_ar': data.judge_name})
            db.link_party_to_case(case_id, judge_id, 'judge')
        
        if data.prosecutor_name:
            prosecutor_id = db.get_or_create_party({'full_name_ar': data.prosecutor_name})
            db.link_party_to_case(case_id, prosecutor_id, 'prosecutor')
        
        if data.secretary_name:
            secretary_id = db.get_or_create_party({'full_name_ar': data.secretary_name})
            db.link_party_to_case(case_id, secretary_id, 'secretary')
        
        # Add event
        db.add_case_event(case_id, {
            'event_type': 'court_hearing',
            'event_date': data.session_date,
            'event_description_ar': f"جلسة محكمة: {data.decision_ar or ''}",
            'related_session_id': session_id,
            'related_document_id': document_id
        })
    
    def _store_police_report(self, db, case_id: int, document_id: int, data: PoliceReportData):
        """Store police report data"""
        # Update case (case matcher already handles this, but ensure dates are set)
        updates = {}
        if data.incident_date:
            updates['incident_date'] = data.incident_date
        if data.report_date:
            updates['report_date'] = data.report_date
        if data.police_station:
            updates['police_station'] = data.police_station
        if updates:
            db.update_case(case_id, updates)
        
        # Link complainant
        if data.complainant:
            complainant_dict = asdict(data.complainant)
            complainant_dict = {k: v for k, v in complainant_dict.items() if v is not None}
            complainant_id = db.get_or_create_party(complainant_dict)
            db.link_party_to_case(case_id, complainant_id, 'complainant')
        
        # Link accused
        if data.accused:
            accused_dict = asdict(data.accused)
            accused_dict = {k: v for k, v in accused_dict.items() if v is not None}
            accused_id = db.get_or_create_party(accused_dict)
            db.link_party_to_case(case_id, accused_id, 'accused')
        
        # Add incident event
        if data.incident_date:
            db.add_case_event(case_id, {
                'event_type': 'incident',
                'event_date': data.incident_date,
                'event_time': data.incident_time,
                'event_description_ar': data.incident_description_ar,
                'event_location': data.incident_location,
                'related_document_id': document_id
            })
        
        # Add report filed event
        if data.report_date:
            report_num = data.case_references.police_report_number if hasattr(data.case_references, 'police_report_number') else None
            db.add_case_event(case_id, {
                'event_type': 'report_filed',
                'event_date': data.report_date,
                'event_description_ar': f"تم تقديم بلاغ رقم {report_num or ''}",
                'related_document_id': document_id
            })
    
    def _store_investigation(self, db, case_id: int, document_id: int, data: InvestigationData):
        """Store investigation data"""
        # Link subject person
        if data.subject_person:
            subject_dict = asdict(data.subject_person)
            subject_dict = {k: v for k, v in subject_dict.items() if v is not None}
            subject_id = db.get_or_create_party(subject_dict)
            
            # Store statement
            import json
            statement_data = {
                'statement_type': 'interrogation',
                'statement_date': data.investigation_date,
                'statement_time': data.investigation_time,
                'oath_taken': data.oath_taken,
                'is_confession': data.confession_made,
                'document_id': document_id,
                'statement_text_ar': json.dumps(data.questions_answers, ensure_ascii=False) if data.questions_answers else None
            }
            db.insert_statement(case_id, subject_id, statement_data)
        
        # Store charges
        if data.charges_presented:
            for charge in data.charges_presented:
                charge_dict = asdict(charge)
                charge_dict['charge_status'] = 'pending'
                db.insert_charge(case_id, charge_dict)
        
        # Add event
        if data.investigation_date:
            db.add_case_event(case_id, {
                'event_type': 'investigation',
                'event_date': data.investigation_date,
                'event_description_ar': 'تحقيق النيابة العامة',
                'related_document_id': document_id
            })
    
    def _store_judgment(self, db, case_id: int, document_id: int, data: JudgmentData):
        """Store judgment data"""
        from psycopg2.extras import RealDictCursor
        
        # Insert judgment
        judgment_data = {
            'case_id': case_id,
            'judgment_date': data.judgment_date,
            'presence_type': data.presence_type,
            'verdict': data.verdict,
            'is_final': True,
            'judgment_reasoning_ar': data.reasoning_summary_ar
        }
        
        with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            fields = [k for k, v in judgment_data.items() if v is not None]
            values = [judgment_data[k] for k in fields]
            placeholders = ', '.join(['%s'] * len(fields))
            sql = f"""
                INSERT INTO judgments ({', '.join(fields)})
                VALUES ({placeholders})
                RETURNING judgment_id
            """
            cursor.execute(sql, values)
            db.connection.commit()
            judgment_id = cursor.fetchone()['judgment_id']
        
        # Insert sentences
        if data.sentences:
            # Valid columns in sentences table
            valid_sentence_columns = {
                'judgment_id', 'charge_id', 'sentence_number', 'sentence_type',
                'fine_amount', 'fine_currency', 'imprisonment_duration_days',
                'imprisonment_type', 'confiscation_items', 'deportation_ordered',
                'license_suspended', 'license_suspension_duration_days',
                'sentence_description_ar', 'sentence_description_en'
            }
            
            for sentence in data.sentences:
                # Convert sentence dict and filter invalid columns
                sentence_data = {}
                
                # Map charge_reference to charge_id if we can find it
                # For now, we'll skip charge_reference since we'd need to lookup charge_id
                # charge_id can be NULL, so it's fine to omit it
                
                # Map imprisonment_days to imprisonment_duration_days
                if 'imprisonment_days' in sentence:
                    sentence_data['imprisonment_duration_days'] = sentence['imprisonment_days']
                
                # Copy other valid fields
                for key, value in sentence.items():
                    if key in valid_sentence_columns and value is not None:
                        sentence_data[key] = value
                    elif key not in ['charge_reference', 'imprisonment_days']:  # Skip invalid fields
                        # Try to map common variations
                        if key == 'imprisonment_duration' and 'imprisonment_duration_days' not in sentence_data:
                            sentence_data['imprisonment_duration_days'] = value
                
                # Add judgment_id
                sentence_data['judgment_id'] = judgment_id
                
                # Only insert if we have valid data
                if len(sentence_data) > 1:  # More than just judgment_id
                    sentence_fields = [k for k, v in sentence_data.items() if v is not None]
                    sentence_values = [sentence_data[k] for k in sentence_fields]
                    
                    with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                        placeholders = ', '.join(['%s'] * len(sentence_fields))
                        sql = f"""
                            INSERT INTO sentences ({', '.join(sentence_fields)})
                            VALUES ({placeholders})
                        """
                        cursor.execute(sql, sentence_values)
                        db.connection.commit()
        
        # Update case status
        if data.judgment_date:
            db.update_case(case_id, {
                'current_status': 'closed',
                'case_closed_date': data.judgment_date,
                'final_judgment_date': data.judgment_date
            })
        
        # Add judgment event
        if data.judgment_date:
            db.add_case_event(case_id, {
                'event_type': 'judgment',
                'event_date': data.judgment_date,
                'event_description_ar': 'صدور الحكم',
                'related_document_id': document_id
            })
    
    def _store_correspondence(self, db, case_id: int, document_id: int, data: CorrespondenceData):
        """Store correspondence data"""
        from psycopg2.extras import RealDictCursor
        
        # Insert correspondence record
        # Map to database schema: from_person, from_organization, to_person, to_organization
        correspondence_data = {
            'case_id': case_id,
            'correspondence_number': data.correspondence_number,
            'correspondence_date': data.correspondence_date,
            'from_person': data.sender_name,  # Map sender_name to from_person
            'from_organization': data.sender_organization,  # Map sender_organization to from_organization
            'to_person': data.recipient_name,  # Map recipient_name to to_person
            'to_organization': data.recipient_organization,  # Map recipient_organization to to_organization
            'subject_ar': data.subject_ar,
            'correspondence_type': data.correspondence_type,
            'body_ar': data.content_summary_ar,  # Map content_summary_ar to body_ar
            'document_id': document_id
        }
        
        with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            fields = [k for k, v in correspondence_data.items() if v is not None]
            values = [correspondence_data[k] for k in fields]
            placeholders = ', '.join(['%s'] * len(fields))
            
            sql = f"""
                INSERT INTO correspondence ({', '.join(fields)})
                VALUES ({placeholders})
                RETURNING correspondence_id
            """
            cursor.execute(sql, values)
            db.connection.commit()
            correspondence_id = cursor.fetchone()['correspondence_id']
        
        # Add correspondence event
        if data.correspondence_date:
            event_desc = f"مخاطبة: {data.subject_ar or data.correspondence_number or ''}"
            db.add_case_event(case_id, {
                'event_type': 'correspondence',
                'event_date': data.correspondence_date,
                'event_description_ar': event_desc,
                'related_document_id': document_id
            })
        
        logger.info(f"Stored correspondence: {correspondence_id} for case {case_id}")
    
    def _store_detention_order(self, db, case_id: int, document_id: int, data: DetentionOrderData):
        """Store detention order data"""
        from psycopg2.extras import RealDictCursor
        
        # Link detained person if available
        detained_party_id = None
        if data.detained_person:
            detained_dict = asdict(data.detained_person)
            detained_dict = {k: v for k, v in detained_dict.items() if v is not None}
            detained_party_id = db.get_or_create_party(detained_dict)
            db.link_party_to_case(case_id, detained_party_id, 'accused')
        
        # Note: detention_records table requires party_id, so create placeholder if needed
        if not detained_party_id:
            logger.warning("No detained person found in detention order, creating placeholder")
            detained_party_id = db.get_or_create_party({'full_name_ar': 'غير محدد'})
        
        # Link judge if available (for ordered_by_party_id)
        ordered_by_party_id = None
        if data.judge_name:
            judge_id = db.get_or_create_party({'full_name_ar': data.judge_name})
            db.link_party_to_case(case_id, judge_id, 'judge')
            ordered_by_party_id = judge_id
        
        # Link prosecutor if available
        if data.prosecutor_name:
            prosecutor_id = db.get_or_create_party({'full_name_ar': data.prosecutor_name})
            db.link_party_to_case(case_id, prosecutor_id, 'prosecutor')
        
        # Insert detention record (matching schema field names)
        # Handle required NOT NULL fields: order_date and start_date
        if not data.order_date:
            logger.warning("Detention order missing order_date, using start_date or current date")
            data.order_date = data.start_date or datetime.now().strftime('%Y-%m-%d')
        
        if not data.start_date:
            logger.warning("Detention order missing start_date, using order_date or current date")
            data.start_date = data.order_date or datetime.now().strftime('%Y-%m-%d')
        
        detention_data = {
            'case_id': case_id,
            'party_id': detained_party_id,
            'order_number': data.detention_order_number,  # Schema uses order_number
            'order_date': data.order_date,  # Required NOT NULL
            'ordered_by_party_id': ordered_by_party_id,
            'detention_type': data.detention_type,
            'detention_reason_ar': data.detention_reason_ar,
            'detention_reason_en': data.detention_reason_en,
            'start_date': data.start_date,  # Required NOT NULL
            'scheduled_end_date': data.expected_end_date,  # Schema uses scheduled_end_date
            'duration_days': data.detention_duration_days,  # Schema uses duration_days
            'detention_facility': data.detention_facility,
            'detention_status': data.detention_status or 'active'
        }
        
        with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            fields = [k for k, v in detention_data.items() if v is not None]
            values = [detention_data[k] for k in fields]
            placeholders = ', '.join(['%s'] * len(fields))
            
            sql = f"""
                INSERT INTO detention_records ({', '.join(fields)})
                VALUES ({placeholders})
                RETURNING detention_id
            """
            cursor.execute(sql, values)
            db.connection.commit()
            detention_id = cursor.fetchone()['detention_id']
        
        # Add detention event
        if data.order_date:
            event_desc = f"أمر حبس احتياطي: {data.detention_reason_ar or data.detention_type or ''}"
            db.add_case_event(case_id, {
                'event_type': 'detention_ordered',
                'event_date': data.order_date,
                'event_description_ar': event_desc,
                'related_document_id': document_id
            })
        
        logger.info(f"Stored detention order: {detention_id} for case {case_id}")
    
    def _store_waiver(self, db, case_id: int, document_id: int, data: WaiverData):
        """Store waiver data"""
        from psycopg2.extras import RealDictCursor
        
        # Link complainant if available (required field)
        complainant_party_id = None
        if data.complainant:
            complainant_dict = asdict(data.complainant)
            complainant_dict = {k: v for k, v in complainant_dict.items() if v is not None}
            complainant_party_id = db.get_or_create_party(complainant_dict)
            db.link_party_to_case(case_id, complainant_party_id, 'complainant')
        
        # Note: waivers table requires complainant_party_id, so create placeholder if needed
        if not complainant_party_id:
            logger.warning("No complainant found in waiver, creating placeholder")
            complainant_party_id = db.get_or_create_party({'full_name_ar': 'غير محدد'})
        
        # Link accused person if available
        if data.accused_person:
            accused_dict = asdict(data.accused_person)
            accused_dict = {k: v for k, v in accused_dict.items() if v is not None}
            accused_id = db.get_or_create_party(accused_dict)
            db.link_party_to_case(case_id, accused_id, 'accused')
        
        # Link witness if available
        witnessed_by_party_id = None
        if data.witnessed_by_name:
            witness_id = db.get_or_create_party({'full_name_ar': data.witnessed_by_name})
            db.link_party_to_case(case_id, witness_id, 'witness')
            witnessed_by_party_id = witness_id
        
        # Insert waiver record
        waiver_data = {
            'case_id': case_id,
            'complainant_party_id': complainant_party_id,
            'waiver_date': data.waiver_date,
            'waiver_location': data.waiver_location,
            'waiver_type': data.waiver_type,
            'waiver_statement_ar': data.waiver_statement_ar,
            'waiver_statement_en': data.waiver_statement_en,
            'waiver_conditions': data.waiver_conditions,
            'witnessed_by_party_id': witnessed_by_party_id,
            'is_voluntary': data.is_voluntary,
            'under_duress': data.under_duress,
            'case_status_after': data.case_status_after,
            'charges_affected': ', '.join(data.charges_affected) if data.charges_affected else None,
            'document_id': document_id
        }
        
        with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            fields = [k for k, v in waiver_data.items() if v is not None]
            values = [waiver_data[k] for k in fields]
            placeholders = ', '.join(['%s'] * len(fields))
            
            sql = f"""
                INSERT INTO waivers ({', '.join(fields)})
                VALUES ({placeholders})
                RETURNING waiver_id
            """
            cursor.execute(sql, values)
            db.connection.commit()
            waiver_id = cursor.fetchone()['waiver_id']
        
        # Add waiver event
        if data.waiver_date:
            event_desc = f"تنازل عن الشكوى: {data.waiver_type or 'تنازل'}"
            db.add_case_event(case_id, {
                'event_type': 'waiver',
                'event_date': data.waiver_date,
                'event_description_ar': event_desc,
                'related_document_id': document_id
            })
        
        # Update case status if specified
        if data.case_status_after:
            db.update_case(case_id, {
                'current_status': data.case_status_after
            })
        
        logger.info(f"Stored waiver: {waiver_id} for case {case_id}")
    
    def _store_notification(self, db, case_id: int, document_id: int, data: NotificationData):
        """Store notification data"""
        from psycopg2.extras import RealDictCursor
        
        # Handle required NOT NULL field: issue_date
        if not data.issue_date:
            logger.warning("Notification missing issue_date, using session_date or current date")
            data.issue_date = data.session_date or datetime.now().strftime('%Y-%m-%d')
        
        # Link recipient if available (required field)
        recipient_party_id = None
        if data.recipient:
            recipient_dict = asdict(data.recipient)
            recipient_dict = {k: v for k, v in recipient_dict.items() if v is not None}
            recipient_party_id = db.get_or_create_party(recipient_dict)
            # Link as appropriate role (usually 'accused' for notifications)
            db.link_party_to_case(case_id, recipient_party_id, 'accused')
        
        # Note: notifications table requires recipient_party_id, so create placeholder if needed
        if not recipient_party_id:
            logger.warning("No recipient found in notification, creating placeholder")
            recipient_party_id = db.get_or_create_party({'full_name_ar': 'غير محدد'})
        
        # Link serving officer if available
        serving_officer_party_id = None
        if data.serving_officer_name:
            officer_id = db.get_or_create_party({'full_name_ar': data.serving_officer_name})
            serving_officer_party_id = officer_id
        
        # Link delivered_to person if different from recipient
        delivered_to_party_id = None
        if data.delivered_to_name and data.delivered_to_name != (data.recipient.full_name_ar if data.recipient else None):
            delivered_id = db.get_or_create_party({'full_name_ar': data.delivered_to_name})
            delivered_to_party_id = delivered_id
        
        # Find session_id if session_date matches an existing session
        session_id = None
        if data.session_date:
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT session_id FROM court_sessions 
                    WHERE case_id = %s AND session_date = %s 
                    LIMIT 1
                """, (case_id, data.session_date))
                result = cursor.fetchone()
                if result:
                    session_id = result['session_id']
        
        # Insert notification record
        notification_data = {
            'case_id': case_id,
            'recipient_party_id': recipient_party_id,
            'notification_number': data.notification_number,
            'notification_type': data.notification_type,
            'notification_purpose_ar': data.notification_purpose_ar,
            'notification_purpose_en': data.notification_purpose_en,
            'session_date': data.session_date,
            'session_id': session_id,
            'issue_date': data.issue_date,
            'delivery_method': data.delivery_method,
            'delivery_location': data.delivery_location,
            'delivery_date': data.delivery_date,
            'delivered_to_party_id': delivered_to_party_id,
            'delivered_to_name': data.delivered_to_name,
            'delivered_to_relationship': data.delivered_to_relationship,
            'delivery_status': data.delivery_status,
            'serving_officer_party_id': serving_officer_party_id,
            'recipient_signature': data.recipient_signature
        }
        
        with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            fields = [k for k, v in notification_data.items() if v is not None]
            values = [notification_data[k] for k in fields]
            placeholders = ', '.join(['%s'] * len(fields))
            
            sql = f"""
                INSERT INTO notifications ({', '.join(fields)})
                VALUES ({placeholders})
                RETURNING notification_id
            """
            cursor.execute(sql, values)
            db.connection.commit()
            notification_id = cursor.fetchone()['notification_id']
        
        # Add notification event
        if data.issue_date:
            event_desc = f"إعلان: {data.notification_type or data.notification_purpose_ar or 'إعلان'}"
            if data.session_date:
                event_desc += f" - جلسة {data.session_date}"
            db.add_case_event(case_id, {
                'event_type': 'notification',
                'event_date': data.issue_date,
                'event_description_ar': event_desc,
                'related_document_id': document_id
            })
        
        logger.info(f"Stored notification: {notification_id} for case {case_id}")
    
    def _store_case_transfer(self, db, case_id: int, document_id: int, data: CaseTransferData):
        """Store case transfer order data"""
        from psycopg2.extras import RealDictCursor
        
        # Link accused person if available
        if data.accused_person:
            accused_dict = asdict(data.accused_person)
            accused_dict = {k: v for k, v in accused_dict.items() if v is not None}
            accused_id = db.get_or_create_party(accused_dict)
            db.link_party_to_case(case_id, accused_id, 'accused')
        
        # Link prosecutor if available
        if data.prosecutor_name:
            prosecutor_dict = {'full_name_ar': data.prosecutor_name}
            if data.prosecutor_title:
                prosecutor_dict['occupation'] = data.prosecutor_title
            prosecutor_id = db.get_or_create_party(prosecutor_dict)
            db.link_party_to_case(case_id, prosecutor_id, 'prosecutor')
        
        # Store charges if available
        if data.charges:
            for charge in data.charges:
                charge_dict = asdict(charge)
                charge_dict['charge_status'] = 'pending'
                db.insert_charge(case_id, charge_dict)
        
        # Update case with transfer information
        case_updates = {}
        if data.target_court_name:
            case_updates['court_name'] = data.target_court_name
        if data.target_circuit_name:
            case_updates['circuit_name'] = data.target_circuit_name
        if data.prosecution_office:
            case_updates['prosecution_office'] = data.prosecution_office
        if data.transfer_date:
            case_updates['case_opened_date'] = data.transfer_date
            case_updates['current_status'] = 'in_trial'
        
        if case_updates:
            db.update_case(case_id, case_updates)
        
        # Add case transfer event
        if data.transfer_date:
            event_desc = f"أمر إحالة: إحالة الدعوى إلى {data.target_court_name or 'المحكمة المختصة'}"
            if data.transfer_order_number:
                event_desc += f" (رقم الأمر: {data.transfer_order_number})"
            db.add_case_event(case_id, {
                'event_type': 'case_transferred',
                'event_date': data.transfer_date,
                'event_description_ar': event_desc,
                'related_document_id': document_id
            })
        
        logger.info(f"Stored case transfer order for case {case_id}")


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

def main():
    """Example usage of AI-powered document processor"""
    
    # Configuration
    ANTHROPIC_API_KEY = ""
    
    DB_CONFIG = {
        'host': 'localhost',
        'user': 'postgres',
        'password': 'postgres',
        'database': 'legal_case'
    }
    
    STORAGE_PATH = '/var/legal_documents/storage'
    
    # Initialize AI processor
    processor = AIDocumentProcessor(
        anthropic_api_key=ANTHROPIC_API_KEY,
        db_config=DB_CONFIG,
        storage_path=STORAGE_PATH
    )
    
    # Process a document
    result = processor.process_document('/path/to/document.txt')
    
    if result['success']:
        print(f"✅ Document processed successfully!")
        print(f"   Document Type: {result['document_type']}")
        print(f"   Confidence: {result['confidence']}%")
        print(f"   Case ID: {result['case_id']}")
        print(f"   Document ID: {result['document_id']}")
        print(f"\n📊 Extracted Data:")
        print(json.dumps(result['extracted_data'], indent=2, ensure_ascii=False))
    else:
        print(f"❌ Error: {result['error']}")


if __name__ == '__main__':
    main()
