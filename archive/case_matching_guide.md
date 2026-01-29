# Quick Start: Intelligent Case Matching System

## 🎯 Problem Solved

**Your Issue**: Documents arrive in different orders, and early documents (like police reports) don't have court case numbers yet!

```
❌ Before (fails):
Police Report → No court_case_number → DATABASE ERROR!

✅ After (works):
Police Report → Uses police_report_number → Creates Case #1
Investigation → Uses police_report_number → Links to Case #1, adds prosecution_number
Court Session → Uses prosecution_number → Links to Case #1, adds court_case_number
Judgment → Uses court_case_number → Links to Case #1, completes case!
```

---

## 🔧 Setup (3 Steps)

### Step 1: Run Database Migration

```bash
psql -U legal_user -d legal_case -f migration_nullable_references.sql
```

This makes `court_case_number` nullable and adds intelligent matching capabilities.

### Step 2: Update Your Code

**Before (fails with police reports):**
```python
from ai_document_parser import AIDocumentProcessor

processor = AIDocumentProcessor(api_key, db_config, storage_path)
result = processor.process_document('police_report.txt')
# ❌ ERROR: null value in column "court_case_number"
```

**After (works with any document type!):**
```python
from improved_ai_processor import ImprovedAIDocumentProcessor
from database_manager import DatabaseManager

with DatabaseManager(**db_config) as db:
    processor = ImprovedAIDocumentProcessor(api_key, db, storage_path)
    result = processor.process_document('police_report.txt')
    # ✅ SUCCESS: Case created with police_report_number
```

### Step 3: Process Your Documents (Any Order!)

```python
# Process all documents (they can be in any order!)
documents = [
    'police_report.txt',           # Has police_report_number only
    'investigation.txt',           # Has police_report + prosecution_number
    'court_session_1.txt',         # Has prosecution + court_case_number
    'court_session_2.txt',         # Has court_case_number
    'judgment.txt',                # Has court_case_number
]

for doc in documents:
    result = processor.process_document(f'documents/{doc}')
    
    print(f"✅ {doc}")
    print(f"   Case ID: {result['case_id']}")
    print(f"   Action: {result['case_action']}")  # 'created' or 'found'
    print(f"   Completeness: {result['completeness']['estimated_stage']}")
    print()
```

---

## 📊 How It Works

### The Magic: Smart Reference Matching

```python
# Document 1: Police Report
References: police_report_number = "2590/2025"
Result: ✅ Creates Case #1

# Document 2: Investigation  
References: police_report_number = "2590/2025", prosecution_case_number = "303/2025"
System finds: Case #1 (matches police_report_number!)
Result: ✅ Links to Case #1, adds prosecution_case_number

# Document 3: Court Session
References: prosecution_case_number = "303/2025", court_case_number = "2552/2025"
System finds: Case #1 (matches prosecution_case_number!)
Result: ✅ Links to Case #1, adds court_case_number

# Now Case #1 has ALL THREE numbers! 🎉
```

### Visual Timeline

```
Time →

Police Report arrives:
  Case #1 created
  References: {police: "2590/2025"}
  
Investigation arrives:
  Case #1 found (by police number)
  References: {police: "2590/2025", prosecution: "303/2025"}
  
Court Session arrives:
  Case #1 found (by prosecution number)
  References: {police: "2590/2025", prosecution: "303/2025", court: "2552/2025"}
  
Judgment arrives:
  Case #1 found (by court number)
  Status: CLOSED ✅
```

---

## 🔍 Monitoring & Debugging

### Check Case Completeness

```python
from case_matcher import SmartCaseProcessor

processor = SmartCaseProcessor(db)
completeness = processor.get_case_completeness(case_id=1)

print(completeness)
# Output:
{
    'case_id': 1,
    'references_complete': True,  # All 3 numbers present
    'has_police_report': True,
    'has_investigation': True,
    'has_judgment': True,
    'document_types': ['police_report', 'investigation', 'court_session', 'judgment'],
    'total_documents': 15,
    'estimated_stage': 'concluded'
}
```

### Find Incomplete Cases

```sql
-- Find cases missing reference numbers
SELECT * FROM v_incomplete_cases;

-- Output:
-- case_id | court_case_number | prosecution_case_number | police_report_number | missing_reference
-- 1       | 2552/2025        | 303/2025                | 2590/2025            | Complete
-- 2       | NULL             | 304/2025                | 2591/2025            | Missing court case number
-- 3       | NULL             | NULL                    | 2592/2025            | Missing prosecution number
```

### Check Merge History

```sql
-- See when each reference was added
SELECT * FROM case_merge_history WHERE case_id = 1 ORDER BY added_at;

-- Output:
-- case_id | reference_type            | reference_value | added_at
-- 1       | police_report_number      | 2590/2025       | 2025-05-15 02:00:00
-- 1       | prosecution_case_number   | 303/2025        | 2025-05-18 08:30:00
-- 1       | court_case_number         | 2552/2025       | 2025-07-01 09:00:00
```

### Find Duplicate Cases (if any)

```sql
SELECT * FROM v_potential_duplicates;

-- If you see duplicates, you can manually merge them
```

---

## 🎓 Best Practices

### 1. Process in Natural Order (Recommended but not required)

```python
# Ideal order (but system handles any order!)
ordered_docs = [
    'police_report.txt',      # Day 1
    'statements.txt',         # Day 2
    'investigation.txt',      # Day 3
    'case_transfer.txt',      # Day 15
    'court_session_1.txt',    # Day 30
    'judgment.txt',           # Day 90
]
```

### 2. Handle Errors Gracefully

```python
result = processor.process_document(doc_path)

if not result['success']:
    print(f"❌ Error: {result['error']}")
    # Log for manual review
    
elif not result['sequence_valid']:
    print(f"⚠️ Warning: Document out of sequence")
    # Flag for review but still processed
    
else:
    print(f"✅ Success: Case {result['case_id']}")
```

### 3. Monitor Completeness

```python
# After processing all documents
completeness = processor.get_case_completeness(case_id)

if not completeness['references_complete']:
    print("⚠️ Case missing some reference numbers")
    
if completeness['estimated_stage'] != 'concluded':
    print(f"📋 Case still at stage: {completeness['estimated_stage']}")
```

---

## 🐛 Troubleshooting

### Problem: "Still getting NULL error"

**Solution**: Make sure you ran the migration!

```bash
psql -U legal_user -d legal_case -f migration_nullable_references.sql
```

### Problem: "Documents not linking to same case"

**Solution**: Check that reference numbers match exactly

```python
# Debug: Print extracted references
result = extractor.classify_and_extract(document_text)
refs = processor._extract_references(result['extracted_data'])
print(refs.get_available_references())

# Make sure numbers match across documents!
```

### Problem: "Case created multiple times"

**Solution**: Check for typos in reference numbers

```sql
-- Find cases with similar numbers
SELECT court_case_number, COUNT(*) 
FROM cases 
GROUP BY court_case_number 
HAVING COUNT(*) > 1;
```

---

## 📈 Performance Tips

### 1. Index Usage

The migration creates these indexes automatically:
- `idx_case_references` - Fast lookup by any reference
- `idx_unique_court_case_number` - Prevents duplicates
- `idx_case_reference_completeness` - Quick completeness checks

### 2. Batch Processing

```python
# Process multiple documents efficiently
results = []
for doc in documents:
    result = processor.process_document(doc)
    results.append(result)
    
    # Log progress
    if result['case_action'] == 'created':
        print(f"📝 New case: {result['case_id']}")
    else:
        print(f"🔗 Linked to case: {result['case_id']}")
```

### 3. Caching

```python
# Cache case lookups for repeated queries
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_case_by_number(case_number):
    # Your lookup logic
    pass
```

---

## ✅ Verification

### Test the System

```python
def test_case_matching():
    """Verify case matching works correctly"""
    
    # Test 1: Police report creates case
    result1 = processor.process_document('police_report.txt')
    assert result1['success']
    assert result1['case_action'] == 'created'
    case_id = result1['case_id']
    
    # Test 2: Investigation links to same case
    result2 = processor.process_document('investigation.txt')
    assert result2['success']
    assert result2['case_action'] == 'found'
    assert result2['case_id'] == case_id  # Same case!
    
    # Test 3: Court session links to same case
    result3 = processor.process_document('court_session.txt')
    assert result3['success']
    assert result3['case_action'] == 'found'
    assert result3['case_id'] == case_id  # Still same case!
    
    print("✅ All tests passed!")

test_case_matching()
```

---

## 📞 Summary

✅ **Migration**: Makes reference numbers nullable  
✅ **CaseMatcher**: Finds cases by ANY reference  
✅ **ImprovedAIProcessor**: Uses smart matching  
✅ **Works with any document order**  
✅ **Automatically merges reference numbers**  
✅ **Tracks completeness and timeline**  

**You're all set!** 🎉

Process documents in any order, and the system will intelligently link them to the correct case!
