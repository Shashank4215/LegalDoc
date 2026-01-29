"""
MongoDB Batch Processor for Legal Case Management System
Two-phase processing: Extract & Store first, then Link to Cases
"""

import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from mongo_manager import MongoManager
from document_processor import DocumentProcessor
from document_type_classifier import DocumentTypeClassifier
from case_linker_mongo import CaseLinkerMongo
from config import CONFIG

logger = logging.getLogger(__name__)


class BatchProcessorMongo:
    """Batch process documents with two-phase approach"""
    
    def __init__(self):
        """Initialize batch processor"""
        self.document_processor = DocumentProcessor()
        self.type_classifier = DocumentTypeClassifier()
        logger.info("Initialized BatchProcessorMongo")
    
    def process_batch(self, file_paths: List[str], 
                     mongo_manager: MongoManager,
                     phase: str = 'both',
                     reextract_linked: bool = False) -> Dict[str, Any]:
        """
        Process batch of documents
        
        Args:
            file_paths: List of file paths to process
            mongo_manager: MongoManager instance
            phase: 'extract', 'link', or 'both' (default)
            
        Returns:
            Dictionary with processing results
        """
        results = {
            'total_files': len(file_paths),
            'processed': 0,
            'failed': 0,
            'documents': [],
            'cases_created': 0,
            'cases_linked': 0,
            'errors': []
        }
        
        if phase in ['extract', 'both']:
            print(f"\n{'='*60}")
            print(f"Phase 1: Extracting and storing {len(file_paths)} documents...")
            print(f"{'='*60}")
            logger.info(f"Phase 1: Extracting and storing {len(file_paths)} documents...")
            phase1_results = self._phase1_extract_and_store(
                file_paths, mongo_manager, reextract_linked=reextract_linked
            )
            results.update(phase1_results)
            print(f"\n✅ Phase 1 complete: {phase1_results['processed']} processed, {phase1_results['failed']} failed")
        
        if phase in ['link', 'both']:
            print(f"\n{'='*60}")
            print("Phase 2: Linking documents to cases...")
            print(f"{'='*60}")
            logger.info("Phase 2: Linking documents to cases...")
            phase2_results = self._phase2_link_to_cases(mongo_manager, relink_linked=False)
            results['cases_created'] = phase2_results.get('cases_created', 0)
            results['cases_linked'] = phase2_results.get('cases_linked', 0)
            print(f"✅ Phase 2 complete: {phase2_results.get('cases_created', 0)} cases created, {phase2_results.get('cases_linked', 0)} linked")
        
        logger.info(f"Batch processing complete: {results['processed']} processed, {results['failed']} failed")
        return results
    
    def _phase1_extract_and_store(self, file_paths: List[str],
                                  mongo_manager: MongoManager,
                                  reextract_linked: bool = False) -> Dict[str, Any]:
        """
        Phase 1: Extract entities and store documents in MongoDB
        
        Args:
            file_paths: List of file paths
            mongo_manager: MongoManager instance
            
        Returns:
            Dictionary with phase 1 results
        """
        results = {
            'processed': 0,
            'failed': 0,
            'documents': []
        }
        
        for idx, file_path in enumerate(file_paths, 1):
            try:
                print(f"\n[{idx}/{len(file_paths)}] Processing: {Path(file_path).name}")
                file_path_obj = Path(file_path)
                if not file_path_obj.exists():
                    print(f"  ❌ File not found: {file_path}")
                    logger.warning(f"File not found: {file_path}")
                    results['failed'] += 1
                    if 'errors' not in results:
                        results['errors'] = []
                    results['errors'].append(f"File not found: {file_path}")
                    continue
                
                # Check for duplicate and if already linked to a case
                print(f"  Checking for duplicates...")
                file_hash = self._calculate_file_hash(file_path)
                existing_doc_id = mongo_manager.check_duplicate_document(file_hash)
                if existing_doc_id:
                    # Check if document is already linked to a case
                    existing_doc = mongo_manager.get_document(existing_doc_id)
                    if (not reextract_linked) and existing_doc and existing_doc.get('case_id'):
                        print(f"  ⏭️  Already processed and linked (skipping)")
                        logger.info(f"Document already processed and linked: {file_path} (doc_id: {existing_doc_id}, case_id: {existing_doc.get('case_id')})")
                        results['documents'].append({
                            'file_path': file_path,
                            'document_id': existing_doc_id,
                            'status': 'already_linked',
                            'skipped': True
                        })
                        results['processed'] += 1  # Count skipped as processed for overall stats
                        continue
                    else:
                        if existing_doc and existing_doc.get('case_id'):
                            print(f"  🔄 Already processed and linked (re-extracting because reextract_linked=True)...")
                            logger.info(f"Document already processed and linked: {file_path} (doc_id: {existing_doc_id}), re-extracting due to reextract_linked=True")
                        else:
                            print(f"  🔄 Already processed but not linked (will update)...")
                            logger.info(f"Document already processed but not linked: {file_path} (doc_id: {existing_doc_id}), will update")
                
                # Process document
                print(f"  📄 Extracting text and generating embedding...")
                logger.info(f"Processing document: {file_path}")
                processing_result = self.document_processor.process_document(file_path)
                
                # Detect document type if not already detected
                document_type = processing_result.get('document_type')
                if not document_type:
                    print(f"  🔍 Classifying document type...")
                    text = processing_result.get('text', '')
                    document_type, confidence = self.type_classifier.classify(text)
                    print(f"  📋 Document type: {document_type} (confidence: {confidence:.2f})")
                    logger.info(f"Detected document type: {document_type}")
                else:
                    print(f"  📋 Document type: {document_type}")
                
                print(f"  🤖 Extracting entities (this may take a moment)...")
                # Prepare document data for MongoDB
                document_data = {
                    'file_path': str(file_path),
                    'file_name': file_path_obj.name,
                    'file_hash': file_hash,
                    'file_size': processing_result.get('file_size', 0),
                    'text': processing_result.get('text', ''),
                    'embedding': processing_result.get('embedding', []),
                    'extracted_entities': processing_result.get('entities', {}),
                    'document_type': document_type,
                    'processing_status': 'extracted',
                    'processing_time_ms': processing_result.get('processing_time_ms', 0)
                }
                
                # Store or update in MongoDB
                print(f"  💾 Storing in MongoDB...")
                if existing_doc_id:
                    # Update existing document (preserve created_at, update other fields)
                    mongo_manager.update_document(existing_doc_id, document_data)
                    document_id = existing_doc_id
                    print(f"  ✅ Updated existing document (ID: {document_id})")
                else:
                    # Create new document
                    document_id = mongo_manager.create_document(document_data)
                    print(f"  ✅ Stored successfully (ID: {document_id})")
                
                results['processed'] += 1
                results['documents'].append({
                    'file_path': file_path,
                    'document_id': document_id,
                    'document_type': document_type,
                    'status': 'extracted'
                })
                
                logger.info(f"Stored document: {document_id} ({file_path})")
            
            except Exception as e:
                print(f"  ❌ Error: {str(e)}")
                logger.error(f"Error processing {file_path}: {str(e)}", exc_info=True)
                results['failed'] += 1
                if 'errors' not in results:
                    results['errors'] = []
                results['errors'].append(f"{file_path}: {str(e)}")
        
        return results
    
    def _phase2_link_to_cases(self, mongo_manager: MongoManager,
                              relink_linked: bool = False) -> Dict[str, Any]:
        """
        Phase 2: Link documents to cases using multi-parameter matching
        
        Args:
            mongo_manager: MongoManager instance
            
        Returns:
            Dictionary with phase 2 results
        """
        results = {
            'cases_created': 0,
            'cases_linked': 0,
            'documents_linked': 0,
            'errors': []
        }
        
        # Initialize case linker
        case_linker = CaseLinkerMongo(mongo_manager)
        
        documents_collection = mongo_manager.db['documents']
        
        # Get all unlinked documents
        unlinked_docs = list(documents_collection.find({'case_id': None}))
        logger.info(f"Found {len(unlinked_docs)} unlinked documents to process")
        
        # Phase 2A: link unlinked documents (existing behavior)
        for doc in unlinked_docs:
            try:
                document_id = str(doc['_id'])
                extracted_entities = doc.get('extracted_entities', {})
                embedding = doc.get('embedding', [])
                
                # Prepare document data for linking
                document_data = {
                    'embedding': embedding,
                    'document_id': document_id
                }
                
                # Find or create case
                case_id, confidence, was_created = case_linker.find_or_create_case(
                    document_data, extracted_entities
                )
                
                # Link document to case
                linking_params = {
                    'confidence': confidence,
                    'linked_at': datetime.now().isoformat()
                }
                
                case_linker.link_document_to_case(
                    case_id, document_id, confidence, linking_params
                )
                
                # Update case with entities
                if was_created:
                    # New case created - entities already stored in _create_new_case
                    results['cases_created'] += 1
                    print(f"  ✅ Created new case: {case_id}")
                else:
                    # Update existing case with new entities
                    case_linker._store_entities_normalized(
                        case_id, extracted_entities, document_id
                    )
                    print(f"  🔗 Linked to existing case: {case_id} (confidence: {confidence:.3f})")
                
                results['cases_linked'] += 1
                results['documents_linked'] += 1
                
                logger.info(f"Linked document {document_id} to case {case_id} (confidence: {confidence:.3f}, created: {was_created})")
            
            except Exception as e:
                logger.error(f"Error linking document {doc.get('_id')}: {str(e)}")
                if 'errors' not in results:
                    results['errors'] = []
                results['errors'].append(f"Document {doc.get('_id')}: {str(e)}")
        
        # Phase 2B: optionally refresh normalized entities for already-linked documents
        if relink_linked:
            linked_docs = list(documents_collection.find({'case_id': {'$ne': None}}))
            logger.info(f"Refreshing normalized entities for {len(linked_docs)} already-linked documents")
            
            for doc in linked_docs:
                try:
                    document_id = str(doc['_id'])
                    case_id = str(doc['case_id'])
                    extracted_entities = doc.get('extracted_entities', {}) or {}
                    
                    # We DO NOT re-run case matching for already-linked docs here.
                    # We only refresh normalized entities on the existing case.
                    case_linker._store_entities_normalized(case_id, extracted_entities, document_id)
                    results['documents_linked'] += 1
                    logger.info(f"Refreshed normalized entities for linked document {document_id} (case {case_id})")
                except Exception as e:
                    logger.error(f"Error refreshing linked document {doc.get('_id')}: {str(e)}")
                    if 'errors' not in results:
                        results['errors'] = []
                    results['errors'].append(f"Linked document {doc.get('_id')}: {str(e)}")
        
        return results
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA256 hash of file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def process_single_document(self, file_path: str, 
                               mongo_manager: MongoManager,
                               link_to_case: bool = True) -> Dict[str, Any]:
        """
        Process a single document (both phases)
        
        Args:
            file_path: Path to document file
            mongo_manager: MongoManager instance
            link_to_case: Whether to link to case immediately
            
        Returns:
            Dictionary with processing results
        """
        # Phase 1: Extract and store
        phase1_results = self._phase1_extract_and_store([file_path], mongo_manager)
        
        if phase1_results['failed'] > 0:
            return {
                'success': False,
                'error': phase1_results.get('errors', ['Unknown error'])[0]
            }
        
        document_id = phase1_results['documents'][0]['document_id']
        
        # Phase 2: Link to case (if requested)
        if link_to_case:
            # For single-document processing we also only process unlinked docs
            phase2_results = self._phase2_link_to_cases(mongo_manager, relink_linked=False)
            return {
                'success': True,
                'document_id': document_id,
                'case_created': phase2_results.get('cases_created', 0) > 0,
                'case_linked': phase2_results.get('cases_linked', 0) > 0
            }
        
        return {
            'success': True,
            'document_id': document_id,
            'status': 'extracted_not_linked'
        }

