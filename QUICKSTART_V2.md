# Quick Start Guide - Vector-Based Legal Case Management System v2

## Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Setup Database
```bash
# Option 1: Using the setup script
./setup_database_v2.sh

# Option 2: Using pgAdmin4
# 1. Open pgAdmin4
# 2. Create database: legal_case_v2
# 3. Run schema_minimal.sql in Query Tool
# Note: No pgvector extension needed - uses FAISS for similarity search
```

### 3. Configure Environment
Update `config.py` or set environment variables:
- `DB_NAME=legal_case_v2`
- `ANTHROPIC_API_KEY=your_key`
- `GROQ_API_KEY=your_key` (for query agent)

## Usage

### Process Documents
```bash
# Process all documents in storage/ directory
python batch_processor.py

# Process specific directory
python batch_processor.py /path/to/documents
```

### Query Cases
```bash
# Interactive query interface
python query_agent_v2.py

# Or use in Python
from query_agent_v2 import query
result = query("Find case 2552/2025")
```

### Test System
```bash
# Run full validation
python test_v2_system.py

# Test with specific directory
python test_v2_system.py /path/to/documents
```

### Migrate Old Data
```bash
# Dry run (preview)
python migrate_to_v2.py

# Actual migration
python migrate_to_v2.py --execute
```

## Architecture

- **3 Tables**: cases (JSONB), documents (with embeddings as JSONB), processing_log
- **FAISS Similarity Search**: Fast in-memory vector similarity (no database extension needed)
- **Vector Embeddings**: Stored as JSONB arrays, searched using FAISS
- **JSONB Storage**: Flexible, queryable data structure
- **Entity Linking**: Parties, charges, evidence remain connected across documents

## Key Features

- ✅ Automatic document clustering by similarity
- ✅ Comprehensive entity extraction (parties, charges, dates, etc.)
- ✅ Entity relationship preservation (P001 → C001 → E001)
- ✅ Vector-based semantic search
- ✅ Natural language querying

