"""
Document Orchestrator - Coordinates document processing pipeline
Integrates AI parser with database operations
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from database_manager import DatabaseManager
from ai_document_parser import AIDocumentProcessor, AIDocumentExtractor
from config import CONFIG

logging.basicConfig(level=getattr(logging, CONFIG['app']['log_level']))
logger = logging.getLogger(__name__)


class DocumentProcessor:
    """
    Main document processor that orchestrates the entire pipeline
    """
    
    def __init__(self, db_config: Dict[str, str], storage_path: str, 
                 anthropic_api_key: str):
        """
        Initialize document processor
        
        Args:
            db_config: Database configuration dictionary
            storage_path: Path for storing document files
            anthropic_api_key: Anthropic API key for Claude
        """
        self.db_config = db_config
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize AI processor
        self.ai_processor = AIDocumentProcessor(
            anthropic_api_key=anthropic_api_key,
            db_config=db_config,
            storage_path=str(storage_path)
        )
        
        logger.info("Document Processor initialized")
    
    def process_document(self, file_path: str) -> Dict[str, Any]:
        """
        Process a single document through the complete pipeline
        
        Args:
            file_path: Path to document file
            
        Returns:
            Processing result dictionary
        """
        logger.info(f"Processing document: {file_path}")
        
        try:
            # Use AI processor to handle everything
            result = self.ai_processor.process_document(file_path)
            
            if result['success']:
                logger.info(f"Successfully processed document: {result['document_id']}")
            else:
                logger.error(f"Failed to process document: {result.get('error')}")
            
            return result
        
        except Exception as e:
            logger.error(f"Error processing document: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def process_batch(self, file_paths: List[str]) -> List[Dict[str, Any]]:
        """
        Process multiple documents
        
        Args:
            file_paths: List of file paths to process
            
        Returns:
            List of processing results
        """
        results = []
        for file_path in file_paths:
            result = self.process_document(file_path)
            results.append({
                'file_path': file_path,
                **result
            })
        return results


class LegalCaseQueryAgent:
    """
    AI-powered query agent for natural language to SQL conversion
    """
    
    def __init__(self, db_config: Dict[str, str], anthropic_api_key: str):
        """
        Initialize query agent
        
        Args:
            db_config: Database configuration
            anthropic_api_key: Anthropic API key
        """
        self.db_config = db_config
        self.extractor = AIDocumentExtractor(api_key=anthropic_api_key)
        logger.info("Legal Case Query Agent initialized")
    
    def get_case_summary(self, case_number: str) -> Dict[str, Any]:
        """
        Get comprehensive case summary
        
        Args:
            case_number: Court case number
            
        Returns:
            Case summary dictionary
        """
        with DatabaseManager(**self.db_config) as db:
            # Get case info
            case = db.get_case_by_number(case_number)
            if not case:
                return {'error': f'Case not found: {case_number}'}
            
            case_id = case['case_id']
            
            # Get parties
            parties_sql = """
                SELECT p.*, cp.role_type, cp.role_subtype
                FROM parties p
                JOIN case_parties cp ON p.party_id = cp.party_id
                WHERE cp.case_id = %s
            """
            parties = db.execute_query(parties_sql, [case_id])
            
            # Get charges
            charges_sql = "SELECT * FROM charges WHERE case_id = %s ORDER BY charge_number"
            charges = db.execute_query(charges_sql, [case_id])
            
            # Get timeline
            timeline_sql = """
                SELECT * FROM case_events 
                WHERE case_id = %s 
                ORDER BY event_date ASC
            """
            timeline = db.execute_query(timeline_sql, [case_id])
            
            # Get judgment
            judgment_sql = """
                SELECT j.*, 
                    (SELECT COUNT(*) FROM sentences WHERE judgment_id = j.judgment_id) as sentence_count
                FROM judgments j
                WHERE j.case_id = %s AND j.is_final = TRUE
                ORDER BY j.judgment_date DESC
                LIMIT 1
            """
            judgment = db.execute_query(judgment_sql, [case_id])
            
            return {
                'case_info': case,
                'parties': parties,
                'charges': charges,
                'timeline': timeline,
                'judgment': judgment[0] if judgment else None
            }
    
    def get_case_summary_by_id(self, case_id: int) -> Dict[str, Any]:
        """Get case summary by case ID"""
        with DatabaseManager(**self.db_config) as db:
            case = db.execute_query("SELECT * FROM cases WHERE case_id = %s", [case_id])
            if not case:
                return {'error': f'Case not found: {case_id}'}
            
            case_number = case[0]['court_case_number']
            return self.get_case_summary(case_number)
    
    def query(self, natural_language_query: str) -> List[Dict[str, Any]]:
        """
        Convert natural language query to SQL and execute
        
        Args:
            natural_language_query: Natural language question
            
        Returns:
            Query results
        """
        # This would use Claude to convert NL to SQL
        # For now, return a placeholder
        logger.info(f"Processing query: {natural_language_query}")
        
        # TODO: Implement NL to SQL conversion using Claude
        # For now, return empty results
        return []


# Convenience functions for easy import
def create_processor() -> DocumentProcessor:
    """Create document processor with default config"""
    return DocumentProcessor(
        db_config=CONFIG['database'],
        storage_path=CONFIG['storage']['path'],
        anthropic_api_key=CONFIG['anthropic']['api_key']
    )


def create_query_agent() -> LegalCaseQueryAgent:
    """Create query agent with default config"""
    return LegalCaseQueryAgent(
        db_config=CONFIG['database'],
        anthropic_api_key=CONFIG['anthropic']['api_key']
    )

