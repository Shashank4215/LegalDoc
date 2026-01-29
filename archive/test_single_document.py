"""
Test processing a single document file
Usage: python test_single_document.py <file_path>
   or: python test_single_document.py  (will prompt for file path)
"""

import sys
import os
from pathlib import Path
from document_orchestrator import create_processor
from database_manager import DatabaseManager
from config import CONFIG

def check_database_connection():
    """Check if database connection works"""
    print("🔌 Checking database connection...")
    try:
        with DatabaseManager(**CONFIG['database']) as db:
            result = db.execute_query("SELECT version()")
            if result:
                print(f"   ✅ Connected to PostgreSQL")
                print(f"   📊 Database: {CONFIG['database']['database']}")
                return True
    except Exception as e:
        print(f"   ❌ Database connection failed: {str(e)}")
        return False

def main():
    """Main function to process a single document"""
    
    # Get file path from command line or prompt
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        # Interactive mode
        print("\n📄 Single Document Tester")
        print("=" * 60)
        file_path = input("\nEnter document file path: ").strip()
        
        # Remove quotes if user pasted path with quotes
        file_path = file_path.strip('"').strip("'")
    
    # Validate file exists
    if not os.path.exists(file_path):
        print(f"\n❌ File not found: {file_path}")
        print("\n💡 Tips:")
        print("   - Use absolute path or relative to current directory")
        print("   - Example: python test_single_document.py documents/test.txt")
        sys.exit(1)
    
    file_path = Path(file_path).resolve()
    print(f"\n📄 Processing: {file_path.name}")
    print(f"   Path: {file_path}")
    print("=" * 60)
    
    # Check API key
    if CONFIG['anthropic']['api_key'] == 'your-api-key-here':
        print("\n⚠️  ANTHROPIC_API_KEY not set!")
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
    
    # Process document
    print("\n" + "=" * 60)
    print("🔄 PROCESSING DOCUMENT")
    print("=" * 60)
    
    try:
        result = processor.process_document(str(file_path))
        
        print("\n" + "=" * 60)
        print("📊 RESULTS")
        print("=" * 60)
        
        if result['success']:
            print("\n✅ SUCCESS!")
            print(f"\n📋 Document Information:")
            print(f"   Document ID: {result['document_id']}")
            print(f"   Document Type: {result['document_type']}")
            print(f"   Confidence: {result['confidence']}%")
            
            print(f"\n🔗 Case Information:")
            print(f"   Case ID: {result['case_id']}")
            print(f"   Case Action: {result.get('case_action', 'N/A')}")
            print(f"   Sequence Valid: {'✅ Yes' if result.get('sequence_valid', True) else '⚠️  No (unusual order)'}")
            
            # Show completeness if available
            if 'completeness' in result and result['completeness']:
                comp = result['completeness']
                print(f"\n📊 Case Completeness:")
                print(f"   References Complete: {'✅' if comp.get('references_complete') else '❌'}")
                print(f"   Has Police Report: {'✅' if comp.get('has_police_report') else '❌'}")
                print(f"   Has Investigation: {'✅' if comp.get('has_investigation') else '❌'}")
                print(f"   Has Judgment: {'✅' if comp.get('has_judgment') else '❌'}")
                print(f"   Total Documents: {comp.get('total_documents', 0)}")
                print(f"   Document Types: {', '.join(comp.get('document_types', []))}")
                print(f"   Estimated Stage: {comp.get('estimated_stage', 'unknown')}")
            
            # Show extracted data summary
            if 'extracted_data' in result and result['extracted_data']:
                print(f"\n📝 Extracted Data Summary:")
                extracted = result['extracted_data']
                
                # Show case references if available
                if isinstance(extracted, dict) and 'case_references' in extracted:
                    refs = extracted['case_references']
                    if isinstance(refs, dict):
                        print(f"   Court Case Number: {refs.get('court_case_number', 'N/A')}")
                        print(f"   Prosecution Number: {refs.get('prosecution_case_number', 'N/A')}")
                        print(f"   Police Report Number: {refs.get('police_report_number', 'N/A')}")
                
                # Show dates
                date_fields = ['judgment_date', 'session_date', 'investigation_date', 
                              'report_date', 'incident_date']
                for field in date_fields:
                    if isinstance(extracted, dict) and extracted.get(field):
                        print(f"   {field.replace('_', ' ').title()}: {extracted[field]}")
            
            print("\n" + "=" * 60)
            print("✅ Document processed successfully!")
            print("=" * 60)
            
        else:
            print("\n❌ FAILED!")
            print(f"\nError: {result.get('error', 'Unknown error')}")
            print("\n" + "=" * 60)
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()

