from batch_processor_mongo import BatchProcessorMongo
from mongo_manager import MongoManager
from config import CONFIG
import sys
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def collect_document_paths(paths):
    """Collect all document files from paths (files or directories)"""
    all_paths = []
    supported_extensions = {'.pdf', '.docx', '.doc', '.txt'}
    
    for path_str in paths:
        path = Path(path_str)
        
        if not path.exists():
            print(f"Warning: Path does not exist: {path_str}")
            continue
        
        if path.is_file():
            # Single file
            if path.suffix.lower() in supported_extensions:
                all_paths.append(str(path))
            else:
                print(f"Warning: Unsupported file type: {path_str}")
        elif path.is_dir():
            # Directory - find all supported files recursively
            for ext in supported_extensions:
                all_paths.extend([str(p) for p in path.rglob(f'*{ext}')])
        else:
            print(f"Warning: Unknown path type: {path_str}")
    
    return list(set(all_paths))  # Remove duplicates

reextract_linked = False
input_paths = []

# Parse args (simple parsing; supports --reextract-linked flag)
if len(sys.argv) > 1:
    for arg in sys.argv[1:]:
        if arg == "--reextract-linked":
            reextract_linked = True
        else:
            input_paths.append(arg)

if input_paths:
    doc_paths = collect_document_paths(input_paths)
else:
    # Default: process all documents in documents/ directory
    doc_dir = Path('documents')
    if doc_dir.exists() and doc_dir.is_dir():
        doc_paths = collect_document_paths([str(doc_dir)])
    else:
        doc_paths = []

if not doc_paths:
    print("No documents found. Place documents in 'documents/' directory or provide paths as arguments.")
    print("\nUsage:")
    print("  python process_documents_mongo.py                    # Process all in documents/")
    print("  python process_documents_mongo.py --reextract-linked  # Re-extract even if already linked")
    print("  python process_documents_mongo.py file1.pdf           # Process single file")
    print("  python process_documents_mongo.py ./documents         # Process directory")
    print("  python process_documents_mongo.py file1.pdf file2.docx # Process multiple files")
    sys.exit(1)

print(f"Found {len(doc_paths)} document(s) to process...")

# Initialize processor
processor = BatchProcessorMongo()

# Process batch
with MongoManager(**CONFIG['mongodb']) as mongo:
    # When we re-extract linked docs, also refresh normalized entities for them.
    results = processor.process_batch(
        doc_paths,
        mongo,
        phase='both',
        reextract_linked=reextract_linked
    )
    
    print("\n" + "="*50)
    print("BATCH PROCESSING RESULTS")
    print("="*50)
    print(f"Total files: {results['total_files']}")
    print(f"Processed: {results['processed']}")
    print(f"Failed: {results['failed']}")
    print(f"Cases created: {results['cases_created']}")
    print(f"Cases linked: {results['cases_linked']}")
    
    if results.get('errors'):
        print(f"\nErrors ({len(results['errors'])}):")
        for error in results['errors'][:5]:  # Show first 5
            print(f"  - {error}")