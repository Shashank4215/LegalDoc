# Legal Case Management System - Setup & Usage Guide

## 📋 Overview

This system provides a comprehensive solution for parsing, storing, and querying Arabic legal documents from Qatar's judicial system. It includes:

1. **Database Schema** - Normalized relational database design
2. **Document Parser** - Automated extraction of structured data from Arabic documents
3. **AI Query Agent** - Natural language to SQL query conversion
4. **API Ready** - Backend ready for REST API development

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      User Interface                          │
│              (Web App / Mobile App / CLI)                    │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                       API Layer                              │
│              (FastAPI / Flask / Django)                      │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│               Document Processing Pipeline                   │
│  ┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐        │
│  │Classify│ → │Extract │ → │  Link  │ → │ Store  │        │
│  └────────┘   └────────┘   └────────┘   └────────┘        │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                  Database Layer                              │
│          MySQL 8.0+ with InnoDB Engine                       │
│     (Cases, Parties, Documents, Charges, etc.)               │
└─────────────────────────────────────────────────────────────┘
```

## 📦 Prerequisites

### System Requirements
- Python 3.9+
- MySQL 8.0+ or MariaDB 10.5+
- 4GB+ RAM (8GB recommended)
- 50GB+ storage for documents

### Python Packages
```bash
pip install --break-system-packages \
    pymysql \
    python-docx \
    pdfplumber \
    python-dateutil \
    arabic-reshaper \
    python-bidi \
    regex \
    jellyfish \
    camel-tools \
    fastapi \
    uvicorn
```

## 🚀 Quick Start

### Step 1: Database Setup

```bash
# 1. Create database
mysql -u root -p
```

```sql
CREATE DATABASE legal_cases CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER 'legal_user'@'localhost' IDENTIFIED BY 'strong_password_here';

GRANT ALL PRIVILEGES ON legal_cases.* TO 'legal_user'@'localhost';

FLUSH PRIVILEGES;
```

```bash
# 2. Run schema creation
mysql -u legal_user -p legal_cases < create_schema.sql
```

### Step 2: Configure Application

Create `config.py`:

```python
# config.py
DATABASE_CONFIG = {
    'host': 'localhost',
    'user': 'legal_user',
    'password': 'your_password',
    'database': 'legal_cases',
    'charset': 'utf8mb4'
}

STORAGE_PATH = '/var/legal_documents/storage'

ALLOWED_EXTENSIONS = {'.txt', '.pdf', '.docx', '.doc'}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
```

### Step 3: Initialize Storage

```bash
# Create storage directory
sudo mkdir -p /var/legal_documents/storage
sudo chown $USER:$USER /var/legal_documents/storage
chmod 755 /var/legal_documents/storage
```

### Step 4: Process Documents

```python
from document_orchestrator import DocumentProcessor
from config import DATABASE_CONFIG, STORAGE_PATH

# Initialize processor
processor = DocumentProcessor(
    db_config=DATABASE_CONFIG,
    storage_path=STORAGE_PATH
)

# Process a single document
result = processor.process_document('/path/to/document.txt')

print(f"Case ID: {result['case_id']}")
print(f"Document Type: {result['document_type']}")
```

### Step 5: Query the System

```python
from document_orchestrator import LegalCaseQueryAgent
from config import DATABASE_CONFIG

# Initialize agent
agent = LegalCaseQueryAgent(db_config=DATABASE_CONFIG)

# Get case summary
summary = agent.get_case_summary('2552/2025')

print(f"Case Status: {summary['case_info']['current_status']}")
print(f"Number of charges: {len(summary['charges'])}")
print(f"Timeline events: {len(summary['timeline'])}")

# Natural language query
results = agent.query("What charges were filed against Ashok?")

for charge in results:
    print(f"- {charge['charge_description_ar']}")
```

## 📚 Document Types Supported

| Document Type | Arabic Name | Description |
|--------------|-------------|-------------|
| Court Session | محضر جلسة | Court hearing minutes |
| Police Report | بلاغ شرطة | Initial police complaint |
| Statement | افادة | Party statements |
| Investigation | محضر تحقيق | Prosecution investigation |
| Judgment | حكم | Court verdict |
| Case Transfer | أمر إحالة | Prosecution to court transfer |
| Notification | إعلان | Legal summons |
| Detention Order | حبس احتياطي | Custody order |
| Waiver | تنازل | Complaint withdrawal |
| Lab Result | نتيجة فحص | Forensic test results |
| Correspondence | مخاطبة | Inter-department letters |

## 🔍 Example Queries

### SQL Queries

```sql
-- 1. Find all cases for a specific accused
SELECT c.court_case_number, c.current_status, c.incident_date
FROM cases c
JOIN case_parties cp ON c.case_id = cp.case_id
JOIN parties p ON cp.party_id = p.party_id
WHERE p.full_name_ar = 'اشوك' AND cp.role_type = 'accused';

-- 2. Get timeline of a specific case
SELECT 
    event_date,
    event_type,
    event_description_ar
FROM case_events
WHERE case_id = (
    SELECT case_id FROM cases WHERE court_case_number = '2552/2025/جنح متنوعة/ابتدائي'
)
ORDER BY event_date;

-- 3. Find cases with specific charge (Article 270)
SELECT DISTINCT
    c.court_case_number,
    c.incident_date,
    ch.charge_description_ar
FROM cases c
JOIN charges ch ON c.case_id = ch.case_id
WHERE ch.article_number = '270';

-- 4. Get all judgments with fines
SELECT 
    c.court_case_number,
    j.judgment_date,
    j.verdict,
    s.fine_amount
FROM cases c
JOIN judgments j ON c.case_id = j.case_id
JOIN sentences s ON j.judgment_id = s.judgment_id
WHERE s.sentence_type = 'fine'
ORDER BY j.judgment_date DESC;

-- 5. Find cases involving specific nationalities
SELECT 
    c.court_case_number,
    p.full_name_ar,
    p.nationality,
    cp.role_type
FROM cases c
JOIN case_parties cp ON c.case_id = cp.case_id
JOIN parties p ON cp.party_id = p.party_id
WHERE p.nationality = 'نيبال';

-- 6. Get statistics by case type
SELECT 
    case_type,
    current_status,
    COUNT(*) as count,
    AVG(DATEDIFF(case_closed_date, case_opened_date)) as avg_duration_days
FROM cases
WHERE case_closed_date IS NOT NULL
GROUP BY case_type, current_status;

-- 7. Find detention records with duration
SELECT 
    p.full_name_ar,
    d.detention_type,
    d.start_date,
    d.actual_end_date,
    d.duration_days,
    d.release_type
FROM detention_records d
JOIN parties p ON d.party_id = p.party_id
WHERE d.detention_status = 'released'
ORDER BY d.start_date DESC;

-- 8. Get most common charge types
SELECT 
    article_number,
    law_name_ar,
    COUNT(*) as frequency
FROM charges
GROUP BY article_number, law_name_ar
ORDER BY frequency DESC
LIMIT 10;

-- 9. Find cases with waivers
SELECT 
    c.court_case_number,
    w.waiver_date,
    w.waiver_type,
    c.current_status
FROM cases c
JOIN waivers w ON c.case_id = w.case_id;

-- 10. Search documents by content
SELECT 
    d.document_type,
    d.document_date,
    c.court_case_number,
    MATCH(d.extracted_text_ar) AGAINST('سكر' IN NATURAL LANGUAGE MODE) as relevance
FROM documents d
JOIN cases c ON d.case_id = c.case_id
WHERE MATCH(d.extracted_text_ar) AGAINST('سكر' IN NATURAL LANGUAGE MODE)
ORDER BY relevance DESC;
```

### Natural Language Queries (AI Agent)

```python
agent = LegalCaseQueryAgent(db_config=DATABASE_CONFIG)

# Example queries:
agent.query("Show me all charges against Ashok")
agent.query("What was the timeline of case 2552/2025?")
agent.query("What was the final sentence?")
agent.query("Did the complainant withdraw the complaint?")
agent.query("How many court sessions were held?")
agent.query("What evidence was presented?")
agent.query("Who was the judge?")
agent.query("What law articles were cited?")
```

## 🔧 Advanced Features

### 1. Batch Processing

```python
# Process all documents in a directory
import os
from pathlib import Path

document_dir = Path('/path/to/documents')
document_files = list(document_dir.glob('*.txt'))

processor = DocumentProcessor(db_config=DATABASE_CONFIG, storage_path=STORAGE_PATH)
results = processor.process_batch(document_files)

# Generate report
successful = [r for r in results if r['success']]
failed = [r for r in results if not r['success']]

print(f"Processed: {len(results)}")
print(f"Successful: {len(successful)}")
print(f"Failed: {len(failed)}")
```

### 2. Export Case Report

```python
def export_case_report(case_id: int, output_path: str):
    """Export complete case report to DOCX"""
    
    agent = LegalCaseQueryAgent(db_config=DATABASE_CONFIG)
    summary = agent.get_case_summary_by_id(case_id)
    
    from docx import Document
    from docx.shared import Pt, RGBColor
    
    doc = Document()
    doc.add_heading('تقرير القضية', 0)
    
    # Case Information
    doc.add_heading('معلومات القضية', level=1)
    doc.add_paragraph(f"رقم القضية: {summary['case_info']['court_case_number']}")
    doc.add_paragraph(f"حالة القضية: {summary['case_info']['current_status']}")
    
    # Parties
    doc.add_heading('الأطراف', level=1)
    for party in summary['parties']:
        doc.add_paragraph(f"- {party['full_name_ar']} ({party['role_type']})")
    
    # Charges
    doc.add_heading('التهم', level=1)
    for charge in summary['charges']:
        doc.add_paragraph(f"- {charge['charge_description_ar']}")
    
    # Timeline
    doc.add_heading('الجدول الزمني', level=1)
    for event in summary['timeline']:
        doc.add_paragraph(f"{event['event_date']}: {event['event_description_ar']}")
    
    # Judgment
    if summary['judgment']:
        doc.add_heading('الحكم', level=1)
        for item in summary['judgment']:
            doc.add_paragraph(f"- {item['sentence_description_ar']}")
    
    doc.save(output_path)
```

### 3. Statistics Dashboard

```python
def get_dashboard_statistics():
    """Get key statistics for dashboard"""
    
    with DatabaseManager(**DATABASE_CONFIG) as db:
        with db.connection.cursor() as cursor:
            stats = {}
            
            # Total cases
            cursor.execute("SELECT COUNT(*) as total FROM cases")
            stats['total_cases'] = cursor.fetchone()['total']
            
            # Cases by status
            cursor.execute("""
                SELECT current_status, COUNT(*) as count 
                FROM cases 
                GROUP BY current_status
            """)
            stats['by_status'] = cursor.fetchall()
            
            # Cases by type
            cursor.execute("""
                SELECT case_type, COUNT(*) as count 
                FROM cases 
                GROUP BY case_type
            """)
            stats['by_type'] = cursor.fetchall()
            
            # Total parties
            cursor.execute("SELECT COUNT(*) as total FROM parties")
            stats['total_parties'] = cursor.fetchone()['total']
            
            # Total documents
            cursor.execute("SELECT COUNT(*) as total FROM documents")
            stats['total_documents'] = cursor.fetchone()['total']
            
            # Recent cases
            cursor.execute("""
                SELECT court_case_number, incident_date, current_status
                FROM cases
                ORDER BY created_at DESC
                LIMIT 10
            """)
            stats['recent_cases'] = cursor.fetchall()
            
            return stats
```

## 🛡️ Security Best Practices

### 1. Database Security
```sql
-- Create read-only user for reporting
CREATE USER 'legal_readonly'@'localhost' IDENTIFIED BY 'readonly_password';
GRANT SELECT ON legal_cases.* TO 'legal_readonly'@'localhost';

-- Enable audit logging
SET GLOBAL general_log = 'ON';
SET GLOBAL log_output = 'TABLE';
```

### 2. File Security
```python
# Validate file types
ALLOWED_EXTENSIONS = {'.txt', '.pdf', '.docx', '.doc'}

def validate_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File type {ext} not allowed")
    
    # Check file size
    if os.path.getsize(file_path) > MAX_FILE_SIZE:
        raise ValueError("File too large")
    
    return True
```

### 3. Data Encryption
```python
# Encrypt sensitive fields
from cryptography.fernet import Fernet

def encrypt_sensitive_data(data: str, key: bytes) -> str:
    f = Fernet(key)
    return f.encrypt(data.encode()).decode()

def decrypt_sensitive_data(encrypted_data: str, key: bytes) -> str:
    f = Fernet(key)
    return f.decrypt(encrypted_data.encode()).decode()
```

## 📊 Performance Optimization

### 1. Database Indexing
```sql
-- Add indexes for common queries
CREATE INDEX idx_case_dates ON cases(incident_date, case_closed_date);
CREATE INDEX idx_party_search ON parties(full_name_ar(50), nationality);
CREATE INDEX idx_document_date ON documents(document_date, document_type);
CREATE INDEX idx_charge_article ON charges(article_number, charge_status);

-- Full-text search indexes
ALTER TABLE documents ADD FULLTEXT INDEX ft_content (extracted_text_ar, extracted_text_en);
ALTER TABLE charges ADD FULLTEXT INDEX ft_charges (charge_description_ar);
```

### 2. Query Optimization
```python
# Use connection pooling
import pymysql.pooling

db_pool = pymysql.pooling.ConnectionPool(
    pool_size=10,
    host='localhost',
    user='legal_user',
    password='password',
    database='legal_cases',
    charset='utf8mb4'
)

# Use batch inserts
def batch_insert_documents(documents: list):
    with db_pool.connection() as conn:
        with conn.cursor() as cursor:
            sql = "INSERT INTO documents (...) VALUES (%s, %s, ...)"
            cursor.executemany(sql, documents)
            conn.commit()
```

### 3. Caching
```python
from functools import lru_cache
import redis

# Redis cache for frequent queries
redis_client = redis.Redis(host='localhost', port=6379, db=0)

@lru_cache(maxsize=1000)
def get_case_by_number(case_number: str):
    # Check cache first
    cached = redis_client.get(f"case:{case_number}")
    if cached:
        return json.loads(cached)
    
    # Query database
    with DatabaseManager(**DATABASE_CONFIG) as db:
        # ... query logic
        
        # Cache result
        redis_client.setex(
            f"case:{case_number}",
            3600,  # 1 hour TTL
            json.dumps(result)
        )
        
        return result
```

## 🧪 Testing

### Unit Tests
```python
import unittest

class TestDocumentClassifier(unittest.TestCase):
    def test_classify_judgment(self):
        text = "حُكم صَادِرْ بِإِسْم حَضَرَةَ..."
        doc_type = DocumentClassifier.classify(text)
        self.assertEqual(doc_type.type_id, 'judgment')
    
    def test_classify_police_report(self):
        text = "بلاغ داخلي رقم: 4308\2025..."
        doc_type = DocumentClassifier.classify(text)
        self.assertEqual(doc_type.type_id, 'police_report')

class TestReferenceExtractor(unittest.TestCase):
    def test_extract_court_case_number(self):
        text = "رقم الدعوى: 2552/2025/جنح متنوعة"
        number = ReferenceNumberExtractor.extract_court_case_number(text)
        self.assertEqual(number, "2552/2025/جنح متنوعة")

if __name__ == '__main__':
    unittest.main()
```

## 📖 API Documentation

### REST API Endpoints (FastAPI Example)

```python
from fastapi import FastAPI, UploadFile, File
from typing import List

app = FastAPI()

@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload and process a legal document"""
    # Save file
    file_path = f"/tmp/{file.filename}"
    with open(file_path, "wb") as f:
        f.write(await file.read())
    
    # Process document
    processor = DocumentProcessor(DATABASE_CONFIG, STORAGE_PATH)
    result = processor.process_document(file_path)
    
    return result

@app.get("/api/cases/{case_number}")
async def get_case(case_number: str):
    """Get case summary"""
    agent = LegalCaseQueryAgent(DATABASE_CONFIG)
    return agent.get_case_summary(case_number)

@app.get("/api/cases/{case_id}/timeline")
async def get_timeline(case_id: int):
    """Get case timeline"""
    # Implementation...
    pass

@app.get("/api/search")
async def search(q: str, type: str = None):
    """Search cases and documents"""
    # Implementation...
    pass

@app.get("/api/statistics")
async def get_statistics():
    """Get dashboard statistics"""
    return get_dashboard_statistics()
```

## 🔄 Maintenance

### Backup
```bash
# Daily backup script
#!/bin/bash
DATE=$(date +%Y%m%d)
BACKUP_DIR="/var/backups/legal_cases"

# Backup database
mysqldump -u legal_user -p legal_cases | gzip > $BACKUP_DIR/db_$DATE.sql.gz

# Backup documents
tar -czf $BACKUP_DIR/docs_$DATE.tar.gz /var/legal_documents/storage

# Keep only last 30 days
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete
```

### Monitoring
```python
# Log parser for monitoring
def monitor_processing_errors():
    with DatabaseManager(**DATABASE_CONFIG) as db:
        with db.connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    DATE(created_at) as date,
                    processing_status,
                    COUNT(*) as count
                FROM documents
                WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                GROUP BY DATE(created_at), processing_status
            """)
            return cursor.fetchall()
```

## 📞 Support

For issues or questions:
1. Check the documentation
2. Review example code
3. Check logs in `/var/log/legal_system/`
4. Contact system administrator

## 📝 License

Proprietary - Internal Use Only

---

**Last Updated:** 2025-01-27
**Version:** 1.0.0
# LegalDoc
