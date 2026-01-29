"""
Test and Validation Script for Vector-Based Legal Case Management System v2
Tests: 21 files → 1 case, entity extraction, performance, JSONB structure
"""

import os
import glob
import logging
import time
from typing import Dict, Any, List
from datetime import datetime

from .batch_processor import BatchProcessor
from .db_manager_v2 import DatabaseManagerV2
from .query_agent_v2 import query
from config import CONFIG

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SystemValidator:
    """Validate the v2 system functionality"""
    
    def __init__(self):
        """Initialize validator"""
        self.db_config = CONFIG['database']
        logger.info("Initialized SystemValidator")
    
    def test_database_connection(self) -> bool:
        """Test database connection"""
        try:
            with DatabaseManagerV2(**self.db_config) as db:
                logger.info("✓ Database connection successful")
                return True
        except Exception as e:
            logger.error(f"✗ Database connection failed: {str(e)}")
            return False
    
    def test_schema_exists(self) -> bool:
        """Test that schema tables exist"""
        try:
            with DatabaseManagerV2(**self.db_config) as db:
                with db.connection.cursor() as cursor:
                    # Check tables exist
                    cursor.execute("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name IN ('cases', 'documents', 'processing_log')
                    """)
                    tables = [row[0] for row in cursor.fetchall()]
                    
                    if len(tables) == 3:
                        logger.info("✓ All schema tables exist")
                        return True
                    else:
                        logger.error(f"✗ Missing tables. Found: {tables}")
                        return False
        except Exception as e:
            logger.error(f"✗ Schema check failed: {str(e)}")
            return False
    
    def test_faiss_available(self) -> bool:
        """Test that FAISS is available"""
        try:
            import faiss
            logger.info("✓ FAISS library available")
            return True
        except ImportError:
            logger.error("✗ FAISS library not installed. Install with: pip install faiss-cpu")
            return False
    
    def test_batch_processing(self, directory: str = None) -> Dict[str, Any]:
        """
        Test batch processing of documents
        
        Args:
            directory: Directory containing documents (default: storage/)
            
        Returns:
            Test results
        """
        if directory is None:
            directory = CONFIG['storage']['path']
        
        logger.info(f"Testing batch processing from: {directory}")
        
        start_time = time.time()
        
        try:
            with DatabaseManagerV2(**self.db_config) as db:
                processor = BatchProcessor(db)
                
                # Process directory
                results = processor.process_directory(directory)
                
                processing_time = time.time() - start_time
                
                # Validate results
                validation = {
                    'success': True,
                    'total_documents': results['total_documents'],
                    'processed_documents': results['processed_documents'],
                    'case_groups': results['case_groups'],
                    'cases_created': results['cases_created'],
                    'processing_time_seconds': processing_time,
                    'avg_time_per_doc': processing_time / results['processed_documents'] if results['processed_documents'] > 0 else 0
                }
                
                # Check if we got 1 case from multiple documents
                if results['case_groups'] == 1 and results['processed_documents'] > 1:
                    validation['single_case_from_multiple_docs'] = True
                    logger.info("✓ Successfully created 1 case from multiple documents")
                else:
                    validation['single_case_from_multiple_docs'] = False
                    logger.warning(f"⚠ Expected 1 case group, got {results['case_groups']}")
                
                return validation
        
        except Exception as e:
            logger.error(f"✗ Batch processing failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def test_entity_extraction(self, case_id: int) -> Dict[str, Any]:
        """
        Test entity extraction quality for a case
        
        Args:
            case_id: Case ID to validate
            
        Returns:
            Validation results
        """
        logger.info(f"Testing entity extraction for case {case_id}")
        
        try:
            with DatabaseManagerV2(**self.db_config) as db:
                case = db.get_case(case_id)
                if not case:
                    return {'success': False, 'error': f'Case {case_id} not found'}
                
                validation = {
                    'success': True,
                    'case_id': case_id,
                    'has_case_numbers': bool(case.get('case_numbers')),
                    'has_parties': len(case.get('parties', [])) > 0,
                    'has_charges': len(case.get('charges', [])) > 0,
                    'has_dates': bool(case.get('key_dates')),
                    'has_timeline': len(case.get('timeline', [])) > 0,
                    'parties_count': len(case.get('parties', [])),
                    'charges_count': len(case.get('charges', [])),
                    'timeline_events': len(case.get('timeline', []))
                }
                
                # Check entity IDs
                parties_with_ids = [p for p in case.get('parties', []) if p.get('party_entity_id')]
                charges_with_ids = [c for c in case.get('charges', []) if c.get('charge_entity_id')]
                
                validation['parties_have_entity_ids'] = len(parties_with_ids) == len(case.get('parties', []))
                validation['charges_have_entity_ids'] = len(charges_with_ids) == len(case.get('charges', []))
                
                logger.info(f"✓ Case {case_id} has {validation['parties_count']} parties, {validation['charges_count']} charges")
                
                return validation
        
        except Exception as e:
            logger.error(f"✗ Entity extraction validation failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def test_jsonb_structure(self, case_id: int) -> Dict[str, Any]:
        """
        Test JSONB structure validity
        
        Args:
            case_id: Case ID to validate
            
        Returns:
            Validation results
        """
        logger.info(f"Testing JSONB structure for case {case_id}")
        
        try:
            with DatabaseManagerV2(**self.db_config) as db:
                case = db.get_case(case_id)
                if not case:
                    return {'success': False, 'error': f'Case {case_id} not found'}
                
                validation = {
                    'success': True,
                    'case_id': case_id,
                    'jsonb_fields_valid': True,
                    'errors': []
                }
                
                # Validate each JSONB field
                jsonb_fields = [
                    'case_numbers', 'parties', 'key_dates', 'locations',
                    'charges', 'judgments', 'financial', 'evidence',
                    'case_status', 'legal_references', 'timeline'
                ]
                
                for field in jsonb_fields:
                    value = case.get(field)
                    if value is not None:
                        try:
                            # Try to serialize/deserialize to ensure it's valid JSON
                            json.dumps(value)
                        except (TypeError, ValueError) as e:
                            validation['jsonb_fields_valid'] = False
                            validation['errors'].append(f"{field}: {str(e)}")
                
                if validation['jsonb_fields_valid']:
                    logger.info("✓ All JSONB fields are valid")
                else:
                    logger.error(f"✗ JSONB validation errors: {validation['errors']}")
                
                return validation
        
        except Exception as e:
            logger.error(f"✗ JSONB structure validation failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def test_query_agent(self, test_queries: List[str]) -> Dict[str, Any]:
        """
        Test query agent functionality
        
        Args:
            test_queries: List of test queries to run
            
        Returns:
            Test results
        """
        logger.info("Testing query agent...")
        
        results = {
            'success': True,
            'queries_tested': len(test_queries),
            'queries_passed': 0,
            'queries_failed': 0,
            'results': []
        }
        
        for query_text in test_queries:
            try:
                logger.info(f"Testing query: {query_text}")
                response = query(query_text)
                
                if response and 'error' not in response.lower():
                    results['queries_passed'] += 1
                    results['results'].append({
                        'query': query_text,
                        'status': 'success',
                        'response_length': len(response)
                    })
                else:
                    results['queries_failed'] += 1
                    results['results'].append({
                        'query': query_text,
                        'status': 'failed',
                        'response': response
                    })
            
            except Exception as e:
                results['queries_failed'] += 1
                results['results'].append({
                    'query': query_text,
                    'status': 'error',
                    'error': str(e)
                })
        
        if results['queries_passed'] == results['queries_tested']:
            logger.info(f"✓ All {results['queries_tested']} queries passed")
        else:
            logger.warning(f"⚠ {results['queries_failed']} queries failed")
        
        return results
    
    def run_full_validation(self, documents_directory: str = None) -> Dict[str, Any]:
        """
        Run full system validation
        
        Args:
            documents_directory: Directory with documents to test (default: storage/)
            
        Returns:
            Complete validation results
        """
        print("\n" + "="*60)
        print("SYSTEM VALIDATION - Vector-Based Architecture v2")
        print("="*60 + "\n")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'tests': {}
        }
        
        # Test 1: Database connection
        print("Test 1: Database Connection")
        results['tests']['database_connection'] = self.test_database_connection()
        print()
        
        # Test 2: Schema exists
        print("Test 2: Schema Validation")
        results['tests']['schema_exists'] = self.test_schema_exists()
        print()
        
        # Test 3: FAISS availability
        print("Test 3: FAISS Library")
        results['tests']['faiss_available'] = self.test_faiss_available()
        print()
        
        # Test 4: Batch processing
        if documents_directory or os.path.exists(CONFIG['storage']['path']):
            print("Test 4: Batch Processing")
            batch_results = self.test_batch_processing(documents_directory)
            results['tests']['batch_processing'] = batch_results
            print()
            
            # Test 5: Entity extraction (if we have cases)
            if batch_results.get('success') and batch_results.get('cases_created', 0) > 0:
                print("Test 5: Entity Extraction")
                with DatabaseManagerV2(**self.db_config) as db:
                    # Get first case
                    cases = db.search_cases({}, limit=1)
                    if cases:
                        case_id = cases[0]['case_id']
                        entity_results = self.test_entity_extraction(case_id)
                        results['tests']['entity_extraction'] = entity_results
                        
                        # Test 6: JSONB structure
                        print("Test 6: JSONB Structure")
                        jsonb_results = self.test_jsonb_structure(case_id)
                        results['tests']['jsonb_structure'] = jsonb_results
                print()
        
        # Test 7: Query agent (basic test)
        print("Test 7: Query Agent")
        test_queries = [
            "How many cases are in the database?",
            "Find case 2552/2025"
        ]
        query_results = self.test_query_agent(test_queries)
        results['tests']['query_agent'] = query_results
        print()
        
        # Summary
        print("="*60)
        print("VALIDATION SUMMARY")
        print("="*60)
        
        passed = sum(1 for test, result in results['tests'].items() 
                    if isinstance(result, dict) and result.get('success', False) or 
                    (isinstance(result, bool) and result))
        total = len(results['tests'])
        
        print(f"Tests passed: {passed}/{total}")
        print("="*60 + "\n")
        
        results['summary'] = {
            'passed': passed,
            'total': total,
            'success': passed == total
        }
        
        return results


def main():
    """Main validation function"""
    import sys
    
    validator = SystemValidator()
    
    # Get directory from command line or use default
    documents_dir = None
    if len(sys.argv) > 1:
        documents_dir = sys.argv[1]
    
    # Run validation
    results = validator.run_full_validation(documents_dir)
    
    # Save results
    import json
    with open('validation_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print("Validation results saved to: validation_results.json")


if __name__ == '__main__':
    main()

