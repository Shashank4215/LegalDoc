"""
Batch Processor for Vector-Based Legal Case Management System
Processes multiple documents, clusters them by similarity, and creates unified cases
"""

import os
import glob
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import numpy as np

try:
    from sklearn.cluster import DBSCAN
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.preprocessing import normalize
except ImportError:
    raise ImportError(
        "scikit-learn is required but not installed. "
        "Install it with: pip install scikit-learn"
    )

from document_processor import DocumentProcessor
from case_linker import CaseLinker
from .db_manager_v2 import DatabaseManagerV2
from config import CONFIG

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Process multiple documents in batch, cluster by similarity, create unified cases"""
    
    def __init__(self, db_manager: DatabaseManagerV2):
        """
        Initialize batch processor
        
        Args:
            db_manager: DatabaseManagerV2 instance
        """
        self.db = db_manager
        self.doc_processor = DocumentProcessor()
        self.case_linker = CaseLinker(db_manager)
        logger.info("Initialized BatchProcessor")
    
    def process_batch(self, file_paths: List[str], 
                     cluster_threshold: float = None,
                     force_reprocess: bool = False) -> Dict[str, Any]:
        """
        Process a batch of documents
        
        Args:
            file_paths: List of file paths to process
            cluster_threshold: Similarity threshold for clustering (default from config)
            force_reprocess: If True, reprocess documents even if they already exist
            
        Returns:
            Dictionary with processing results
        """
        if cluster_threshold is None:
            cluster_threshold = CONFIG['vector_search']['similarity_threshold']
        
        logger.info(f"Processing batch of {len(file_paths)} documents")
        
        # Phase 0: If force_reprocess, delete existing documents from database
        if force_reprocess:
            logger.info("Force reprocess enabled - clearing existing documents")
            self._clear_existing_documents(file_paths)
        
        # Phase 1: Process each document (BERT model doesn't need batch fitting)
        processing_results = []
        for file_path in file_paths:
            try:
                result = self._process_single_document(file_path, force_reprocess=force_reprocess)
                processing_results.append(result)
            except Exception as e:
                logger.error(f"Error processing {file_path}: {str(e)}")
                self.db.log_processing(
                    file_path=file_path,
                    status='failed',
                    error_message=str(e)
                )
        
        logger.info(f"Processed {len(processing_results)} documents successfully")
        
        # Phase 2: Cluster documents by similarity
        case_groups = self._cluster_documents(processing_results, cluster_threshold)
        logger.info(f"Clustered documents into {len(case_groups)} case groups")
        
        # Phase 3: Create/update cases for each group
        case_results = []
        for group_id, group_docs in enumerate(case_groups, 1):
            try:
                case_result = self._process_case_group(group_docs, group_id)
                case_results.append(case_result)
            except Exception as e:
                logger.error(f"Error processing case group {group_id}: {str(e)}")
        
        return {
            'total_documents': len(file_paths),
            'processed_documents': len(processing_results),
            'case_groups': len(case_groups),
            'cases_created': len(case_results),
            'results': case_results
        }
    
    def _process_single_document(self, file_path: str, force_reprocess: bool = False) -> Dict[str, Any]:
        """
        Process a single document
        
        Args:
            file_path: Path to document file
            force_reprocess: If True, reprocess even if already exists
            
        Returns:
            Processing result dictionary
        """
        # Check for duplicate (unless force_reprocess)
        file_hash = self.doc_processor.calculate_file_hash(file_path)
        existing_doc_id = None if force_reprocess else self.db.check_duplicate_document(file_hash)
        
        if existing_doc_id:
            logger.info(f"Document {file_path} already processed (duplicate)")
            existing_doc = self.db.get_document(existing_doc_id)
            # Get embedding from database for clustering
            embedding = existing_doc.get('document_embedding')
            # If document is not linked to a case, include it in clustering
            status = 'duplicate' if existing_doc.get('case_id') else 'processed'
            return {
                'file_path': file_path,
                'document_id': existing_doc_id,
                'case_id': existing_doc.get('case_id'),
                'status': status,
                'embedding': embedding,  # Include embedding for clustering
                'entities': existing_doc.get('extracted_entities', {})
            }
        
        # Process document
        result = self.doc_processor.process_document(file_path)
        
        # Store document in database
        document_data = {
            'file_path': file_path,
            'file_hash': result['file_hash'],
            'original_filename': os.path.basename(file_path),
            'file_size_bytes': result['file_size'],
            'document_embedding': result['embedding'],
            'extracted_entities': result['entities'],
            'document_metadata': result['entities'].get('document_metadata', {}),
            'processing_status': 'processed',
            'confidence_score': None  # Will be set after case linking
        }
        
        document_id = self.db.create_document(document_data)
        
        # Log processing
        self.db.log_processing(
            file_path=file_path,
            status='success',
            document_id=document_id,
            processing_time_ms=result['processing_time_ms'],
            entities_extracted=self._count_entities(result['entities'])
        )
        
        return {
            'file_path': file_path,
            'document_id': document_id,
            'case_id': None,  # Will be set after clustering
            'status': 'processed',
            'embedding': result['embedding'],
            'entities': result['entities']
        }
    
    def _cluster_documents(self, processing_results: List[Dict], 
                          threshold: float) -> List[List[Dict]]:
        """
        Cluster documents by similarity using DBSCAN
        
        Args:
            processing_results: List of processing results
            threshold: Similarity threshold for clustering
            
        Returns:
            List of document groups (each group is a case)
        """
        # Include documents that are processed (new or unlinked duplicates)
        # Exclude only documents that are already linked to cases
        valid_results = [r for r in processing_results 
                        if r.get('embedding') is not None 
                        and (r['status'] == 'processed' or (r['status'] == 'duplicate' and r.get('case_id') is None))]
        
        if not valid_results:
            return []
        
        if len(valid_results) == 1:
            # Single document, return as single group
            return [valid_results]
        
        # Extract embeddings
        embeddings = np.array([r['embedding'] for r in valid_results])
        
        # Normalize embeddings for proper cosine similarity
        # This ensures similarity values are in [-1, 1] range
        embeddings_normalized = normalize(embeddings, norm='l2')
        
        # Calculate similarity matrix (now guaranteed to be in [-1, 1])
        similarity_matrix = cosine_similarity(embeddings_normalized)
        
        # Convert similarity to distance (1 - similarity)
        # Clamp to ensure non-negative (handle any edge cases)
        distance_matrix = 1 - similarity_matrix
        distance_matrix = np.maximum(distance_matrix, 0)  # Ensure non-negative
        
        # Use DBSCAN for clustering
        # eps = 1 - threshold (distance threshold)
        # min_samples = 1 (each document can be its own cluster)
        eps = 1 - threshold
        clustering = DBSCAN(eps=eps, min_samples=1, metric='precomputed')
        labels = clustering.fit_predict(distance_matrix)
        
        # Group documents by cluster label
        groups = {}
        for idx, label in enumerate(labels):
            if label not in groups:
                groups[label] = []
            groups[label].append(valid_results[idx])
        
        # Convert to list of lists
        case_groups = list(groups.values())
        
        logger.info(f"Clustered {len(valid_results)} documents into {len(case_groups)} groups")
        
        return case_groups
    
    def _process_case_group(self, group_docs: List[Dict], group_id: int) -> Dict[str, Any]:
        """
        Process a group of documents (one case)
        
        Args:
            group_docs: List of documents in this case group
            group_id: Group identifier
            
        Returns:
            Case processing result
        """
        logger.info(f"Processing case group {group_id} with {len(group_docs)} documents")
        
        if not group_docs:
            return {'group_id': group_id, 'case_id': None, 'status': 'empty'}
        
        # Get the first document as reference
        first_doc = group_docs[0]
        first_entities = first_doc['entities']
        
        # Check if any document is already linked to a case
        existing_case_id = None
        for doc in group_docs:
            if doc.get('case_id'):
                existing_case_id = doc['case_id']
                break
        
        if existing_case_id:
            # Merge into existing case
            case_id = existing_case_id
            logger.info(f"Merging {len(group_docs)} documents into existing case {case_id}")
            
            for doc in group_docs:
                if doc.get('document_id') and not doc.get('case_id'):
                    # Merge entities
                    self.case_linker.merge_entities_into_case(
                        case_id,
                        doc['entities'],
                        doc['file_path']
                    )
                    
                    # Link document
                    confidence = self._calculate_confidence(doc, group_docs)
                    self.case_linker.link_document_to_case(
                        doc['document_id'],
                        case_id,
                        confidence
                    )
        else:
            # Create new case
            logger.info(f"Creating new case from {len(group_docs)} documents")
            case_id = self.case_linker.create_new_case(first_entities)
            
            # Merge remaining documents
            for doc in group_docs[1:]:
                if doc.get('document_id'):
                    self.case_linker.merge_entities_into_case(
                        case_id,
                        doc['entities'],
                        doc['file_path']
                    )
                    
                    confidence = self._calculate_confidence(doc, group_docs)
                    self.case_linker.link_document_to_case(
                        doc['document_id'],
                        case_id,
                        confidence
                    )
        
        return {
            'group_id': group_id,
            'case_id': case_id,
            'documents_count': len(group_docs),
            'status': 'success'
        }
    
    def _calculate_confidence(self, doc: Dict, group_docs: List[Dict]) -> float:
        """
        Calculate confidence score for document-case linking
        
        Args:
            doc: Document being linked
            group_docs: All documents in the case group
            
        Returns:
            Confidence score (0-1)
        """
        # Base confidence on similarity to other documents in group
        if len(group_docs) == 1:
            return 0.9  # Single document, high confidence
        
        # Calculate average similarity to other documents
        doc_embedding = np.array(doc['embedding'])
        similarities = []
        
        for other_doc in group_docs:
            if other_doc['file_path'] != doc['file_path'] and other_doc.get('embedding'):
                other_embedding = np.array(other_doc['embedding'])
                similarity = cosine_similarity([doc_embedding], [other_embedding])[0][0]
                similarities.append(similarity)
        
        if similarities:
            avg_similarity = np.mean(similarities)
            # Confidence is based on average similarity
            confidence = min(0.95, max(0.7, avg_similarity))
        else:
            confidence = 0.8
        
        return float(confidence)
    
    def _clear_existing_documents(self, file_paths: List[str]):
        """Clear existing documents from database for force reprocess"""
        with self.db.connection.cursor() as cursor:
            # Get file hashes
            file_hashes = []
            for file_path in file_paths:
                try:
                    file_hash = self.doc_processor.calculate_file_hash(file_path)
                    file_hashes.append(file_hash)
                except Exception as e:
                    logger.warning(f"Could not calculate hash for {file_path}: {str(e)}")
            
            if file_hashes:
                # Delete documents with matching hashes
                placeholders = ','.join(['%s'] * len(file_hashes))
                cursor.execute(f"""
                    DELETE FROM documents 
                    WHERE file_hash IN ({placeholders})
                """, file_hashes)
                self.db.connection.commit()
                logger.info(f"Cleared {cursor.rowcount} existing documents")
    
    def _count_entities(self, entities: Dict) -> int:
        """Count total entities extracted"""
        count = 0
        count += len(entities.get('parties', []))
        count += len(entities.get('charges', []))
        count += len(entities.get('judgments', []))
        count += len(entities.get('evidence', []))
        count += len(entities.get('statements', []))
        return count
    
    def process_directory(self, directory_path: str, 
                         file_pattern: str = "*.txt",
                         force_reprocess: bool = False) -> Dict[str, Any]:
        """
        Process all documents in a directory
        
        Args:
            directory_path: Path to directory
            file_pattern: File pattern to match (default: *.txt)
            force_reprocess: If True, reprocess documents even if they already exist
            
        Returns:
            Processing results
        """
        # Find all matching files
        pattern = os.path.join(directory_path, file_pattern)
        file_paths = glob.glob(pattern)
        
        if not file_paths:
            logger.warning(f"No files found matching {pattern}")
            return {'total_documents': 0, 'processed_documents': 0}
        
        logger.info(f"Found {len(file_paths)} files in {directory_path}")
        
        return self.process_batch(file_paths, force_reprocess=force_reprocess)


def main():
    """Main function for batch processing"""
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Parse command line arguments
    force_reprocess = '--force' in sys.argv or '-f' in sys.argv
    if force_reprocess:
        sys.argv = [arg for arg in sys.argv if arg not in ['--force', '-f']]
    
    # Get directory from command line or use default
    if len(sys.argv) > 1:
        directory = sys.argv[1]
    else:
        directory = CONFIG['storage']['path']
    
    # Initialize database and processor
    with DatabaseManagerV2(**CONFIG['database']) as db:
        processor = BatchProcessor(db)
        
        # Process directory
        results = processor.process_directory(directory, force_reprocess=force_reprocess)
        
        print(f"\n{'='*60}")
        print("BATCH PROCESSING RESULTS")
        print(f"{'='*60}")
        print(f"Total documents: {results['total_documents']}")
        print(f"Processed documents: {results['processed_documents']}")
        print(f"Case groups created: {results['case_groups']}")
        print(f"Cases created/updated: {results['cases_created']}")
        print(f"\n{'='*60}")


if __name__ == '__main__':
    main()

