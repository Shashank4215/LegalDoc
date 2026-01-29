# Legal Document Linking & Storage Architecture Plan

## 🎯 **Objective**
Fix the current data linking issues where **21 files from ONE case** are creating **8+ separate case records**, and establish a scalable architecture for future multi-case processing.

---

## 🚨 **Current Problems Identified**

### 1. **Data Duplication Crisis**
- Single case split into 8+ database records
- Same case numbers in different formats: `2552/2025` vs `2025/2552`
- Documents not linking due to format variations
- Orphan cases proliferating

### 2. **Brittle Rule-Based Matching**
- Hardcoded reference number patterns
- No handling of format variations
- Complex if/else logic breaking with new formats
- Cannot adapt to different jurisdictions

### 3. **Over-Engineered Database Schema**
- 15+ tables for different document types
- Constant schema updates needed
- Conflicting data across documents
- Performance issues with complex joins

---

## ✅ **Proposed Solution: Hybrid Vector + Minimal DB Architecture**

### **Core Principle**: 
Store **key extracted data** in database + use **vector embeddings** for document linking + keep **raw documents** for detailed queries.

---

## 🏗️ **Architecture Overview**

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Raw Documents │───▶│  Vector Engine  │───▶│  Minimal DB     │
│   (21 files)    │    │  (Linking)      │    │  (Key Data)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
        │                        │                        │
        │                        │                        │
        ▼                        ▼                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Document Store  │    │ Embeddings DB   │    │ Query Interface │
│ (File System)   │    │ (Similarity)    │    │ (API/UI)        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

---

## 📊 **Database Schema: Minimal & Flexible**

### **Core Tables (Only 3 needed!)**

```sql
-- 1. Cases: High-level case information
CREATE TABLE cases (
    case_id SERIAL PRIMARY KEY,
    case_numbers JSONB,              -- All number variations: {"court": "2552/2025", "police": "2590/2025"}
    parties JSONB,                   -- Key people: [{"name": "محمد", "id": "29052", "role": "victim"}]
    key_dates JSONB,                 -- Important dates: {"incident": "2025-05-14", "judgment": "2025-07-28"}
    case_status TEXT,                -- Current status: "closed", "open", "in_trial"
    case_type TEXT,                  -- "criminal", "civil", "family"
    jurisdiction TEXT,               -- "qatar", "uae", etc.
    case_summary TEXT,               -- AI-generated summary
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 2. Documents: File references with embeddings
CREATE TABLE documents (
    document_id SERIAL PRIMARY KEY,
    case_id INTEGER REFERENCES cases(case_id),
    file_path TEXT NOT NULL,         -- Path to actual document
    file_hash TEXT,                  -- For deduplication
    document_type TEXT,              -- "police_report", "judgment", "investigation"
    document_date DATE,              -- When document was created
    extracted_entities JSONB,       -- Key entities found: {"people": [...], "dates": [...]}
    document_embedding vector(768),  -- For similarity search (pgvector extension)
    confidence_score FLOAT,          -- How confident we are in case linking
    created_at TIMESTAMP DEFAULT NOW()
);

-- 3. Processing Log: Track what's been processed
CREATE TABLE processing_log (
    log_id SERIAL PRIMARY KEY,
    file_path TEXT,
    case_id INTEGER,
    processing_status TEXT,          -- "success", "failed", "duplicate"
    error_message TEXT,
    processing_time TIMESTAMP DEFAULT NOW()
);
```

### **JSONB Examples:**

```json
-- cases.case_numbers
{
  "court": "2552/2025/جنح متنوعة/ابتدائي",
  "prosecution": "303/2025/نيابة الشمال", 
  "police": "2590/2025/مركز ام صلال",
  "internal": "4308/2025",
  "variations": ["2552/2025", "2025/2552", "303/2025", "2590/2025"]
}

-- cases.parties
[
  {
    "name": "محمد",
    "name_en": "Mohammed", 
    "personal_id": "29052",
    "nationality": "نيبال",
    "role": "complainant",
    "source_documents": ["police_report.txt", "investigation.txt"]
  },
  {
    "name": "اشوك",
    "name_en": "Ashok",
    "personal_id": "29952", 
    "nationality": "نيبال",
    "role": "accused",
    "age": 26,
    "source_documents": ["investigation.txt", "judgment.txt"]
  }
]

-- cases.key_dates
{
  "incident": "2025-05-14",
  "report_filed": "2025-05-15", 
  "investigation": "2025-05-18",
  "case_transfer": "2025-06-02",
  "first_hearing": "2025-07-01",
  "judgment": "2025-07-28"
}
```

---

## 🔄 **Document Processing Pipeline**

### **Phase 1: Document Ingestion & Embedding**

```python
def process_document(file_path: str) -> ProcessingResult:
    """Process a single document through the pipeline"""
    
    # 1. Read and extract text
    document_text = extract_text(file_path)
    
    # 2. Generate embedding for similarity matching
    doc_embedding = generate_embedding(document_text)
    
    # 3. Extract key entities (using AI/NLP)
    entities = extract_entities(document_text)
    
    # 4. Find similar documents/cases
    similar_cases = find_similar_cases(doc_embedding, similarity_threshold=0.8)
    
    return ProcessingResult(
        text=document_text,
        embedding=doc_embedding,
        entities=entities,
        similar_cases=similar_cases
    )
```

### **Phase 2: Case Linking via Vector Similarity**

```python
def link_document_to_case(doc_result: ProcessingResult) -> int:
    """Link document to existing case or create new one"""
    
    if doc_result.similar_cases:
        # Found similar case(s)
        case_id = resolve_case_conflicts(doc_result.similar_cases)
        merge_entities_into_case(case_id, doc_result.entities)
        return case_id
    else:
        # Create new case
        case_id = create_new_case(doc_result.entities)
        return case_id
```

### **Phase 3: Entity Extraction & Merging**

```python
def extract_entities(text: str) -> Dict[str, Any]:
    """Extract key entities using AI"""
    
    # Use Claude/GPT to extract structured data
    prompt = f"""
    Extract key entities from this legal document:
    {text}
    
    Return JSON with:
    - case_numbers: List of all case/report numbers found
    - parties: List of people with names, IDs, roles
    - dates: Key dates in YYYY-MM-DD format
    - locations: Court names, police stations
    - charges: Legal charges mentioned
    - amounts: Fines, penalties
    """
    
    return ai_extract_entities(prompt)
```

---

## 🚀 **Implementation Phases**

### **Phase 1: Fix Current 21 Files (Week 1-2)**

#### **Step 1.1: Setup Vector Environment**
```bash
# Install dependencies
pip install sentence-transformers pgvector-python psycopg2

# Setup PostgreSQL with pgvector
CREATE EXTENSION IF NOT EXISTS vector;
```

#### **Step 1.2: Process 21 Files**
```python
# Process all 21 files
all_files = glob("project_documents/*.txt")
processing_results = []

for file_path in all_files:
    result = process_document(file_path)
    processing_results.append(result)

# Cluster similar documents
similarity_matrix = compute_similarity_matrix(processing_results)
case_groups = cluster_documents(similarity_matrix, threshold=0.8)

# Should result in 1 case group with 21 documents
assert len(case_groups) == 1
assert len(case_groups[0]) == 21
```

#### **Step 1.3: Create Unified Case Record**
```python
# Extract merged entities from all 21 documents
unified_entities = merge_all_entities(case_groups[0])

# Create single case record
case_id = create_case_record(
    case_numbers=unified_entities['case_numbers'],
    parties=unified_entities['parties'], 
    key_dates=unified_entities['dates'],
    case_summary=generate_case_summary(unified_entities)
)

# Link all 21 documents to this case
for doc_result in case_groups[0]:
    link_document_to_case(case_id, doc_result)
```

### **Phase 2: Clean Existing Database (Week 2)**

#### **Step 2.1: Migrate Existing Data**
```python
# Export existing case data
existing_cases = export_current_database()

# Identify and merge duplicates
duplicate_groups = identify_duplicates(existing_cases)

# Merge duplicate records
for group in duplicate_groups:
    primary_case = choose_primary_case(group)
    merge_duplicate_cases(primary_case, group)
```

#### **Step 2.2: Data Migration Script**
```python
def migrate_to_new_schema():
    """Migrate from complex schema to minimal schema"""
    
    # 1. Export all existing cases
    old_cases = db.query("SELECT * FROM cases")
    
    # 2. Group by similarity 
    case_groups = group_similar_cases(old_cases)
    
    # 3. Create new case records
    for group in case_groups:
        merged_case = merge_case_group(group)
        new_case_id = create_minimal_case_record(merged_case)
        
        # Update document references
        update_document_case_links(group, new_case_id)
```

### **Phase 3: Production System (Week 3-4)**

#### **Step 3.1: Build Processing Pipeline**
```python
class DocumentProcessor:
    def __init__(self, db_config, embedding_model):
        self.db = DatabaseManager(db_config)
        self.embeddings = EmbeddingModel(embedding_model)
        
    def process_new_document(self, file_path: str):
        # Full pipeline for new documents
        pass
        
    def batch_process(self, file_paths: List[str]):
        # Efficient batch processing
        pass
```

#### **Step 3.2: Query Interface**
```python
class CaseQueryInterface:
    def find_case_by_reference(self, reference: str):
        # Vector search for case references
        pass
        
    def get_case_summary(self, case_id: int):
        # Get structured case data
        pass
        
    def search_documents(self, query: str, case_id: int = None):
        # Semantic search across documents
        pass
```

### **Phase 4: Scaling & Monitoring (Week 4+)**

#### **Step 4.1: Performance Optimization**
- Index embeddings for fast similarity search
- Batch processing for multiple documents
- Caching for frequent queries

#### **Step 4.2: Quality Monitoring**
- Duplicate detection alerts
- Confidence score tracking
- Manual review interface for low-confidence links

---

## 📈 **Expected Outcomes**

### **Immediate (After Phase 1)**
- ✅ 21 files → 1 unified case record
- ✅ All case numbers properly linked
- ✅ No more orphan cases
- ✅ Clean, queryable data structure

### **Medium-term (After Phase 2-3)**
- ✅ Existing database cleaned and consolidated
- ✅ Production-ready processing pipeline
- ✅ Scalable architecture for multiple cases
- ✅ Fast semantic search capabilities

### **Long-term (Phase 4+)**
- ✅ Multi-jurisdiction support
- ✅ Real-time duplicate detection
- ✅ AI-powered case insights
- ✅ Robust monitoring and alerts

---

## 🛠️ **Technology Stack**

### **Core Components**
- **Database**: PostgreSQL with pgvector extension
- **Embeddings**: sentence-transformers (multilingual BERT)
- **AI Extraction**: Claude/GPT API
- **Language**: Python
- **Storage**: Local filesystem + database

### **Libraries**
```bash
pip install:
- sentence-transformers        # For embeddings
- pgvector-python             # PostgreSQL vector support
- psycopg2-binary             # Database connectivity
- anthropic                   # Claude API
- scikit-learn                # Clustering/similarity
- pandas numpy                # Data manipulation
```

---

## 🎯 **Success Metrics**

### **Technical Metrics**
- **Document linking accuracy**: >95% correct case assignments
- **Duplicate detection**: <1% false positives/negatives  
- **Processing speed**: <30 seconds per document
- **Storage efficiency**: <50% of current database size

### **Business Metrics**
- **Case completeness**: All 21 files linked to 1 case
- **Query performance**: Case lookups <1 second
- **Data consistency**: Zero conflicting case records
- **Scalability**: Handle 1000+ cases without architecture changes

---

## 🚨 **Risk Mitigation**

### **Data Loss Prevention**
- Keep all original files untouched
- Version control for schema changes
- Backup before any migration
- Rollback procedures documented

### **Quality Assurance**
- Manual review for low-confidence links
- Duplicate detection alerts
- Regular data quality audits
- User feedback integration

### **Performance Safeguards**
- Incremental processing (not all-at-once)
- Resource monitoring during migration
- Fallback to rule-based matching if needed
- Graceful degradation for high load

---

## 📅 **Timeline Summary**

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| **Phase 1** | 1-2 weeks | 21 files correctly linked to 1 case |
| **Phase 2** | 1 week | Existing database cleaned |
| **Phase 3** | 2 weeks | Production pipeline ready |
| **Phase 4** | Ongoing | Scaling and optimization |

**Total Implementation Time: ~1 month**

---

## 🎉 **Final Architecture Benefits**

1. **Simplicity**: 3 tables instead of 15+
2. **Flexibility**: JSONB allows schema evolution
3. **Performance**: Vector search scales to millions
4. **Accuracy**: AI-powered entity extraction
5. **Maintainability**: No hardcoded patterns
6. **Scalability**: Works for 1 case or 1 million cases
7. **Future-proof**: Adapts to new document types automatically

This architecture solves your immediate 21-file linking problem while building a foundation that scales to handle thousands of cases across multiple jurisdictions.
