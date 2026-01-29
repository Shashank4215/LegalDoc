from mongo_manager import MongoManager
from config import CONFIG

# Test MongoDB connection
try:
    with MongoManager(**CONFIG['mongodb']) as mongo:
        print("✅ MongoDB connection successful!")
        print(f"Database: {CONFIG['mongodb']['database']}")
        
        # Test creating a document
        test_doc = {
            'file_path': 'test.txt',
            'file_name': 'test.txt',
            'text': 'Test document',
            'document_type': 'test'
        }
        doc_id = mongo.create_document(test_doc)
        print(f"✅ Test document created: {doc_id}")
        
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}")