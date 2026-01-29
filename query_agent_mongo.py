"""
Query Agent for MongoDB-based Legal Case Management System
Natural language queries using LangGraph and Groq
"""

from typing import Dict, List, Any, Optional, TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_groq import ChatGroq
from langchain_core.tools import tool, StructuredTool
from langchain_core.callbacks import BaseCallbackHandler
import json
import logging
import time
from bson import ObjectId

from config import CONFIG
from mongo_manager import MongoManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TokenMonitoringHandler(BaseCallbackHandler):
    """Callback handler to monitor token generation speed"""
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        
    def on_llm_start(self, serialized, prompts, **kwargs):
        """Called when LLM starts"""
        self.start_time = time.time()
        # Estimate input tokens (rough approximation: 1 token ≈ 4 chars)
        self.input_tokens = sum(len(str(p)) // 4 for p in prompts)
        logger.info(f"🚀 LLM inference started | Input tokens: ~{self.input_tokens}")
        
    def on_llm_end(self, response, **kwargs):
        """Called when LLM ends"""
        self.end_time = time.time()
        if hasattr(response, 'llm_output') and response.llm_output:
            if 'token_usage' in response.llm_output:
                usage = response.llm_output['token_usage']
                self.output_tokens = usage.get('completion_tokens', 0)
                self.total_tokens = usage.get('total_tokens', 0)
            else:
                # Fallback: estimate from response length
                response_text = str(response.generations[0][0].text) if hasattr(response, 'generations') else str(response)
                self.output_tokens = len(response_text) // 4
        
        duration = self.end_time - self.start_time if self.start_time else 0
        tokens_per_sec = self.output_tokens / duration if duration > 0 else 0
        
        logger.info(f"✅ LLM inference completed")
        logger.info(f"   ⏱️  Duration: {duration:.2f}s")
        logger.info(f"   📊 Input tokens: ~{self.input_tokens} | Output tokens: ~{self.output_tokens} | Total: ~{self.total_tokens}")
        logger.info(f"   ⚡ Speed: {tokens_per_sec:.2f} tokens/s")
        
    def on_llm_error(self, error, **kwargs):
        """Called on LLM error"""
        logger.error(f"❌ LLM error: {error}")


class AgentState(TypedDict):
    messages: Annotated[List, "messages"]
    query: str
    results: Optional[List[Dict]]
    error: Optional[str]


# Schema information for MongoDB
SCHEMA_INFO = """
MongoDB Schema for Qatar Legal Case Management System:

COLLECTIONS:
1. cases - Main case information
   - _id (ObjectId)
   - case_numbers: {"court": "...", "prosecution": "...", "police": "...", "variations": [...]}
   - created_at, updated_at

2. documents - Document metadata with embeddings
   - _id (ObjectId), case_id (ObjectId reference)
   - file_path, file_name, file_hash
   - text, embedding (array)
   - extracted_entities (JSON): All entities extracted from document
   - document_type: Type of document (police_complaint, court_judgment, etc.)
   - processing_status: 'extracted', 'linked', 'processed'

3. parties - Normalized party entities
   - _id (ObjectId)
   - name_ar, name_en
   - personal_id
   - signature: For deduplication

4. charges - Normalized charge entities
   - _id (ObjectId)
   - article_number, description_ar, description_en
   - signature: For deduplication

5. evidence_items - Normalized evidence entities
   - _id (ObjectId)
   - type, description_ar, description_en
   - signature: For deduplication

6. case_parties - Links parties to cases
   - case_id, party_id, role_type, source_document_id

7. case_charges - Links charges to cases
   - case_id, charge_id, source_document_id

8. case_evidence - Links evidence to cases
   - case_id, evidence_id, source_document_id

9. case_documents - Links documents to cases
   - case_id, document_id, confidence, linking_params

COMMON QUERIES:
- Find case by reference number (any variation)
- Find all parties in a case (with roles)
- Find charges for a case
- Find documents for a case
- Search cases by party name or personal_id
"""


# Query Tools
@tool
def query_cases(
    court_case_number: Optional[str] = None,
    prosecution_case_number: Optional[str] = None,
    police_report_number: Optional[str] = None,
    case_status: Optional[str] = None,
    limit: int = 10
) -> str:
    """Find cases by reference numbers or status."""
    try:
        with MongoManager(**CONFIG['mongodb']) as mongo:
            cases_collection = mongo.db['cases']
            results = []
            
            # Search by reference numbers
            if court_case_number:
                cc = str(court_case_number).strip()
                # Try as ObjectId first if it's a valid hex string
                if len(cc) == 24:
                    try:
                        case = cases_collection.find_one({'_id': ObjectId(cc)})
                        if case:
                            results.append(case)
                    except:
                        pass
                
                # Search in case_numbers
                if not results:
                    query = {
                        '$or': [
                            {'case_numbers.court': cc},
                            {'case_numbers.prosecution': cc},
                            {'case_numbers.police': cc},
                            {'case_numbers.variations': cc}
                        ]
                    }
                    results = list(cases_collection.find(query).limit(limit))
            
            if prosecution_case_number and not results:
                query = {
                    '$or': [
                        {'case_numbers.prosecution': prosecution_case_number},
                        {'case_numbers.variations': prosecution_case_number}
                    ]
                }
                results = list(cases_collection.find(query).limit(limit))
            
            if police_report_number and not results:
                query = {
                    '$or': [
                        {'case_numbers.police': police_report_number},
                        {'case_numbers.variations': police_report_number}
                    ]
                }
                results = list(cases_collection.find(query).limit(limit))
            
            # If no specific search, get recent cases
            if not results:
                results = list(cases_collection.find({}).sort('created_at', -1).limit(limit))
            
            # Format results
            if not results:
                return "No cases found matching the criteria."
            
            formatted = []
            for case in results[:limit]:
                case_id = str(case['_id'])
                case_numbers = case.get('case_numbers', {})
                formatted.append({
                    'case_id': case_id,
                    'court_case_number': case_numbers.get('court', 'N/A'),
                    'prosecution_case_number': case_numbers.get('prosecution', 'N/A'),
                    'police_report_number': case_numbers.get('police', 'N/A'),
                    'variations': case_numbers.get('variations', [])
                })
            
            return json.dumps(formatted, indent=2, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"Error querying cases: {e}", exc_info=True)
        return f"Error querying cases: {str(e)}"


@tool
def query_parties(
    case_id: Optional[str] = None,
    party_name: Optional[str] = None,
    personal_id: Optional[str] = None,
    role_type: Optional[str] = None,
    limit: int = 50
) -> str:
    """Find parties in cases. If case_id provided, returns parties for that case. Otherwise searches by name or personal_id."""
    try:
        with MongoManager(**CONFIG['mongodb']) as mongo:
            if case_id:
                # Get parties for specific case
                case_parties_collection = mongo.db['case_parties']
                parties_collection = mongo.db['parties']
                
                query = {'case_id': ObjectId(case_id)}
                if role_type:
                    query['role_type'] = role_type
                
                links = list(case_parties_collection.find(query).limit(limit))
                parties = []
                for link in links:
                    party = parties_collection.find_one({'_id': link['party_id']})
                    if party:
                        parties.append({
                            'party_id': str(party['_id']),
                            'name_ar': party.get('name_ar', ''),
                            'name_en': party.get('name_en', ''),
                            'personal_id': party.get('personal_id', ''),
                            'role': link.get('role_type', ''),
                            'occupation': party.get('occupation', ''),
                            'nationality': party.get('nationality', '')
                        })
                
                if not parties:
                    return f"No parties found for case {case_id}."
                
                return json.dumps(parties, indent=2, ensure_ascii=False)
            
            else:
                # Search parties by name or personal_id
                parties_collection = mongo.db['parties']
                query = {}
                if party_name:
                    query['$or'] = [
                        {'name_ar': {'$regex': party_name, '$options': 'i'}},
                        {'name_en': {'$regex': party_name, '$options': 'i'}}
                    ]
                if personal_id:
                    query['personal_id'] = personal_id
                
                parties = list(parties_collection.find(query).limit(limit))
                if not parties:
                    return "No parties found matching the criteria."
                
                formatted = []
                for party in parties:
                    formatted.append({
                        'party_id': str(party['_id']),
                        'name_ar': party.get('name_ar', ''),
                        'name_en': party.get('name_en', ''),
                        'personal_id': party.get('personal_id', ''),
                        'occupation': party.get('occupation', ''),
                        'nationality': party.get('nationality', '')
                    })
                
                return json.dumps(formatted, indent=2, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"Error querying parties: {e}", exc_info=True)
        return f"Error querying parties: {str(e)}"


@tool
def query_charges(
    case_id: Optional[str] = None,
    article_number: Optional[str] = None,
    limit: int = 50
) -> str:
    """Find charges for cases. If case_id provided, returns charges for that case."""
    try:
        with MongoManager(**CONFIG['mongodb']) as mongo:
            if case_id:
                # Get charges for specific case
                case_charges_collection = mongo.db['case_charges']
                charges_collection = mongo.db['charges']
                
                links = list(case_charges_collection.find({'case_id': ObjectId(case_id)}).limit(limit))
                charges = []
                for link in links:
                    charge = charges_collection.find_one({'_id': link['charge_id']})
                    if charge:
                        charges.append({
                            'charge_id': str(charge['_id']),
                            'article_number': charge.get('article_number', ''),
                            'description_ar': charge.get('description_ar', ''),
                            'description_en': charge.get('description_en', ''),
                            'law_name': charge.get('law_name', '')
                        })
                
                if not charges:
                    return f"No charges found for case {case_id}."
                
                return json.dumps(charges, indent=2, ensure_ascii=False)
            
            else:
                # Search charges by article number
                charges_collection = mongo.db['charges']
                query = {}
                if article_number:
                    query['article_number'] = article_number
                
                charges = list(charges_collection.find(query).limit(limit))
                if not charges:
                    return "No charges found matching the criteria."
                
                formatted = []
                for charge in charges:
                    formatted.append({
                        'charge_id': str(charge['_id']),
                        'article_number': charge.get('article_number', ''),
                        'description_ar': charge.get('description_ar', ''),
                        'description_en': charge.get('description_en', ''),
                        'law_name': charge.get('law_name', '')
                    })
                
                return json.dumps(formatted, indent=2, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"Error querying charges: {e}", exc_info=True)
        return f"Error querying charges: {str(e)}"


@tool
def query_documents(
    case_id: Optional[str] = None,
    document_type: Optional[str] = None,
    limit: int = 50
) -> str:
    """Find documents. If case_id provided, returns documents for that case."""
    try:
        with MongoManager(**CONFIG['mongodb']) as mongo:
            documents_collection = mongo.db['documents']
            
            query = {}
            if case_id:
                query['case_id'] = ObjectId(case_id)
            if document_type:
                query['document_type'] = document_type
            
            documents = list(documents_collection.find(query).sort('created_at', -1).limit(limit))
            
            if not documents:
                return f"No documents found matching the criteria."
            
            formatted = []
            for doc in documents:
                formatted.append({
                    'document_id': str(doc['_id']),
                    'case_id': str(doc['case_id']) if doc.get('case_id') else None,
                    'file_name': doc.get('file_name', ''),
                    'document_type': doc.get('document_type', ''),
                    'processing_status': doc.get('processing_status', ''),
                    'created_at': str(doc.get('created_at', ''))
                })
            
            return json.dumps(formatted, indent=2, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"Error querying documents: {e}", exc_info=True)
        return f"Error querying documents: {str(e)}"


@tool
def query_victims(case_id: str) -> str:
    """Find victims (مشتكي/شاكي) in a specific case."""
    try:
        with MongoManager(**CONFIG['mongodb']) as mongo:
            case_parties_collection = mongo.db['case_parties']
            parties_collection = mongo.db['parties']

            # Common victim roles (Arabic)
            victim_roles = ['مشتكي', 'شاكي', 'مجني عليه']
            links = list(case_parties_collection.find({
                'case_id': ObjectId(case_id),
                'role_type': {'$in': victim_roles}
            }).limit(200))

            parties = []
            for link in links:
                party = parties_collection.find_one({'_id': link['party_id']})
                if party:
                    parties.append({
                        'party_id': str(party['_id']),
                        'name_ar': party.get('name_ar', ''),
                        'name_en': party.get('name_en', ''),
                        'personal_id': party.get('personal_id', ''),
                        'role': link.get('role_type', ''),
                        'occupation': party.get('occupation', ''),
                        'nationality': party.get('nationality', '')
                    })

            if not parties:
                return json.dumps({
                    'case_id': case_id,
                    'victims': [],
                    'message': 'No victims found for this case.'
                }, ensure_ascii=False)

            return json.dumps({
                'case_id': case_id,
                'victims': parties
            }, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Error querying victims: {e}", exc_info=True)
        return f"Error querying victims: {str(e)}"


@tool
def query_accused(case_id: str) -> str:
    """Find accused (متهم) in a specific case."""
    try:
        with MongoManager(**CONFIG['mongodb']) as mongo:
            case_parties_collection = mongo.db['case_parties']
            parties_collection = mongo.db['parties']

            accused_roles = ['متهم', 'مشتبه به']
            links = list(case_parties_collection.find({
                'case_id': ObjectId(case_id),
                'role_type': {'$in': accused_roles}
            }).limit(200))

            parties = []
            for link in links:
                party = parties_collection.find_one({'_id': link['party_id']})
                if party:
                    parties.append({
                        'party_id': str(party['_id']),
                        'name_ar': party.get('name_ar', ''),
                        'name_en': party.get('name_en', ''),
                        'personal_id': party.get('personal_id', ''),
                        'role': link.get('role_type', ''),
                        'occupation': party.get('occupation', ''),
                        'nationality': party.get('nationality', '')
                    })

            if not parties:
                return json.dumps({
                    'case_id': case_id,
                    'accused': [],
                    'message': 'No accused found for this case.'
                }, ensure_ascii=False)

            return json.dumps({
                'case_id': case_id,
                'accused': parties
            }, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Error querying accused: {e}", exc_info=True)
        return f"Error querying accused: {str(e)}"


def _extract_case_id_from_messages(messages: List) -> Optional[str]:
    """
    Extract case ID from a list of LangChain messages.
    Looks for ObjectId pattern (24 hex characters) in message content.
    Searches in ALL messages (user, assistant, system) to find case IDs.
    Returns the first valid case ID found, or None.
    """
    import re
    case_id_pattern = r'\b[0-9a-fA-F]{24}\b'
    
    # Search through all messages (including assistant messages which might have mentioned case IDs)
    for msg in reversed(messages):  # Search from most recent to oldest
        content = ""
        if hasattr(msg, 'content'):
            content = str(msg.content)
        elif isinstance(msg, dict):
            content = str(msg.get('content', ''))
        else:
            content = str(msg)
        
        # Skip system messages that are just prompts (but keep ones with case IDs)
        if isinstance(msg, SystemMessage):
            if "CASE ID:" in content or "IMPORTANT:" in content:
                # This might contain a case ID, check it
                pass
            else:
                # Skip regular system prompts
                continue
        
        case_ids = re.findall(case_id_pattern, content)
        if case_ids:
            # Verify case ID exists in database
            try:
                with MongoManager(**CONFIG['mongodb']) as mongo:
                    cases_collection = mongo.db['cases']
                    for cid in case_ids:
                        try:
                            case = cases_collection.find_one({'_id': ObjectId(cid)})
                            if case:
                                logger.info(f"✅ Found valid case ID in conversation history: {cid} (from message type: {type(msg).__name__}, content preview: {content[:100]}...)")
                                return cid
                        except Exception as e:
                            logger.debug(f"Error checking case ID {cid}: {e}")
                            continue
            except Exception as e:
                logger.warning(f"Error verifying case ID: {e}")
    
    logger.warning(f"No valid case ID found in conversation history (searched {len(messages)} messages)")
    return None


@tool
def check_case_id_needed(query: str) -> str:
    """
    Check if a case-related query needs a case ID. Use this tool when the user asks about cases, parties, charges, etc. but doesn't specify which case.
    
    IMPORTANT: This tool automatically checks ALL previous messages in the conversation for case IDs.
    If the user says "yes" or agrees to use a previously mentioned case, this tool will find it.
    
    This tool will:
    1. Check if the query is case-related
    2. Check if query contains "yes", "نعم", "ok", "حسناً" - these mean "use the case ID from earlier"
    3. Extract case ID from ALL previous conversation messages (both user and assistant messages)
    4. Return the case ID if found, or ask for clarification if not found
    
    Args:
        query: The current user query
    """
    try:
        import re
        
        # Check if user is confirming/agreeing (yes, نعم, ok, etc.)
        confirmation_keywords = ["yes", "نعم", "ok", "حسناً", "تمام", "موافق", "okay", "yep", "yeah"]
        query_lower = query.lower().strip()
        is_confirmation = any(keyword in query_lower for keyword in confirmation_keywords)
        
        # Case-related keywords (more specific - removed generic words like "who", "what", "which")
        # Only trigger if query contains actual case-related terms
        case_keywords = [
            "case", "قضية", "دعوى", "ملف", "verdict", "حكم", "judgment",
            "party", "طرف", "متهم", "مشتكي", "victim", "accused",
            "charge", "جريمة", "مادة", "اتهام",
            "incident", "حادثة", "document", "مستند",
            "court", "محكمة", "prosecution", "نيابة", "police", "شرطة"
        ]
        
        # Check for case-related context (not just generic questions)
        # Require at least one case-specific keyword, not just "who" or "what"
        has_case_keyword = any(keyword in query_lower for keyword in case_keywords)
        
        # Also check for case-related phrases (more specific)
        case_phrases = [
            "who was the", "من هو", "من هي",
            "what happened in the case", "ماذا حدث في القضية",
            "which case", "أي قضية",
            "the accused", "المتهم",
            "the victim", "المجني عليه", "المشتكي"
        ]
        has_case_phrase = any(phrase in query_lower for phrase in case_phrases)
        
        is_case_query = (has_case_keyword or has_case_phrase) or is_confirmation
        
        if not is_case_query:
            return json.dumps({
                'needs_clarification': False,
                'message': 'This query is not case-related.'
            }, ensure_ascii=False)
        
        # Check if case ID is already in the query
        # Look for ObjectId pattern (24 hex characters)
        case_id_pattern = r'\b[0-9a-fA-F]{24}\b'
        case_ids_in_query = re.findall(case_id_pattern, query)
        
        if case_ids_in_query:
            return json.dumps({
                'needs_clarification': False,
                'case_id_found': case_ids_in_query[0],
                'message': f'Case ID found in query: {case_ids_in_query[0]}'
            }, ensure_ascii=False)
        
        # IMPORTANT: The conversation history is available in the agent's state
        # We need to access it from the messages that were passed to the agent
        # Since this tool is called by the agent, the messages are in the agent's context
        # We'll return a special response that tells the agent to check the messages
        
        # If user confirmed, the case ID extraction should have happened in call_model
        # But if this tool is called again, it means we need to check history
        if is_confirmation:
            # User said "yes" - check if there's a case ID in the conversation
            # Note: This tool doesn't have direct access to full conversation, but the agent's call_model
            # should have already extracted it. If we're here, return a message that tells the agent
            # the case ID should already be in the system message
            return json.dumps({
                'needs_clarification': False,
                'check_history': True,
                'message': 'User confirmed. If a case ID was mentioned earlier in the conversation, it should already be extracted. Check the system messages for the case ID. If no case ID is found in system messages, ask the user to provide the case ID.',
                'instruction': 'Look for a system message that says "The case ID is: [ID]". If found, use that case ID. If not found, ask the user to provide the case ID.'
            }, ensure_ascii=False)
        
        # No case ID found - need clarification
        return json.dumps({
            'needs_clarification': True,
            'message': 'عذراً، يبدو أنك تسأل عن قضية معينة، لكن لم أتمكن من تحديد رقم القضية. هل يمكنك إخباري برقم القضية (case ID) أو رقم القضية في المحكمة أو النيابة أو الشرطة؟ على سبيل المثال: "من هو المتهم في القضية 6979c405fa024fa3f8a3ad1b؟"',
            'english_message': 'Sorry, it seems you are asking about a specific case, but I could not identify the case number. Could you please provide the case ID or the case number from the court, prosecution, or police? For example: "Who is the accused in case 6979c405fa024fa3f8a3ad1b?"'
        }, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"Error checking case ID: {e}", exc_info=True)
        return json.dumps({
            'needs_clarification': True,
            'message': 'عذراً، حدث خطأ في التحقق من رقم القضية. يرجى إعادة المحاولة.',
            'error': str(e)
        }, ensure_ascii=False)


# Initialize LLM based on configuration (local or Groq)
def _get_llm():
    """Initialize LLM based on configuration (local or Groq)"""
    monitoring_handler = TokenMonitoringHandler()
    
    if CONFIG['local_llm']['enabled']:
        logger.info("🔧 Using LOCAL LLM (Qwen3-14B)")
        logger.info(f"   Model path: {CONFIG['local_llm']['model_path']}")
        logger.info(f"   Backend: {CONFIG['local_llm']['backend']}")
        logger.info(f"   Device: {CONFIG['local_llm']['device']}")
        
        if CONFIG['local_llm']['backend'] == 'vllm':
            try:
                # Try to use vLLM with OpenAI-compatible API server
                # This is the most compatible approach
                logger.info("Attempting to use vLLM with OpenAI-compatible API...")
                
                # Note: vLLM needs to be run as a server first
                # For now, fall back to transformers
                logger.warning("⚠️  vLLM OpenAI API server not detected. Using transformers backend.")
                logger.info("💡 To use vLLM, start it with: python -m vllm.entrypoints.openai.api_server --model <path>")
                logger.info("💡 Then set LOCAL_LLM_BACKEND=transformers or configure OpenAI API endpoint")
                return _get_llm_transformers(monitoring_handler)
                
            except Exception as e:
                logger.error(f"❌ Error with vLLM: {e}", exc_info=True)
                logger.info("Falling back to transformers backend...")
                return _get_llm_transformers(monitoring_handler)
        else:
            return _get_llm_transformers(monitoring_handler)
    else:
        logger.info("🔧 Using Groq API")
        return ChatGroq(
    model=CONFIG['groq']['model'],
    temperature=0.1,
            groq_api_key=CONFIG['groq']['api_key'],
            callbacks=[monitoring_handler]
        )


def _get_llm_transformers(monitoring_handler):
    """Initialize LLM using transformers backend"""
    logger.info("🔧 Using transformers backend for local LLM")
    try:
        from langchain_community.llms import HuggingFacePipeline
    except ImportError:
        # Fallback if langchain_community is not available
        logger.warning("langchain_community not found, using direct transformers")
        from transformers import pipeline as hf_pipeline
        HuggingFacePipeline = None
    
    from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
    import torch
    
    device = CONFIG['local_llm']['device']
    model_path = CONFIG['local_llm']['model_path']
    
    logger.info(f"Loading model from {model_path}...")
    
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        
        # Set pad token if not set
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.float16 if device == 'cuda' else torch.float32,
            device_map="auto",
            trust_remote_code=True,
            low_cpu_mem_usage=True
        )
        
        # Create pipeline
        pipe = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            max_new_tokens=4096,
            temperature=0.1,
            device=0 if device == 'cuda' else -1,
            return_full_text=False,
            do_sample=True,
            top_p=0.95
        )
        
        # Create LangChain wrapper
        if HuggingFacePipeline:
            hf_llm = HuggingFacePipeline(pipeline=pipe, callbacks=[monitoring_handler])
        else:
            # Create a simple wrapper if HuggingFacePipeline is not available
            class SimpleLLMWrapper:
                def __init__(self, pipeline, callbacks):
                    self.pipeline = pipeline
                    self.callbacks = callbacks
                def invoke(self, prompt, stop=None):
                    result = self.pipeline(prompt, max_new_tokens=4096, temperature=0.1)
                    if isinstance(result, list) and len(result) > 0:
                        return result[0].get('generated_text', '')
                    return str(result)
            hf_llm = SimpleLLMWrapper(pipe, [monitoring_handler])
        
        # Create chat wrapper for LangGraph compatibility
        chat_llm = _create_chat_wrapper(hf_llm, monitoring_handler)
        logger.info("✅ Transformers backend initialized successfully")
        return chat_llm
        
    except Exception as e:
        logger.error(f"❌ Error initializing transformers backend: {e}", exc_info=True)
        raise


def _create_chat_wrapper(llm, monitoring_handler):
    """Create a chat model wrapper for LangGraph compatibility"""
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.outputs import ChatGeneration, ChatResult, ChatGenerationChunk
    from langchain_core.messages import AIMessage
    
    class ChatModelWrapper(BaseChatModel):
        """Wrapper to convert LLM to ChatModel for LangGraph"""
        def __init__(self, llm):
            super().__init__(callbacks=[monitoring_handler])
            self.llm = llm
            
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            """Generate response from messages"""
            # Convert messages to prompt using Qwen3 format
            prompt = self._messages_to_prompt(messages)
            
            # Generate response
            response_text = self.llm.invoke(prompt, stop=stop)
            
            # Handle string response
            if isinstance(response_text, str):
                response_content = response_text
            else:
                response_content = str(response_text)
            
            # Create AIMessage
            message = AIMessage(content=response_content)
            generation = ChatGeneration(message=message)
            
            return ChatResult(generations=[generation])
        
        async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
            """Stream response from messages"""
            # Convert messages to prompt using Qwen3 format
            prompt = self._messages_to_prompt(messages)
            
            # Check if underlying LLM supports streaming
            if hasattr(self.llm, 'stream'):
                # Stream from underlying LLM
                full_content = ""
                async for chunk in self.llm.stream(prompt, stop=stop):
                    if isinstance(chunk, str):
                        content = chunk
                    else:
                        content = str(chunk)
                    if content:
                        full_content += content
                        yield ChatGenerationChunk(message=AIMessage(content=content))
            else:
                # Fallback to non-streaming
                response_text = self.llm.invoke(prompt, stop=stop)
                content = response_text if isinstance(response_text, str) else str(response_text)
                yield ChatGenerationChunk(message=AIMessage(content=content))
        
        def _messages_to_prompt(self, messages):
            """Convert messages to Qwen3 chat format"""
            # Qwen3 uses a specific chat template
            # Format: <|im_start|>role\ncontent<|im_end|>\n
            prompt_parts = []
            
            for msg in messages:
                if isinstance(msg, SystemMessage):
                    prompt_parts.append(f"<|im_start|>system\n{msg.content}<|im_end|>")
                elif isinstance(msg, HumanMessage):
                    prompt_parts.append(f"<|im_start|>user\n{msg.content}<|im_end|>")
                elif isinstance(msg, AIMessage):
                    prompt_parts.append(f"<|im_start|>assistant\n{msg.content}<|im_end|>")
            
            # Add assistant start token
            prompt_parts.append("<|im_start|>assistant\n")
            return "\n".join(prompt_parts)
        
        @property
        def _llm_type(self):
            return "qwen3-14b-local"
    
    return ChatModelWrapper(llm)


# Initialize LLM
llm = _get_llm()

# Additional detailed query tools
@tool
def get_case_incident_details(case_id: str) -> str:
    """Get detailed incident information from police complaints and statements for a case."""
    try:
        with MongoManager(**CONFIG['mongodb']) as mongo:
            documents_collection = mongo.db['documents']
            
            # Get police complaints and statements for this case
            docs = list(documents_collection.find({
                'case_id': ObjectId(case_id),
                'document_type': {'$in': ['police_complaint', 'police_statement', 'investigation_record']}
            }).sort('created_at', 1))
            
            if not docs:
                return json.dumps({'message': 'No incident documents found for this case.'}, ensure_ascii=False)
            
            details = []
            for doc in docs:
                entities = doc.get('extracted_entities', {}) or {}
                doc_info = {
                    'document_type': doc.get('document_type', ''),
                    'file_name': doc.get('file_name', ''),
                    'incident_date': entities.get('incident_date') or entities.get('dates', {}).get('incident') if isinstance(entities.get('dates'), dict) else None,
                    'incident_time': entities.get('incident_time') or entities.get('dates', {}).get('incident_time') if isinstance(entities.get('dates'), dict) else None,
                    'incident_location': entities.get('incident_location') or entities.get('locations', {}).get('incident_location') if isinstance(entities.get('locations'), dict) else None,
                    'incident_description': entities.get('incident_description_ar') or entities.get('description_ar') or entities.get('statements', [{}])[0].get('content_ar', '') if entities.get('statements') else '',
                    'cause': entities.get('cause_ar') or entities.get('reason_ar'),
                    'weapon_tool': entities.get('weapon') or entities.get('tool_used') or entities.get('evidence', [{}])[0].get('type', '') if entities.get('evidence') else None,
                    'injuries': entities.get('injuries') or entities.get('medical_findings_ar'),
                    'hospital': entities.get('hospital') or entities.get('hospital_name'),
                    'hospital_reason': entities.get('hospital_reason_ar') or entities.get('transfer_reason_ar'),
                    'alcohol_influence': entities.get('alcohol_detected') or entities.get('under_influence'),
                    'threat_with_weapon': entities.get('threat_with_weapon') or any('تهديد' in str(c.get('description_ar', '')) for c in (entities.get('charges') or [])),
                    'police_actions': entities.get('police_actions_ar') or entities.get('actions_taken_ar'),
                    'confession': entities.get('confession') or entities.get('admission'),
                    'denial': entities.get('denial') or entities.get('denied_charges'),
                    'consequences': entities.get('consequences_ar') or entities.get('damages_ar')
                }
                details.append(doc_info)
            
            return json.dumps(details, indent=2, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"Error getting incident details: {e}", exc_info=True)
        return f"Error: {str(e)}"


@tool
def get_case_location_info(case_id: str) -> str:
    """Get location information (incident location, police station, court) for a case."""
    try:
        with MongoManager(**CONFIG['mongodb']) as mongo:
            documents_collection = mongo.db['documents']
            cases_collection = mongo.db['cases']
            
            case = cases_collection.find_one({'_id': ObjectId(case_id)})
            if not case:
                return json.dumps({'error': 'Case not found'}, ensure_ascii=False)
            
            # Get all documents for this case
            docs = list(documents_collection.find({'case_id': ObjectId(case_id)}))
            
            locations = {
                'incident_location': None,
                'police_station': None,
                'court': None,
                'hospital': None
            }
            
            # Extract from documents
            for doc in docs:
                entities = doc.get('extracted_entities', {}) or {}
                locs = entities.get('locations', {})
                if isinstance(locs, dict):
                    if not locations['incident_location'] and locs.get('incident_location'):
                        locations['incident_location'] = locs['incident_location']
                    if not locations['police_station'] and locs.get('police_station'):
                        locations['police_station'] = locs['police_station']
                    if not locations['court'] and locs.get('court'):
                        locations['court'] = locs['court']
                    if not locations['hospital'] and locs.get('hospital'):
                        locations['hospital'] = locs['hospital']
            
            return json.dumps(locations, indent=2, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"Error getting location info: {e}", exc_info=True)
        return f"Error: {str(e)}"


@tool
def get_case_dates_times(case_id: str) -> str:
    """Get all dates and times related to a case (incident, report, court sessions, judgment)."""
    try:
        with MongoManager(**CONFIG['mongodb']) as mongo:
            documents_collection = mongo.db['documents']
            
            docs = list(documents_collection.find({'case_id': ObjectId(case_id)}).sort('created_at', 1))
            
            dates_info = {
                'incident_date': None,
                'incident_time': None,
                'report_date': None,
                'court_sessions': [],
                'judgment_date': None,
                'detention_dates': []
            }
            
            for doc in docs:
                entities = doc.get('extracted_entities', {}) or {}
                doc_type = doc.get('document_type', '')
                
                if doc_type == 'police_complaint':
                    dates_info['report_date'] = entities.get('incident_date') or entities.get('report_date')
                    dates_info['incident_date'] = entities.get('incident_date')
                    dates_info['incident_time'] = entities.get('incident_time')
                
                elif doc_type == 'court_session':
                    session_date = entities.get('session_date')
                    if session_date:
                        dates_info['court_sessions'].append({
                            'date': session_date,
                            'next_session': entities.get('next_session')
                        })
                
                elif doc_type == 'court_judgment':
                    dates_info['judgment_date'] = entities.get('judgment_date')
                
                elif doc_type in ['detention_order', 'detention_renewal']:
                    order_date = entities.get('order_date') or entities.get('renewal_date')
                    if order_date:
                        dates_info['detention_dates'].append({
                            'date': order_date,
                            'type': doc_type
                        })
            
            return json.dumps(dates_info, indent=2, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"Error getting dates: {e}", exc_info=True)
        return f"Error: {str(e)}"


@tool
def get_case_medical_info(case_id: str) -> str:
    """Get medical information (injuries, hospital transfers, lab tests) for a case."""
    try:
        with MongoManager(**CONFIG['mongodb']) as mongo:
            documents_collection = mongo.db['documents']
            
            # Get medical-related documents
            docs = list(documents_collection.find({
                'case_id': ObjectId(case_id),
                'document_type': {'$in': ['lab_test_results', 'forensic_medical_report', 'police_complaint', 'police_statement']}
            }).sort('created_at', 1))
            
            medical_info = {
                'injuries': [],
                'hospital_transfers': [],
                'lab_tests': [],
                'alcohol_tests': []
            }
            
            for doc in docs:
                entities = doc.get('extracted_entities', {}) or {}
                doc_type = doc.get('document_type', '')
                
                if doc_type == 'lab_test_results':
                    test_info = {
                        'test_date': entities.get('test_date'),
                        'test_type': entities.get('test_type'),
                        'result': entities.get('result'),
                        'subject': entities.get('subject_party', {}).get('name_ar') if isinstance(entities.get('subject_party'), dict) else None
                    }
                    if entities.get('test_type') == 'alcohol' or 'كحول' in str(entities.get('test_type', '')):
                        medical_info['alcohol_tests'].append(test_info)
                    else:
                        medical_info['lab_tests'].append(test_info)
                
                elif doc_type == 'forensic_medical_report':
                    medical_info['injuries'].append({
                        'report_date': entities.get('report_date'),
                        'findings': entities.get('medical_findings_ar'),
                        'examination_type': entities.get('examination_type'),
                        'conclusions': entities.get('conclusions_ar')
                    })
                
                elif doc_type in ['police_complaint', 'police_statement']:
                    if entities.get('injuries'):
                        medical_info['injuries'].append({'description': entities.get('injuries')})
                    if entities.get('hospital') or entities.get('hospital_name'):
                        medical_info['hospital_transfers'].append({
                            'hospital': entities.get('hospital') or entities.get('hospital_name'),
                            'reason': entities.get('hospital_reason_ar') or entities.get('transfer_reason_ar')
                        })
            
            return json.dumps(medical_info, indent=2, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"Error getting medical info: {e}", exc_info=True)
        return f"Error: {str(e)}"


@tool
def get_case_weapons_tools(case_id: str) -> str:
    """Get information about weapons or tools used in the incident."""
    try:
        with MongoManager(**CONFIG['mongodb']) as mongo:
            documents_collection = mongo.db['documents']
            evidence_collection = mongo.db['evidence_items']
            
            # Get evidence linked to case
            case_evidence_collection = mongo.db['case_evidence']
            evidence_links = list(case_evidence_collection.find({'case_id': ObjectId(case_id)}))
            
            weapons_tools = []
            
            # Get from evidence collection
            for link in evidence_links:
                evidence = evidence_collection.find_one({'_id': link['evidence_id']})
                if evidence:
                    ev_type = evidence.get('type', '')
                    desc = evidence.get('description_ar', '')
                    if 'سلاح' in desc or 'سكين' in desc or 'أداة' in desc or ev_type in ['weapon', 'tool']:
                        weapons_tools.append({
                            'type': ev_type,
                            'description': desc,
                            'source': 'evidence_collection'
                        })
            
            # Also check documents' extracted_entities
            docs = list(documents_collection.find({
                'case_id': ObjectId(case_id),
                'document_type': {'$in': ['police_complaint', 'police_statement', 'investigation_record']}
            }))
            
            for doc in docs:
                entities = doc.get('extracted_entities', {}) or {}
                if entities.get('weapon') or entities.get('tool_used'):
                    weapons_tools.append({
                        'description': entities.get('weapon') or entities.get('tool_used'),
                        'source': doc.get('document_type')
                    })
            
            if not weapons_tools:
                return json.dumps({'message': 'No weapons or tools information found.'}, ensure_ascii=False)
            
            return json.dumps(weapons_tools, indent=2, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"Error getting weapons/tools: {e}", exc_info=True)
        return f"Error: {str(e)}"


@tool
def get_case_confession_denial(case_id: str) -> str:
    """Get information about whether the accused confessed or denied charges."""
    try:
        with MongoManager(**CONFIG['mongodb']) as mongo:
            documents_collection = mongo.db['documents']
            
            docs = list(documents_collection.find({
                'case_id': ObjectId(case_id),
                'document_type': {'$in': ['police_statement', 'investigation_record', 'court_session']}
            }).sort('created_at', 1))
            
            confession_info = {
                'confessions': [],
                'denials': []
            }
            
            for doc in docs:
                entities = doc.get('extracted_entities', {}) or {}
                statements = entities.get('statements', []) or []
                
                for stmt in statements:
                    if isinstance(stmt, dict):
                        content = stmt.get('content_ar', '') or stmt.get('content', '')
                        if 'اعترف' in content or 'أقر' in content:
                            confession_info['confessions'].append({
                                'document': doc.get('file_name'),
                                'statement': content[:200]  # First 200 chars
                            })
                        if 'أنكر' in content or 'نفى' in content:
                            confession_info['denials'].append({
                                'document': doc.get('file_name'),
                                'statement': content[:200]
                            })
            
            return json.dumps(confession_info, indent=2, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"Error getting confession/denial: {e}", exc_info=True)
        return f"Error: {str(e)}"


@tool
def get_case_waiver_info(case_id: str) -> str:
    """Get information about any waivers (تنازل) filed in the case."""
    try:
        with MongoManager(**CONFIG['mongodb']) as mongo:
            documents_collection = mongo.db['documents']
            
            waiver_docs = list(documents_collection.find({
                'case_id': ObjectId(case_id),
                'document_type': 'waiver'
            }).sort('created_at', 1))
            
            if not waiver_docs:
                return json.dumps({'message': 'No waivers found for this case.'}, ensure_ascii=False)
            
            waivers = []
            for doc in waiver_docs:
                entities = doc.get('extracted_entities', {}) or {}
                waivers.append({
                    'waiver_date': entities.get('waiver_date'),
                    'complainant': entities.get('complainant_party', {}).get('name_ar') if isinstance(entities.get('complainant_party'), dict) else None,
                    'waiver_type': entities.get('waiver_type'),
                    'reasoning': entities.get('reasoning_ar')
                })
            
            return json.dumps(waivers, indent=2, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"Error getting waiver info: {e}", exc_info=True)
        return f"Error: {str(e)}"


@tool
def get_case_verdict_punishment(case_id: str) -> str:
    """Get final verdict, punishment/sentence, and judge name for a case. Use this tool when asked about the judge (القاضي), verdict (الحكم), or punishment (العقوبة)."""
    try:
        with MongoManager(**CONFIG['mongodb']) as mongo:
            documents_collection = mongo.db['documents']
            
            judgment_docs = list(documents_collection.find({
                'case_id': ObjectId(case_id),
                'document_type': 'court_judgment'
            }).sort('created_at', -1))
            
            if not judgment_docs:
                return json.dumps({'message': 'No judgment found for this case yet.'}, ensure_ascii=False)
            
            # Get most recent judgment
            judgment = judgment_docs[0]
            entities = judgment.get('extracted_entities', {}) or {}
            
            verdict_info = {
                'judgment_date': entities.get('judgment_date'),
                'verdict': entities.get('verdict'),
                'sentences': entities.get('sentences', []),
                'reasoning': entities.get('reasoning_ar'),
                'judge_name': entities.get('judge_name'),
                'appeal_deadline': entities.get('appeal_deadline')
            }
            
            return json.dumps(verdict_info, indent=2, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"Error getting verdict: {e}", exc_info=True)
        return f"Error: {str(e)}"


@tool
def get_case_current_status(case_id: str) -> str:
    """Get current procedural status/stage of the case."""
    try:
        with MongoManager(**CONFIG['mongodb']) as mongo:
            documents_collection = mongo.db['documents']
            cases_collection = mongo.db['cases']
            
            case = cases_collection.find_one({'_id': ObjectId(case_id)})
            if not case:
                return json.dumps({'error': 'Case not found'}, ensure_ascii=False)
            
            # Get most recent document
            recent_docs = list(documents_collection.find({
                'case_id': ObjectId(case_id)
            }).sort('created_at', -1).limit(5))
            
            status_info = {
                'last_document_type': recent_docs[0].get('document_type') if recent_docs else None,
                'last_document_date': str(recent_docs[0].get('created_at')) if recent_docs else None,
                'total_documents': len(recent_docs),
                'has_judgment': any(d.get('document_type') == 'court_judgment' for d in recent_docs),
                'has_waiver': any(d.get('document_type') == 'waiver' for d in recent_docs),
                'recent_activities': [d.get('document_type') for d in recent_docs[:3]]
            }
            
            return json.dumps(status_info, indent=2, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"Error getting case status: {e}", exc_info=True)
        return f"Error: {str(e)}"


@tool
def get_case_police_station(case_id: str) -> str:
    """Get the police station that registered/filed the complaint."""
    try:
        with MongoManager(**CONFIG['mongodb']) as mongo:
            documents_collection = mongo.db['documents']
            
            # Get police complaint document
            complaint_docs = list(documents_collection.find({
                'case_id': ObjectId(case_id),
                'document_type': 'police_complaint'
            }).sort('created_at', 1))
            
            if not complaint_docs:
                return json.dumps({'message': 'No police complaint found for this case.'}, ensure_ascii=False)
            
            complaint = complaint_docs[0]
            entities = complaint.get('extracted_entities', {}) or {}
            locations = entities.get('locations', {})
            
            police_station = None
            if isinstance(locations, dict):
                police_station = locations.get('police_station')
            
            return json.dumps({
                'police_station': police_station,
                'complaint_file': complaint.get('file_name')
            }, indent=2, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"Error getting police station: {e}", exc_info=True)
        return f"Error: {str(e)}"


@tool
def get_judge_name(case_id: str) -> str:
    """Get the name of the judge who presided over the case. 
    
    CRITICAL: Use this tool ONLY when asked about the JUDGE (القاضي). 
    - Keywords: "judge", "who was the judge", "judge name", "القاضي", "من هو القاضي"
    - DO NOT use this for accused/defendant (متهم) - use query_accused instead
    - DO NOT use this for victims (مشتكي) - use query_victims instead
    - The judge is the person who makes the legal decision, NOT a party to the case."""
    try:
        with MongoManager(**CONFIG['mongodb']) as mongo:
            documents_collection = mongo.db['documents']
            
            # Get court judgment document
            judgment_docs = list(documents_collection.find({
                'case_id': ObjectId(case_id),
                'document_type': 'court_judgment'
            }).sort('created_at', -1))
            
            if not judgment_docs:
                return json.dumps({'message': 'No judgment found for this case yet, so judge name is not available.'}, ensure_ascii=False)
            
            # Get most recent judgment
            judgment = judgment_docs[0]
            entities = judgment.get('extracted_entities', {}) or {}
            judge_name = entities.get('judge_name')
            
            return json.dumps({
                'judge_name': judge_name,
                'judgment_date': entities.get('judgment_date'),
                'judgment_file': judgment.get('file_name')
            }, indent=2, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"Error getting judge name: {e}", exc_info=True)
        return f"Error: {str(e)}"


@tool
def get_verdict_level(case_id: str) -> str:
    """Get the verdict level/court level for the case judgment. Use this tool when asked about the court level (مستوى الحكم, "verdict level", "court level")."""
    try:
        with MongoManager(**CONFIG['mongodb']) as mongo:
            documents_collection = mongo.db['documents']
            
            # Get court judgment document
            judgment_docs = list(documents_collection.find({
                'case_id': ObjectId(case_id),
                'document_type': 'court_judgment'
            }).sort('created_at', -1))
            
            if not judgment_docs:
                return json.dumps({'message': 'No judgment found for this case yet, so verdict level is not available.'}, ensure_ascii=False)
            
            # Get most recent judgment
            judgment = judgment_docs[0]
            entities = judgment.get('extracted_entities', {}) or {}
            
            # Check for verdict_level, court_level, or judgment_level in entities
            verdict_level = (entities.get('verdict_level') or 
                            entities.get('court_level') or 
                            entities.get('judgment_level') or
                            entities.get('court_name'))  # Sometimes court name indicates level
            
            return json.dumps({
                'verdict_level': verdict_level,
                'judgment_date': entities.get('judgment_date'),
                'judgment_file': judgment.get('file_name')
            }, indent=2, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"Error getting verdict level: {e}", exc_info=True)
        return f"Error: {str(e)}"


@tool
def get_judgment_date(case_id: str) -> str:
    """Get the date when the judgment was issued. Use this tool when asked about judgment date (تاريخ الحكم, "judgment date", "when was the verdict issued")."""
    try:
        with MongoManager(**CONFIG['mongodb']) as mongo:
            documents_collection = mongo.db['documents']
            
            # Get court judgment document
            judgment_docs = list(documents_collection.find({
                'case_id': ObjectId(case_id),
                'document_type': 'court_judgment'
            }).sort('created_at', -1))
            
            if not judgment_docs:
                return json.dumps({'message': 'No judgment found for this case yet, so judgment date is not available.'}, ensure_ascii=False)
            
            # Get most recent judgment
            judgment = judgment_docs[0]
            entities = judgment.get('extracted_entities', {}) or {}
            judgment_date = entities.get('judgment_date')
            
            return json.dumps({
                'judgment_date': judgment_date,
                'judgment_file': judgment.get('file_name')
            }, indent=2, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"Error getting judgment date: {e}", exc_info=True)
        return f"Error: {str(e)}"


@tool
def get_appeal_deadline(case_id: str) -> str:
    """Get the appeal deadline for the case judgment. Use this tool when asked about appeal deadline (موعد الاستئناف, "appeal deadline", "when can I appeal")."""
    try:
        with MongoManager(**CONFIG['mongodb']) as mongo:
            documents_collection = mongo.db['documents']
            
            # Get court judgment document
            judgment_docs = list(documents_collection.find({
                'case_id': ObjectId(case_id),
                'document_type': 'court_judgment'
            }).sort('created_at', -1))
            
            if not judgment_docs:
                return json.dumps({'message': 'No judgment found for this case yet, so appeal deadline is not available.'}, ensure_ascii=False)
            
            # Get most recent judgment
            judgment = judgment_docs[0]
            entities = judgment.get('extracted_entities', {}) or {}
            appeal_deadline = entities.get('appeal_deadline')
            
            return json.dumps({
                'appeal_deadline': appeal_deadline,
                'judgment_date': entities.get('judgment_date'),
                'judgment_file': judgment.get('file_name')
            }, indent=2, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"Error getting appeal deadline: {e}", exc_info=True)
        return f"Error: {str(e)}"


# Create tools list
tools = [
    check_case_id_needed,  # Check if case ID is needed (should be called first for vague queries)
    query_cases,
    query_parties,
    query_charges,
    query_documents,
    query_victims,
    query_accused,
    get_case_incident_details,
    get_case_location_info,
    get_case_dates_times,
    get_case_medical_info,
    get_case_weapons_tools,
    get_case_confession_denial,
    get_case_waiver_info,
    get_case_verdict_punishment,
    get_case_current_status,
    get_case_police_station,
    get_judge_name,  # Dedicated tool for judge name
    get_verdict_level,  # Dedicated tool for verdict/court level
    get_judgment_date,  # Dedicated tool for judgment date
    get_appeal_deadline  # Dedicated tool for appeal deadline
]

# Bind tools to LLM
llm_with_tools = llm.bind_tools(tools)

# Create tool node
tool_node = ToolNode(tools)

# System prompt
SYSTEM_PROMPT = f"""You are a friendly and helpful legal case management assistant for Qatar's judicial system. You communicate in a warm, professional, and approachable manner while providing accurate information.

{SCHEMA_INFO}

CRITICAL RULE #0 - JUDGE QUERIES (READ THIS FIRST):
**If the user asks "who was the judge?", "من هو القاضي?", "judge name", or ANY question about the JUDGE:**
- You MUST use `get_judge_name(case_id='...')` tool
- NEVER use `query_accused` - the judge is NOT an accused person
- NEVER use `query_parties` - the judge is NOT a party to the case
- NEVER use `query_victims` - the judge is NOT a victim
- The judge presides over the case and makes legal decisions
- Judge ≠ Accused/Defendant (متهم) - completely different roles!

IMPORTANT RULES:
1. **CHECK FOR CASE ID FIRST**: If the user asks a vague question about a SPECIFIC CASE (e.g., "who was the accused?", "what happened in the case?", "what is the verdict?", "who was the judge?") without specifying a case ID, the system will automatically check the conversation history for a previously mentioned case ID. 
   - **AUTOMATIC CASE ID EXTRACTION**: If a case ID is found in the conversation history, it will be provided in a system message (format: "CASE ID: [24-character hex string]"). When you see this, use the case ID directly - DO NOT call `check_case_id_needed`.
   - **IF NO CASE ID IN HISTORY**: If no case ID is found in the conversation history, you MUST call the `check_case_id_needed` tool to ask the user for the case ID.
   - **IMPORTANT**: Only use `check_case_id_needed` if the question is clearly about a specific case AND no case ID was found in history. Do NOT use it for:
     * General questions like "I have a question" or "Can you help me?"
     * Questions about how the system works
     * General inquiries that are not case-specific
     * Questions that don't mention cases, parties, charges, incidents, or legal matters
   - **CRITICAL - CASE ID EXTRACTION**: When you see a system message that says "CRITICAL INSTRUCTION" and contains "CASE ID: [24-character hex string]", this means a case ID has been extracted from conversation history. You MUST:
     a. **IMMEDIATELY extract the case ID from that system message** (look for "CASE ID: " followed by a 24-character hex string)
     b. **ABSOLUTELY DO NOT call check_case_id_needed** - the case ID is already provided, calling it again will cause an infinite loop
     c. **IMMEDIATELY call the appropriate tool** with the provided case ID:
        * If question is about judge (القاضي, "who was the judge") → call get_judge_name(case_id='[the case ID]')
        * If about verdict level/court level → call get_verdict_level(case_id='[the case ID]')
        * If about police station → call get_case_police_station(case_id='[the case ID]')
        * If about judgment date → call get_judgment_date(case_id='[the case ID]')
        * If about appeal deadline → call get_appeal_deadline(case_id='[the case ID]')
        * If about accused/defendant → call query_accused(case_id='[the case ID]')
        * If about victims → call query_victims(case_id='[the case ID]')
        * If about incident → call get_case_incident_details(case_id='[the case ID]')
        * If about verdict/punishment → call get_case_verdict_punishment(case_id='[the case ID]')
        * etc.
     d. Provide a complete answer using the tool results
     e. **NEVER call check_case_id_needed when a case ID is provided in a system message**
   - Example flow: 
     * User: "who was the accused?" 
     * You: "عذراً، يبدو أنك تسأل عن قضية معينة، لكن لم أتمكن من تحديد رقم القضية..."
     * User: "yes" 
     * System: "IMPORTANT: The case ID is: 6979c405fa024fa3f8a3ad1b"
     * You: Call query_accused("6979c405fa024fa3f8a3ad1b") and answer "who was the accused?"
   - If no case ID is found, respond with the clarification message asking the user to specify which case
2. **YOU MUST USE TOOLS** for any query about cases, parties, charges, documents, incidents, or legal matters. DO NOT answer from memory, general knowledge, or conversation history - ALWAYS call the appropriate tool(s) first, even if you think you know the answer from previous messages.
   - **CRITICAL RULE**: If you see a system message with "CRITICAL INSTRUCTION" and "CASE ID: [24-character hex string]", you MUST:
     * Extract the case ID from that message
     * Call the appropriate tool IMMEDIATELY with that case_id parameter
     * DO NOT call check_case_id_needed - it will cause an infinite loop
     * DO NOT ask for the case ID again
   - **CRITICAL - JUDGE QUERIES**: When asked about the judge (القاضي, "who was the judge", "judge name", "judge"), you MUST use `get_judge_name` tool - NEVER use `query_accused`, `query_parties`, or any other tool. The judge is NOT a defendant, accused party, or victim. Examples:
     * "who was the judge?" → get_judge_name(case_id='...')
     * "من هو القاضي؟" → get_judge_name(case_id='...')
     * "judge name" → get_judge_name(case_id='...')
     * "القاضي" → get_judge_name(case_id='...')
     * DO NOT confuse judge with accused/defendant - they are completely different!
3. **CRITICAL**: Even if conversation history mentions a case ID or details, you MUST still call tools to get the current, accurate data from MongoDB. Do not rely on information from previous messages - always query the database.
4. When user asks about "case N" or "case number N", they mean case_id=N (the internal case ID)
5. Always use Arabic names (name_ar) as primary - English names are secondary
6. When querying parties, use query_parties with case_id parameter
7. When querying victims, use query_victims tool
8. When querying accused, use query_accused tool
9. If a tool returns empty results, respond in a friendly way: "عذراً، لم أتمكن من العثور على نتائج مطابقة لطلبك. هل يمكنك التأكد من رقم القضية أو إعادة صياغة السؤال؟" (Sorry, I couldn't find matching results. Could you please verify the case number or rephrase your question?)
9.5. **INTELLIGENT DATA MERGING (SILENT)**: When presenting information about people (accused, victims, parties, witnesses, etc.), if you see multiple entries with the SAME NAME (name_ar or name_en matches) but different or complementary information fields, you MUST intelligently merge them into ONE entry in your response. This applies to ALL queries about people/parties:
   - **Merging Logic**: If two or more entries have the same name (or very similar names), combine all available information from all entries:
     * Use the name from any entry (they should match)
     * Combine personal_id from whichever entry has it
     * Combine occupation from whichever entry has it  
     * Combine nationality from whichever entry has it
     * Combine any other fields (address, phone, etc.) from whichever entry has them
   - **Presentation**: Present it as a SINGLE person with complete information, not as duplicates
   - **CRITICAL - DO NOT MENTION MERGING**: Never mention that you merged data, combined entries, or performed any deduplication. Present the information naturally as if it came from a single source. Do not say things like "I merged the entries", "I combined the data", "I found duplicate entries and merged them", "The system merged...", or any similar phrases. Just present the complete information naturally.
   - **Example**: If tool returns:
     * Entry 1: name="Ahmed Ali", occupation="Engineer", personal_id=""
     * Entry 2: name="Ahmed Ali", occupation="", personal_id="123456"
     * Present as: "Ahmed Ali - Personal ID: 123456, Occupation: Engineer" (one person, not two)
     * DO NOT say: "I found two entries for Ahmed Ali and merged them" or "I combined duplicate entries"
   - **When to merge**: Merge entries that have the same or very similar names (exact match or minor variations)
   - **When NOT to merge**: If names are clearly different people, keep them separate
   - This helps avoid confusion and presents accurate, complete information to users
10. **HANDLING GENERAL QUESTIONS**: For general questions that are NOT about specific cases (e.g., "I have a question", "Can you help me?", "How does this work?", "What can you do?"), respond naturally and conversationally WITHOUT calling any tools. Be helpful and friendly, explain what you can do, and invite them to ask about specific cases. Do NOT use check_case_id_needed or any case-related tools for these general inquiries.
11. **COMMUNICATION STYLE**: Be warm, friendly, and conversational while remaining professional. Use natural, flowing language. Start responses with friendly greetings when appropriate (مرحباً، أهلاً وسهلاً). Show empathy and understanding.
12. Format Arabic text properly in responses
13. **NEVER invent or guess any fact** that is not present in tool results or clearly implied by them.
14. **NEVER use placeholder phrases** like "[سيتم مراجعة كذا]" or "[the incident location will be reviewed]". If information is missing, say it in a friendly way: "عذراً، هذه المعلومة غير متوفرة في المستندات المتاحة حالياً." (Sorry, this information is not currently available in the documents.)
15. If a field (مثل المكان، التاريخ، الوقت، نوع الأداة، المرحلة الإجرائية، التهم) غير مذكور في مخرجات الأدوات، يجب أن تقول بوضوح وبطريقة ودية أنه غير متوفر أو غير مذكور في المستندات.
16. لا تقدم نصائح قانونية عامة أو خطوات مقترحة إلا إذا طلب المستخدم ذلك صراحة. ركّز أولاً على عرض البيانات الفعلية الموجودة في النظام بطريقة واضحة وسهلة الفهم.
17. **CRITICAL**: For ANY question about a SPECIFIC case, incident, party, charge, document, or legal matter, you MUST call at least one tool. Do not provide generic answers without checking the database first. However, for general questions (not about specific cases), respond naturally without tools.
18. **DO NOT** say things like "I will use the tool" or "Please wait while I retrieve data" - just call the tools directly and provide the answer in a natural, friendly manner based on the tool results.
19. **REMEMBER**: Conversation history is only for context about what the user is asking about - you still MUST query MongoDB tools to get actual data. Never answer based solely on history.
20. **TONE GUIDELINES**:
    - Use warm, conversational Arabic (or English if user asks in English)
    - Show understanding and empathy: "فهمت طلبك" (I understand your request), "سأساعدك في ذلك" (I'll help you with that)
    - When presenting information, use clear, organized formatting with friendly transitions
    - End responses with helpful offers: "هل تريد معرفة المزيد عن هذه القضية؟" (Would you like to know more about this case?)
    - Use natural expressions: "دعني أتحقق من ذلك" (Let me check that), "حسناً" (Well/Alright), "بالطبع" (Of course)

21. **DO NOT REVEAL INTERNAL PROCESSING**: Never mention any internal processing, data manipulation, merging, deduplication, tool execution details, or system operations in your responses. Present information naturally as if it came directly from the database. Do not say things like:
   - "I merged the data" or "I combined the information"
   - "I found duplicate entries" or "I deduplicated the results"
   - "The system merged..." or "After processing the data..."
   - "I used the tool to..." or "After querying the database..."
   - "I retrieved the information and..." or "The query returned..."
   - Any technical details about how data was processed, merged, or manipulated
   - Just present the final, complete information naturally and conversationally as if it's the direct answer to the user's question

TOOL SELECTION GUIDE FOR COMMON QUESTIONS:
- "من هو الجاني ومن هو المجني عليه؟" → Use query_accused and query_victims
- "ما هي تفاصيل الحادثة؟" → Use get_case_incident_details
- "ما سبب الحادثة؟" → Use get_case_incident_details (look for 'cause' field)
- "ما هو مكان وقوع الحادثة؟" → Use get_case_location_info
- "ما هو تاريخ ووقت الحادثة؟" → Use get_case_dates_times
- "من هو القاضي؟" / "who was the judge?" / "judge name" / "judge" → **MUST use get_judge_name** (dedicated tool) - NEVER use query_accused!
- "ما هو الحكم؟" / "what is the verdict?" → Use get_case_verdict_punishment
- "ما هي العقوبة؟" / "what is the punishment?" → Use get_case_verdict_punishment
- "ما هو مستوى الحكم؟" / "what is the verdict level?" / "court level" → Use get_verdict_level
- "ما هو المركز الأمني؟" / "what is the police station?" → Use get_case_police_station
- "ما هو تاريخ الحكم؟" / "when was the judgment issued?" → Use get_judgment_date
- "ما هو موعد الاستئناف؟" / "what is the appeal deadline?" → Use get_appeal_deadline
- "في أي مستشفى تم نقل المشتكي؟" → Use get_case_medical_info
- "هل توجد إصابات؟" → Use get_case_medical_info
- "ما الأداة المستخدمة؟" → Use get_case_weapons_tools
- "هل كان المتهم تحت تأثير مسكر؟" → Use get_case_medical_info (alcohol_tests) or get_case_incident_details
- "هل وُجد تهديد باستخدام سلاح؟" → Use get_case_incident_details or get_case_weapons_tools
- "ما هي الجريمة محل البلاغ؟" → Use query_charges
- "ما الإجراءات التي اتخذتها الشرطة؟" → Use get_case_incident_details (police_actions)
- "هل اعترف المتهم؟" → Use get_case_confession_denial
- "هل أنكر المتهم؟" → Use get_case_confession_denial
- "هل تنازل المجني عليه؟" → Use get_case_waiver_info
- "ما المرحلة الإجرائية الحالية؟" → Use get_case_current_status
- "ما العقوبة الصادرة؟" → Use get_case_verdict_punishment
- "ما هو المركز الأمني؟" → Use get_case_police_station

Always respond in Arabic when the question is in Arabic. Provide detailed, comprehensive answers using the appropriate tools, presented in a friendly and easy-to-understand manner.

Available tools:
- check_case_id_needed: **USE THIS ONLY** when user asks vague questions about SPECIFIC CASES (mentions cases, parties, charges, incidents) without specifying a case ID. Do NOT use for general questions like "I have a question" or "Can you help?". This tool checks if a case ID is needed and looks for it in conversation history.
- query_cases: Find cases by reference numbers
- query_parties: Find parties by case_id, name, or personal_id
- query_charges: Find charges by case_id or article_number
- query_documents: Find documents by case_id or type
- query_victims: Find victims (مشتكي) in a case
- query_accused: Find accused (متهم) in a case
- get_case_incident_details: Get detailed incident information (what happened, cause, location, date/time)
- get_case_location_info: Get location information (incident location, police station, court, hospital)
- get_case_dates_times: Get all dates and times (incident, report, court sessions, judgment)
- get_case_medical_info: Get medical information (injuries, hospital transfers, lab tests, alcohol tests)
- get_case_weapons_tools: Get information about weapons or tools used
- get_case_confession_denial: Get information about confessions or denials
- get_case_waiver_info: Get information about waivers (تنازل)
- get_case_verdict_punishment: Get final verdict and punishment/sentence
- get_case_current_status: Get current procedural status/stage
- get_case_police_station: Get the police station that registered the complaint
- get_judge_name: Get the name of the judge who presided over the case (القاضي)
- get_verdict_level: Get the verdict level/court level for the case judgment (مستوى الحكم)
- get_judgment_date: Get the date when the judgment was issued (تاريخ الحكم)
- get_appeal_deadline: Get the appeal deadline for the case judgment (موعد الاستئناف)
"""


# Create graph
def create_agent():
    workflow = StateGraph(AgentState)
    
    def should_continue(state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools"
        return END
    
    def call_model(state: AgentState):
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
        
        # Check if a case ID was already extracted (to avoid re-extraction)
        case_id_already_extracted = False
        extracted_case_id = None
        for msg in state["messages"]:
            if isinstance(msg, SystemMessage) and "CASE ID:" in msg.content:
                case_id_already_extracted = True
                # Extract the case ID from the system message
                import re
                case_id_match = re.search(r'CASE ID:\s*([0-9a-fA-F]{24})', msg.content)
                if case_id_match:
                    extracted_case_id = case_id_match.group(1)
                break
        
        # Get the last user message
        last_user_msg = None
        last_user_msg_content = None
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                last_user_msg = msg.content.lower().strip()
                last_user_msg_content = msg.content
                break
        
        # Check if user said "yes" or similar confirmation - if so, extract case ID from history
        if not case_id_already_extracted and last_user_msg and any(keyword in last_user_msg for keyword in ["yes", "نعم", "ok", "حسناً", "تمام", "موافق"]):
            # User confirmed - check if we need to extract case ID
            case_id = _extract_case_id_from_messages(state["messages"])
            if case_id:
                logger.info(f"✅ Extracted case ID from conversation history: {case_id}")
                # Find the original question (the one before the clarification request)
                original_question = None
                for msg in reversed(state["messages"][:-1]):  # Skip the last "yes" message
                    if isinstance(msg, HumanMessage):
                        # Skip if it's also a confirmation
                        content_lower = msg.content.lower().strip()
                        if not any(kw in content_lower for kw in ["yes", "نعم", "ok", "حسناً", "تمام", "موافق"]):
                            original_question = msg.content
                            break
                
                # Add a clear, explicit hint message with the case ID prominently displayed
                if original_question:
                    hint_msg = SystemMessage(content=f"CRITICAL INSTRUCTION: The user confirmed to use a case ID from earlier conversation.\n\nCASE ID: {case_id}\n\nORIGINAL QUESTION: '{original_question}'\n\nYOU MUST IMMEDIATELY call the appropriate tool (e.g., get_case_verdict_punishment, query_accused, etc.) with case_id='{case_id}' to answer the original question. DO NOT call check_case_id_needed - the case ID is provided above.")
                else:
                    hint_msg = SystemMessage(content=f"CRITICAL INSTRUCTION: The user confirmed to use a case ID from earlier conversation.\n\nCASE ID: {case_id}\n\nLook at the conversation history to find the original question and IMMEDIATELY call the appropriate tool with case_id='{case_id}'. DO NOT call check_case_id_needed - the case ID is provided above.")
                messages = [SystemMessage(content=SYSTEM_PROMPT), hint_msg] + [m for m in state["messages"] if not isinstance(m, SystemMessage)]
        
        # PROACTIVE CASE ID EXTRACTION: If user asks a case-related question without a case ID,
        # check if there's a case ID in the conversation history BEFORE calling the LLM
        elif not case_id_already_extracted and last_user_msg_content:
            # Check if the query is case-related (similar logic to check_case_id_needed)
            case_keywords = [
                "case", "قضية", "دعوى", "ملف", "verdict", "حكم", "judgment",
                "party", "طرف", "متهم", "مشتكي", "victim", "accused",
                "charge", "جريمة", "مادة", "اتهام",
                "incident", "حادثة", "document", "مستند",
                "court", "محكمة", "prosecution", "نيابة", "police", "شرطة",
                "judge", "قاضي"
            ]
            case_phrases = [
                "who was the", "من هو", "من هي",
                "what happened in the case", "ماذا حدث في القضية",
                "which case", "أي قضية",
                "the accused", "المتهم",
                "the victim", "المجني عليه", "المشتكي"
            ]
            has_case_keyword = any(keyword in last_user_msg.lower() for keyword in case_keywords)
            has_case_phrase = any(phrase in last_user_msg.lower() for phrase in case_phrases)
            
            # Check if query contains a case ID
            import re
            case_id_pattern = r'\b[0-9a-fA-F]{24}\b'
            case_ids_in_query = re.findall(case_id_pattern, last_user_msg_content)
            
            # If it's a case-related query without a case ID, check history
            if (has_case_keyword or has_case_phrase) and not case_ids_in_query:
                case_id = _extract_case_id_from_messages(state["messages"])
                if case_id:
                    logger.info(f"✅ Proactively extracted case ID from conversation history for query: {last_user_msg_content[:50]}...")
                    # Determine which tool to use based on the question
                    question_lower = last_user_msg_content.lower()
                    tool_hint = ""
                    if any(keyword in question_lower for keyword in ["judge", "قاضي", "who was the judge"]):
                        tool_hint = "get_judge_name(case_id='{case_id}')"
                    elif any(keyword in question_lower for keyword in ["accused", "defendant", "متهم", "الجاني"]):
                        tool_hint = "query_accused(case_id='{case_id}')"
                    elif any(keyword in question_lower for keyword in ["victim", "مشتكي", "المجني عليه"]):
                        tool_hint = "query_victims(case_id='{case_id}')"
                    elif any(keyword in question_lower for keyword in ["verdict level", "court level", "مستوى الحكم"]):
                        tool_hint = "get_verdict_level(case_id='{case_id}')"
                    elif any(keyword in question_lower for keyword in ["police station", "المركز الأمني"]):
                        tool_hint = "get_case_police_station(case_id='{case_id}')"
                    else:
                        tool_hint = "the appropriate tool"
                    
                    hint_msg = SystemMessage(content=f"CRITICAL INSTRUCTION: The user asked a case-related question without specifying a case ID, but a case ID was found in the conversation history.\n\nCASE ID: {case_id}\n\nCURRENT QUESTION: '{last_user_msg_content}'\n\nYOU MUST IMMEDIATELY call {tool_hint} to answer the question. DO NOT call check_case_id_needed - the case ID is provided above.")
                    messages = [SystemMessage(content=SYSTEM_PROMPT), hint_msg] + [m for m in state["messages"] if not isinstance(m, SystemMessage)]
        
        # If case ID was already extracted, make sure it's in the messages
        elif case_id_already_extracted and extracted_case_id:
            # Re-inject the case ID instruction to ensure it's used
            hint_msg = SystemMessage(content=f"CRITICAL INSTRUCTION: A case ID has been extracted from conversation history.\n\nCASE ID: {extracted_case_id}\n\nYOU MUST use this case ID to answer the user's question. Call the appropriate tool with case_id='{extracted_case_id}'. DO NOT call check_case_id_needed.")
            messages = [SystemMessage(content=SYSTEM_PROMPT), hint_msg] + [m for m in state["messages"] if not isinstance(m, SystemMessage) or "CASE ID:" not in str(m.content)]
        
        response = llm_with_tools.invoke(messages)
        # Append the response to existing messages (don't replace!)
        return {"messages": state["messages"] + [response]}
    
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            END: END
        }
    )
    workflow.add_edge("tools", "agent")
    
    return workflow.compile()


# Create agent instance
agent = create_agent()


async def query_stream(user_query: str, conversation_history: Optional[List] = None):
    """
    Execute a natural language query with streaming support.
    Yields tokens as they are generated.
    
    Args:
        user_query: The user's question/query
        conversation_history: Optional list of LangChain messages (HumanMessage/AIMessage) for context
    
    Yields:
        str: Tokens/chunks of the response as they are generated
    """
    try:
        logger.info(f"Executing streaming query: {user_query[:100]}...")
        
        # Build messages list with conversation history if provided
        messages_list = []
        if conversation_history:
            messages_list.extend(conversation_history)
            logger.info(f"Using {len(conversation_history)} messages from conversation history")
        
        # Add current query
        messages_list.append(HumanMessage(content=user_query))
        
        logger.info(f"Streaming agent with {len(messages_list)} messages total")
        
        # Stream events from the agent using astream_events
        full_response = ""
        async for event in agent.astream_events(
            {
                "messages": messages_list,
                "query": user_query,
                "results": None,
                "error": None
            },
            version="v2"
        ):
            # Stream LLM token generation events
            if event.get("event") == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk", {})
                if hasattr(chunk, "content") and chunk.content:
                    content = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                    if content:
                        full_response += content
                        yield content
            
            # Handle final AIMessage after tool execution
            elif event.get("event") == "on_chain_end":
                name = event.get("name", "")
                if name == "agent":
                    output = event.get("data", {}).get("output", {})
                    if output and "messages" in output:
                        for msg in output["messages"]:
                            if isinstance(msg, AIMessage) and hasattr(msg, "content"):
                                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                                # Yield any remaining content that wasn't streamed
                                if content and len(content) > len(full_response):
                                    remaining = content[len(full_response):]
                                    if remaining:
                                        yield remaining
                                        full_response = content
        
        logger.info(f"✅ Streaming completed (total length: {len(full_response)})")
        
    except Exception as e:
        logger.error(f"Error in streaming query: {e}", exc_info=True)
        yield f"Error: {str(e)}"


def query(user_query: str, conversation_history: Optional[List] = None) -> str:
    """
    Execute a natural language query using the agent with MongoDB tools.
    
    Args:
        user_query: The user's question/query
        conversation_history: Optional list of LangChain messages (HumanMessage/AIMessage) for context
    """
    try:
        logger.info(f"Executing query: {user_query[:100]}...")
        
        # Build messages list with conversation history if provided
        # IMPORTANT: Include ALL messages (both user and assistant) so the agent can find case IDs mentioned earlier
        messages_list = []
        if conversation_history:
            # Include all messages - assistant messages may contain case IDs that were fetched earlier
            messages_list.extend(conversation_history)
            logger.info(f"Using {len(conversation_history)} messages from conversation history (includes both user and assistant messages for case ID extraction)")
        
        # Add current query
        messages_list.append(HumanMessage(content=user_query))
        
        # Check if query is vague (case-related but no case ID) - this helps the agent know to use check_case_id_needed
        case_keywords = [
            "case", "قضية", "دعوى", "ملف", "verdict", "حكم", "judgment",
            "party", "طرف", "متهم", "مشتكي", "victim", "accused",
            "charge", "جريمة", "مادة", "اتهام",
            "incident", "حادثة", "document", "مستند"
        ]
        query_lower = user_query.lower()
        is_case_query = any(keyword in query_lower for keyword in case_keywords)
        
        # Check if case ID is in query (ObjectId pattern: 24 hex characters)
        import re
        case_id_pattern = r'\b[0-9a-fA-F]{24}\b'
        has_case_id = bool(re.search(case_id_pattern, user_query))
        
        if is_case_query and not has_case_id:
            logger.info("⚠️  Vague case query detected - agent should use check_case_id_needed tool")
        
        logger.info(f"Invoking agent with {len(messages_list)} messages total")
        result = agent.invoke({
            "messages": messages_list,
            "query": user_query,
            "results": None,
            "error": None
        })
        
        # Extract the final AI response after all tool calls
        messages = result.get("messages", [])
        logger.info(f"Agent returned {len(messages)} messages in final state")
        
        # Debug: Log message types
        msg_types = {}
        for msg in messages:
            msg_type = type(msg).__name__
            msg_types[msg_type] = msg_types.get(msg_type, 0) + 1
        logger.info(f"Message types: {msg_types}")
        
        # Log tool calls for debugging
        # Check for both: AIMessage with tool_calls (initiated) AND ToolMessage (executed)
        tool_calls_count = 0
        tool_names = []
        tool_messages_count = 0
        
        for msg in messages:
            # Check for AIMessage that initiated tool calls
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                tool_calls_count += len(msg.tool_calls)
                tool_names.extend([tc.get('name', 'unknown') for tc in msg.tool_calls])
            # Check for ToolMessage (means tool was executed)
            elif isinstance(msg, ToolMessage):
                tool_messages_count += 1
                # Extract tool name from ToolMessage if available
                if hasattr(msg, 'name'):
                    tool_names.append(msg.name)
        
        # Tools were called if we have either tool_calls OR ToolMessages
        tools_were_called = tool_calls_count > 0 or tool_messages_count > 0
        
        if tools_were_called:
            logger.info(f"✅ Agent executed tools: {tool_calls_count} tool call(s) initiated, {tool_messages_count} tool message(s) returned")
            if tool_names:
                logger.info(f"✅ Tools used: {tool_names}")
        else:
            # Check if this is a case-related query that SHOULD have called tools
            case_keywords = [
                "case", "قضية", "دعوى", "ملف", "verdict", "حكم", "judgment",
                "party", "طرف", "متهم", "مشتكي", "victim", "accused",
                "charge", "جريمة", "مادة", "اتهام",
                "incident", "حادثة", "document", "مستند"
            ]
            query_lower = user_query.lower()
            is_case_query = any(keyword in query_lower for keyword in case_keywords)
            
            if is_case_query:
                logger.error(f"❌ ERROR: No tools were called for case-related query: {user_query[:100]}...")
                logger.error("This query should have called MongoDB tools! The agent may be hallucinating.")
                # Return an error message instead of potentially fake data
                return "عذراً، حدث خطأ في استرجاع البيانات من قاعدة البيانات. يرجى المحاولة مرة أخرى أو إعادة صياغة السؤال."
            else:
                logger.info(f"ℹ️  No tools called for general query (this is OK for non-case queries)")
        
        if messages:
            # Find the last AIMessage that doesn't have tool_calls (final answer)
            # The workflow should complete with: HumanMessage -> AIMessage (with tool_calls) -> ToolMessages -> AIMessage (final answer)
            # We want the LAST AIMessage that has NO tool_calls (meaning tools already executed)
            
            # First, check if we have any tool calls at all
            has_tool_calls = False
            for msg in messages:
                if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                    has_tool_calls = True
                    break
            
            # If we have tool calls, we MUST have a final answer after tool execution
            # Find the last AIMessage that comes AFTER all tool messages
            final_answer = None
            found_tool_messages = False
            
            for msg in reversed(messages):
                # Check if this is a ToolMessage (means tools executed)
                if isinstance(msg, ToolMessage):
                    found_tool_messages = True
                    continue
                
                # After finding tool messages, the next AIMessage should be the final answer
                if isinstance(msg, AIMessage):
                    if found_tool_messages:
                        # This is the final answer after tool execution
                        final_answer = msg
                        break
                    elif hasattr(msg, 'tool_calls') and msg.tool_calls:
                        # This is a tool-calling message, skip it
                        continue
                    elif not has_tool_calls:
                        # No tools were called, this is the direct answer
                        final_answer = msg
                        break
            
            # If we didn't find a final answer after tools, try to find any AIMessage without tool_calls
            if not final_answer:
                for msg in reversed(messages):
                    if isinstance(msg, AIMessage):
                        if hasattr(msg, 'tool_calls') and msg.tool_calls:
                            continue  # Skip tool-calling messages
                        final_answer = msg
                        break
            
            if final_answer and hasattr(final_answer, 'content'):
                answer_text = final_answer.content if isinstance(final_answer.content, str) else str(final_answer.content)
                
                # CRITICAL CHECK: If this is a case-related query and no tools were called, reject the answer
                case_keywords = [
                    "case", "قضية", "دعوى", "ملف", "verdict", "حكم", "judgment",
                    "party", "طرف", "متهم", "مشتكي", "victim", "accused",
                    "charge", "جريمة", "مادة", "اتهام",
                    "incident", "حادثة", "document", "مستند"
                ]
                query_lower = user_query.lower()
                is_case_query = any(keyword in query_lower for keyword in case_keywords)
                
                # Use the same detection logic - check for both tool_calls and ToolMessages
                tools_were_called_check = tool_calls_count > 0 or tool_messages_count > 0
                if is_case_query and not tools_were_called_check:
                    logger.error(f"❌ REJECTING ANSWER: Case query but no tools called! Answer was: {answer_text[:200]}...")
                    return "عذراً، لم يتم استرجاع البيانات من قاعدة البيانات. يرجى المحاولة مرة أخرى أو إعادة صياغة السؤال بشكل أكثر تحديداً."
                
                # Remove any "I will use tool" type messages - these shouldn't be in final answer
                if "will be used" in answer_text.lower() or "please wait" in answer_text.lower() or "retrieving" in answer_text.lower():
                    logger.warning(f"Got intermediate message instead of final answer: {answer_text[:200]}")
                    # Try to find another message
                    for msg in reversed(messages):
                        if isinstance(msg, AIMessage) and msg != final_answer:
                            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                                continue
                            if hasattr(msg, 'content'):
                                alt_text = msg.content if isinstance(msg.content, str) else str(msg.content)
                                if "will be used" not in alt_text.lower() and "please wait" not in alt_text.lower():
                                    logger.info("Using alternative message")
                                    return alt_text
                    return "حدث خطأ في معالجة الاستعلام. يرجى المحاولة مرة أخرى."
                
                tools_status = f"{tool_calls_count} calls, {tool_messages_count} executed" if tools_were_called_check else "none"
                logger.info(f"✅ Returning final answer (length: {len(answer_text)}, tools: {tools_status})")
                return answer_text
            elif final_answer:
                logger.warning("Final answer found but no content attribute")
                return str(final_answer)
            
            # Fallback: if no final answer found, return last message content
            logger.warning("No final AI answer found, using last message")
            last_message = messages[-1]
            if hasattr(last_message, 'content'):
                return last_message.content if isinstance(last_message.content, str) else str(last_message.content)
            return str(last_message)
        
        logger.error("No messages returned from agent")
        return "No response generated."
    
    except Exception as e:
        logger.error(f"Error executing query: {e}", exc_info=True)
        return f"Error: {str(e)}"


def main():
    """Interactive query interface"""
    print("=" * 60)
    print("Legal Case Query Agent (MongoDB)")
    print("=" * 60)
    print("Type 'exit' or 'quit' to exit\n")
    
    while True:
        try:
            user_input = input("Query: ").strip()
            if user_input.lower() in ['exit', 'quit', 'q']:
                print("Goodbye!")
                break
            
            if not user_input:
                continue
            
            print("\nProcessing...")
            result = query(user_input)
            print(f"\n{result}\n")
            print("-" * 60)
        
        except KeyboardInterrupt:
            print("\n\nExiting...")
            break
        except Exception as e:
            print(f"\nError: {str(e)}\n")


if __name__ == '__main__':
    main()

