"""
Database Manager for Legal Case Management System
Handles all database operations with connection pooling and transaction management
PostgreSQL version using psycopg2
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Database manager with context manager support for connection handling"""
    
    def __init__(self, host: str, user: str, password: str, database: str, 
                 charset: str = 'utf8', port: int = 5432):
        """
        Initialize database manager
        
        Args:
            host: Database host
            user: Database user
            password: Database password
            database: Database name
            charset: Character set (default: utf8 for PostgreSQL)
            port: Database port (default: 5432 for PostgreSQL)
        """
        self.config = {
            'host': host,
            'user': user,
            'password': password,
            'database': database,
            'port': port
        }
        self.connection = None
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
        return False
    
    def connect(self):
        """Establish database connection"""
        try:
            self.connection = psycopg2.connect(**self.config)
            # Set encoding to UTF-8 for Arabic support
            self.connection.set_client_encoding('UTF8')
            logger.info(f"Connected to database: {self.config['database']}")
        except Exception as e:
            logger.error(f"Failed to connect to database: {str(e)}")
            raise
    
    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")
    
    def commit(self):
        """Commit transaction"""
        if self.connection:
            self.connection.commit()
    
    def rollback(self):
        """Rollback transaction"""
        if self.connection:
            self.connection.rollback()
    
    # ========================================================================
    # CASE OPERATIONS
    # ========================================================================
    
    def get_or_create_case(self, case_refs: Dict[str, Optional[str]]) -> int:
        """
        Get existing case or create new one based on reference numbers
        
        Args:
            case_refs: Dictionary with court_case_number, prosecution_case_number, etc.
            
        Returns:
            case_id
        """
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            # Try to find existing case by any reference number
            conditions = []
            params = []
            
            if case_refs.get('court_case_number'):
                conditions.append("court_case_number = %s")
                params.append(case_refs['court_case_number'])
            
            if case_refs.get('prosecution_case_number'):
                conditions.append("prosecution_case_number = %s")
                params.append(case_refs['prosecution_case_number'])
            
            if case_refs.get('police_report_number'):
                conditions.append("police_report_number = %s")
                params.append(case_refs['police_report_number'])
            
            if conditions:
                sql = f"SELECT case_id FROM cases WHERE {' OR '.join(conditions)} LIMIT 1"
                cursor.execute(sql, params)
                result = cursor.fetchone()
                
                if result:
                    logger.info(f"Found existing case: {result['case_id']}")
                    return result['case_id']
            
            # Create new case
            case_data = {
                'court_case_number': case_refs.get('court_case_number', ''),
                'prosecution_case_number': case_refs.get('prosecution_case_number'),
                'police_report_number': case_refs.get('police_report_number'),
                'internal_report_number': case_refs.get('internal_report_number'),
                'case_type': case_refs.get('case_type', 'criminal'),
                'current_status': case_refs.get('current_status', 'open'),
                'status_date': case_refs.get('status_date', datetime.now())
            }
            
            fields = [k for k, v in case_data.items() if v is not None]
            values = [case_data[k] for k in fields]
            placeholders = ', '.join(['%s'] * len(fields))
            
            sql = f"""
                INSERT INTO cases ({', '.join(fields)})
                VALUES ({placeholders})
            """
            cursor.execute(sql, values)
            self.connection.commit()
            # PostgreSQL uses RETURNING or cursor.fetchone() after INSERT
            cursor.execute("SELECT lastval()")
            case_id = cursor.fetchone()[0]
            logger.info(f"Created new case: {case_id}")
            return case_id
    
    def update_case(self, case_id: int, updates: Dict[str, Any]):
        """Update case fields"""
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            fields = [k for k, v in updates.items() if v is not None]
            if not fields:
                return
            
            values = [updates[k] for k in fields]
            set_clause = ', '.join([f"{f} = %s" for f in fields])
            
            sql = f"UPDATE cases SET {set_clause} WHERE case_id = %s"
            cursor.execute(sql, values + [case_id])
            self.connection.commit()
            logger.info(f"Updated case {case_id}")
    
    def get_case_by_number(self, case_number: str) -> Optional[Dict[str, Any]]:
        """Get case by court case number"""
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            sql = "SELECT * FROM cases WHERE court_case_number = %s"
            cursor.execute(sql, [case_number])
            return cursor.fetchone()
    
    # ========================================================================
    # PARTY OPERATIONS
    # ========================================================================
    
    def get_or_create_party(self, party_data: Dict[str, Any]) -> int:
        """
        Get existing party or create new one
        
        Args:
            party_data: Dictionary with party information
            
        Returns:
            party_id
        """
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            # Try to find existing party
            conditions = []
            params = []
            
            if party_data.get('personal_id'):
                conditions.append("personal_id = %s")
                params.append(party_data['personal_id'])
            
            if party_data.get('full_name_ar'):
                conditions.append("full_name_ar = %s")
                params.append(party_data['full_name_ar'])
            
            if conditions:
                sql = f"SELECT party_id FROM parties WHERE {' OR '.join(conditions)} LIMIT 1"
                cursor.execute(sql, params)
                result = cursor.fetchone()
                
                if result:
                    logger.info(f"Found existing party: {result['party_id']}")
                    return result['party_id']
            
            # Create new party
            fields = [k for k, v in party_data.items() if v is not None]
            values = [party_data[k] for k in fields]
            placeholders = ', '.join(['%s'] * len(fields))
            
            sql = f"""
                INSERT INTO parties ({', '.join(fields)})
                VALUES ({placeholders})
                RETURNING party_id
            """
            cursor.execute(sql, values)
            party_id = cursor.fetchone()['party_id']
            self.connection.commit()
            logger.info(f"Created new party: {party_id}")
            return party_id
    
    def link_party_to_case(self, case_id: int, party_id: int, role_type: str, 
                          role_data: Optional[Dict[str, Any]] = None):
        """Link party to case with specific role"""
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            link_data = {
                'case_id': case_id,
                'party_id': party_id,
                'role_type': role_type,
                'assigned_date': datetime.now(),
                'status': 'active'
            }
            
            if role_data:
                link_data.update(role_data)
            
            fields = list(link_data.keys())
            values = list(link_data.values())
            placeholders = ', '.join(['%s'] * len(fields))
            
            # PostgreSQL uses ON CONFLICT instead of ON DUPLICATE KEY UPDATE
            sql = f"""
                INSERT INTO case_parties ({', '.join(fields)})
                VALUES ({placeholders})
                ON CONFLICT (case_id, party_id, role_type) 
                DO UPDATE SET
                    status = EXCLUDED.status,
                    assigned_date = EXCLUDED.assigned_date
            """
            cursor.execute(sql, values)
            self.connection.commit()
            logger.info(f"Linked party {party_id} to case {case_id} as {role_type}")
    
    # ========================================================================
    # DOCUMENT OPERATIONS
    # ========================================================================
    
    def insert_document(self, document_data: Dict[str, Any]) -> int:
        """Insert document record"""
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            fields = [k for k, v in document_data.items() if v is not None]
            values = [document_data[k] for k in fields]
            placeholders = ', '.join(['%s'] * len(fields))
            
            sql = f"""
                INSERT INTO documents ({', '.join(fields)})
                VALUES ({placeholders})
                RETURNING document_id
            """
            cursor.execute(sql, values)
            document_id = cursor.fetchone()['document_id']
            self.connection.commit()
            logger.info(f"Inserted document: {document_id}")
            return document_id
    
    # ========================================================================
    # COURT SESSION OPERATIONS
    # ========================================================================
    
    def insert_court_session(self, case_id: int, session_data: Dict[str, Any]) -> int:
        """Insert court session record"""
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            session_data['case_id'] = case_id
            fields = [k for k, v in session_data.items() if v is not None]
            values = [session_data[k] for k in fields]
            placeholders = ', '.join(['%s'] * len(fields))
            
            sql = f"""
                INSERT INTO court_sessions ({', '.join(fields)})
                VALUES ({placeholders})
                RETURNING session_id
            """
            cursor.execute(sql, values)
            session_id = cursor.fetchone()['session_id']
            self.connection.commit()
            logger.info(f"Inserted court session: {session_id}")
            return session_id
    
    # ========================================================================
    # CHARGE OPERATIONS
    # ========================================================================
    
    def insert_charge(self, case_id: int, charge_data: Dict[str, Any]) -> int:
        """Insert charge record"""
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            charge_data['case_id'] = case_id
            fields = [k for k, v in charge_data.items() if v is not None]
            values = [charge_data[k] for k in fields]
            placeholders = ', '.join(['%s'] * len(fields))
            
            sql = f"""
                INSERT INTO charges ({', '.join(fields)})
                VALUES ({placeholders})
                RETURNING charge_id
            """
            cursor.execute(sql, values)
            charge_id = cursor.fetchone()['charge_id']
            self.connection.commit()
            logger.info(f"Inserted charge: {charge_id}")
            return charge_id
    
    # ========================================================================
    # STATEMENT OPERATIONS
    # ========================================================================
    
    def insert_statement(self, case_id: int, party_id: int, statement_data: Dict[str, Any]) -> int:
        """Insert statement record"""
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            statement_data['case_id'] = case_id
            statement_data['party_id'] = party_id
            fields = [k for k, v in statement_data.items() if v is not None]
            values = [statement_data[k] for k in fields]
            placeholders = ', '.join(['%s'] * len(fields))
            
            sql = f"""
                INSERT INTO statements ({', '.join(fields)})
                VALUES ({placeholders})
                RETURNING statement_id
            """
            cursor.execute(sql, values)
            statement_id = cursor.fetchone()['statement_id']
            self.connection.commit()
            logger.info(f"Inserted statement: {statement_id}")
            return statement_id
    
    # ========================================================================
    # CASE EVENT OPERATIONS
    # ========================================================================
    
    def add_case_event(self, case_id: int, event_data: Dict[str, Any]) -> int:
        """Add event to case timeline"""
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            event_data['case_id'] = case_id
            fields = [k for k, v in event_data.items() if v is not None]
            values = [event_data[k] for k in fields]
            placeholders = ', '.join(['%s'] * len(fields))
            
            sql = f"""
                INSERT INTO case_events ({', '.join(fields)})
                VALUES ({placeholders})
                RETURNING event_id
            """
            cursor.execute(sql, values)
            event_id = cursor.fetchone()['event_id']
            self.connection.commit()
            logger.info(f"Added case event: {event_id}")
            return event_id
    
    # ========================================================================
    # QUERY OPERATIONS
    # ========================================================================
    
    def execute_query(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """Execute SELECT query and return results"""
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(sql, params or [])
            return cursor.fetchall()
    
    def execute_update(self, sql: str, params: Optional[List[Any]] = None) -> int:
        """Execute UPDATE/INSERT/DELETE query"""
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(sql, params or [])
            self.connection.commit()
            return cursor.rowcount

