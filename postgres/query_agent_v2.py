"""
Query Agent v2 for Vector-Based Legal Case Management System
Natural language queries with vector search and JSONB querying
"""

from typing import Dict, List, Any, Optional, TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_groq import ChatGroq
from langchain_core.tools import tool, StructuredTool
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import logging
import time
from sentence_transformers import SentenceTransformer
import re

from config import CONFIG
from .db_manager_v2 import DatabaseManagerV2

# Token limits and chunking
MAX_TOKENS_PER_REQUEST = 3500  # Stay well under 6000 limit (accounting for system prompt and message history)
CHUNK_SIZE = 2000  # Characters per chunk (smaller chunks)
CHUNK_DELAY = 1.5  # Delay between chunks in seconds
MAX_ITEMS_IN_SUMMARY = 3  # Maximum items to show in summaries

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiting for Groq API
GROQ_RATE_LIMIT_DELAY = 2.0


class AgentState(TypedDict):
    messages: Annotated[List, "messages"]
    query: str
    results: Optional[List[Dict]]
    error: Optional[str]


# Schema information for the new JSONB-based architecture
SCHEMA_INFO = """
Database Schema for Qatar Legal Case Management System (v2 - JSONB Architecture):

TABLES:
1. cases - Main case information (JSONB-based)
   - case_id (PK)
   - case_numbers (JSONB): {"court": "...", "prosecution": "...", "police": "...", "variations": [...]}
   - parties (JSONB): Array of party objects with entity IDs, names, roles, relationships
   - key_dates (JSONB): {"incident": "...", "judgment": "...", etc.}
   - locations (JSONB): {"court": "...", "police_station": "...", etc.}
   - charges (JSONB): Array of charge objects with entity IDs, articles, status
   - judgments (JSONB): Array of judgment objects with verdicts, sentences
   - financial (JSONB): {"fines": [...], "damages": [...], "bail": ...}
   - evidence (JSONB): Array of evidence objects
   - case_status (JSONB): {"current_status": "...", "case_type": "...", "summary_ar": "...", etc.}
   - timeline (JSONB): Array of timeline events
   - legal_references (JSONB): Array of legal articles/laws cited

2. documents - Document metadata with vector embeddings
   - document_id (PK), case_id (FK)
   - file_path, file_hash, original_filename
   - document_metadata (JSONB): Type, number, date, author, language
   - extracted_entities (JSONB): All entities extracted from document
   - document_embedding (vector): For similarity search
   - confidence_score: Linking confidence
   - processing_status: 'pending', 'processed', 'error'

3. processing_log - Processing history
   - log_id (PK), file_path, case_id, document_id
   - processing_status, error_message, processing_time_ms

QUERYING JSONB:
- Access JSONB fields: cases->'case_numbers'->>'court'
- Query arrays: cases->'parties' @> '[{"name_ar": "محمد"}]'::jsonb
- Search in variations: cases->'case_numbers'->'variations' @> '["2552/2025"]'::jsonb
- Get party by entity ID: cases->'parties' @> '[{"party_entity_id": "P001"}]'::jsonb

COMMON QUERIES:
- Find case by reference number (any variation)
- Find all parties in a case (with roles and relationships)
- Find charges for a case (with status evolution)
- Find case timeline/events
- Search documents by semantic similarity
- Find cases by party name or personal_id
"""


# Query Tools
@tool
def query_cases(
    court_case_number: Optional[str] = None,
    prosecution_case_number: Optional[str] = None,
    police_report_number: Optional[str] = None,
    case_status: Optional[str] = None,
    case_type: Optional[str] = None,
    limit: int = 10
) -> str:
    """Find cases by reference numbers or status. Handles all number variations."""
    try:
        with DatabaseManagerV2(**CONFIG['database']) as db:
            results = []
            
            # Search by reference numbers
            if court_case_number:
                # If the user/LLM passed a pure integer, treat it as internal case_id first
                cc = str(court_case_number).strip()
                case_id = None
                if cc.isdigit():
                    candidate_id = int(cc)
                    if db.get_case(candidate_id):
                        case_id = candidate_id
                if not case_id:
                    case_id = db.find_case_by_reference('court', court_case_number)
                if case_id:
                    case = db.get_case(case_id)
                    if case:
                        results.append(case)
            
            if prosecution_case_number and not results:
                case_id = db.find_case_by_reference('prosecution', prosecution_case_number)
                if case_id:
                    case = db.get_case(case_id)
                    if case:
                        results.append(case)
            
            if police_report_number and not results:
                case_id = db.find_case_by_reference('police', police_report_number)
                if case_id:
                    case = db.get_case(case_id)
                    if case:
                        results.append(case)
            
            # If no results, try general search
            if not results:
                search_query = {}
                if case_status:
                    search_query['case_status'] = case_status
                if case_type:
                    search_query['case_type'] = case_type
                
                if search_query:
                    results = db.search_cases(search_query, limit=limit)

            # If the user provided a reference number but nothing matched, return an explicit error
            if not results and (court_case_number or prosecution_case_number or police_report_number):
                return json.dumps({
                    "error": "Case not found for provided reference number(s)",
                    "court_case_number": court_case_number,
                    "prosecution_case_number": prosecution_case_number,
                    "police_report_number": police_report_number
                }, ensure_ascii=False)

            return json.dumps([dict(r) for r in results], default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> List[str]:
    """Split text into chunks"""
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunks.append(text[i:i + chunk_size])
    return chunks


def _estimate_tokens(text: str) -> int:
    """Rough token estimation (1 token ≈ 4 characters)"""
    return len(text) // 4


def _normalize_arabic_name(value: str) -> str:
    """Normalize Arabic name for deduping (remove diacritics/tatweel and common letter variants)."""
    if not value:
        return ""
    s = str(value).strip()
    # Remove tatweel + harakat/diacritics
    s = re.sub(r"[\u0640\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]", "", s)
    # Normalize common variants
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ى", "ي").replace("ة", "ه")
    # Normalize whitespace
    s = " ".join(s.split())
    return s


def _dedupe_people(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate people returned from tools so the LLM doesn't have to guess.
    Priority: personal_id > normalized Arabic name > normalized English name.
    """
    merged: Dict[str, Dict[str, Any]] = {}

    for r in rows:
        pid = (r.get("personal_id") or "").strip()
        name_ar = (r.get("name_ar") or "").strip()
        name_en = (r.get("name_en") or "").strip()

        if pid:
            key = f"id:{pid}"
        else:
            nar = _normalize_arabic_name(name_ar)
            if nar:
                key = f"ar:{nar}"
            elif name_en:
                key = f"en:{' '.join(name_en.lower().split())}"
            else:
                # Can't dedupe reliably
                continue

        cur = merged.get(key, {"name_ar": "", "name_en": "", "personal_id": None})

        # Prefer Arabic; keep longer (more complete) strings
        if name_ar and (not cur["name_ar"] or len(name_ar) > len(cur["name_ar"])):
            cur["name_ar"] = name_ar
        if name_en and (not cur["name_en"] or len(name_en) > len(cur["name_en"])):
            cur["name_en"] = name_en
        if pid and not cur.get("personal_id"):
            cur["personal_id"] = pid

        merged[key] = cur

    return list(merged.values())


def _summarize_large_data(data: Dict[str, Any], max_items: int = 10) -> Dict[str, Any]:
    """Summarize large data structures to reduce size"""
    summarized = {}
    
    for key, value in data.items():
        if isinstance(value, list):
            if len(value) > max_items:
                summarized[key] = {
                    "total_count": len(value),
                    "items": value[:max_items],
                    "note": f"... and {len(value) - max_items} more items (truncated)"
                }
            else:
                summarized[key] = value
        elif isinstance(value, dict):
            summarized[key] = _summarize_large_data(value, max_items)
        else:
            summarized[key] = value
    
    return summarized


@tool
def query_case_details(case_id: int, summarize: bool = True) -> str:
    """Get comprehensive details for a specific case including all parties, charges, timeline.
    If summarize=True, returns a summary for large cases to avoid token limits."""
    try:
        with DatabaseManagerV2(**CONFIG['database']) as db:
            case = db.get_case(case_id)
            if not case:
                return json.dumps({"error": f"Case {case_id} not found"}, ensure_ascii=False)
            
            # Get all documents for this case
            documents = db.get_documents_by_case(case_id)
            
            # Prepare response
            response_data = dict(case)
            
            # If summarize is True or data is too large, summarize it
            full_response = json.dumps(response_data, default=str, ensure_ascii=False)
            estimated_tokens = _estimate_tokens(full_response)
            
            if summarize or estimated_tokens > MAX_TOKENS_PER_REQUEST:
                logger.info(f"Case {case_id} data is large ({estimated_tokens} tokens), summarizing aggressively...")
                # Aggressively summarize large arrays
                response_data = _summarize_large_data(response_data, max_items=MAX_ITEMS_IN_SUMMARY)
                # Limit documents to just count and sample
                if len(documents) > 0:
                    response_data['documents'] = {
                        "total_count": len(documents),
                        "sample": documents[:MAX_ITEMS_IN_SUMMARY] if len(documents) > MAX_ITEMS_IN_SUMMARY else documents,
                        "note": f"... and {len(documents) - MAX_ITEMS_IN_SUMMARY} more documents" if len(documents) > MAX_ITEMS_IN_SUMMARY else ""
                    }
                else:
                    response_data['documents'] = []
            else:
                response_data['documents'] = documents
            
            return json.dumps(response_data, default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_case_parties(case_id: int, role: Optional[str] = None) -> str:
    """Get all parties for a case, optionally filtered by role (accused, complainant, victim, etc.)."""
    try:
        with DatabaseManagerV2(**CONFIG['database']) as db:
            # Query ONLY the parties field
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT parties FROM cases WHERE case_id = %s", (case_id,))
                result = cursor.fetchone()
                if not result:
                    return json.dumps({"error": f"Case {case_id} not found"}, ensure_ascii=False)
                
                parties = result.get('parties', []) or []
            
            # Log size
            parties_tokens = _estimate_tokens(json.dumps(parties, default=str, ensure_ascii=False))
            logger.info(f"query_case_parties: Retrieved {len(parties)} parties (~{parties_tokens} tokens)")
            
            # Sanity check
            if len(parties) > 1000:
                logger.warning(f"WARNING: Case {case_id} has {len(parties)} parties - this seems excessive")
            
            if role:
                # Filter by role
                parties = [p for p in parties if role.lower() in [r.lower() for r in (p.get('roles', []) or [p.get('role', '')])]]
            
            # Deduplicate and limit
            seen_parties = set()
            unique_parties = []
            for party in parties:
                name_ar = party.get('name_ar', '')
                name_en = party.get('name_en', '')
                party_key = f"{name_ar}|{name_en}".strip()
                
                if party_key and party_key not in seen_parties:
                    seen_parties.add(party_key)
                    unique_parties.append(party)
                
                # Limit to 50
                if len(unique_parties) >= 50:
                    break
            
            # If too many, return summary
            if len(unique_parties) > 20:
                result = {
                    'total_parties': len(unique_parties),
                    'sample': unique_parties[:10],
                    'note': f'Showing first 10 of {len(unique_parties)} parties. Use query_case_details for complete list.'
                }
            else:
                result = unique_parties
            
            result_json = json.dumps(result, default=str, ensure_ascii=False)
            result_tokens = _estimate_tokens(result_json)
            logger.info(f"query_case_parties: Returning {len(unique_parties) if isinstance(result, list) else result.get('total_parties', 0)} parties ({result_tokens} tokens)")
            
            return result_json
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_victims(case_id: Optional[int] = None, court_case_number: Optional[str] = None) -> str:
    """Get only victim information for a case. Use this when user asks about victims specifically.
    Provide either case_id or court_case_number."""
    try:
        with DatabaseManagerV2(**CONFIG['database']) as db:
            # Prefer normalized entity tables if available
            if db.table_exists("case_parties") and db.table_exists("parties"):
                # Resolve case_id if only court_case_number provided
                if not case_id and court_case_number:
                    cc = str(court_case_number).strip()
                    if cc.isdigit():
                        candidate_id = int(cc)
                        if db.get_case(candidate_id):
                            case_id = candidate_id
                    if not case_id:
                        case_id = db.find_case_by_reference('court', court_case_number)
                        if not case_id:
                            return json.dumps({"error": f"Case with number {court_case_number} not found"}, ensure_ascii=False)

                if not case_id:
                    return json.dumps({"error": "Please provide either case_id or court_case_number"}, ensure_ascii=False)

                with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        """
                        SELECT p.name_ar, p.name_en, p.personal_id, cp.role_type
                        FROM case_parties cp
                        JOIN parties p ON p.party_id = cp.party_id
                        WHERE cp.case_id = %s
                          AND (cp.role_type ILIKE 'victim%%' OR cp.role_type ILIKE '%%victim%%' OR cp.role_type LIKE '%%ضحية%%')
                        LIMIT 50
                        """,
                        (case_id,)
                    )
                    rows = cursor.fetchall() or []

                victims = [
                    {"name_ar": r.get("name_ar", ""), "name_en": r.get("name_en", ""), "personal_id": r.get("personal_id")}
                    for r in rows
                ]
                victims = _dedupe_people(victims)

                if not victims:
                    return json.dumps(
                        {
                            "case_id": case_id,
                            "total_victims": 0,
                            "victims": [],
                            "note": "Case exists but no victims were detected in normalized case_parties roles."
                        },
                        ensure_ascii=False
                    )

                return json.dumps(
                    {
                        "case_id": case_id,
                        "total_victims": len(victims),
                        "victims": victims,
                        "note": "Deduplicated by personal_id when present; otherwise by normalized Arabic name."
                    },
                    ensure_ascii=False
                )

            # Find case if only case number provided
            if not case_id and court_case_number:
                # If we got a pure integer, treat it as internal case_id first
                cc = str(court_case_number).strip()
                if cc.isdigit():
                    candidate_id = int(cc)
                    if db.get_case(candidate_id):
                        case_id = candidate_id
                if not case_id:
                    case_id = db.find_case_by_reference('court', court_case_number)
                if not case_id:
                    return json.dumps({"error": f"Case with number {court_case_number} not found"}, ensure_ascii=False)
            
            if not case_id:
                return json.dumps({"error": "Please provide either case_id or court_case_number"}, ensure_ascii=False)
            
            # Query ONLY the parties field, not the entire case!
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT parties FROM cases WHERE case_id = %s", (case_id,))
                result = cursor.fetchone()
                if not result:
                    return json.dumps({"error": f"Case {case_id} not found"}, ensure_ascii=False)
                
                all_parties = result.get('parties', []) or []
            
            # Log the size of parties field
            parties_json = json.dumps(all_parties, default=str, ensure_ascii=False)
            parties_tokens = _estimate_tokens(parties_json)
            logger.info(f"query_victims: Retrieved parties field ({len(all_parties)} parties, ~{parties_tokens} tokens)")
            
            # Sanity check - if there are too many parties, something is wrong
            if len(all_parties) > 1000:
                logger.warning(f"WARNING: Case {case_id} has {len(all_parties)} parties - this seems excessive, likely data corruption/duplication")
            
            # (debug) do not print parties to stdout; it can be extremely large
            # Filter only victims - return minimal data (just names)
            victims = []
            seen_names = set()  # Deduplicate by name
            for party in all_parties:
                roles = party.get('roles', []) or [party.get('role', '')]
                if any('victim' in str(r).lower() or 'ضحية' in str(r) for r in roles):
                    name_ar = party.get('name_ar', '')
                    name_en = party.get('name_en', '')
                    # Create unique key for deduplication
                    name_key = (name_ar or '').strip() + '|' + (name_en or '').strip()
                    
                    # Skip if we've seen this name before (deduplication)
                    if name_key and name_key not in seen_names:
                        seen_names.add(name_key)
                        victims.append({
                            'name_ar': name_ar,
                            'name_en': name_en,
                            'personal_id': party.get('personal_id')
                        })
                    
                    # Limit to first 50 unique victims to prevent huge responses
                    if len(victims) >= 50:
                        logger.warning(f"Limiting victims to first 50 (found {len(victims)} unique victims)")
                        break
            
            # If still too many, return summary instead
            if len(victims) > 20:
                result = {
                    'case_id': case_id,
                    'parties_total': len(all_parties),
                    'total_victims': len(victims),
                    'sample': victims[:10],  # Show first 10
                    'note': f'Showing first 10 of {len(victims)} victims. Use query_case_details for complete list.'
                }
            else:
                # If none found, return explicit structured info (avoid LLM guessing "case not found")
                if len(victims) == 0:
                    result = {
                        'case_id': case_id,
                        'parties_total': len(all_parties),
                        'total_victims': 0,
                        'victims': [],
                        'note': (
                            "Case exists but no victims were detected based on party roles. "
                            "This may mean roles are missing/incorrect in extracted data."
                        )
                    }
                else:
                    result = {
                        'case_id': case_id,
                        'parties_total': len(all_parties),
                        'total_victims': len(victims),
                        'victims': victims
                    }
            
            result_json = json.dumps(result, default=str, ensure_ascii=False)
            result_tokens = _estimate_tokens(result_json)
            logger.info(f"query_victims: Returning {len(victims) if isinstance(result, list) else result.get('total_victims', 0)} victims ({result_tokens} tokens)")
            
            return result_json
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_accused(case_id: Optional[int] = None, court_case_number: Optional[str] = None) -> str:
    """Get only accused/defendant information for a case. Use this when user asks about the accused specifically.
    Provide either case_id or court_case_number."""
    try:
        with DatabaseManagerV2(**CONFIG['database']) as db:
            # Prefer normalized entity tables if available
            if db.table_exists("case_parties") and db.table_exists("parties"):
                if not case_id and court_case_number:
                    cc = str(court_case_number).strip()
                    if cc.isdigit():
                        candidate_id = int(cc)
                        if db.get_case(candidate_id):
                            case_id = candidate_id
                    if not case_id:
                        case_id = db.find_case_by_reference('court', court_case_number)
                        if not case_id:
                            return json.dumps({"error": f"Case with number {court_case_number} not found"}, ensure_ascii=False)

                if not case_id:
                    return json.dumps({"error": "Please provide either case_id or court_case_number"}, ensure_ascii=False)

                with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        """
                        SELECT p.name_ar, p.name_en, p.personal_id, cp.role_type
                        FROM case_parties cp
                        JOIN parties p ON p.party_id = cp.party_id
                        WHERE cp.case_id = %s
                          AND (cp.role_type ILIKE 'accused%%' OR cp.role_type ILIKE '%%accused%%'
                               OR cp.role_type ILIKE 'defendant%%' OR cp.role_type ILIKE '%%defendant%%'
                               OR cp.role_type LIKE '%%متهم%%')
                        LIMIT 50
                        """,
                        (case_id,)
                    )
                    rows = cursor.fetchall() or []

                accused = [
                    {"name_ar": r.get("name_ar", ""), "name_en": r.get("name_en", ""), "personal_id": r.get("personal_id")}
                    for r in rows
                ]
                accused = _dedupe_people(accused)

                if not accused:
                    return json.dumps(
                        {
                            "case_id": case_id,
                            "total_accused": 0,
                            "accused": [],
                            "note": "Case exists but no accused were detected in normalized case_parties roles."
                        },
                        ensure_ascii=False
                    )

                return json.dumps(
                    {
                        "case_id": case_id,
                        "total_accused": len(accused),
                        "accused": accused,
                        "note": "Deduplicated by personal_id when present; otherwise by normalized Arabic name."
                    },
                    ensure_ascii=False
                )

            # Find case if only case number provided
            if not case_id and court_case_number:
                cc = str(court_case_number).strip()
                if cc.isdigit():
                    candidate_id = int(cc)
                    if db.get_case(candidate_id):
                        case_id = candidate_id
                if not case_id:
                    case_id = db.find_case_by_reference('court', court_case_number)
                if not case_id:
                    return json.dumps({"error": f"Case with number {court_case_number} not found"}, ensure_ascii=False)
            
            if not case_id:
                return json.dumps({"error": "Please provide either case_id or court_case_number"}, ensure_ascii=False)
            
            # Query ONLY the parties field, not the entire case!
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT parties FROM cases WHERE case_id = %s", (case_id,))
                result = cursor.fetchone()
                if not result:
                    return json.dumps({"error": f"Case {case_id} not found"}, ensure_ascii=False)
                
                all_parties = result.get('parties', []) or []
            
            # Log the size of parties field
            parties_tokens = _estimate_tokens(json.dumps(all_parties, default=str, ensure_ascii=False))
            logger.info(f"query_accused: Retrieved parties field ({len(all_parties)} parties, ~{parties_tokens} tokens)")
            
            # Sanity check
            if len(all_parties) > 1000:
                logger.warning(f"WARNING: Case {case_id} has {len(all_parties)} parties - this seems excessive, likely data corruption/duplication")
            
            # Filter only accused - return minimal data (just names)
            accused = []
            seen_names = set()  # Deduplicate by name
            for party in all_parties:
                roles = party.get('roles', []) or [party.get('role', '')]
                if any('accused' in str(r).lower() or 'defendant' in str(r).lower() or 'متهم' in str(r) for r in roles):
                    name_ar = party.get('name_ar', '')
                    name_en = party.get('name_en', '')
                    name_key = (name_ar or '').strip() + '|' + (name_en or '').strip()
                    
                    if name_key and name_key not in seen_names:
                        seen_names.add(name_key)
                        accused.append({
                            'name_ar': name_ar,
                            'name_en': name_en,
                            'personal_id': party.get('personal_id')
                        })
                    
                    # Limit to first 50 unique accused
                    if len(accused) >= 50:
                        logger.warning(f"Limiting accused to first 50 (found {len(accused)} unique accused)")
                        break
            
            # If still too many, return summary instead
            if len(accused) > 20:
                result = {
                    'total_accused': len(accused),
                    'sample': accused[:10],
                    'note': f'Showing first 10 of {len(accused)} accused. Use query_case_details for complete list.'
                }
            else:
                result = accused
            
            result_json = json.dumps(result, default=str, ensure_ascii=False)
            result_tokens = _estimate_tokens(result_json)
            logger.info(f"query_accused: Returning {len(accused) if isinstance(result, list) else result.get('total_accused', 0)} accused ({result_tokens} tokens)")
            
            return result_json
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_judgments_only(case_id: Optional[int] = None, court_case_number: Optional[str] = None) -> str:
    """Get only judgment/verdict information for a case. Use this when user asks about judgments, verdicts, or sentences specifically.
    Provide either case_id or court_case_number."""
    try:
        with DatabaseManagerV2(**CONFIG['database']) as db:
            # Find case if only case number provided
            if not case_id and court_case_number:
                cc = str(court_case_number).strip()
                if cc.isdigit():
                    candidate_id = int(cc)
                    if db.get_case(candidate_id):
                        case_id = candidate_id
                if not case_id:
                    case_id = db.find_case_by_reference('court', court_case_number)
                if not case_id:
                    return json.dumps({"error": f"Case with number {court_case_number} not found"}, ensure_ascii=False)
            
            if not case_id:
                return json.dumps({"error": "Please provide either case_id or court_case_number"}, ensure_ascii=False)
            
            # Query ONLY the judgments field, not the entire case!
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT judgments FROM cases WHERE case_id = %s", (case_id,))
                result = cursor.fetchone()
                if not result:
                    return json.dumps({"error": f"Case {case_id} not found"}, ensure_ascii=False)
                
                judgments = result.get('judgments', []) or []
            
            # Log size
            judgments_tokens = _estimate_tokens(json.dumps(judgments, default=str, ensure_ascii=False))
            logger.info(f"query_judgments_only: Retrieved {len(judgments)} judgments (~{judgments_tokens} tokens)")
            
            # Sanity check
            if len(judgments) > 100:
                logger.warning(f"WARNING: Case {case_id} has {len(judgments)} judgments - this seems excessive")
            
            # Limit and summarize if too many
            if len(judgments) > 20:
                # Return most recent judgments (sorted by date)
                sorted_judgments = sorted(judgments, key=lambda x: x.get('judgment_date', ''), reverse=True)
                result = {
                    'total_judgments': len(judgments),
                    'recent': sorted_judgments[:10],  # Most recent 10
                    'note': f'Showing most recent 10 of {len(judgments)} judgments. Use query_case_details for complete list.'
                }
            else:
                result = judgments
            
            result_json = json.dumps(result, default=str, ensure_ascii=False)
            result_tokens = _estimate_tokens(result_json)
            logger.info(f"query_judgments_only: Returning {len(judgments) if isinstance(result, list) else result.get('total_judgments', 0)} judgments ({result_tokens} tokens)")
            
            return result_json
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_charges_only(case_id: Optional[int] = None, court_case_number: Optional[str] = None) -> str:
    """Get only charge information for a case. Use this when user asks about charges or crimes specifically.
    Provide either case_id or court_case_number."""
    try:
        with DatabaseManagerV2(**CONFIG['database']) as db:
            # Prefer normalized entity tables if available
            if db.table_exists("case_charges") and db.table_exists("charges"):
                if not case_id and court_case_number:
                    cc = str(court_case_number).strip()
                    if cc.isdigit():
                        candidate_id = int(cc)
                        if db.get_case(candidate_id):
                            case_id = candidate_id
                    if not case_id:
                        case_id = db.find_case_by_reference('court', court_case_number)
                        if not case_id:
                            return json.dumps({"error": f"Case with number {court_case_number} not found"}, ensure_ascii=False)

                if not case_id:
                    return json.dumps({"error": "Please provide either case_id or court_case_number"}, ensure_ascii=False)

                with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        """
                        SELECT c.article_number, c.description_ar, c.description_en, cc.status
                        FROM case_charges cc
                        JOIN charges c ON c.charge_id = cc.charge_id
                        WHERE cc.case_id = %s
                        LIMIT 50
                        """,
                        (case_id,)
                    )
                    rows = cursor.fetchall() or []

                charges = [dict(r) for r in rows]
                return json.dumps(
                    {"case_id": case_id, "total_charges": len(charges), "charges": charges},
                    default=str,
                    ensure_ascii=False
                )

            # Find case if only case number provided
            if not case_id and court_case_number:
                cc = str(court_case_number).strip()
                if cc.isdigit():
                    candidate_id = int(cc)
                    if db.get_case(candidate_id):
                        case_id = candidate_id
                if not case_id:
                    case_id = db.find_case_by_reference('court', court_case_number)
                if not case_id:
                    return json.dumps({"error": f"Case with number {court_case_number} not found"}, ensure_ascii=False)
            
            if not case_id:
                return json.dumps({"error": "Please provide either case_id or court_case_number"}, ensure_ascii=False)
            
            # Query ONLY the charges field, not the entire case!
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT charges FROM cases WHERE case_id = %s", (case_id,))
                result = cursor.fetchone()
                if not result:
                    return json.dumps({"error": f"Case {case_id} not found"}, ensure_ascii=False)
                
                charges = result.get('charges', []) or []
            
            # Log size
            charges_tokens = _estimate_tokens(json.dumps(charges, default=str, ensure_ascii=False))
            logger.info(f"query_charges_only: Retrieved {len(charges)} charges (~{charges_tokens} tokens)")
            
            # Sanity check
            if len(charges) > 100:
                logger.warning(f"WARNING: Case {case_id} has {len(charges)} charges - this seems excessive")
            
            # Deduplicate charges by article number and description
            seen_charges = set()
            unique_charges = []
            for charge in charges:
                article = charge.get('article_number', '')
                desc = charge.get('description_ar', '') or charge.get('description_en', '')
                charge_key = f"{article}|{desc}".strip()
                
                if charge_key and charge_key not in seen_charges:
                    seen_charges.add(charge_key)
                    unique_charges.append(charge)
            
            # Limit if too many
            if len(unique_charges) > 20:
                result = {
                    'total_charges': len(unique_charges),
                    'sample': unique_charges[:10],
                    'note': f'Showing first 10 of {len(unique_charges)} charges. Use query_case_details for complete list.'
                }
            else:
                result = unique_charges
            
            result_json = json.dumps(result, default=str, ensure_ascii=False)
            result_tokens = _estimate_tokens(result_json)
            logger.info(f"query_charges_only: Returning {len(unique_charges) if isinstance(result, list) else result.get('total_charges', 0)} charges ({result_tokens} tokens)")
            
            return result_json
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_evidence_only(case_id: Optional[int] = None, court_case_number: Optional[str] = None) -> str:
    """Get only evidence information for a case. Use this when user asks about evidence specifically.
    Provide either case_id or court_case_number."""
    try:
        with DatabaseManagerV2(**CONFIG['database']) as db:
            # Prefer normalized entity tables if available
            if db.table_exists("case_evidence") and db.table_exists("evidence_items"):
                if not case_id and court_case_number:
                    cc = str(court_case_number).strip()
                    if cc.isdigit():
                        candidate_id = int(cc)
                        if db.get_case(candidate_id):
                            case_id = candidate_id
                    if not case_id:
                        case_id = db.find_case_by_reference('court', court_case_number)
                        if not case_id:
                            return json.dumps({"error": f"Case with number {court_case_number} not found"}, ensure_ascii=False)

                if not case_id:
                    return json.dumps({"error": "Please provide either case_id or court_case_number"}, ensure_ascii=False)

                with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        """
                        SELECT e.evidence_type, e.description_ar, e.description_en, e.collected_date, e.location
                        FROM case_evidence ce
                        JOIN evidence_items e ON e.evidence_id = ce.evidence_id
                        WHERE ce.case_id = %s
                        LIMIT 50
                        """,
                        (case_id,)
                    )
                    rows = cursor.fetchall() or []

                evidence = [dict(r) for r in rows]
                return json.dumps(
                    {"case_id": case_id, "total_evidence": len(evidence), "evidence": evidence},
                    default=str,
                    ensure_ascii=False
                )

            # Find case if only case number provided
            if not case_id and court_case_number:
                cc = str(court_case_number).strip()
                if cc.isdigit():
                    candidate_id = int(cc)
                    if db.get_case(candidate_id):
                        case_id = candidate_id
                if not case_id:
                    case_id = db.find_case_by_reference('court', court_case_number)
                if not case_id:
                    return json.dumps({"error": f"Case with number {court_case_number} not found"}, ensure_ascii=False)
            
            if not case_id:
                return json.dumps({"error": "Please provide either case_id or court_case_number"}, ensure_ascii=False)
            
            # Query ONLY the evidence field, not the entire case!
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT evidence FROM cases WHERE case_id = %s", (case_id,))
                result = cursor.fetchone()
                if not result:
                    return json.dumps({"error": f"Case {case_id} not found"}, ensure_ascii=False)
                
                evidence = result.get('evidence', []) or []
            
            # Log size
            evidence_tokens = _estimate_tokens(json.dumps(evidence, default=str, ensure_ascii=False))
            logger.info(f"query_evidence_only: Retrieved {len(evidence)} evidence items (~{evidence_tokens} tokens)")
            
            # Sanity check
            if len(evidence) > 100:
                logger.warning(f"WARNING: Case {case_id} has {len(evidence)} evidence items - this seems excessive")
            
            # Deduplicate evidence by description
            seen_evidence = set()
            unique_evidence = []
            for ev in evidence:
                desc_ar = ev.get('description_ar', '')
                desc_en = ev.get('description_en', '')
                ev_type = ev.get('type', '')
                ev_key = f"{ev_type}|{desc_ar}|{desc_en}".strip()
                
                if ev_key and ev_key not in seen_evidence:
                    seen_evidence.add(ev_key)
                    unique_evidence.append(ev)
            
            # Limit if too many
            if len(unique_evidence) > 20:
                result = {
                    'total_evidence': len(unique_evidence),
                    'sample': unique_evidence[:10],
                    'note': f'Showing first 10 of {len(unique_evidence)} evidence items. Use query_case_details for complete list.'
                }
            else:
                result = unique_evidence
            
            result_json = json.dumps(result, default=str, ensure_ascii=False)
            result_tokens = _estimate_tokens(result_json)
            logger.info(f"query_evidence_only: Returning {len(unique_evidence) if isinstance(result, list) else result.get('total_evidence', 0)} evidence items ({result_tokens} tokens)")
            
            return result_json
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_case_charges(case_id: int) -> str:
    """Get all charges for a case with their status and legal articles."""
    try:
        with DatabaseManagerV2(**CONFIG['database']) as db:
            # Query ONLY the charges field
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT charges FROM cases WHERE case_id = %s", (case_id,))
                result = cursor.fetchone()
                if not result:
                    return json.dumps({"error": f"Case {case_id} not found"}, ensure_ascii=False)
                
                charges = result.get('charges', []) or []
            
            # Log size
            charges_tokens = _estimate_tokens(json.dumps(charges, default=str, ensure_ascii=False))
            logger.info(f"query_case_charges: Retrieved {len(charges)} charges (~{charges_tokens} tokens)")
            
            # Sanity check
            if len(charges) > 100:
                logger.warning(f"WARNING: Case {case_id} has {len(charges)} charges - this seems excessive")
            
            # Deduplicate charges
            seen_charges = set()
            unique_charges = []
            for charge in charges:
                article = charge.get('article_number', '')
                desc = charge.get('description_ar', '') or charge.get('description_en', '')
                charge_key = f"{article}|{desc}".strip()
                
                if charge_key and charge_key not in seen_charges:
                    seen_charges.add(charge_key)
                    unique_charges.append(charge)
            
            # Limit if too many
            if len(unique_charges) > 20:
                result = {
                    'total_charges': len(unique_charges),
                    'sample': unique_charges[:10],
                    'note': f'Showing first 10 of {len(unique_charges)} charges. Use query_case_details for complete list.'
                }
            else:
                result = unique_charges
            
            result_json = json.dumps(result, default=str, ensure_ascii=False)
            result_tokens = _estimate_tokens(result_json)
            logger.info(f"query_case_charges: Returning {len(unique_charges) if isinstance(result, list) else result.get('total_charges', 0)} charges ({result_tokens} tokens)")
            
            return result_json
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_case_timeline(case_id: int) -> str:
    """Get chronological timeline of events for a case."""
    try:
        with DatabaseManagerV2(**CONFIG['database']) as db:
            case = db.get_case(case_id)
            if not case:
                return json.dumps({"error": f"Case {case_id} not found"}, ensure_ascii=False)
            
            timeline = case.get('timeline', [])
            key_dates = case.get('key_dates', {})
            
            # Combine timeline and key_dates
            result = {
                'timeline_events': timeline,
                'key_dates': key_dates
            }
            
            return json.dumps(result, default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def search_documents_semantic(query_text: str, case_id: Optional[int] = None, limit: int = 10) -> str:
    """Search documents using semantic similarity with FAISS. Provide natural language query."""
    try:
        # Generate embedding for query
        embedding_model = SentenceTransformer(CONFIG['embeddings']['model'], device=CONFIG['embeddings']['device'])
        query_embedding = embedding_model.encode(query_text, convert_to_numpy=True).tolist()
        
        with DatabaseManagerV2(**CONFIG['database']) as db:
            # Find similar documents using FAISS
            similar_docs = db.find_similar_documents(
                query_embedding,
                threshold=0.7,  # Lower threshold for search
                limit=limit
            )
            
            # Filter by case_id if provided
            if case_id:
                similar_docs = [d for d in similar_docs if d.get('case_id') == case_id]
            
            return json.dumps(similar_docs, default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_by_party_name(name: str, limit: int = 10) -> str:
    """Find cases by party name (Arabic or English)."""
    try:
        with DatabaseManagerV2(**CONFIG['database']) as db:
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                # Search in parties JSONB array
                sql = """
                    SELECT case_id, case_numbers, parties, case_status
                    FROM cases
                    WHERE parties @> %s::jsonb
                       OR parties::text ILIKE %s
                    LIMIT %s
                """
                name_json = json.dumps([{"name_ar": name}])
                name_pattern = f"%{name}%"
                cursor.execute(sql, (name_json, name_pattern, limit))
                results = cursor.fetchall()
                
                return json.dumps([dict(r) for r in results], default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def query_by_personal_id(personal_id: str) -> str:
    """Find cases by party personal ID."""
    try:
        with DatabaseManagerV2(**CONFIG['database']) as db:
            with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                sql = """
                    SELECT case_id, case_numbers, parties, case_status
                    FROM cases
                    WHERE parties @> %s::jsonb
                """
                id_json = json.dumps([{"personal_id": personal_id}])
                cursor.execute(sql, (id_json,))
                results = cursor.fetchall()
                
                return json.dumps([dict(r) for r in results], default=str, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def execute_custom_jsonb_query(query_description: str) -> str:
    """
    Execute a custom JSONB query. Use this for complex queries not covered by other tools.
    Only SELECT queries are allowed. Describe what you want to find.
    """
    try:
        # This is a simplified version - in production, you'd want more sophisticated query generation
        # For now, return a message suggesting to use specific tools
        return json.dumps({
            "message": "For complex queries, please use the specific query tools available. "
                      "If you need something specific, describe it clearly and I'll use the appropriate tool."
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# Ensure all tools have names
def ensure_tool_names(tools):
    """Ensure all tools have explicit names for Groq compatibility"""
    named_tools = []
    for tool_obj in tools:
        if isinstance(tool_obj, StructuredTool):
            named_tools.append(tool_obj)
        else:
            # Convert to StructuredTool with explicit name
            name = getattr(tool_obj, 'name', tool_obj.func.__name__)
            named_tools.append(StructuredTool.from_function(
                tool_obj.func,
                name=name,
                description=tool_obj.description
            ))
    return named_tools


# Create tools list
tools = [
    query_cases,
    query_case_details,  # Use for comprehensive queries
    query_case_parties,
    query_case_charges,
    query_case_timeline,
    query_victims,  # Specific tool for victim queries
    query_accused,  # Specific tool for accused queries
    query_judgments_only,  # Specific tool for judgment queries
    query_charges_only,  # Specific tool for charge queries
    query_evidence_only,  # Specific tool for evidence queries
    search_documents_semantic,
    query_by_party_name,
    query_by_personal_id,
    execute_custom_jsonb_query
]

# Ensure tool names
tools = ensure_tool_names(tools)
tool_node = ToolNode(tools)


def create_agent():
    """Create LangGraph agent"""
    
    # System prompt
    system_prompt = f"""You are an expert assistant for querying a Qatar Legal Case Management System.

{SCHEMA_INFO}

IMPORTANT:
- Use the available tools to answer user queries
- The database uses JSONB for flexible data storage
- Case numbers may have variations - search all variations
- IMPORTANT: When a user says "case 1", "case 2", etc. they almost always mean the internal database case_id (integer PK).
  Court/prosecution/police reference numbers are NOT the same as case_id and usually contain slashes/years (e.g. "2552/2025").
- Parties have entity IDs (P001, P002, etc.) and relationships
- Charges have entity IDs (C001, C002, etc.) and status evolution
- Use semantic search for document queries
- Always return comprehensive results

Available tools:
- query_cases: Find cases by reference numbers or status
- query_case_details: Get full case details (use only when user asks for comprehensive/complete information)
- query_case_parties: Get parties for a case
- query_case_charges: Get charges for a case
- query_case_timeline: Get case timeline
- query_victims: Get ONLY victim information (use when user asks "who was the victim?", "victims?", etc.)
- query_accused: Get ONLY accused/defendant information (use when user asks "who was accused?", "defendant?", etc.)
- query_judgments_only: Get ONLY judgments/verdicts (use when user asks about judgments, verdicts, sentences)
- query_charges_only: Get ONLY charges (use when user asks about charges, crimes, offenses)
- query_evidence_only: Get ONLY evidence (use when user asks about evidence)
- search_documents_semantic: Semantic document search
- query_by_party_name: Find cases by party name
- query_by_personal_id: Find cases by personal ID

IMPORTANT: 
- For specific questions (e.g., "who was the victim?"), use the targeted tool (query_victims) instead of query_case_details
- Only use query_case_details when the user explicitly asks for "all details", "complete information", "full case", etc.
- Be concise and return only what was asked for
- If a targeted tool returns an empty result (e.g., 0 victims), answer "none found for this case" rather than searching other cases unless the user asked you to broaden the search.

CRITICAL: Use the standard OpenAI-compatible function calling format - do NOT use XML tags or custom formats."""

    # Initialize LLM
    llm = ChatGroq(
        model=CONFIG['groq']['model'],
        temperature=0.1,
        groq_api_key=CONFIG['groq']['api_key']
    )
    
    # Create graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.add_node("process_responses", process_tool_responses)
    
    # Set entry point
    workflow.set_entry_point("agent")
    
    # Add conditional edges
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "continue": "tools",
            "end": END
        }
    )
    
    # Process tool responses before sending back to agent
    workflow.add_edge("tools", "process_responses")
    workflow.add_edge("process_responses", "agent")
    
    # Compile graph
    app = workflow.compile()
    
    return app


def _process_large_tool_response(tool_response: str, llm: ChatGroq) -> str:
    """Process large tool responses by chunking and summarizing aggressively"""
    estimated_tokens = _estimate_tokens(tool_response)
    
    if estimated_tokens <= MAX_TOKENS_PER_REQUEST:
        return tool_response
    
    logger.info(f"Tool response is large ({estimated_tokens} tokens), processing aggressively...")
    
    # Try to parse as JSON first - if it's a simple array, extract directly
    try:
        data = json.loads(tool_response)
        
        # If it's a simple array of objects (like victims, charges), extract key fields
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            # Extract only essential fields from each item
            simplified = []
            for item in data:
                simplified_item = {}
                # Keep only name fields and essential identifiers
                for key in ['name_ar', 'name_en', 'personal_id', 'verdict', 'judgment_date', 
                           'article_number', 'description_ar', 'type', 'description_ar', 
                           'sentence_type', 'fine_amount', 'duration_days', 'collected_date']:
                    if key in item:
                        simplified_item[key] = item[key]
                if simplified_item:
                    simplified.append(simplified_item)
            
            simplified_json = json.dumps(simplified, ensure_ascii=False)
            simplified_tokens = _estimate_tokens(simplified_json)
            
            if simplified_tokens <= MAX_TOKENS_PER_REQUEST:
                logger.info(f"Extracted simplified data from array ({simplified_tokens} tokens)")
                return simplified_json
        
        # If it's a dict, extract key fields
        if isinstance(data, dict):
            # Create a very concise summary
            summary_parts = []
            # Case numbers
            if 'case_numbers' in data:
                summary_parts.append(f"Case Numbers: {json.dumps(data['case_numbers'], ensure_ascii=False)}")
            
            # Parties (limit to MAX_ITEMS_IN_SUMMARY)
            if 'parties' in data:
                parties = data['parties'][:MAX_ITEMS_IN_SUMMARY] if isinstance(data['parties'], list) else []
                total = len(data['parties']) if isinstance(data['parties'], list) else 0
                summary_parts.append(f"Parties ({total} total): {json.dumps(parties, ensure_ascii=False)}")
            
            # Charges (limit to MAX_ITEMS_IN_SUMMARY)
            if 'charges' in data:
                charges = data['charges'][:MAX_ITEMS_IN_SUMMARY] if isinstance(data['charges'], list) else []
                total = len(data['charges']) if isinstance(data['charges'], list) else 0
                summary_parts.append(f"Charges ({total} total): {json.dumps(charges, ensure_ascii=False)}")
            
            # Judgments (limit to 2)
            if 'judgments' in data:
                judgments = data['judgments'][:2] if isinstance(data['judgments'], list) else []
                total = len(data['judgments']) if isinstance(data['judgments'], list) else 0
                summary_parts.append(f"Judgments ({total} total): {json.dumps(judgments, ensure_ascii=False)}")
            
            # Evidence (limit to 2)
            if 'evidence' in data:
                evidence = data['evidence'][:2] if isinstance(data['evidence'], list) else []
                total = len(data['evidence']) if isinstance(data['evidence'], list) else 0
                summary_parts.append(f"Evidence ({total} total): {json.dumps(evidence, ensure_ascii=False)}")
            
            # Key dates
            if 'key_dates' in data:
                summary_parts.append(f"Key Dates: {json.dumps(data['key_dates'], ensure_ascii=False)}")
            
            # Case status
            if 'case_status' in data:
                summary_parts.append(f"Status: {json.dumps(data['case_status'], ensure_ascii=False)}")
            
            concise_summary = "\n".join(summary_parts)
            estimated_after = _estimate_tokens(concise_summary)
            
            if estimated_after <= MAX_TOKENS_PER_REQUEST:
                logger.info(f"Created concise summary ({estimated_after} tokens)")
                return concise_summary
    except Exception as e:
        logger.debug(f"JSON parsing failed, using chunking: {str(e)}")
        pass  # If JSON parsing fails, fall through to chunking
    
    # Fallback: Chunk the response
    chunks = _chunk_text(tool_response, chunk_size=CHUNK_SIZE)
    logger.info(f"Split into {len(chunks)} chunks for processing")
    
    # Process each chunk with aggressive summarization
    summarized_chunks = []
    for i, chunk in enumerate(chunks):
        logger.info(f"Processing chunk {i+1}/{len(chunks)}...")
        time.sleep(CHUNK_DELAY)  # Rate limiting between chunks
        
        # Very aggressive summarization prompt
        chunk_preview = chunk[:1500]  # Limit chunk size for prompt
        summary_prompt = f"""Extract ONLY the most critical information from this legal case data. Be extremely concise (under 150 words):

{chunk_preview}

Return ONLY:
- Case reference numbers
- Top 2-3 parties with roles
- Top 2-3 charges
- Judgment verdict (if any)
- Key dates

Keep response under 150 words."""
        
        try:
            summary_response = llm.invoke([HumanMessage(content=summary_prompt)])
            summary = summary_response.content if hasattr(summary_response, 'content') else str(summary_response)
            # Truncate summary if still too long
            if len(summary) > 400:
                summary = summary[:400] + "..."
            summarized_chunks.append(summary)
        except Exception as e:
            logger.warning(f"Error summarizing chunk {i+1}: {str(e)}, truncating")
            summarized_chunks.append(chunk[:200] + "...")  # Aggressive truncation
    
    # Combine all summaries
    combined_summary = "\n".join(summarized_chunks)
    
    # Final aggressive summarization
    final_prompt = f"""Create an extremely concise summary (under 200 words) of this legal case information:

{combined_summary[:1500]}  # Limit input size

Focus only on: case numbers, key parties, main charges, judgment verdict, important dates."""
    
    try:
        time.sleep(CHUNK_DELAY)
        final_response = llm.invoke([HumanMessage(content=final_prompt)])
        final_summary = final_response.content if hasattr(final_response, 'content') else combined_summary
        # Ensure final summary is small
        if len(final_summary) > 800:
            final_summary = final_summary[:800] + "..."
        logger.info(f"Final summary length: {len(final_summary)} chars, ~{_estimate_tokens(final_summary)} tokens")
        return final_summary
    except Exception as e:
        logger.warning(f"Error in final summarization: {str(e)}, returning truncated combined summaries")
        return combined_summary[:800] + "..."


def agent_node(state: AgentState):
    """Agent node that processes messages and decides on tool calls"""
    time.sleep(GROQ_RATE_LIMIT_DELAY)  # Rate limiting
    
    messages = state["messages"]
    
    # Get system prompt
    system_prompt = f"""You are an expert assistant for querying a Qatar Legal Case Management System.

{SCHEMA_INFO}

IMPORTANT - Tool Selection Strategy:
- For SPECIFIC questions (e.g., "who was the victim?", "what was the judgment?", "who was accused?"), use the TARGETED tools:
  * query_victims - for victim questions
  * query_accused - for accused/defendant questions  
  * query_judgments_only - for judgment/verdict questions
  * query_charges_only - for charge/crime questions
  * query_evidence_only - for evidence questions
- For COMPREHENSIVE questions (e.g., "tell me everything about case 3", "give me all details"), use query_case_details
- Always return ONLY what was asked - be concise and targeted
- If tool responses are large, they will be automatically summarized.
- IMPORTANT: When user says "case N" they mean internal case_id=N (integer PK), not court case number.
- If a targeted tool returns empty results, report that for the same case_id; do not invent different case numbers."""
    
    # Prepare messages with system prompt
    llm_messages = [SystemMessage(content=system_prompt)] + messages
    
    # Initialize LLM and bind tools - CRITICAL for tool calling
    llm = ChatGroq(
        model=CONFIG['groq']['model'],
        temperature=0.1,
        groq_api_key=CONFIG['groq']['api_key']
    )
    
    # Bind tools to LLM so it can generate tool calls
    llm_with_tools = llm.bind_tools(tools)
    
    # Get response
    response = llm_with_tools.invoke(llm_messages)
    
    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    """Determine if we should continue to tools or end"""
    messages = state["messages"]
    last_message = messages[-1]
    
    # If last message has tool calls, continue to tools
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "continue"
    
    return "end"


def process_tool_responses(state: AgentState) -> AgentState:
    """Post-process tool responses to handle large data by chunking and summarizing"""
    messages = state["messages"]
    processed_messages = []
    
    llm = ChatGroq(
        model=CONFIG['groq']['model'],
        temperature=0.1,
        groq_api_key=CONFIG['groq']['api_key']
    )
    
    for message in messages:
        # Check if this is a tool message with large content
        if isinstance(message, ToolMessage):
            tool_response = message.content
            estimated_tokens = _estimate_tokens(tool_response)
            
            # Log which tool produced this response
            logger.info(f"Processing tool response: {estimated_tokens} tokens")
            
            # More aggressive threshold - process if over 2500 tokens
            if estimated_tokens > 2500:
                logger.warning(f"Tool response is large ({estimated_tokens} tokens), processing...")
                processed_response = _process_large_tool_response(tool_response, llm)
                processed_tokens = _estimate_tokens(processed_response)
                logger.info(f"Processed response: {processed_tokens} tokens")
                
                # If still too large, truncate aggressively
                if processed_tokens > MAX_TOKENS_PER_REQUEST:
                    logger.warning(f"Processed response still too large ({processed_tokens} tokens), truncating...")
                    max_chars = MAX_TOKENS_PER_REQUEST * 3  # Rough estimate
                    processed_response = processed_response[:max_chars] + "... [truncated]"
                
                # Replace with processed version
                processed_messages.append(ToolMessage(
                    content=processed_response,
                    tool_call_id=message.tool_call_id
                ))
            else:
                processed_messages.append(message)
        else:
            processed_messages.append(message)
    
    return {"messages": processed_messages}


# Cached agent instance
_cached_agent = None


def query(user_query: str) -> str:
    """
    Query the database using natural language
    
    Args:
        user_query: Natural language query
        
    Returns:
        Query result as string
    """
    global _cached_agent
    
    # Initialize agent if needed
    if _cached_agent is None:
        logger.info("Initializing query agent...")
        _cached_agent = create_agent()
        logger.info("Query agent initialized")
    
    # Create initial state
    initial_state = {
        "messages": [HumanMessage(content=user_query)],
        "query": user_query,
        "results": None,
        "error": None
    }
    
    # Execute agent
    try:
        result = _cached_agent.invoke(initial_state)
        
        # Get final response
        messages = result.get("messages", [])
        if messages:
            last_message = messages[-1]
            if hasattr(last_message, 'content'):
                return last_message.content
            return str(last_message)
        
        return "No response generated"
    
    except Exception as e:
        logger.error(f"Error in query execution: {str(e)}")
        return f"Error: {str(e)}"


def main():
    """Interactive query interface"""
    print("Legal Case Query Agent v2")
    print("Type 'exit' to quit\n")
    
    while True:
        try:
            user_input = input("Query: ").strip()
            if user_input.lower() in ['exit', 'quit', 'q']:
                break
            
            if not user_input:
                continue
            
            result = query(user_input)
            print(f"\nResult:\n{result}\n")
        
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {str(e)}\n")


if __name__ == '__main__':
    main()

