# RAG System Design Document
## Qatar Legal Case Management System - Retrieval Augmented Generation (RAG)

**Version:** 1.0  
**Date:** January 2025  
**Status:** Production Implementation

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [System Overview](#system-overview)
3. [Data & Ingestion](#data--ingestion)
4. [Retrieval Architecture](#retrieval-architecture)
5. [UX & Features](#ux--features)
6. [Infrastructure & Non-Functional Requirements](#infrastructure--non-functional-requirements)
7. [Security & Compliance](#security--compliance)
8. [Implementation Roadmap](#implementation-roadmap)
9. [Success Metrics & Evaluation](#success-metrics--evaluation)
10. [Future Enhancements](#future-enhancements)

---

## Executive Summary

This document describes the RAG (Retrieval Augmented Generation) system implemented for the Qatar Legal Case Management System. The system enables natural language querying of legal case documents using MongoDB for storage, vector embeddings for semantic search, and LLM-powered agents for intelligent retrieval and response generation.

**Key Capabilities:**
- Natural language queries in Arabic and English
- Semantic search across legal documents using vector embeddings
- Entity extraction and structured data storage
- Multi-turn conversational interface
- Tool-based retrieval with MongoDB integration
- **Custom fine-tuned LLM model** (self-hosted) for responses and reasoning (no external cloud LLM API dependency)

---

## System Overview

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Interface                           │
│              (React Frontend - chat-companion-hub)              │
│                    Single Port Deployment                        │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP/REST API
┌────────────────────────────▼────────────────────────────────────┐
│                      FastAPI Backend                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Chat API     │  │ Chat Service │  │ Query Agent  │          │
│  │ (REST)       │→ │ (Orchestr.)  │→ │ (LangGraph)  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
┌───────▼────────┐  ┌────────▼────────┐  ┌────────▼────────┐
│   MongoDB      │  │   LLM Engine   │  │  Embedding      │
│   (Storage)    │  │  (Qwen3-14B)   │  │  Model          │
│                │  │                │  │  (Arabic BERT)  │
│ - cases        │  │                │  │                 │
│ - documents    │  │ - Local (vLLM) │  │ - aubmindlab/   │
│ - parties      │  │                │  │   bert-base-    │
│ - embeddings   │  │                │  │   arabert       │
│ - chat_sessions│  │                │  │                 │
└────────────────┘  └────────────────┘  └────────────────┘
```

### Core Components

1. **Document Processing Pipeline**
   - Text extraction (PDF, DOCX, TXT)
   - Entity extraction (Custom LLM Model)
   - Embedding generation (Arabic BERT)
   - MongoDB storage

2. **Query Agent (LangGraph)**
   - Tool-based retrieval system
   - MongoDB query tools
   - LLM-powered reasoning
   - Multi-turn conversation support

3. **Chat Interface**
   - React frontend
   - Session management
   - Real-time messaging
   - Single-port deployment

---

## Data & Ingestion

### A) Data Types & Volume

**Current State:**
- **Format**: Primarily text files (extracted from PDFs and Word documents)
- **Volume**: ~20-50 documents per case, multiple cases
- **Language**: Arabic (primary), English (secondary)
- **Domain**: Qatar legal/judicial documents

**Supported Formats:**
- Plain text files
- PDF documents (digital PDFs with direct text extraction)
- Word documents with paragraph-based extraction

**Storage:**
- **File System**: Documents stored in designated directory structure
- **Database**: MongoDB collections for structured data
- **Embeddings**: Vector embeddings stored in database for fast similarity search

### B) Document Quality & Processing

**Text Extraction:**
- Digital PDFs: Direct text extraction
- Scanned PDFs: Requires OCR (not currently implemented)
- Word Documents: Paragraph-based extraction
- Text Files: Direct read

**Entity Extraction:**
- **Tool**:
- **Extracted Entities**:
  - Case numbers (court, prosecution, police)
  - Parties (names, personal IDs, roles)
  - Charges (article numbers, descriptions)
  - Dates (incident, report, judgment)
  - Locations (police stations, courts)
  - Medical information (injuries, hospital transfers)
  - Evidence items
  - Verdicts and punishments

**Embedding Generation:**
- **Model**: Arabic BERT model optimized for Arabic text
- **Dimension**: 768-dimensional vectors
- **Device**: CPU-optimized (GPU acceleration optional)
- **Storage**: Vector embeddings stored in database for efficient retrieval

### C) Update Frequency

**Current Implementation:**
- **Batch Processing**: Documents processed in batches
- **Incremental**: New documents can be added incrementally
- **Linking**: Automatic case linking via vector similarity

**Processing Pipeline:**
- Batch processing: Multiple documents processed together for efficiency
- Single document processing: Individual documents can be processed on-demand
- Automatic case linking: Documents automatically linked to cases via vector similarity

### D) Data Schema (MongoDB)

**Data Collections:**

1. **Cases Collection**
   - Unique case identifiers
   - Case numbers from multiple sources (court, prosecution, police)
   - Creation and update timestamps
   - Case metadata and status

2. **Documents Collection**
   - Document references and file information
   - Full document text content
   - Vector embeddings for similarity search (768 dimensions)
   - Extracted entities and structured data
   - Document type classification (police complaints, court judgments, etc.)
   - Processing status tracking

3. **Parties Collection**
   - Party names in Arabic and English
   - Personal identification numbers
   - Occupation and nationality information
   - Deduplication signatures to prevent duplicates

4. **Charges Collection**
   - Legal article numbers
   - Charge descriptions in Arabic and English
   - Charge metadata

5. **Case-Party Linking**
   - Relationships between cases and parties
   - Party roles (accused, victim, witness, etc.)

6. **Chat Sessions Collection**
   - User session management
   - Session titles and metadata
   - Creation and update timestamps

7. **Chat Messages Collection**
   - Individual messages within sessions
   - User and assistant message tracking
   - Message content and timestamps
   - Full conversation history

### E) Access & Permissions

**Current State:**
- No role-based access control (RBAC) implemented
- All documents accessible to all users
- MongoDB connection: Local/network access

**Future Requirements:**
- Department-based access control
- User role management
- Document-level permissions
- Audit logging for access

---

## Retrieval Architecture

### A) Retrieval Strategy

**Hybrid Approach:**
1. **Vector Similarity Search** (Primary)
   - Cosine similarity on document embeddings
   - Threshold: 0.8 (configurable)
   - Used for document linking and semantic search

2. **Structured Query Tools** (Secondary)
   - MongoDB query tools for specific entities
   - Case lookup by reference numbers
   - Party search by name/ID
   - Charge lookup by article number

3. **LLM-Powered Tool Selection**
   - LangGraph agent selects appropriate tools
   - Multi-step reasoning for complex queries
   - Tool execution with MongoDB queries

### B) Embedding Model

**Model**: Arabic BERT model
- **Type**: Specialized BERT model for Arabic language processing
- **Dimension**: 768-dimensional vector space
- **Language Support**: Arabic (primary), English (secondary)
- **Performance**: Optimized for CPU, with optional GPU acceleration

**Embedding Generation:**
- Document text is extracted from source files
- Text is processed through Arabic BERT model
- Generates 768-dimensional vector representation
- Vector stored in MongoDB for similarity search

### C) Retrieval Tools

**Available Tools (17 total):**

1. **Case Lookup**
   - Find cases by reference numbers (supports multiple formats)
   - Flexible number format matching

2. **Party Queries**
   - Find parties by case ID, name, or personal ID
   - Identify victims (مشتكي) in specific cases
   - Identify accused (متهم) in specific cases

3. **Charge Queries**
   - Find charges by case ID or legal article number
   - Retrieve charge descriptions and details

4. **Document Queries**
   - Find documents by case ID or document type
   - Search across document collections

5. **Detailed Case Information**
   - Incident details and descriptions
   - Location information (police stations, courts, hospitals)
   - Complete timeline of dates and times
   - Medical information (injuries, hospital transfers, lab tests)
   - Weapons and tools used in incidents
   - Confession and denial information
   - Waiver information
   - Final verdicts and punishments
   - Current procedural status and stage
   - Police station registration details

6. **Clarification Tool**
   - Intelligent detection of vague queries
   - Automatic prompting for case ID when needed
   - Context-aware case ID extraction from conversation history

### D) Query Processing Flow

**Query Processing Flow:**
1. User submits natural language query
2. System checks if query needs clarification (case ID required)
3. If clarification needed: System prompts user for case ID
4. If query is complete: AI agent selects appropriate retrieval tools
5. System executes database queries to retrieve relevant information
6. Tool results are collected and processed
7. AI generates comprehensive response based on retrieved data
8. Response delivered to user with source citations

### E) Precision vs Recall

**Current Configuration:**
- **Similarity Threshold**: 0.8 (high precision)
- **Max Similar Documents**: 10
- **Tool-based retrieval**: Ensures precision
- **LLM filtering**: Removes irrelevant results

**Trade-offs:**
- Higher threshold (0.8) → Fewer but more relevant results
- Lower threshold (0.6) → More results but may include noise
- Current setting prioritizes precision over recall

---

## UX & Features

### A) Channels

**Current Implementation:**
- **Web Application**: React frontend (chat-companion-hub)
- **API**: REST API (FastAPI)
- **Deployment**: Single-port (frontend + backend on port 8000)

**Access Methods:**
- Direct web access via browser
- Secure tunneling for remote access (ngrok support)
- RESTful API for programmatic access

**Future Channels:**
- Teams/Slack integration (API-based)
- WhatsApp bot (via API)
- Embedded widget (iframe)

### B) Response Requirements

**Current Features:**
- ✅ **Citations**: Tool results include source document references
- ✅ **Conversation Memory**: Multi-turn conversations with session history
- ✅ **Friendly Responses**: Conversational, warm tone in Arabic
- ✅ **Data Merging**: Intelligent merging of duplicate entries

**Response Format:**
- Natural language responses in Arabic (or English if user asks in English)
- Structured information when appropriate
- Friendly, professional tone
- Explicit "not available" messages for missing data

**Missing Features:**
- ❌ Downloadable source snippets
- ❌ Multi-document comparison UI
- ❌ Visual citations with document links
- ❌ Export conversation history

### C) Conversation Memory

**Implementation:**
- **Session-based**: Each conversation has a session ID
- **Storage**: MongoDB collections for chat sessions and messages
- **Retention**: Persistent (no automatic deletion)
- **Context**: Full conversation history passed to LLM (filtered to user messages for tool selection)

**Session Management:**
- Create new conversation sessions
- List all user sessions
- Retrieve session history with full message context
- Delete sessions when no longer needed

**Context Window:**
- LLM context: 8192 tokens (configurable)
- History filtering: Only user messages passed to tool selection
- Full history available for LLM response generation

### D) User Experience Features

**Implemented:**
- ✅ Real-time typing indicators
- ✅ Message timestamps
- ✅ Session management (create, delete, switch)
- ✅ Optimistic UI updates
- ✅ Error handling and retry

**Future Enhancements:**
- Search within conversation history
- Export conversations (PDF/JSON)
- Share conversations
- Conversation templates
- Quick actions (predefined queries)

---

## Infrastructure & Non-Functional Requirements

### A) Server Specifications

**Current Setup:**
- **CPU**: Standard server CPU
- **RAM**: 8GB+ recommended
- **GPU**: Optional (40GB available for local LLM)
- **Storage**: 100GB+ for models and documents

**LLM Options:**
1. **Local (Qwen3-14B)**
   - GPU: 40GB VRAM
   - Backend: vLLM or transformers
   - Inference: ~10 seconds per query

2. **Custom Fine-Tuned LLM (Self-Hosted)**
   - Model: Custom LLM model fine-tuned for Qatar legal documents
   - Deployment: Runs on your infrastructure (VM/server), not a cloud LLM API
   - Access: Local inference (no external API key required for LLM calls)

**Embedding Model:**
- **Model**: Arabic BERT (768 dimensions)
- **Device**: CPU (CUDA optional)
- **Memory**: ~500MB for model

### B) Remote Connectivity

**Current State:**
- ✅ Local development environment supported
- ✅ Secure tunneling support (ngrok) for remote access
- ✅ Network access configurable for deployment

**Deployment Options:**
- Local server
- Cloud server (AWS, Azure, GCP)
- Docker containerization (not yet implemented)
- Kubernetes (future)

### C) Users & Load

**Current Capacity:**
- **Users**: Single-user to small team (10-50 users)
- **Concurrency**: Not load-tested
- **Target Latency**: <10 seconds per query

**Performance Characteristics:**
- **Document Processing**: ~30 seconds per document
- **Query Response**: 2-10 seconds (depending on LLM)
- **Embedding Generation**: ~1-2 seconds per document

**Scaling Considerations:**
- MongoDB: Horizontal scaling supported
- LLM: Scale by running additional **self-hosted** inference instances (custom fine-tuned model)
- Embeddings: CPU-bound, can parallelize
- API: Stateless, can scale horizontally

### D) Availability & Support

**Current State:**
- **Availability**: Development/Testing phase
- **Monitoring**: Basic application logging
- **Alerts**: None implemented
- **SLA**: Not defined

**Monitoring:**
- Application logs for system events
- Token generation speed monitoring (tokens per second)
- Error tracking and exception logging

**Future Requirements:**
- Health check monitoring (basic implementation completed)
- Comprehensive metrics collection and visualization
- Automated alerting system for system issues
- Uptime monitoring and reporting
- Performance dashboards for system insights

---

## Security & Compliance

### A) Security Requirements

**Current Implementation:**
- **Authentication**: None (open access)
- **Authorization**: None (all documents accessible)
- **Encryption**: MongoDB connection (optional TLS)
- **LLM**: **Custom fine-tuned model** is self-hosted (no cloud LLM API keys required)

**Data Protection:**
- Any secrets (database credentials, service tokens) stored securely in environment variables / configuration (not in source code)
- Database credentials managed through environment variables
- File storage on secure local filesystem

**Missing Security Features:**
- ❌ User authentication
- ❌ Role-based access control
- ❌ API rate limiting
- ❌ Input validation/sanitization
- ❌ Database injection protection (MongoDB provides inherent protection)
- ❌ Audit logging

### B) Compliance Requirements

**Data Residency:**
- **Current**: Data stored locally (MongoDB on localhost)
- **Future**: May need cloud deployment with data residency requirements

**Audit Logs:**
- **Current**: Application logs only
- **Future**: Comprehensive audit trail needed
  - User actions
  - Document access
  - Query history
  - Data modifications

**Retention:**
- **Current**: No automatic deletion
- **Future**: Configurable retention policies
  - Document retention
  - Conversation history retention
  - Log retention

**Encryption:**
- **At Rest**: Not implemented
- **In Transit**: HTTPS (when deployed)
- **Database**: MongoDB encryption (optional)

**Vulnerability Scanning:**
- **Current**: Manual dependency updates
- **Future**: Automated scanning (Dependabot, Snyk)

---

## Implementation Roadmap

### Phase 1: Current State (✅ Completed)

**Completed Features:**
- ✅ MongoDB-based document storage
- ✅ Vector embeddings with Arabic BERT
- ✅ LangGraph query agent with 17 tools
- ✅ Chat interface (React frontend)
- ✅ Session management
- ✅ Local LLM support (Qwen3-14B)
- ✅ **Custom fine-tuned LLM model** (self-hosted) support
- ✅ Single-port deployment
- ✅ ngrok support
- ✅ Intelligent data merging
- ✅ Vague query handling

### Phase 2: Production Hardening (🔄 In Progress)

**Priority Items:**
1. **Security**
   - [ ] User authentication (JWT/OAuth)
   - [ ] Role-based access control
   - [ ] API rate limiting
   - [ ] Input validation

2. **Performance**
   - [ ] Query caching
   - [ ] Embedding caching
   - [ ] Database indexing optimization
   - [ ] Load testing

3. **Monitoring**
   - [ ] Health check endpoints
   - [ ] Metrics collection
   - [ ] Error tracking (Sentry)
   - [ ] Performance monitoring

4. **Documentation**
   - [ ] API documentation (Swagger/OpenAPI)
   - [ ] User guide
   - [ ] Admin guide
   - [ ] Deployment guide

### Phase 3: Enhanced Features (📋 Planned)

**Feature Enhancements:**
1. **Advanced Retrieval**
   - [ ] Hybrid search (BM25 + embeddings)
   - [ ] Reranking model
   - [ ] Multi-query expansion
   - [ ] Query understanding improvements

2. **User Experience**
   - [ ] Citation links to source documents
   - [ ] Document preview in chat
   - [ ] Export conversations
   - [ ] Search within conversations
   - [ ] Conversation templates

3. **Data Quality**
   - [ ] Duplicate detection alerts
   - [ ] Data quality scoring
   - [ ] Manual review interface
   - [ ] Confidence score display

4. **Integration**
   - [ ] Teams/Slack bot
   - [ ] WhatsApp integration
   - [ ] Email notifications
   - [ ] Webhook support

### Phase 4: Scaling & Optimization (🔮 Future)

**Scaling Features:**
1. **Infrastructure**
   - [ ] Docker containerization
   - [ ] Kubernetes deployment
   - [ ] Auto-scaling
   - [ ] Load balancing

2. **Performance**
   - [ ] Distributed embeddings
   - [ ] Query optimization
   - [ ] Caching layer (Redis)
   - [ ] CDN for static assets

3. **Advanced Features**
   - [ ] Multi-language support expansion
   - [ ] OCR for scanned documents
   - [ ] Table extraction
   - [ ] Image analysis
   - [ ] Audio transcription

---

## Success Metrics & Evaluation

### A) Technical Metrics

**Current Targets:**
- **Query Latency**: <10 seconds (target: <5 seconds)
- **Tool Execution**: 100% tool usage for case-related queries
- **Response Accuracy**: No hallucinated data
- **Uptime**: 99% (when deployed)

**Measurement:**
- Token generation speed: Logged per request
- Tool call success rate: Logged
- Error rate: Tracked in logs
- Response time: Tracked per request

### B) Quality Metrics

**Data Quality:**
- **Duplicate Detection**: Intelligent merging implemented
- **Entity Extraction Accuracy**: Validated against manual review
- **Case Linking Accuracy**: >95% correct assignments
- **Document Linking**: Vector similarity threshold 0.8

**Response Quality:**
- **Hallucination Prevention**: Strict tool usage enforcement
- **Citation Accuracy**: Tool results include source references
- **Completeness**: Explicit "not available" for missing data
- **Friendliness**: Conversational, warm tone

### C) Acceptance Criteria

**Golden Set (To Be Created):**
- 20-50 representative questions covering:
  - Case lookups
  - Party queries
  - Charge information
  - Incident details
  - Verdict queries
  - Vague queries (case ID needed)

**Evaluation Metrics:**
- **Precision**: Correct answers / Total answers
- **Recall**: Relevant answers found / Total relevant
- **F1 Score**: Harmonic mean of precision and recall
- **User Satisfaction**: Qualitative feedback

**Success Criteria:**
- ✅ >90% precision on golden set
- ✅ >85% recall on golden set
- ✅ Zero hallucinated case data
- ✅ All case-related queries use tools
- ✅ <10 second response time (average)

---

## Future Enhancements

### A) Advanced RAG Features

**Hybrid Search:**
- BM25 keyword search + vector embeddings
- Weighted combination for better recall
- Query expansion techniques

**Reranking:**
- Cross-encoder reranking model
- Improve precision of top results
- Context-aware reranking

**Multi-hop Reasoning:**
- Chain multiple tool calls
- Cross-document reasoning
- Temporal reasoning (timeline queries)

### B) Metadata & Labeling

**Auto-labeling:**
- Document type classification
- Jurisdiction detection
- Date extraction and normalization
- Topic tagging

**Metadata Enhancement:**
- Confidence scores for extractions
- Source document tracking
- Version control for documents
- Change tracking

### C) Graph Capabilities (Future)

**Entity Relationship Graph:**
- Party-to-party relationships
- Case-to-case relationships
- Document-to-document links
- Timeline reconstruction

**Note**: Graph RAG not currently implemented. MongoDB-based approach provides flexibility for future graph layer addition.

---

## Appendix

### A) Technology Stack

**Backend Technologies:**
- Modern Python runtime environment
- RESTful API framework for web services
- NoSQL database for flexible data storage
- AI agent framework for intelligent query processing
- Machine learning libraries for text embeddings
- Custom LLM model for entity extraction
- **Custom fine-tuned LLM model** for response generation (self-hosted)

**Frontend Technologies:**
- Modern React-based user interface
- TypeScript for type safety and reliability
- Build and development tools
- Responsive CSS framework for modern UI

**Infrastructure:**
- Production-ready web server
- Secure tunneling support for remote access

### B) Configuration

**Configuration Areas:**
- **Database**: MongoDB connection settings (host, port, database name)
- **LLM**: **Custom fine-tuned LLM model** configuration (model paths, inference runtime settings)
- **Embeddings**: Model selection, device configuration (CPU/GPU)
- **Similarity Search**: Threshold settings, maximum document limits
- **All settings**: Configurable via environment variables for flexible deployment

### C) API Endpoints

**Chat API:**
- Send messages and receive AI responses
- Manage conversation sessions (create, list, retrieve, delete)
- Health check endpoint for system monitoring
- RESTful API design for easy integration

### D) System Components

**Backend Components:**
- API layer for handling HTTP requests
- Chat orchestration service for managing conversations
- Query agent with intelligent tool selection
- Document processing engine for text extraction and entity extraction
- Database manager for MongoDB operations
- Configuration management system
- Batch processing capabilities for bulk operations
- Case linking logic for document organization

**Frontend Components:**
- React-based user interface
- Source code for development and customization
- Built/distributed files for production deployment

---

## Document Control

**Version History:**
- v1.0 (2025-01-XX): Initial comprehensive design document

**Authors:**
- System Architecture: Development Team
- Requirements: Based on consultant feedback and system analysis

**Review Status:**
- [ ] Technical Review
- [ ] Security Review
- [ ] Compliance Review
- [ ] Stakeholder Approval

---

**End of Document**

