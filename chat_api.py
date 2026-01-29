"""
FastAPI backend for chat companion.

Exposes REST endpoints for managing chat sessions and sending messages.
"""

from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response, FileResponse, StreamingResponse
from pydantic import BaseModel, Field
import os
import json
import asyncio

from mongo_manager import MongoManager
from config import CONFIG
from chat_service import generate_chat_response

# Suppress verbose HTTP client logs (httpx, httpcore)
import logging
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class ChatMessageDTO(BaseModel):
    id: Optional[str] = None
    sessionId: str
    role: str
    content: str
    timestamp: datetime


class ChatSessionDTO(BaseModel):
    id: str
    title: str
    createdAt: datetime
    updatedAt: datetime


class ChatSessionWithMessagesDTO(ChatSessionDTO):
    messages: List[ChatMessageDTO] = Field(default_factory=list)


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None
    userId: Optional[str] = None


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    user_id: Optional[str] = None


class ChatResponseDTO(BaseModel):
    session_id: str
    session: ChatSessionDTO
    messages: List[ChatMessageDTO]


app = FastAPI(title="QPPChatbot API")

# CORS configuration: allow local Vite dev server and ngrok by default (for development)
# In production, CORS is less critical since frontend is served from same origin
# Note: When using allow_origins=["*"], allow_credentials must be False (browser security restriction)
# For ngrok, we'll use a custom middleware that dynamically allows ngrok origins

def is_ngrok_origin(origin: str) -> bool:
    """Check if origin is an ngrok URL"""
    if not origin:
        return False
    origin_lower = origin.lower()
    return "ngrok" in origin_lower or "ngrok.io" in origin_lower or "ngrok-free.app" in origin_lower()

# Default origins for local development
default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8080",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

# Custom CORS middleware that dynamically allows ngrok origins
from starlette.middleware.cors import CORSMiddleware as StarletteCORSMiddleware
from starlette.requests import Request as StarletteRequest

class DynamicCORSMiddleware(StarletteCORSMiddleware):
    def is_allowed_origin(self, origin: str) -> bool:
        # Always allow if origin is in the list
        if origin in self.allow_origins_list:
            return True
        # Dynamically allow ngrok origins
        if is_ngrok_origin(origin):
            return True
        return False

# Use dynamic CORS middleware that allows ngrok
app.add_middleware(
    DynamicCORSMiddleware,
    allow_origins=["*"],  # Base list of allowed origins
    allow_credentials=True,  # Can use credentials since we're not using "*"
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# Explicit OPTIONS handler for API routes to ensure CORS preflight works
# This must be defined before the catch-all route
@app.options("/api/{path:path}")
async def options_handler(path: str, request: Request):
    """Handle OPTIONS preflight requests for API routes"""
    origin = request.headers.get("origin", "")
    
    # Determine allowed origin
    if not origin or origin == "null":
        allowed_origin = "*"
    elif origin in default_origins or is_ngrok_origin(origin):
        # Allow if it's in default list or is ngrok
        allowed_origin = origin
    else:
        # For development, allow any origin
        allowed_origin = origin
    
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": allowed_origin,
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, HEAD",
            "Access-Control-Allow-Headers": request.headers.get("access-control-request-headers", "*"),
            "Access-Control-Allow-Credentials": "true" if allowed_origin != "*" else "false",
            "Access-Control-Max-Age": "3600",
        }
    )

# Path to frontend dist folder
FRONTEND_DIST_PATH = os.path.join(os.path.dirname(__file__), "chat-companion-hub", "dist")

# Mount static files (assets folder for JS/CSS)
if os.path.exists(FRONTEND_DIST_PATH):
    assets_path = os.path.join(FRONTEND_DIST_PATH, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")


def _session_doc_to_dto(doc) -> ChatSessionDTO:
    return ChatSessionDTO(
        id=str(doc["_id"]),
        title=doc.get("title", "New Chat"),
        createdAt=doc.get("created_at", datetime.utcnow()),
        updatedAt=doc.get("updated_at", datetime.utcnow()),
    )


def _message_doc_to_dto(doc) -> ChatMessageDTO:
    return ChatMessageDTO(
        id=str(doc.get("_id")) if doc.get("_id") else None,
        sessionId=str(doc.get("session_id")),
        role=doc.get("role", "assistant"),
        content=doc.get("content", ""),
        timestamp=doc.get("timestamp", datetime.utcnow()),
    )


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/sessions", response_model=List[ChatSessionDTO])
def list_sessions():
    with MongoManager(**CONFIG["mongodb"]) as mongo:
        docs = mongo.list_chat_sessions()
        return [_session_doc_to_dto(doc) for doc in docs]


@app.post("/api/sessions", response_model=ChatSessionDTO)
def create_session(req: CreateSessionRequest):
    with MongoManager(**CONFIG["mongodb"]) as mongo:
        session_id = mongo.create_chat_session(user_id=req.userId, title=req.title)
        doc = mongo.get_chat_session(session_id)
        if not doc:
            raise HTTPException(status_code=500, detail="Failed to create chat session")
        return _session_doc_to_dto(doc)


@app.get("/api/sessions/{session_id}", response_model=ChatSessionWithMessagesDTO)
def get_session(session_id: str):
    with MongoManager(**CONFIG["mongodb"]) as mongo:
        doc = mongo.get_chat_session(session_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Session not found")
        messages = mongo.get_session_messages(session_id)
        return ChatSessionWithMessagesDTO(
            **_session_doc_to_dto(doc).model_dump(),
            messages=[_message_doc_to_dto(m) for m in messages],
        )


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    with MongoManager(**CONFIG["mongodb"]) as mongo:
        mongo.delete_chat_session(session_id)
    return {"status": "deleted"}


@app.post("/api/chat", response_model=ChatResponseDTO)
def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    result = generate_chat_response(
        session_id=req.session_id or "",
        user_message=req.message,
        user_id=req.user_id,
    )

    session = ChatSessionDTO(
        id=result["session"]["id"],
        title=result["session"]["title"],
        createdAt=datetime.fromisoformat(result["session"]["createdAt"]),
        updatedAt=datetime.fromisoformat(result["session"]["updatedAt"]),
    )
    messages = [
        ChatMessageDTO(
            id=m["id"],
            sessionId=m["sessionId"],
            role=m["role"],
            content=m["content"],
            timestamp=datetime.fromisoformat(m["timestamp"]),
        )
        for m in result["messages"]
    ]

    return ChatResponseDTO(
        session_id=result["session_id"],
        session=session,
        messages=messages,
    )


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    Streaming chat endpoint using Server-Sent Events (SSE).
    Streams the LLM response token by token.
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    from langchain_core.messages import HumanMessage
    from mongo_manager import MongoManager
    
    async def event_generator():
        session_id = req.session_id or ""
        full_response = ""
        
        try:
            with MongoManager(**CONFIG["mongodb"]) as mongo:
                # Create session if needed
                if not session_id:
                    session_id = mongo.create_chat_session(user_id=req.user_id)
                
                # Persist user message
                mongo.append_chat_message(session_id, "user", req.message)
                
                # Get conversation history
                history = mongo.get_session_messages(session_id)
                user_history = []
                for msg in history:
                    if msg.get("role") == "user":
                        user_history.append(HumanMessage(content=msg.get("content", "")))
                
                # Import streaming query
                from query_agent_mongo import query_stream
                
                # Stream the response
                async for chunk in query_stream(req.message, conversation_history=user_history):
                    if chunk:
                        full_response += chunk
                        # Send as SSE
                        yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
                
                # Persist complete assistant message
                mongo.append_chat_message(session_id, "assistant", full_response)
                
                # Send completion event
                session_doc = mongo.get_chat_session(session_id)
                yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'session': {'id': session_id, 'title': session_doc.get('title', 'New Chat') if session_doc else 'New Chat'}})}\n\n"
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error in streaming chat: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': 'حدث خطأ أثناء معالجة طلبك.'})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


# Serve frontend static files and handle SPA routing
# This must be after all API routes (GET only, so OPTIONS will pass through)
@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    """
    Serve frontend files. For SPA routing, all non-API routes return index.html.
    """
    # Don't interfere with API routes
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    
    # Don't interfere with assets (already mounted)
    if full_path.startswith("assets/"):
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Check if it's a request for a static file in dist root (favicon.ico, robots.txt, etc.)
    file_path = os.path.join(FRONTEND_DIST_PATH, full_path)
    
    # If it's a file that exists, serve it
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    
    # For all other routes (SPA routing), serve index.html
    index_path = os.path.join(FRONTEND_DIST_PATH, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    
    raise HTTPException(status_code=404, detail="Frontend not found")


