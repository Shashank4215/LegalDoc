"""
Batch process all documents in the documents/ folder
Checks database connection before processing
"""

from document_orchestrator import create_processor
from database_manager import DatabaseManager
from config import CONFIG
import os
import sys
from pathlib import Path

def check_database_connection():
    """Check if database connection works"""
    print("🔌 Checking database connection...")
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            # Try a simple query
            result = db.execute_query("SELECT version()")
            if result:
                print(f"   ✅ Connected to PostgreSQL")
                print(f"   📊 Database: {CONFIG['database']['database']}")
                return True
    except Exception as e:
        print(f"   ❌ Database connection failed: {str(e)}")
        print("\n💡 Troubleshooting:")
        print("   1. Make sure PostgreSQL is running")
        print("   2. Check your database credentials in config.py or .env")
        print("   3. Verify the database 'legal_case' exists")
        print("   4. Run the schema migration if not done: psql -U postgres -d legal_case -f create_schema_postgresql.sql")
        return False

def main():
    """Main function to process documents"""
    
    # Check API key
    if CONFIG['anthropic']['api_key'] == 'your-api-key-here':
        print("⚠️  ANTHROPIC_API_KEY not set!")
        print("   Please set it:")
        print("   export ANTHROPIC_API_KEY='your-actual-key'")
        print("   Or add it to your .env file")
        sys.exit(1)
    
    print("✅ API key configured")
    
    # Check database connection
    if not check_database_connection():
        print("\n❌ Cannot proceed without database connection")
        sys.exit(1)
    
    # Initialize processor
    print("\n📄 Initializing Document Processor...")
    try:
        processor = create_processor()
        print("   ✅ Processor initialized")
    except Exception as e:
        print(f"   ❌ Failed to initialize processor: {str(e)}")
        sys.exit(1)
    
    # Process all .txt files in documents folder
    documents_dir = Path('./documents')
    
    if not documents_dir.exists():
        print(f"\n❌ Documents directory not found: {documents_dir}")
        print("   Please create it and add your documents")
        sys.exit(1)
    
    txt_files = list(documents_dir.glob('*.txt'))
    
    if not txt_files:
        print(f"\n❌ No .txt files found in {documents_dir}")
        print("   Supported formats: .txt, .docx, .pdf")
        sys.exit(1)
    
    print(f"\n📚 Found {len(txt_files)} documents to process\n")
    print("=" * 60)
    
    successful = []
    failed = []
    
    for i, txt_file in enumerate(txt_files, 1):
        print(f"\n[{i}/{len(txt_files)}] Processing: {txt_file.name}")
        print("-" * 60)
        try:
            result = processor.process_document(str(txt_file))
            
            if result['success']:
                print(f"   ✅ Success!")
                print(f"      Case ID: {result['case_id']}")
                print(f"      Document ID: {result['document_id']}")
                print(f"      Document Type: {result['document_type']}")
                print(f"      Confidence: {result['confidence']}%")
                successful.append({
                    'file': txt_file.name,
                    'case_id': result['case_id'],
                    'document_id': result['document_id'],
                    'type': result['document_type']
                })
            else:
                error_msg = result.get('error', 'Unknown error')
                print(f"   ❌ Failed: {error_msg}")
                failed.append({
                    'file': txt_file.name,
                    'error': error_msg
                })
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            import traceback
            traceback.print_exc()
            failed.append({
                'file': txt_file.name,
                'error': str(e)
            })
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 PROCESSING SUMMARY")
    print("=" * 60)
    print(f"✅ Successful: {len(successful)}")
    print(f"❌ Failed: {len(failed)}")
    
    if successful:
        print("\n✅ Successfully processed documents:")
        for item in successful:
            print(f"   • {item['file']}")
            print(f"     Case ID: {item['case_id']}, Type: {item['type']}")
    
    if failed:
        print("\n❌ Failed documents:")
        for item in failed:
            print(f"   • {item['file']}")
            print(f"     Error: {item['error']}")
    
    print("\n" + "=" * 60)
    
    # Exit with error code if any failed
    if failed:
        sys.exit(1)

if __name__ == '__main__':
    main()

