"""
Example usage of the Legal Case Management System
"""

from document_orchestrator import create_processor, create_query_agent
from config import CONFIG
import os

def main():
    """Example usage"""
    
    # Check if API key is set
    if CONFIG['anthropic']['api_key'] == 'your-api-key-here':
        print("⚠️  Please set ANTHROPIC_API_KEY environment variable")
        print("   export ANTHROPIC_API_KEY='your-actual-key'")
        return
    
    # Initialize processor
    print("📄 Initializing Document Processor...")
    processor = create_processor()
    
    # Example: Process a document
    # Replace with actual document path
    document_path = "/path/to/your/document.txt"
    
    if os.path.exists(document_path):
        print(f"\n🔄 Processing document: {document_path}")
        result = processor.process_document(document_path)
        
        if result['success']:
            print(f"✅ Success!")
            print(f"   Case ID: {result['case_id']}")
            print(f"   Document ID: {result['document_id']}")
            print(f"   Document Type: {result['document_type']}")
            print(f"   Confidence: {result['confidence']}%")
        else:
            print(f"❌ Error: {result.get('error')}")
    else:
        print(f"\n⚠️  Document not found: {document_path}")
        print("   Please update document_path with a valid file path")
    
    # Example: Query case information
    print("\n🔍 Initializing Query Agent...")
    agent = create_query_agent()
    
    # Get case summary
    case_number = "2552/2025/جنح متنوعة/ابتدائي"
    print(f"\n📊 Getting summary for case: {case_number}")
    summary = agent.get_case_summary(case_number)
    
    if 'error' not in summary:
        print(f"✅ Case Status: {summary['case_info']['current_status']}")
        print(f"   Number of charges: {len(summary['charges'])}")
        print(f"   Timeline events: {len(summary['timeline'])}")
        print(f"   Parties involved: {len(summary['parties'])}")
    else:
        print(f"❌ {summary['error']}")
    
    # Example: Natural language query
    print("\n💬 Natural Language Query:")
    query = "What charges were filed against Ashok?"
    print(f"   Query: {query}")
    results = agent.query(query)
    print(f"   Results: {len(results)} items found")


if __name__ == '__main__':
    main()

