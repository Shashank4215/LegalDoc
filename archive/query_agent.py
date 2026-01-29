"""
LangGraph Agent for Querying Legal Case Database
Uses natural language to generate and execute SQL queries
"""

from typing import Dict, List, Any, Optional, TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_groq import ChatGroq
from langchain_core.tools import tool, StructuredTool, StructuredTool
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import logging
import time
from config import CONFIG
from database_manager import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiting configuration for Groq API
GROQ_RATE_LIMIT_DELAY = 2.0  # Delay in seconds between API calls (increased to avoid 429 errors)


class AgentState(TypedDict):
    messages: Annotated[List, "messages"]
    query: str
    sql_query: Optional[str]
    results: Optional[List[Dict]]
    error: Optional[str]


# Database Schema Information
SCHEMA_INFO = """
Database Schema for Qatar Legal Case Management System:

TABLES:
1. cases - Main case information
   - case_id (PK), court_case_number, prosecution_case_number, police_report_number, internal_report_number
   - case_type, case_category, case_subcategory
   - court_name, circuit_number, circuit_name
   - police_station, prosecution_office
   - incident_date, report_date, case_opened_date, case_closed_date, final_judgment_date
   - current_status, status_date
   - case_summary_ar, case_summary_en

2. parties - People involved in cases
   - party_id (PK), personal_id, full_name_ar, full_name_en, latin_name
   - date_of_birth, age, gender, nationality, religion
   - phone_mobile, phone_landline, email
   - area, compound, building_number, apartment_number, street
   - occupation, sponsor_name, sponsor_id

3. case_parties - Links parties to cases with roles
   - case_party_id (PK), case_id (FK), party_id (FK)
   - role_type: 'accused', 'complainant', 'victim', 'witness', 'lawyer', 'judge', 'prosecutor'
   - role_subtype, role_description_ar, role_description_en
   - status, assigned_date, removed_date

4. documents - All case documents
   - document_id (PK), case_id (FK)
   - document_type: 'police_report', 'investigation', 'court_session', 'judgment', 'notification', 'detention_order', 'waiver', 'correspondence', 'case_transfer'
   - document_number, document_date, creation_date
   - original_filename, stored_filename, file_hash
   - extracted_text_ar, extracted_text_en, raw_text

5. charges - Criminal charges
   - charge_id (PK), case_id (FK)
   - charge_number, charge_description_ar, charge_description_en
   - article_number, law_name_ar, law_year
   - charge_status: 'pending', 'dismissed', 'convicted', 'acquitted'

6. court_sessions - Court hearing records
   - session_id (PK), case_id (FK)
   - session_date, session_time, session_type
   - court_name, circuit_name, judge_name
   - session_summary_ar, session_summary_en
   - outcome, next_session_date

7. judgments - Court decisions
   - judgment_id (PK), case_id (FK), session_id (FK)
   - judgment_date, verdict: 'guilty', 'not_guilty', 'dismissed'
   - judgment_reasoning_ar, judgment_reasoning_en
   - is_final, appeal_deadline

8. sentences - Sentencing information
   - sentence_id (PK), judgment_id (FK), charge_id (FK)
   - sentence_type: 'imprisonment', 'fine', 'community_service', 'probation'
   - imprisonment_duration_days, fine_amount, fine_currency
   - probation_duration_months, community_service_hours

9. evidence - Evidence items
   - evidence_id (PK), case_id (FK)
   - evidence_type, evidence_description_ar, evidence_description_en
   - collected_date, collected_location, storage_location
   - lab_analysis_requested, lab_result_summary

10. lab_results - Forensic test results
    - result_id (PK), case_id (FK), evidence_id (FK), subject_party_id (FK)
    - test_type, test_number, test_date
    - lab_name, analyst_name
    - result_summary_ar, result_value, interpretation

11. statements - Party statements
    - statement_id (PK), case_id (FK), party_id (FK)
    - statement_type: 'complaint', 'testimony', 'interrogation', 'defense'
    - statement_date, statement_time, statement_location
    - statement_text_ar, statement_text_en
    - oath_taken, is_confession

12. detention_records - Detention/custody orders
    - detention_id (PK), case_id (FK), party_id (FK)
    - order_number, order_date, start_date
    - detention_type, detention_reason_ar
    - scheduled_end_date, actual_end_date, duration_days
    - detention_facility, detention_status

13. notifications - Legal notifications/summons
    - notification_id (PK), case_id (FK), recipient_party_id (FK)
    - notification_number, notification_type, issue_date
    - session_date, delivery_status, delivery_date

14. case_events - Timeline of case events
    - event_id (PK), case_id (FK)
    - event_type, event_date, event_description_ar, event_description_en
    - related_document_id

15. waivers - Complaint waivers
    - waiver_id (PK), case_id (FK), complainant_party_id (FK)
    - waiver_date, waiver_type, waiver_statement_ar

16. correspondence - Inter-department communications
    - correspondence_id (PK), case_id (FK)
    - correspondence_number, correspondence_date
    - from_organization, from_person, to_organization, to_person
    - subject_ar, body_ar

RELATIONSHIPS:
- cases.case_id -> case_parties.case_id
- cases.case_id -> documents.case_id
- cases.case_id -> charges.case_id
- cases.case_id -> court_sessions.case_id
- cases.case_id -> judgments.case_id
- cases.case_id -> evidence.case_id
- parties.party_id -> case_parties.party_id
- parties.party_id -> statements.party_id
- parties.party_id -> detention_records.party_id

COMMON QUERIES:
- Find case by reference number (court_case_number, prosecution_case_number, police_report_number)
- Find all parties in a case
- Find all documents for a case
- Find case timeline/events
- Find charges and sentences
- Find detention records
- Search by person name or personal_id
- Search by date range
- Search by case status
"""


# SQL Tools
@tool
def query_cases(
    court_case_number: Optional[str] = None,
    prosecution_case_number: Optional[str] = None,
    police_report_number: Optional[str] = None,
    case_status: Optional[str] = None,
    case_type: Optional[str] = None,
    limit: int = 10
) -> str:
    """Query cases table by various criteria. Use this to find cases by reference numbers, status, or type."""
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            conditions = []
            params = []
            
            if court_case_number:
                # Handle different formats: "2552/2025" or "2025/2552"
                court_num_clean = court_case_number.strip()
                logger.info(f"Searching for court_case_number: '{court_num_clean}'")
                
                # Build court_case_number conditions with OR logic
                court_conditions = []
                court_conditions.append("court_case_number = %s")
                params.append(court_num_clean)
                
                # Try reversed format (e.g., "2025/2552" if user searches "2552/2025")
                if '/' in court_num_clean:
                    parts = court_num_clean.split('/')
                    if len(parts) == 2 and parts[0] != parts[1]:  # Only reverse if different
                        reversed_format = f"{parts[1]}/{parts[0]}"
                        logger.info(f"  Also trying reversed format: '{reversed_format}'")
                        court_conditions.append("court_case_number = %s")
                        params.append(reversed_format)
                
                # Try ILIKE pattern matching (case-insensitive, partial match)
                court_conditions.append("court_case_number ILIKE %s")
                params.append(f"%{court_num_clean}%")
                
                # Combine court conditions with OR
                court_condition_str = "(" + " OR ".join(court_conditions) + ")"
                conditions.append(court_condition_str)
                
            if prosecution_case_number:
                conditions.append("prosecution_case_number = %s")
                params.append(prosecution_case_number)
            if police_report_number:
                conditions.append("police_report_number = %s")
                params.append(police_report_number)
            if case_status:
                conditions.append("current_status = %s")
                params.append(case_status)
            if case_type:
                conditions.append("case_type = %s")
                params.append(case_type)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            params.append(limit)
            
            query = f"""
                SELECT * FROM cases 
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s
            """
            
            logger.info(f"Executing SQL query with {len(params)} parameters")
            logger.info(f"Query: {query[:200]}...")
            logger.info(f"Params: {params}")
            
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()
                logger.info(f"Query returned {len(results)} result(s)")
                if results:
                    first_result = dict(results[0])
                    logger.info(f"First result - case_id: {first_result.get('case_id')}, court_case_number: {first_result.get('court_case_number')}")
                return json.dumps([dict(row) for row in results], default=str, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in query_cases: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_parties(
    name_ar: Optional[str] = None,
    name_en: Optional[str] = None,
    personal_id: Optional[str] = None,
    nationality: Optional[str] = None,
    limit: int = 10
) -> str:
    """Query parties table by name, personal_id, or nationality. Use this to find people involved in cases."""
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            conditions = []
            params = []
            
            if name_ar:
                conditions.append("full_name_ar ILIKE %s")
                params.append(f"%{name_ar}%")
            if name_en:
                conditions.append("full_name_en ILIKE %s")
                params.append(f"%{name_en}%")
            if personal_id:
                conditions.append("personal_id = %s")
                params.append(personal_id)
            if nationality:
                conditions.append("nationality = %s")
                params.append(nationality)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            params.append(limit)
            
            query = f"""
                SELECT * FROM parties 
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s
            """
            
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()
                return json.dumps([dict(row) for row in results], default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_case_parties(case_id: int) -> str:
    """Get all parties involved in a specific case with their roles (accused, complainant, witness, etc.)."""
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            query = """
                SELECT 
                    cp.case_party_id,
                    cp.role_type,
                    cp.role_subtype,
                    cp.role_description_ar,
                    cp.status,
                    p.party_id,
                    p.full_name_ar,
                    p.full_name_en,
                    p.personal_id,
                    p.nationality,
                    p.age,
                    p.gender
                FROM case_parties cp
                JOIN parties p ON cp.party_id = p.party_id
                WHERE cp.case_id = %s
                ORDER BY cp.role_type, cp.created_at
            """
            
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, [case_id])
                results = cursor.fetchall()
                return json.dumps([dict(row) for row in results], default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_documents(
    case_id: Optional[int] = None,
    document_type: Optional[str] = None,
    document_number: Optional[str] = None,
    limit: int = 20
) -> str:
    """Query documents table by case_id, document_type, or document_number. Returns list of documents."""
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            conditions = []
            params = []
            
            if case_id:
                conditions.append("case_id = %s")
                params.append(case_id)
            if document_type:
                conditions.append("document_type = %s")
                params.append(document_type)
            if document_number:
                conditions.append("document_number = %s")
                params.append(document_number)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            params.append(limit)
            
            query = f"""
                SELECT 
                    document_id,
                    case_id,
                    document_type,
                    document_number,
                    document_date,
                    original_filename,
                    created_at
                FROM documents 
                WHERE {where_clause}
                ORDER BY document_date DESC NULLS LAST, created_at DESC
                LIMIT %s
            """
            
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()
                return json.dumps([dict(row) for row in results], default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_charges(case_id: int) -> str:
    """Get all charges for a specific case. Returns charges with article numbers and status."""
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            query = """
                SELECT 
                    charge_id,
                    charge_number,
                    charge_description_ar,
                    charge_description_en,
                    article_number,
                    law_name_ar,
                    law_year,
                    charge_status
                FROM charges
                WHERE case_id = %s
                ORDER BY charge_number
            """
            
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, [case_id])
                results = cursor.fetchall()
                return json.dumps([dict(row) for row in results], default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_judgments(case_id: int) -> str:
    """Get all judgments and sentences for a specific case. Returns verdict and sentencing details."""
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            query = """
                SELECT 
                    j.judgment_id,
                    j.judgment_date,
                    j.verdict,
                    j.judgment_reasoning_ar,
                    j.is_final,
                    s.sentence_id,
                    s.sentence_type,
                    s.imprisonment_duration_days,
                    s.fine_amount,
                    s.fine_currency
                FROM judgments j
                LEFT JOIN sentences s ON j.judgment_id = s.judgment_id
                WHERE j.case_id = %s
                ORDER BY j.judgment_date DESC
            """
            
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, [case_id])
                results = cursor.fetchall()
                return json.dumps([dict(row) for row in results], default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_case_timeline(case_id: int) -> str:
    """Get complete timeline of events for a case. Returns chronological list of all case events."""
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            query = """
                SELECT 
                    event_id,
                    event_type,
                    event_date,
                    event_description_ar,
                    event_description_en,
                    related_document_id
                FROM case_events
                WHERE case_id = %s
                ORDER BY event_date ASC NULLS LAST, created_at ASC
            """
            
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, [case_id])
                results = cursor.fetchall()
                return json.dumps([dict(row) for row in results], default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_detention_records(
    case_id: Optional[int] = None,
    party_id: Optional[int] = None,
    limit: int = 10
) -> str:
    """Query detention records by case_id or party_id. Returns detention orders and custody information."""
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            conditions = []
            params = []
            
            if case_id:
                conditions.append("dr.case_id = %s")
                params.append(case_id)
            if party_id:
                conditions.append("dr.party_id = %s")
                params.append(party_id)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            params.append(limit)
            
            query = f"""
                SELECT 
                    dr.detention_id,
                    dr.case_id,
                    dr.party_id,
                    p.full_name_ar,
                    dr.order_number,
                    dr.order_date,
                    dr.start_date,
                    dr.scheduled_end_date,
                    dr.detention_type,
                    dr.detention_status
                FROM detention_records dr
                LEFT JOIN parties p ON dr.party_id = p.party_id
                WHERE {where_clause}
                ORDER BY dr.start_date DESC
                LIMIT %s
            """
            
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()
                return json.dumps([dict(row) for row in results], default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_court_sessions(case_id: int) -> str:
    """Get all court sessions for a specific case. Returns session dates, outcomes, and next session dates."""
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            query = """
                SELECT 
                    session_id,
                    session_date,
                    session_time,
                    session_type,
                    court_name,
                    circuit_name,
                    judge_name,
                    session_summary_ar,
                    outcome,
                    next_session_date
                FROM court_sessions
                WHERE case_id = %s
                ORDER BY session_date ASC
            """
            
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, [case_id])
                results = cursor.fetchall()
                return json.dumps([dict(row) for row in results], default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_evidence(case_id: int) -> str:
    """Get all evidence items for a specific case. Returns evidence descriptions and storage information."""
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            query = """
                SELECT 
                    evidence_id,
                    evidence_type,
                    evidence_description_ar,
                    evidence_description_en,
                    collected_date,
                    collected_location,
                    storage_location,
                    storage_status,
                    lab_analysis_requested
                FROM evidence
                WHERE case_id = %s
                ORDER BY collected_date DESC
            """
            
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, [case_id])
                results = cursor.fetchall()
                return json.dumps([dict(row) for row in results], default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_statements(case_id: int) -> str:
    """Get all statements for a specific case. Returns party statements, interrogations, and testimonies."""
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            query = """
                SELECT 
                    s.statement_id,
                    s.party_id,
                    p.full_name_ar,
                    s.statement_type,
                    s.statement_date,
                    s.statement_time,
                    s.statement_location,
                    s.oath_taken,
                    s.is_confession
                FROM statements s
                LEFT JOIN parties p ON s.party_id = p.party_id
                WHERE s.case_id = %s
                ORDER BY s.statement_date ASC
            """
            
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, [case_id])
                results = cursor.fetchall()
                return json.dumps([dict(row) for row in results], default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def execute_custom_sql(query: str) -> str:
    """
    Execute a custom SQL query. 
    WARNING: Only SELECT queries are allowed. 
    Use this for complex queries that other tools cannot handle.
    """
    # Security: Only allow SELECT queries
    query_upper = query.strip().upper()
    if not query_upper.startswith('SELECT'):
        return json.dumps({"error": "Only SELECT queries are allowed"}, ensure_ascii=False)
    
    # Additional safety checks
    forbidden_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE', 'TRUNCATE', 'EXEC', 'EXECUTE']
    if any(keyword in query_upper for keyword in forbidden_keywords):
        return json.dumps({"error": "Query contains forbidden keywords"}, ensure_ascii=False)
    
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query)
                results = cursor.fetchall()
                return json.dumps([dict(row) for row in results], default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_case_with_parties(
    court_case_number: Optional[str] = None,
    case_id: Optional[int] = None
) -> str:
    """
    Get case information along with all involved parties (accused, victims, witnesses, etc.) in one call.
    Provide either court_case_number (e.g., "2025/2552") or case_id.
    This is more efficient than calling query_cases and query_case_parties separately.
    """
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            # First, find the case
            case_query = "SELECT * FROM cases WHERE "
            case_params = []
            
            if case_id:
                case_query += "case_id = %s"
                case_params.append(case_id)
            elif court_case_number:
                court_num_clean = court_case_number.strip()
                # Try multiple formats
                case_query += "(court_case_number = %s OR court_case_number = %s OR court_case_number ILIKE %s)"
                case_params.append(court_num_clean)
                if '/' in court_num_clean:
                    parts = court_num_clean.split('/')
                    if len(parts) == 2 and parts[0] != parts[1]:
                        case_params.append(f"{parts[1]}/{parts[0]}")
                    else:
                        case_params.append(court_num_clean)
                else:
                    case_params.append(court_num_clean)
                case_params.append(f"%{court_num_clean}%")
            else:
                return json.dumps({"error": "Either court_case_number or case_id is required"}, ensure_ascii=False)
            
            case_query += " LIMIT 1"
            
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(case_query, case_params)
                case_result = cursor.fetchone()
                
                if not case_result:
                    return json.dumps({"error": "Case not found"}, ensure_ascii=False)
                
                case_data = dict(case_result)
                case_id_found = case_data['case_id']
                
                # Now get all parties for this case
                parties_query = """
                    SELECT 
                        cp.case_party_id,
                        cp.role_type,
                        cp.role_subtype,
                        cp.role_description_ar,
                        cp.status,
                        p.party_id,
                        p.full_name_ar,
                        p.full_name_en,
                        p.personal_id,
                        p.nationality,
                        p.age,
                        p.gender,
                        p.address_ar,
                        p.phone_number
                    FROM case_parties cp
                    JOIN parties p ON cp.party_id = p.party_id
                    WHERE cp.case_id = %s
                    ORDER BY cp.role_type, cp.created_at
                """
                
                cursor.execute(parties_query, [case_id_found])
                parties_results = cursor.fetchall()
                
                # Combine results
                result = {
                    "case": case_data,
                    "parties": [dict(row) for row in parties_results],
                    "parties_count": len(parties_results)
                }
                
                return json.dumps(result, default=str, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in query_case_with_parties: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_case_full_details(
    court_case_number: Optional[str] = None,
    case_id: Optional[int] = None
) -> str:
    """
    Get comprehensive case details including: case info, parties, charges, documents, court sessions, 
    judgments, and timeline - all in one call. Provide either court_case_number or case_id.
    Use this for complete case overview instead of multiple separate tool calls.
    """
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            # Find the case
            case_query = "SELECT * FROM cases WHERE "
            case_params = []
            
            if case_id:
                case_query += "case_id = %s"
                case_params.append(case_id)
            elif court_case_number:
                court_num_clean = court_case_number.strip()
                case_query += "(court_case_number = %s OR court_case_number = %s OR court_case_number ILIKE %s)"
                case_params.append(court_num_clean)
                if '/' in court_num_clean:
                    parts = court_num_clean.split('/')
                    if len(parts) == 2 and parts[0] != parts[1]:
                        case_params.append(f"{parts[1]}/{parts[0]}")
                    else:
                        case_params.append(court_num_clean)
                else:
                    case_params.append(court_num_clean)
                case_params.append(f"%{court_num_clean}%")
            else:
                return json.dumps({"error": "Either court_case_number or case_id is required"}, ensure_ascii=False)
            
            case_query += " LIMIT 1"
            
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(case_query, case_params)
                case_result = cursor.fetchone()
                
                if not case_result:
                    return json.dumps({"error": "Case not found"}, ensure_ascii=False)
                
                case_data = dict(case_result)
                case_id_found = case_data['case_id']
                
                result = {"case": case_data}
                
                # Get parties
                cursor.execute("""
                    SELECT cp.*, p.full_name_ar, p.full_name_en, p.personal_id, p.nationality, p.age, p.gender
                    FROM case_parties cp
                    JOIN parties p ON cp.party_id = p.party_id
                    WHERE cp.case_id = %s
                    ORDER BY cp.role_type
                """, [case_id_found])
                result["parties"] = [dict(row) for row in cursor.fetchall()]
                
                # Get charges
                cursor.execute("SELECT * FROM charges WHERE case_id = %s ORDER BY charge_date", [case_id_found])
                result["charges"] = [dict(row) for row in cursor.fetchall()]
                
                # Get documents
                cursor.execute("SELECT document_id, document_type, document_date, file_name, storage_path FROM documents WHERE case_id = %s ORDER BY document_date DESC", [case_id_found])
                result["documents"] = [dict(row) for row in cursor.fetchall()]
                
                # Get court sessions
                cursor.execute("SELECT * FROM court_sessions WHERE case_id = %s ORDER BY session_date", [case_id_found])
                result["court_sessions"] = [dict(row) for row in cursor.fetchall()]
                
                # Get judgments
                cursor.execute("SELECT * FROM judgments WHERE case_id = %s ORDER BY judgment_date DESC", [case_id_found])
                result["judgments"] = [dict(row) for row in cursor.fetchall()]
                
                # Get timeline events
                cursor.execute("SELECT * FROM case_events WHERE case_id = %s ORDER BY event_date, created_at", [case_id_found])
                result["timeline"] = [dict(row) for row in cursor.fetchall()]
                
                # Add counts
                result["summary"] = {
                    "parties_count": len(result["parties"]),
                    "charges_count": len(result["charges"]),
                    "documents_count": len(result["documents"]),
                    "sessions_count": len(result["court_sessions"]),
                    "judgments_count": len(result["judgments"]),
                    "events_count": len(result["timeline"])
                }
                
                return json.dumps(result, default=str, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in query_case_full_details: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_case_parties_by_role(
    court_case_number: Optional[str] = None,
    case_id: Optional[int] = None,
    role_type: Optional[str] = None
) -> str:
    """
    Get parties involved in a case, optionally filtered by role type.
    Role types: 'accused', 'complainant', 'victim', 'witness', 'lawyer', 'prosecutor', 'judge', etc.
    Provide either court_case_number or case_id. If role_type is not provided, returns all parties.
    """
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            # First find the case
            case_query = "SELECT case_id FROM cases WHERE "
            case_params = []
            
            if case_id:
                case_query += "case_id = %s"
                case_params.append(case_id)
            elif court_case_number:
                court_num_clean = court_case_number.strip()
                case_query += "(court_case_number = %s OR court_case_number = %s OR court_case_number ILIKE %s)"
                case_params.append(court_num_clean)
                if '/' in court_num_clean:
                    parts = court_num_clean.split('/')
                    if len(parts) == 2 and parts[0] != parts[1]:
                        case_params.append(f"{parts[1]}/{parts[0]}")
                    else:
                        case_params.append(court_num_clean)
                else:
                    case_params.append(court_num_clean)
                case_params.append(f"%{court_num_clean}%")
            else:
                return json.dumps({"error": "Either court_case_number or case_id is required"}, ensure_ascii=False)
            
            case_query += " LIMIT 1"
            
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(case_query, case_params)
                case_result = cursor.fetchone()
                
                if not case_result:
                    return json.dumps({"error": "Case not found"}, ensure_ascii=False)
                
                case_id_found = case_result['case_id']
                
                # Get parties with optional role filter
                parties_query = """
                    SELECT 
                        cp.case_party_id,
                        cp.role_type,
                        cp.role_subtype,
                        cp.role_description_ar,
                        cp.status,
                        p.party_id,
                        p.full_name_ar,
                        p.full_name_en,
                        p.personal_id,
                        p.nationality,
                        p.age,
                        p.gender,
                        p.address_ar,
                        p.phone_number
                    FROM case_parties cp
                    JOIN parties p ON cp.party_id = p.party_id
                    WHERE cp.case_id = %s
                """
                parties_params = [case_id_found]
                
                if role_type:
                    parties_query += " AND cp.role_type = %s"
                    parties_params.append(role_type.lower())
                
                parties_query += " ORDER BY cp.role_type, cp.created_at"
                
                cursor.execute(parties_query, parties_params)
                parties_results = cursor.fetchall()
                
                result = {
                    "case_id": case_id_found,
                    "role_filter": role_type,
                    "parties": [dict(row) for row in parties_results],
                    "count": len(parties_results)
                }
                
                return json.dumps(result, default=str, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in query_case_parties_by_role: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_victims(
    case_id: Optional[int] = None,
    court_case_number: Optional[str] = None
) -> str:
    """
    Directly get all victims in a case. If no case_id or court_case_number is provided, 
    returns victims from all cases (useful when database has only one case).
    """
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            query = """
                SELECT 
                    cp.case_party_id,
                    cp.role_type,
                    cp.role_subtype,
                    cp.role_description_ar,
                    cp.status,
                    c.case_id,
                    c.court_case_number,
                    c.prosecution_case_number,
                    p.party_id,
                    p.full_name_ar,
                    p.full_name_en,
                    p.personal_id,
                    p.nationality,
                    p.age,
                    p.gender,
                    p.address_ar,
                    p.phone_number
                FROM case_parties cp
                JOIN parties p ON cp.party_id = p.party_id
                JOIN cases c ON cp.case_id = c.case_id
                WHERE cp.role_type = 'victim'
            """
            params = []
            
            if case_id:
                query += " AND cp.case_id = %s"
                params.append(case_id)
            elif court_case_number:
                court_num_clean = court_case_number.strip()
                query += " AND (c.court_case_number = %s OR c.court_case_number = %s OR c.court_case_number ILIKE %s)"
                params.append(court_num_clean)
                if '/' in court_num_clean:
                    parts = court_num_clean.split('/')
                    if len(parts) == 2 and parts[0] != parts[1]:
                        params.append(f"{parts[1]}/{parts[0]}")
                    else:
                        params.append(court_num_clean)
                else:
                    params.append(court_num_clean)
                params.append(f"%{court_num_clean}%")
            
            query += " ORDER BY c.case_id, cp.created_at"
            
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()
                return json.dumps([dict(row) for row in results], default=str, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in query_victims: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_accused(
    case_id: Optional[int] = None,
    court_case_number: Optional[str] = None
) -> str:
    """
    Directly get all accused persons in a case. If no case_id or court_case_number is provided, 
    returns accused from all cases (useful when database has only one case).
    """
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            query = """
                SELECT 
                    cp.case_party_id,
                    cp.role_type,
                    cp.role_subtype,
                    cp.role_description_ar,
                    cp.status,
                    c.case_id,
                    c.court_case_number,
                    c.prosecution_case_number,
                    p.party_id,
                    p.full_name_ar,
                    p.full_name_en,
                    p.personal_id,
                    p.nationality,
                    p.age,
                    p.gender,
                    p.address_ar,
                    p.phone_number
                FROM case_parties cp
                JOIN parties p ON cp.party_id = p.party_id
                JOIN cases c ON cp.case_id = c.case_id
                WHERE cp.role_type = 'accused'
            """
            params = []
            
            if case_id:
                query += " AND cp.case_id = %s"
                params.append(case_id)
            elif court_case_number:
                court_num_clean = court_case_number.strip()
                query += " AND (c.court_case_number = %s OR c.court_case_number = %s OR c.court_case_number ILIKE %s)"
                params.append(court_num_clean)
                if '/' in court_num_clean:
                    parts = court_num_clean.split('/')
                    if len(parts) == 2 and parts[0] != parts[1]:
                        params.append(f"{parts[1]}/{parts[0]}")
                    else:
                        params.append(court_num_clean)
                else:
                    params.append(court_num_clean)
                params.append(f"%{court_num_clean}%")
            
            query += " ORDER BY c.case_id, cp.created_at"
            
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()
                return json.dumps([dict(row) for row in results], default=str, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in query_accused: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_witnesses(
    case_id: Optional[int] = None,
    court_case_number: Optional[str] = None
) -> str:
    """
    Directly get all witnesses in a case. If no case_id or court_case_number is provided, 
    returns witnesses from all cases (useful when database has only one case).
    """
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            query = """
                SELECT 
                    cp.case_party_id,
                    cp.role_type,
                    cp.role_subtype,
                    cp.role_description_ar,
                    cp.status,
                    c.case_id,
                    c.court_case_number,
                    c.prosecution_case_number,
                    p.party_id,
                    p.full_name_ar,
                    p.full_name_en,
                    p.personal_id,
                    p.nationality,
                    p.age,
                    p.gender,
                    p.address_ar,
                    p.phone_number
                FROM case_parties cp
                JOIN parties p ON cp.party_id = p.party_id
                JOIN cases c ON cp.case_id = c.case_id
                WHERE cp.role_type = 'witness'
            """
            params = []
            
            if case_id:
                query += " AND cp.case_id = %s"
                params.append(case_id)
            elif court_case_number:
                court_num_clean = court_case_number.strip()
                query += " AND (c.court_case_number = %s OR c.court_case_number = %s OR c.court_case_number ILIKE %s)"
                params.append(court_num_clean)
                if '/' in court_num_clean:
                    parts = court_num_clean.split('/')
                    if len(parts) == 2 and parts[0] != parts[1]:
                        params.append(f"{parts[1]}/{parts[0]}")
                    else:
                        params.append(court_num_clean)
                else:
                    params.append(court_num_clean)
                params.append(f"%{court_num_clean}%")
            
            query += " ORDER BY c.case_id, cp.created_at"
            
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()
                return json.dumps([dict(row) for row in results], default=str, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in query_witnesses: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_complainants(
    case_id: Optional[int] = None,
    court_case_number: Optional[str] = None
) -> str:
    """
    Directly get all complainants in a case. If no case_id or court_case_number is provided, 
    returns complainants from all cases (useful when database has only one case).
    """
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            query = """
                SELECT 
                    cp.case_party_id,
                    cp.role_type,
                    cp.role_subtype,
                    cp.role_description_ar,
                    cp.status,
                    c.case_id,
                    c.court_case_number,
                    c.prosecution_case_number,
                    p.party_id,
                    p.full_name_ar,
                    p.full_name_en,
                    p.personal_id,
                    p.nationality,
                    p.age,
                    p.gender,
                    p.address_ar,
                    p.phone_number
                FROM case_parties cp
                JOIN parties p ON cp.party_id = p.party_id
                JOIN cases c ON cp.case_id = c.case_id
                WHERE cp.role_type = 'complainant'
            """
            params = []
            
            if case_id:
                query += " AND cp.case_id = %s"
                params.append(case_id)
            elif court_case_number:
                court_num_clean = court_case_number.strip()
                query += " AND (c.court_case_number = %s OR c.court_case_number = %s OR c.court_case_number ILIKE %s)"
                params.append(court_num_clean)
                if '/' in court_num_clean:
                    parts = court_num_clean.split('/')
                    if len(parts) == 2 and parts[0] != parts[1]:
                        params.append(f"{parts[1]}/{parts[0]}")
                    else:
                        params.append(court_num_clean)
                else:
                    params.append(court_num_clean)
                params.append(f"%{court_num_clean}%")
            
            query += " ORDER BY c.case_id, cp.created_at"
            
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()
                return json.dumps([dict(row) for row in results], default=str, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in query_complainants: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# All tools - ensure they have explicit names for Groq compatibility
# The openai/gpt-oss-20b model requires tools to have explicit names
# We'll convert them to StructuredTool objects with explicit names
TOOLS_LIST = [
    # Direct role-based queries (no case number needed - works with single case database)
    query_victims,      # Get all victims directly
    query_accused,      # Get all accused directly
    query_witnesses,    # Get all witnesses directly
    query_complainants, # Get all complainants directly
    
    # Comprehensive tools (preferred - fetch multiple related things in one call)
    query_case_with_parties,  # Case + all parties
    query_case_full_details,   # Case + parties + charges + documents + sessions + judgments + timeline
    query_case_parties_by_role,  # Parties filtered by role (accused, victim, etc.)
    
    # Individual tools (for specific queries)
    query_cases,
    query_parties,
    query_case_parties,
    query_documents,
    query_charges,
    query_judgments,
    query_case_timeline,
    query_detention_records,
    query_court_sessions,
    query_evidence,
    query_statements,
    execute_custom_sql
]

# Ensure all tools have explicit names for Groq compatibility
# The openai/gpt-oss-20b model requires tools to have explicit names
def ensure_tool_names(tools):
    """Ensure all tools have explicit names - required for openai/gpt-oss-20b"""
    fixed_tools = []
    for tool_obj in tools:
        # Get the function and its name
        if hasattr(tool_obj, 'func'):
            func = tool_obj.func
            func_name = func.__name__
        elif callable(tool_obj):
            func = tool_obj
            func_name = tool_obj.__name__
        else:
            logger.error(f"Tool {tool_obj} is not callable and has no func attribute!")
            continue
        
        # ALWAYS create StructuredTool with explicit name to ensure Groq compatibility
        # This is the only reliable way to ensure the name is properly set for openai/gpt-oss-20b
        description = getattr(tool_obj, 'description', '') or ''
        args_schema = getattr(tool_obj, 'args_schema', None)
        
        try:
            fixed_tool = StructuredTool.from_function(
                func=func,
                name=func_name,
                description=description,
                args_schema=args_schema
            )
            # Double-check the name is set
            if not fixed_tool.name:
                fixed_tool.name = func_name
            fixed_tools.append(fixed_tool)
        except Exception as e:
            logger.error(f"Failed to create StructuredTool for {func_name}: {e}")
            # Fallback: try to use original tool if it has a name
            if hasattr(tool_obj, 'name') and tool_obj.name:
                fixed_tools.append(tool_obj)
            else:
                logger.error(f"Skipping tool {func_name} - cannot create StructuredTool")
    
    return fixed_tools

# Apply name fixing for Groq compatibility
TOOLS = ensure_tool_names(TOOLS_LIST)

# Cache the agent to avoid recreating it on every query
_cached_agent = None


def create_agent():
    """Create LangGraph agent with SQL tools"""
    
    # Initialize LLM with Groq
    import os
    groq_api_key = os.getenv('GROQ_API_KEY', '')
    if not groq_api_key:
        raise ValueError("GROQ_API_KEY environment variable is required. Set it with: export GROQ_API_KEY='your-key'")
    
    # System prompt
    system_prompt_content = f"""
You are an expert SQL query assistant for a Qatar Legal Case Management System database.

Your role:
1. Understand user queries in natural language (Arabic or English)
2. Determine which SQL tools to use to answer the query
3. Execute queries using the provided tools
4. Synthesize results into clear, comprehensive answers

Database Schema:
{SCHEMA_INFO}

Guidelines:
- DIRECT ROLE QUERIES (preferred when user asks about specific roles - no case number needed):
  * query_victims: when user asks about "victims", "victim", "المجني عليهم"
  * query_accused: when user asks about "accused", "defendant", "المتهمين"
  * query_witnesses: when user asks about "witnesses", "witness", "الشهود"
  * query_complainants: when user asks about "complainants", "complainant", "المشتكين"
  * These work without case_id/court_case_number (useful when database has only one case)
  
- PREFER comprehensive tools that fetch multiple related things in one call:
  * For case with parties: use query_case_with_parties (more efficient than query_cases + query_case_parties)
  * For complete case overview: use query_case_full_details (gets case + parties + charges + documents + sessions + judgments + timeline)
  * For parties by role: use query_case_parties_by_role (e.g., "accused", "victim", "witness")
  
- Use individual tools only for specific, targeted queries:
  * query_cases: when you only need basic case info
  * query_parties: when searching for people by name
  * query_documents, query_charges, etc.: when you only need that specific type of data
  
- Use execute_custom_sql only for complex queries that other tools cannot handle
- Always provide context and explain what information you found
- Format dates and numbers clearly
- Support both Arabic and English queries
- IMPORTANT: If user asks "who are the victims?" or "list the accused" without mentioning a case, use query_victims or query_accused directly (they work without case number)

CRITICAL FUNCTION CALLING RULES:
- You MUST use the standard OpenAI-compatible function calling format
- DO NOT use XML tags like <function=...> or <function>...</function>
- DO NOT use custom formats or text-based function calls
- The model will automatically handle function calls when you use tool_calls in your response
- Simply respond normally - the LangChain framework will handle the function calling format
- When you need to call a tool, think about what tool to use and what parameters it needs
- The tools are bound to your model - LangChain will convert your intent into proper function calls

Example of CORRECT behavior:
- User asks: "Find case 2552/2025"
- You think: "I need to use query_cases with court_case_number='2552/2025'"
- The framework will automatically create the proper function call

Example of INCORRECT behavior (DO NOT DO THIS):
- DO NOT write: <function=query_cases({{"court_case_number": "2552/2025"}})</function>
- DO NOT write: query_cases(court_case_number="2552/2025") as plain text

When answering:
- Start with a brief summary of what you found
- Present key information clearly
- Include relevant details (dates, names, statuses)
- If no results found, suggest alternative search criteria
- For multi-step queries, explain what information you're gathering
"""
    
    # Use Groq model - try different models for better function calling support
    # Note: Some Groq models may have issues with function calling
    # If this doesn't work, we may need to use a different approach
    llm = ChatGroq(
        model="qwen/qwen3-32b",  # Better function calling support
        groq_api_key=groq_api_key,
        temperature=0,
        max_tokens=4096  # Increase max tokens for better responses
    )
    
    # Prepare tools with explicit names for Groq compatibility
    # Verify all tools have names (required for openai/gpt-oss-20b)
    logger.info(f"Preparing {len(TOOLS)} tools for LLM...")
    tools_to_bind = []
    for i, tool in enumerate(TOOLS):
        tool_name = getattr(tool, 'name', None)
        if not tool_name:
            # Try to get name from function
            if hasattr(tool, 'func'):
                tool_name = tool.func.__name__
            elif callable(tool):
                tool_name = tool.__name__
            else:
                logger.error(f"  Tool #{i}: No way to determine name! Type: {type(tool)}")
                continue
        
        # Always verify tool has name, if not, it should have been fixed in ensure_tool_names
        if not getattr(tool, 'name', None):
            logger.warning(f"  Tool #{i} ({tool_name}) missing name attribute, will rebind on each call")
        
        tools_to_bind.append(tool)
        logger.info(f"  Tool #{i}: '{tool_name}' ✓")
    
    if len(tools_to_bind) != len(TOOLS):
        logger.warning(f"Only {len(tools_to_bind)}/{len(TOOLS)} tools prepared. This may cause issues.")
    
    # Bind tools to LLM once (not on every API call) - this avoids repeated initialization
    logger.info(f"Binding {len(tools_to_bind)} tools to LLM (one-time setup)...")
    llm_with_tools = llm.bind_tools(tools_to_bind)
    
    # Create tool node - use the same tools that were bound to LLM
    tool_node = ToolNode(tools_to_bind)
    
    # System prompt as SystemMessage
    system_prompt = SystemMessage(content=system_prompt_content)
    
    # Define graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    def agent_node(state: AgentState):
        """Agent node that processes messages and decides on tool calls"""
        # Add delay to avoid rate limiting (increased delay to prevent 429 errors)
        logger.info(f"Waiting {GROQ_RATE_LIMIT_DELAY} seconds before API call to avoid rate limiting...")
        time.sleep(GROQ_RATE_LIMIT_DELAY)
        
        messages = state["messages"]
        # Add system prompt only if it's not already in the messages
        # Check if first message is already a SystemMessage
        if not messages or not isinstance(messages[0], SystemMessage):
            messages_with_system = [system_prompt] + messages
        else:
            messages_with_system = messages
        
        # Log message history for debugging
        logger.info("=" * 70)
        logger.info("AGENT NODE EXECUTION")
        logger.info("=" * 70)
        logger.info(f"Message count: {len(messages_with_system)}")
        for i, msg in enumerate(messages_with_system):
            if isinstance(msg, HumanMessage):
                logger.info(f"  [{i}] HumanMessage: {msg.content[:100]}...")
            elif isinstance(msg, AIMessage):
                logger.info(f"  [{i}] AIMessage: {msg.content[:100] if msg.content else 'No content'}...")
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    logger.info(f"       Tool calls: {len(msg.tool_calls)}")
                    for tc in msg.tool_calls:
                        logger.info(f"         - {tc.get('name', 'unknown')}({tc.get('args', {})})")
            elif isinstance(msg, ToolMessage):
                logger.info(f"  [{i}] ToolMessage: {msg.content[:100]}...")
            elif isinstance(msg, SystemMessage):
                logger.info(f"  [{i}] SystemMessage: [System prompt]")
        
        logger.info(f"\nMaking API call to Groq (model: {llm.model_name})...")
        # Use the pre-bound LLM (tools are already bound once in create_agent)
        # No need to rebind on every call - this was causing unnecessary overhead
        response = llm_with_tools.invoke(messages_with_system)
        
        # Log the response
        logger.info("API call completed successfully")
        if isinstance(response, AIMessage):
            logger.info(f"Response content: {response.content[:200] if response.content else 'No content'}...")
            if hasattr(response, 'tool_calls') and response.tool_calls:
                logger.info(f"Tool calls requested: {len(response.tool_calls)}")
                for tc in response.tool_calls:
                    tool_name = tc.get('name', 'unknown')
                    tool_args = tc.get('args', {})
                    logger.info(f"  → Calling tool: {tool_name}")
                    logger.info(f"    Arguments: {json.dumps(tool_args, indent=2, ensure_ascii=False)}")
            else:
                logger.info("No tool calls - generating final answer")
        
        logger.info("=" * 70)
        return {"messages": [response]}
    
    # Custom tool node with logging
    def tool_node_with_logging(state: AgentState):
        """Tool node that executes tools and logs the execution"""
        logger.info("=" * 70)
        logger.info("TOOL NODE EXECUTION")
        logger.info("=" * 70)
        
        messages = state["messages"]
        last_message = messages[-1]
        
        if isinstance(last_message, AIMessage) and hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            logger.info(f"Executing {len(last_message.tool_calls)} tool call(s)")
            
            for i, tool_call in enumerate(last_message.tool_calls):
                tool_name = tool_call.get('name', 'unknown')
                tool_args = tool_call.get('args', {})
                tool_id = tool_call.get('id', 'unknown')
                
                logger.info(f"\n[{i+1}] Tool: {tool_name}")
                logger.info(f"    ID: {tool_id}")
                logger.info(f"    Arguments: {json.dumps(tool_args, indent=4, ensure_ascii=False, default=str)}")
                logger.info(f"    Executing SQL query...")
        
        # Execute tools using ToolNode
        result = tool_node.invoke(state)
        
        # Log tool results
        if "messages" in result:
            tool_messages = [msg for msg in result["messages"] if isinstance(msg, ToolMessage)]
            logger.info(f"\nTool execution completed: {len(tool_messages)} result(s)")
            for i, msg in enumerate(tool_messages):
                result_preview = msg.content[:300] if len(msg.content) > 300 else msg.content
                logger.info(f"  [{i+1}] Result preview: {result_preview}")
                if len(msg.content) > 300:
                    logger.info(f"       [Result truncated, full length: {len(msg.content)} chars]")
                    # Try to parse JSON and show structure
                    try:
                        result_data = json.loads(msg.content)
                        if isinstance(result_data, list):
                            logger.info(f"       [Result is a list with {len(result_data)} items]")
                        elif isinstance(result_data, dict):
                            logger.info(f"       [Result keys: {list(result_data.keys())}]")
                    except:
                        pass
        
        logger.info("=" * 70)
        return result
    
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node_with_logging)
    
    # Add edges
    workflow.set_entry_point("agent")
    
    def should_continue(state: AgentState):
        """Determine if we should continue to tools or end"""
        messages = state["messages"]
        last_message = messages[-1]
        # Check if last message has tool_calls
        if isinstance(last_message, AIMessage) and hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "tools"
        return "end"
    
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "end": END}
    )
    workflow.add_edge("tools", "agent")
    
    return workflow.compile()


def query(user_query: str) -> str:
    """
    Main query function - takes natural language query and returns answer
    
    Args:
        user_query: Natural language question about cases, parties, documents, etc.
    
    Returns:
        Formatted answer with relevant information
    """
    logger.info(f"Starting query: {user_query}")
    logger.info(f"Rate limit delay: {GROQ_RATE_LIMIT_DELAY} seconds between API calls")
    
    # Use cached agent to avoid recreating it on every query
    global _cached_agent
    if _cached_agent is None:
        logger.info("Creating agent (first time)...")
        _cached_agent = create_agent()
    else:
        logger.debug("Using cached agent")
    agent = _cached_agent
    
    initial_state = {
        "messages": [HumanMessage(content=user_query)],
        "query": user_query,
        "sql_query": None,
        "results": None,
        "error": None
    }
    
    try:
        # Track execution flow
        api_call_count = 0
        tool_call_count = 0
        
        logger.info("\n" + "=" * 70)
        logger.info("QUERY EXECUTION START")
        logger.info("=" * 70)
        logger.info(f"User Query: {user_query}")
        logger.info(f"Rate limit delay: {GROQ_RATE_LIMIT_DELAY} seconds between API calls")
        logger.info("=" * 70 + "\n")
        
        # Stream execution to track iterations
        for chunk in agent.stream(initial_state):
            # Count iterations
            for node_name, node_output in chunk.items():
                logger.info(f"\n>>> Node executed: {node_name}")
                
                if node_name == "agent":
                    api_call_count += 1
                    logger.info(f"    → API Call #{api_call_count}")
                    if "messages" in node_output:
                        last_msg = node_output["messages"][-1] if node_output["messages"] else None
                        if isinstance(last_msg, AIMessage):
                            if hasattr(last_msg, 'tool_calls') and last_msg.tool_calls:
                                logger.info(f"    → Agent decided to call {len(last_msg.tool_calls)} tool(s)")
                            else:
                                logger.info(f"    → Agent generating final answer")
                
                elif node_name == "tools":
                    tool_call_count += 1
                    logger.info(f"    → Tool Execution #{tool_call_count}")
                    if "messages" in node_output:
                        tool_msgs = [m for m in node_output["messages"] if isinstance(m, ToolMessage)]
                        logger.info(f"    → {len(tool_msgs)} tool result(s) returned")
            
            # Check if we're done
            if "messages" in chunk:
                last_message = chunk["messages"][-1] if chunk["messages"] else None
                if isinstance(last_message, AIMessage) and not (hasattr(last_message, 'tool_calls') and last_message.tool_calls):
                    logger.info("\n" + "=" * 70)
                    logger.info("QUERY EXECUTION COMPLETE")
                    logger.info("=" * 70)
                    logger.info(f"Total API Calls: {api_call_count}")
                    logger.info(f"Total Tool Executions: {tool_call_count}")
                    logger.info("=" * 70 + "\n")
                    return last_message.content
        
        # Fallback: use invoke if streaming didn't work
        logger.info("Using invoke fallback...")
        result = agent.invoke(initial_state)
        
        logger.info("\n" + "=" * 70)
        logger.info("QUERY EXECUTION COMPLETE (via invoke)")
        logger.info("=" * 70)
        logger.info(f"Total API Calls: {api_call_count}")
        logger.info(f"Total Tool Executions: {tool_call_count}")
        logger.info("=" * 70 + "\n")
        
        # Extract final answer from messages
        final_message = result["messages"][-1]
        if isinstance(final_message, AIMessage):
            logger.info(f"Query completed successfully")
            return final_message.content
        else:
            return str(final_message)
            
    except Exception as e:
        logger.error(f"Error in query agent: {e}", exc_info=True)
        return f"Error processing query: {str(e)}"


if __name__ == "__main__":
    # Example usage
    print("Legal Case Query Agent")
    print("=" * 50)
    
    examples = [
        "Find case 2025/2552",
        "Who are all the parties in case 2025/2552?",
        "What documents exist for case 2025/2552?",
        "What are the charges in case 2025/2552?",
        "Find all cases involving person with personal_id 29952",
        "Show me the timeline for case 2025/2552",
        "What is the judgment for case 2025/2552?",
    ]
    
    for example in examples:
        print(f"\nQuery: {example}")
        print("-" * 50)
        answer = query(example)
        print(f"Answer: {answer}")

