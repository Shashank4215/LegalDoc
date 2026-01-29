# LLM and Embeddings for Document Parsing

## Overview

This document explains how Large Language Models (LLMs) and vector embeddings are used in the Qatar Legal Case Management System to parse, classify, and process Arabic legal documents.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [LLM-Based Document Processing](#llm-based-document-processing)
3. [Embedding Generation](#embedding-generation)
4. [Document Processing Pipeline](#document-processing-pipeline)
5. [Technical Details](#technical-details)
6. [Configuration](#configuration)

---

## Architecture Overview

The system uses a **hybrid approach** combining:
- **LLM (Claude Sonnet)** for intelligent entity extraction and document classification
- **Arabic BERT embeddings** for semantic similarity and document linking
- **Type-specific schemas** for structured data extraction

```
┌─────────────────┐
│  Document File  │
│  (.txt, .pdf,   │
│   .docx, .doc)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Text Extraction │
│  (pdfplumber,   │
│   python-docx)  │
└────────┬────────┘
         │
         ├─────────────────┐
         │                 │
         ▼                 ▼
┌─────────────────┐  ┌─────────────────┐
│  LLM Classifier │  │  LLM Entity     │
│  (Claude)       │  │  Extraction     │
│                 │  │  (Claude)       │
└────────┬────────┘  └────────┬────────┘
         │                   │
         ▼                   ▼
┌─────────────────┐  ┌─────────────────┐
│ Document Type   │  │ Structured      │
│ Classification  │  │ Entities (JSON) │
└─────────────────┘  └────────┬────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  BERT Embedding │
                    │  Generation     │
                    │  (Arabic BERT)  │
                    └────────┬────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  MongoDB Storage │
                    │  (text, entities,│
                    │   embedding)     │
                    └─────────────────┘
```

---

## LLM-Based Document Processing

### 1. Document Type Classification

**Purpose**: Automatically identify the type of legal document (e.g., police complaint, court judgment, lab test results).

**Model**: Claude Sonnet (via Anthropic API)

**Process**:
1. Document text is extracted from the file
2. First 10,000 characters are sent to Claude with a classification prompt
3. LLM analyzes the content and returns:
   - Document type identifier (e.g., `police_complaint`, `court_judgment`)
   - Confidence score (0.0-1.0)

**Prompt Structure**:
```
System: You are an expert at classifying Arabic legal documents for Qatar's judicial system.
        Choose from: police_complaint, court_judgment, lab_test_results, etc.
        Return: TYPE|CONFIDENCE

User: Classify this Arabic legal document: [document text]
```

**Fallback**: If LLM classification fails, the system uses pattern matching on Arabic keywords (e.g., "افادة طرف" for police complaints, "حكم" for judgments).

**Code Location**: `document_type_classifier.py`

### 2. Entity Extraction

**Purpose**: Extract structured information (parties, charges, dates, locations, etc.) from unstructured document text.

**Model**: Claude Sonnet (via Anthropic API)

**Process**:
1. Document type is determined (from classification step)
2. Type-specific schema is loaded (required and optional fields)
3. Document text (up to 50,000 characters) is sent to Claude with a structured extraction prompt
4. LLM returns JSON with extracted entities

**Type-Specific Extraction**:
Each document type has a schema defining:
- **Required fields**: Must be extracted (e.g., parties, case_numbers for police_complaint)
- **Optional fields**: Extracted if present (e.g., hospital, injuries, weapons)

**Example Schema** (`police_complaint`):
```python
{
    'required_fields': ['parties', 'incident_date', 'charges', 'locations', 'case_numbers'],
    'optional_fields': [
        'injuries', 'hospital', 'hospital_name', 'weapon', 'evidence',
        'witnesses', 'statements', 'police_station', ...
    ]
}
```

**Prompt Structure**:
```
System: You are an expert at extracting structured information from Arabic legal documents.
        DOCUMENT TYPE: [type_name]
        REQUIRED FIELDS: [list]
        OPTIONAL FIELDS: [list]
        
        CRITICAL: PRIORITIZE ARABIC DATA
        - Always extract Arabic names (name_ar) - primary source
        - Only use English (name_en) if Arabic not available
        - Extract ALL fields listed if they appear in text
        - Return ONLY valid JSON

User: Extract all entities from this legal document: [document text]
```

**Output Format**:
```json
{
    "case_numbers": {
        "court": "...",
        "prosecution": "...",
        "police": "..."
    },
    "parties": [
        {
            "name_ar": "أحمد محمد",
            "name_en": "Ahmed Mohammed",
            "personal_id": "123456789",
            "role": "accused"
        }
    ],
    "charges": [
        {
            "description_ar": "ضرب",
            "article_number": "123"
        }
    ],
    "dates": {
        "incident": "2024-01-15",
        "report_filed": "2024-01-16"
    },
    "locations": {
        "incident_location": "...",
        "police_station": "..."
    },
    ...
}
```

**Key Features**:
- **Arabic-first extraction**: Prioritizes Arabic text, falls back to English only if Arabic unavailable
- **Type-aware**: Uses document-specific schemas for relevant fields only
- **Validation**: Limits entities to prevent excessive extraction (e.g., max 100 parties per document)
- **Error handling**: Falls back to generic extraction if type-specific fails

**Code Location**: `document_processor.py` (methods: `extract_entities()`, `_extract_entities_type_specific()`)

---

## Embedding Generation

### Purpose

Vector embeddings enable:
- **Semantic similarity search**: Find documents with similar content
- **Document linking**: Automatically link related documents to cases
- **RAG (Retrieval-Augmented Generation)**: Retrieve relevant documents for query answering

### Model: Arabic BERT

**Model**: `aubmindlab/bert-base-arabert` (Arabic BERT model)

**Why Arabic BERT?**
- Pre-trained on Arabic text
- Handles Arabic morphology and context
- 768-dimensional embeddings
- Optimized for Arabic legal documents

### Process

1. **Text Tokenization**:
   ```python
   inputs = tokenizer(
       text,
       return_tensors='pt',
       truncation=True,
       max_length=512,  # BERT's max sequence length
       padding='max_length'
   )
   ```

2. **Embedding Generation**:
   ```python
   with torch.no_grad():
       outputs = bert_model(**inputs)
       # Get hidden states: (batch_size, seq_len, hidden_size)
       embeddings = outputs.last_hidden_state
       # Mean pooling: average over sequence length
       embedding = embeddings.mean(dim=1).squeeze()
   ```

3. **Dimension Adjustment**:
   - Model dimension: 768 (BERT-base)
   - Storage dimension: Configurable (default: 768)
   - If different, truncate or pad as needed

4. **Storage**:
   - Embeddings stored as arrays in MongoDB
   - Used for cosine similarity calculations

### Technical Details

**Mean Pooling Strategy**:
- Takes average of all token embeddings (not just CLS token)
- Better captures full document semantics
- More robust for longer documents

**Device Support**:
- CUDA (GPU) if available
- CPU fallback
- Automatic device selection

**Code Location**: `document_processor.py` (method: `generate_embedding()`)

---

## Document Processing Pipeline

### Complete Flow

```
1. Document Upload
   │
   ├─> Extract Text (pdfplumber, python-docx)
   │
   ├─> Classify Document Type (LLM)
   │   └─> Returns: document_type, confidence
   │
   ├─> Extract Entities (LLM)
   │   ├─> Load type-specific schema
   │   ├─> Build extraction prompt
   │   ├─> Call Claude API
   │   ├─> Parse JSON response
   │   └─> Validate & limit entities
   │
   ├─> Generate Embedding (Arabic BERT)
   │   ├─> Tokenize text
   │   ├─> Generate embeddings
   │   ├─> Mean pooling
   │   └─> Adjust dimensions
   │
   └─> Store in MongoDB
       ├─> text: Full document text
       ├─> extracted_entities: Structured JSON
       ├─> embedding: Vector array
       ├─> document_type: Classified type
       └─> file_hash, file_size, metadata
```

### Code Example

```python
from document_processor import DocumentProcessor

processor = DocumentProcessor()

# Process a document
result = processor.process_document(
    file_path="path/to/document.pdf",
    document_type=None  # Auto-detect if None
)

# Result contains:
# {
#     'text': '...',
#     'embedding': [0.123, -0.456, ...],  # 768-dim vector
#     'entities': {
#         'parties': [...],
#         'charges': [...],
#         ...
#     },
#     'document_type': 'police_complaint',
#     'file_hash': '...',
#     'file_size': 12345,
#     'processing_time_ms': 2345
# }
```

---

## Technical Details

### LLM Configuration

**Model**: Claude Sonnet 4 (via Anthropic API)
- **API**: Anthropic Messages API
- **Max Tokens**: 4096 (for entity extraction), 100 (for classification)
- **Temperature**: Default (not specified, uses model default)
- **System Prompts**: Detailed instructions for Arabic-first extraction

**Rate Limiting**:
- Handled by Anthropic API
- No explicit rate limiting in code (relies on API)

**Error Handling**:
- JSON parsing errors: Logged, returns empty entities
- API errors: Logged, falls back to pattern matching (classification) or generic extraction (entities)

### Embedding Configuration

**Model**: `aubmindlab/bert-base-arabert`
- **Framework**: HuggingFace Transformers
- **Dimension**: 768 (model) / configurable (storage)
- **Max Length**: 512 tokens (BERT limit)
- **Pooling**: Mean pooling over all tokens
- **Device**: CUDA if available, else CPU

**Performance**:
- GPU: ~50-100ms per document
- CPU: ~200-500ms per document
- Depends on document length and hardware

### Entity Validation

**Limits Applied** (to prevent excessive extraction):
```python
{
    'max_parties_per_document': 100,
    'max_charges_per_document': 50,
    'max_evidence_per_document': 100,
    'max_judgments_per_document': 20,
    'max_court_sessions_per_document': 50,
    'max_statements_per_document': 100,
    ...
}
```

**Validation Process**:
1. LLM extracts entities
2. System checks counts against limits
3. If exceeded, truncates to limit and logs warning
4. Prevents database bloat and processing errors

---

## Configuration

### Environment Variables

```bash
# Anthropic (LLM)
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514

# Embeddings
EMBEDDING_MODEL=aubmindlab/bert-base-arabert
EMBEDDING_DIMENSION=768
EMBEDDING_DEVICE=cuda  # or 'cpu'
```

### Config File Structure

```python
CONFIG = {
    'anthropic': {
        'api_key': os.getenv('ANTHROPIC_API_KEY'),
        'model': os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')
    },
    'embeddings': {
        'model': os.getenv('EMBEDDING_MODEL', 'aubmindlab/bert-base-arabert'),
        'dimension': int(os.getenv('EMBEDDING_DIMENSION', '768')),
        'device': os.getenv('EMBEDDING_DEVICE', 'cpu')
    },
    'processing': {
        'entity_limits': {
            'max_parties_per_document': 100,
            'max_charges_per_document': 50,
            ...
        }
    }
}
```

---

## Use Cases

### 1. Document Ingestion
- Upload document → Extract text → Classify → Extract entities → Generate embedding → Store

### 2. Document Linking
- Compare embeddings (cosine similarity) to link documents to cases
- Use extracted entities (case numbers, parties) for exact matching

### 3. Query Answering
- Use embeddings for semantic search to find relevant documents
- Use extracted entities for structured queries (e.g., "find all cases with party X")

### 4. Case Matching
- Combine entity matching (exact) with embedding similarity (fuzzy)
- Weighted scoring: entity matches (0.6) + vector similarity (0.4)

---

## Best Practices

### 1. Arabic-First Extraction
- Always prioritize Arabic text in extraction
- Use English only as fallback
- Ensures accuracy for Qatar legal system

### 2. Type-Specific Schemas
- Use document type classification to apply correct schema
- Reduces noise and improves extraction accuracy
- Only extract relevant fields per document type

### 3. Validation and Limits
- Always validate entity counts
- Prevent excessive extraction that could slow down system
- Log warnings for unusual extractions

### 4. Error Handling
- Always have fallbacks (pattern matching, generic extraction)
- Log errors for debugging
- Don't fail silently

### 5. Performance Optimization
- Use GPU for embeddings when available
- Limit text length sent to LLM (50k chars for extraction, 10k for classification)
- Cache embeddings if processing same document multiple times

---

## Future Improvements

1. **Batch Processing**: Process multiple documents in parallel
2. **Embedding Caching**: Cache embeddings for duplicate documents
3. **Fine-tuning**: Fine-tune Arabic BERT on legal documents
4. **Hybrid Search**: Combine keyword search with semantic search
5. **Incremental Updates**: Update embeddings when documents are modified
6. **Multi-language Support**: Support English documents alongside Arabic

---

## Troubleshooting

### LLM Extraction Returns Empty Entities
- Check API key is valid
- Verify document text is not empty
- Check if document type classification succeeded
- Review logs for JSON parsing errors

### Embeddings Are Slow
- Use GPU if available (set `EMBEDDING_DEVICE=cuda`)
- Reduce max_length if documents are very long
- Consider batch processing

### Classification Fails
- System falls back to pattern matching automatically
- Check if document contains recognizable Arabic keywords
- Review classification logs for LLM errors

---

## References

- **Arabic BERT**: [aubmindlab/bert-base-arabert](https://huggingface.co/aubmindlab/bert-base-arabert)
- **Anthropic Claude**: [Anthropic API Documentation](https://docs.anthropic.com/)
- **HuggingFace Transformers**: [Transformers Documentation](https://huggingface.co/docs/transformers)

---

*Last Updated: January 2025*

