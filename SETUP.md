# Setup Guide - Legal Case Management System (PostgreSQL)

## Quick Start

### Option 1: Automated Setup (Recommended)

```bash
# Run the setup script
./setup_postgresql.sh
```

This script will:
- Check PostgreSQL installation
- Create the database
- Run the schema creation
- Set up Python virtual environment
- Install dependencies
- Create .env file

### Option 2: Manual Setup

### 1. Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install packages
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Set Up PostgreSQL Database

#### Using pgAdmin4:
1. Open pgAdmin4
2. Connect to PostgreSQL server
3. Right-click "Databases" → Create → Database
4. Name: `legal_cases`
5. Owner: `postgres`
6. Encoding: `UTF8`
7. Open Query Tool and run `create_schema_postgresql.sql`

#### Using Command Line:
```bash
# Create database
createdb -U postgres legal_cases

# Run schema creation
psql -U postgres -d legal_cases -f create_schema_postgresql.sql
```

### 3. Configure Environment Variables

The setup script creates a `.env` file automatically. Or create it manually:

```bash
# Create .env file
cat > .env << EOF
DB_HOST=localhost
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=legal_cases
DB_PORT=5432

ANTHROPIC_API_KEY=your-anthropic-api-key
ANTHROPIC_MODEL=claude-sonnet-4-20250514

STORAGE_PATH=./storage
LOG_LEVEL=INFO
DEBUG=False
EOF
```

Or update `config.py` directly with your values.

### 4. Create Storage Directory

```bash
mkdir -p storage
chmod 755 storage
```

### 5. Test the System

```python
from document_orchestrator import create_processor

processor = create_processor()
result = processor.process_document('/path/to/document.txt')
print(result)
```

## Project Structure

```
QPPChatbot/
├── ai_document_parser.py      # AI-powered document extraction
├── database_manager.py         # Database operations
├── document_orchestrator.py   # Main orchestrator
├── config.py                  # Configuration
├── create_schema.sql          # Database schema
├── requirements.txt           # Python dependencies
├── example_usage.py          # Usage examples
└── README.md                  # Full documentation
```

## Key Components

### 1. AI Document Parser (`ai_document_parser.py`)
- Uses Claude API for intelligent extraction
- Supports multiple document types
- Returns structured data

### 2. Database Manager (`database_manager.py`)
- Handles all database operations
- Connection pooling
- Transaction management

### 3. Document Orchestrator (`document_orchestrator.py`)
- Coordinates document processing
- Integrates AI parser with database
- Provides query agent for NL queries

## Usage Examples

### Process a Document

```python
from document_orchestrator import create_processor

processor = create_processor()
result = processor.process_document('document.txt')

if result['success']:
    print(f"Case ID: {result['case_id']}")
    print(f"Document Type: {result['document_type']}")
```

### Query Case Information

```python
from document_orchestrator import create_query_agent

agent = create_query_agent()
summary = agent.get_case_summary('2552/2025/جنح متنوعة/ابتدائي')

print(f"Status: {summary['case_info']['current_status']}")
print(f"Charges: {len(summary['charges'])}")
```

## Troubleshooting

### Database Connection Issues
- Verify PostgreSQL is running: `pg_isready`
- Check credentials in `config.py` or `.env`
- Ensure database exists: `psql -U postgres -l`
- Check PostgreSQL is listening: `lsof -i :5432`

### PostgreSQL Not Running
```bash
# Try starting PostgreSQL
brew services start postgresql@15
# Or if installed via installer:
sudo /Library/PostgreSQL/15/bin/pg_ctl restart -D /Library/PostgreSQL/15/data
```

### API Key Issues
- Verify Anthropic API key is set correctly
- Check API key has sufficient credits
- Verify model name is correct

### Import Errors
- Ensure all dependencies are installed: `pip install -r requirements.txt`
- Check Python version (3.9+ required)
- Verify virtual environment is activated

## Next Steps

1. Process your first document
2. Query case information
3. Build API endpoints (FastAPI example in README.md)
4. Implement natural language to SQL conversion
5. Add more document type extractors

