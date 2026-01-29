"""
Chat service for QPPChatbot

Provides a thin wrapper around Groq/Anthropic models for conversational chat,
using existing CONFIG settings. Integrates with MongoDB query agent tools to answer
questions about legal cases.
"""

from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from config import CONFIG
from mongo_manager import MongoManager

logger = logging.getLogger(__name__)

# Import the MongoDB query agent high-level function (raw answer)
try:
    from query_agent_mongo import query as mongo_query, SYSTEM_PROMPT as QUERY_SYSTEM_PROMPT
    QUERY_AGENT_AVAILABLE = True
except ImportError:
    logger.warning("query_agent_mongo not available, chat will use basic LLM without case data")
    QUERY_AGENT_AVAILABLE = False


def _get_llm() -> ChatGroq:
    """Initialize and return a ChatGroq client using CONFIG."""
    return ChatGroq(
        model=CONFIG["groq"]["model"],
        temperature=0.2,
        groq_api_key=CONFIG["groq"]["api_key"],
    )


def _build_system_prompt() -> str:
    """
    Base system prompt for the chat assistant.
    
    Uses the query agent system prompt if available, otherwise falls back to basic prompt.
    """
    if QUERY_AGENT_AVAILABLE:
        return QUERY_SYSTEM_PROMPT
    return (
        "You are an AI assistant helping users understand and work with legal cases. "
        "Answer clearly and concisely. When the user asks about specific case numbers "
        "or legal documents, you may reference the case database if that context is provided. "
        "If you don't know something, say that you don't know rather than guessing."
    )


def _should_use_query_agent(user_message: str) -> bool:
    """
    Determine if the user's message should use the query agent with MongoDB tools.
    
    Returns True if the message seems to be asking about cases, documents, parties, etc.
    """
    if not QUERY_AGENT_AVAILABLE:
        return False
    
    # Keywords that suggest case-related queries
    case_keywords = [
        "case", "قضية", "دعوى", "ملف",
        "party", "طرف", "متهم", "مشتكي", "مجني عليه",
        "charge", "جريمة", "مادة", "اتهام",
        "document", "مستند", "وثيقة",
        "judgment", "حكم", "قرار",
        "incident", "حادثة", "واقعة",
        "victim", "شاكي", "مشتكي",
        "accused", "متهم",
        "court", "محكمة",
        "police", "شرطة", "أمن",
    ]
    
    message_lower = user_message.lower()
    return any(keyword in message_lower for keyword in case_keywords)


def get_session_history_for_llm(
    mongo: MongoManager, session_id: str
) :  # returns List[HumanMessage | AIMessage]
    """
    Load messages for a session from MongoDB and convert them into LangChain messages.
    """
    from langchain_core.messages import BaseMessage  # local import to avoid circular hints

    history: List[BaseMessage] = []
    messages = mongo.get_session_messages(session_id)
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "user":
            history.append(HumanMessage(content=content))
        elif role == "assistant":
            history.append(AIMessage(content=content))
    return history


def generate_chat_response(
    session_id: str,
    user_message: str,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate an assistant reply for a given session and user message.
    
    - Ensures the session exists (creates if needed)
    - Persists the user message and assistant reply in MongoDB
    - Returns the updated session and messages for the frontend
    """
    llm = _get_llm()
    system_prompt = _build_system_prompt()

    with MongoManager(**CONFIG["mongodb"]) as mongo:
        # Create session if needed
        if not session_id:
            session_id = mongo.create_chat_session(user_id=user_id)
            logger.info(f"Created new chat session from chat_service: {session_id}")

        # Persist user message
        mongo.append_chat_message(session_id, "user", user_message)

        # Build conversation history for the model
        history = get_session_history_for_llm(mongo, session_id)
        
        # ALWAYS use the query agent with MongoDB tools for ALL queries
        # The agent can handle both case-related queries (using tools) and general questions
        try:
            if QUERY_AGENT_AVAILABLE:
                # Use the MongoDB query agent for ALL queries - it has tools and can handle everything
                # IMPORTANT: Include ALL messages (both user and assistant) so the agent can:
                # 1. Maintain context across the conversation
                # 2. Extract case IDs from assistant messages (which may have mentioned them)
                # 3. Understand the full conversation flow
                logger.info(f"Using mongo_query agent for session {session_id} with {len(history)} messages from conversation history (includes both user and assistant messages)")
                assistant_text = mongo_query(user_message, conversation_history=history)
                
                # Verify that tools were called (for case-related queries, tools should always be used)
                # If no tools were called and it's a case-related query, log a warning
                if _should_use_query_agent(user_message):
                    # Check logs or add verification here if needed
                    logger.info("Case-related query processed through agent")
            else:
                # Fallback only if query agent is not available
                logger.warning("Query agent not available, using basic LLM (no MongoDB tools)")
                messages = [SystemMessage(content=system_prompt)] + history
                response: AIMessage = llm.invoke(messages)  # type: ignore[assignment]
                assistant_text = response.content if isinstance(response.content, str) else str(
                    response.content
                )
        except Exception as e:
            logger.error(f"Error generating chat response: {e}", exc_info=True)
            assistant_text = (
                "حدث خطأ أثناء معالجة طلبك. يرجى المحاولة مرة أخرى لاحقًا أو صياغة سؤالك بشكل مختلف."
            )

        # Persist assistant message
        mongo.append_chat_message(session_id, "assistant", assistant_text)

        # Fetch updated session + messages
        session_doc = mongo.get_chat_session(session_id)
        session_messages = mongo.get_session_messages(session_id)

        # Shape response for API/frontend
        return {
            "session_id": session_id,
            "session": {
                "id": session_id,
                "title": session_doc.get("title") if session_doc else "New Chat",
                "createdAt": session_doc.get("created_at", datetime.utcnow()).isoformat()
                if session_doc and session_doc.get("created_at")
                else datetime.utcnow().isoformat(),
                "updatedAt": session_doc.get("updated_at", datetime.utcnow()).isoformat()
                if session_doc and session_doc.get("updated_at")
                else datetime.utcnow().isoformat(),
            },
            "messages": [
                {
                    "id": msg.get("_id"),
                    "sessionId": msg.get("session_id"),
                    "role": msg.get("role"),
                    "content": msg.get("content"),
                    "timestamp": msg.get("timestamp", datetime.utcnow()).isoformat()
                    if msg.get("timestamp")
                    else datetime.utcnow().isoformat(),
                }
                for msg in session_messages
            ],
        }


