"""
Database Manager v2 for Vector-Based Legal Case Management System
Handles JSONB operations, vector similarity queries, and case/document CRUD
"""

import psycopg2
from psycopg2.extras import RealDictCursor, Json
from psycopg2.extensions import register_adapter, AsIs
from contextlib import contextmanager
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import logging
import json

# Register JSON adapter for psycopg2
register_adapter(dict, Json)
register_adapter(list, Json)

logger = logging.getLogger(__name__)


class DatabaseManagerV2:
    """Database manager with context manager support for v2 architecture"""
    
    def __init__(self, host: str, user: str, password: str, database: str, port: int = 5432, **kwargs):
        """
        Initialize database manager
        
        Args:
            host: Database host
            user: Database user
            password: Database password
            database: Database name
            port: Database port (default: 5432)
            **kwargs: Additional arguments (like charset) - ignored for PostgreSQL
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
    # SCHEMA / FEATURE DETECTION
    # ========================================================================

    def table_exists(self, table_name: str) -> bool:
        """Return True if a table exists in the current schema."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = %s
                )
                """,
                (table_name,)
            )
            return bool(cursor.fetchone()[0])

    # ========================================================================
    # NORMALIZED ENTITY OPERATIONS (Medium-term scaling)
    # ========================================================================

    @staticmethod
    def _normalize_text_for_signature(value: Optional[str]) -> str:
        if not value:
            return ""
        return " ".join(str(value).strip().lower().split())

    def _party_signature(self, party: Dict[str, Any]) -> Optional[str]:
        personal_id = (party.get("personal_id") or "").strip()
        if personal_id:
            return f"id:{personal_id}"
        name_ar = self._normalize_text_for_signature(party.get("name_ar"))
        if name_ar:
            return f"ar:{name_ar}"
        name_en = self._normalize_text_for_signature(party.get("name_en"))
        if name_en:
            return f"en:{name_en}"
        return None

    def get_or_create_party_entity(self, party: Dict[str, Any]) -> Optional[int]:
        """
        Upsert a party entity into normalized `parties` table (if present).
        Returns party_id, or None if table doesn't exist or signature can't be built.
        """
        if not self.table_exists("parties"):
            return None

        signature = self._party_signature(party)
        if not signature:
            return None

        payload = {
            "signature": signature,
            "personal_id": (party.get("personal_id") or None),
            "name_ar": (party.get("name_ar") or None),
            "name_en": (party.get("name_en") or None),
            "nationality": (party.get("nationality") or None),
            "age": (party.get("age") or None),
            "gender": (party.get("gender") or None),
            "occupation": (party.get("occupation") or None),
            "phone": (party.get("phone") or None),
            "address": (party.get("address") or None),
        }

        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO parties
                    (signature, personal_id, name_ar, name_en, nationality, age, gender, occupation, phone, address)
                VALUES
                    (%(signature)s, %(personal_id)s, %(name_ar)s, %(name_en)s, %(nationality)s, %(age)s, %(gender)s,
                     %(occupation)s, %(phone)s, %(address)s)
                ON CONFLICT (signature) DO UPDATE SET
                    personal_id = COALESCE(parties.personal_id, EXCLUDED.personal_id),
                    name_ar     = COALESCE(parties.name_ar, EXCLUDED.name_ar),
                    name_en     = COALESCE(parties.name_en, EXCLUDED.name_en),
                    nationality = COALESCE(parties.nationality, EXCLUDED.nationality),
                    age         = COALESCE(parties.age, EXCLUDED.age),
                    gender      = COALESCE(parties.gender, EXCLUDED.gender),
                    occupation  = COALESCE(parties.occupation, EXCLUDED.occupation),
                    phone       = COALESCE(parties.phone, EXCLUDED.phone),
                    address     = COALESCE(parties.address, EXCLUDED.address),
                    updated_at  = NOW()
                RETURNING party_id
                """,
                payload
            )
            party_id = cursor.fetchone()["party_id"]
            self.connection.commit()
            return int(party_id)

    def link_party_entity_to_case(
        self,
        case_id: int,
        party_id: int,
        role_type: Optional[str] = None,
        source_document_id: Optional[int] = None,
        confidence_score: Optional[float] = None,
    ) -> None:
        """Link a normalized party to a case (if link table exists)."""
        if not self.table_exists("case_parties"):
            return

        # Normalize role
        role = (role_type or "").strip() or None

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO case_parties (case_id, party_id, role_type, source_document_id, confidence_score)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (case_id, party_id, role_type) DO UPDATE SET
                    source_document_id = COALESCE(EXCLUDED.source_document_id, case_parties.source_document_id),
                    confidence_score = COALESCE(EXCLUDED.confidence_score, case_parties.confidence_score)
                """,
                (case_id, party_id, role, source_document_id, confidence_score)
            )
            self.connection.commit()

    def _charge_signature(self, charge: Dict[str, Any]) -> Optional[str]:
        article = (charge.get("article_number") or "").strip()
        if article:
            return f"art:{article}"
        desc_ar = self._normalize_text_for_signature(charge.get("description_ar"))
        if desc_ar:
            return f"ar:{desc_ar}"
        desc_en = self._normalize_text_for_signature(charge.get("description_en"))
        if desc_en:
            return f"en:{desc_en}"
        return None

    def get_or_create_charge_entity(self, charge: Dict[str, Any]) -> Optional[int]:
        if not self.table_exists("charges"):
            return None

        signature = self._charge_signature(charge)
        if not signature:
            return None

        payload = {
            "signature": signature,
            "charge_number": (charge.get("charge_number") or None),
            "article_number": (charge.get("article_number") or None),
            "description_ar": (charge.get("description_ar") or None),
            "description_en": (charge.get("description_en") or None),
            "law_name_ar": (charge.get("law_name_ar") or charge.get("law_name") or None),
            "law_name_en": (charge.get("law_name_en") or None),
            "law_year": (charge.get("law_year") or None),
        }

        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO charges
                    (signature, charge_number, article_number, description_ar, description_en, law_name_ar, law_name_en, law_year)
                VALUES
                    (%(signature)s, %(charge_number)s, %(article_number)s, %(description_ar)s, %(description_en)s,
                     %(law_name_ar)s, %(law_name_en)s, %(law_year)s)
                ON CONFLICT (signature) DO UPDATE SET
                    charge_number  = COALESCE(charges.charge_number, EXCLUDED.charge_number),
                    article_number = COALESCE(charges.article_number, EXCLUDED.article_number),
                    description_ar = COALESCE(charges.description_ar, EXCLUDED.description_ar),
                    description_en = COALESCE(charges.description_en, EXCLUDED.description_en),
                    law_name_ar    = COALESCE(charges.law_name_ar, EXCLUDED.law_name_ar),
                    law_name_en    = COALESCE(charges.law_name_en, EXCLUDED.law_name_en),
                    law_year       = COALESCE(charges.law_year, EXCLUDED.law_year),
                    updated_at     = NOW()
                RETURNING charge_id
                """,
                payload
            )
            charge_id = cursor.fetchone()["charge_id"]
            self.connection.commit()
            return int(charge_id)

    def link_charge_entity_to_case(
        self,
        case_id: int,
        charge_id: int,
        status: Optional[str] = None,
        source_document_id: Optional[int] = None,
    ) -> None:
        if not self.table_exists("case_charges"):
            return

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO case_charges (case_id, charge_id, status, source_document_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (case_id, charge_id) DO UPDATE SET
                    status = COALESCE(EXCLUDED.status, case_charges.status),
                    source_document_id = COALESCE(EXCLUDED.source_document_id, case_charges.source_document_id)
                """,
                (case_id, charge_id, status, source_document_id)
            )
            self.connection.commit()

    def _evidence_signature(self, ev: Dict[str, Any]) -> Optional[str]:
        ev_type = self._normalize_text_for_signature(ev.get("type") or ev.get("evidence_type"))
        desc_ar = self._normalize_text_for_signature(ev.get("description_ar"))
        desc_en = self._normalize_text_for_signature(ev.get("description_en"))
        if ev_type and desc_ar:
            return f"{ev_type}:{desc_ar}"
        if ev_type and desc_en:
            return f"{ev_type}:{desc_en}"
        if desc_ar:
            return f"ar:{desc_ar}"
        if desc_en:
            return f"en:{desc_en}"
        return None

    def get_or_create_evidence_entity(self, ev: Dict[str, Any]) -> Optional[int]:
        if not self.table_exists("evidence_items"):
            return None

        signature = self._evidence_signature(ev)
        if not signature:
            return None

        payload = {
            "signature": signature,
            "evidence_type": (ev.get("type") or ev.get("evidence_type") or None),
            "description_ar": (ev.get("description_ar") or None),
            "description_en": (ev.get("description_en") or None),
            "collected_date": (ev.get("collected_date") or None),
            "location": (ev.get("location") or None),
        }

        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO evidence_items
                    (signature, evidence_type, description_ar, description_en, collected_date, location)
                VALUES
                    (%(signature)s, %(evidence_type)s, %(description_ar)s, %(description_en)s, %(collected_date)s, %(location)s)
                ON CONFLICT (signature) DO UPDATE SET
                    evidence_type  = COALESCE(evidence_items.evidence_type, EXCLUDED.evidence_type),
                    description_ar = COALESCE(evidence_items.description_ar, EXCLUDED.description_ar),
                    description_en = COALESCE(evidence_items.description_en, EXCLUDED.description_en),
                    collected_date = COALESCE(evidence_items.collected_date, EXCLUDED.collected_date),
                    location       = COALESCE(evidence_items.location, EXCLUDED.location),
                    updated_at     = NOW()
                RETURNING evidence_id
                """,
                payload
            )
            evidence_id = cursor.fetchone()["evidence_id"]
            self.connection.commit()
            return int(evidence_id)

    def link_evidence_entity_to_case(
        self,
        case_id: int,
        evidence_id: int,
        source_document_id: Optional[int] = None,
    ) -> None:
        if not self.table_exists("case_evidence"):
            return

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO case_evidence (case_id, evidence_id, source_document_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (case_id, evidence_id) DO UPDATE SET
                    source_document_id = COALESCE(EXCLUDED.source_document_id, case_evidence.source_document_id)
                """,
                (case_id, evidence_id, source_document_id)
            )
            self.connection.commit()
    
    # ========================================================================
    # CASE OPERATIONS
    # ========================================================================
    
    def create_case(self, case_data: Dict[str, Any]) -> int:
        """
        Create a new case record
        
        Args:
            case_data: Dictionary with JSONB columns (case_numbers, parties, etc.)
            
        Returns:
            case_id
        """
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            # Prepare JSONB columns
            jsonb_columns = [
                'case_numbers', 'parties', 'key_dates', 'locations',
                'charges', 'judgments', 'financial', 'evidence',
                'case_status', 'legal_references', 'timeline'
            ]
            
            fields = []
            values = []
            
            for col in jsonb_columns:
                if col in case_data:
                    fields.append(col)
                    values.append(Json(case_data[col]))
            
            if not fields:
                raise ValueError("At least one JSONB field must be provided")
            
            sql = f"""
                INSERT INTO cases ({', '.join(fields)})
                VALUES ({', '.join(['%s'] * len(fields))})
                RETURNING case_id
            """
            cursor.execute(sql, values)
            case_id = cursor.fetchone()['case_id']
            self.connection.commit()
            logger.info(f"Created case: {case_id}")
            return case_id
    
    def get_case(self, case_id: int) -> Optional[Dict[str, Any]]:
        """Get case by ID"""
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT * FROM cases WHERE case_id = %s", (case_id,))
            result = cursor.fetchone()
            if result:
                return dict(result)
            return None
    
    def update_case(self, case_id: int, updates: Dict[str, Any]):
        """
        Update case with new data (merges JSONB fields)
        
        Args:
            case_id: Case ID to update
            updates: Dictionary with fields to update (JSONB fields will be merged)
        """
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            jsonb_columns = [
                'case_numbers', 'parties', 'key_dates', 'locations',
                'charges', 'judgments', 'financial', 'evidence',
                'case_status', 'legal_references', 'timeline'
            ]
            
            set_clauses = []
            values = []
            
            for field, value in updates.items():
                if field in jsonb_columns:
                    # JSONB merge strategy:
                    # - dict/object: merge (||) to preserve existing keys
                    # - list/array: REPLACE (avoids unbounded array concatenation)
                    if isinstance(value, dict):
                        set_clauses.append(f"{field} = COALESCE({field}, '{{}}'::jsonb) || %s::jsonb")
                        values.append(Json(value))
                    else:
                        # Replace for arrays or scalar JSON
                        set_clauses.append(f"{field} = %s::jsonb")
                        values.append(Json(value))
                elif field == 'updated_at':
                    set_clauses.append(f"{field} = NOW()")
                else:
                    set_clauses.append(f"{field} = %s")
                    values.append(value)
            
            if not set_clauses:
                return
            
            values.append(case_id)
            sql = f"""
                UPDATE cases 
                SET {', '.join(set_clauses)}
                WHERE case_id = %s
            """
            cursor.execute(sql, values)
            self.connection.commit()
            logger.info(f"Updated case: {case_id}")
    
    def find_case_by_reference(self, reference_type: str, reference_value: str) -> Optional[int]:
        """
        Find case by reference number using JSONB query
        
        Args:
            reference_type: 'court', 'prosecution', 'police', 'internal'
            reference_value: Reference number value
            
        Returns:
            case_id or None
        """
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            # Search in case_numbers JSONB field
            sql = """
                SELECT case_id FROM cases
                WHERE case_numbers->>%s = %s
                   OR case_numbers->'variations' @> %s::jsonb
                LIMIT 1
            """
            cursor.execute(sql, (
                reference_type,
                reference_value,
                Json([reference_value])
            ))
            result = cursor.fetchone()
            if result:
                return result['case_id']
            return None
    
    def search_cases(self, query: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search cases using JSONB queries
        
        Args:
            query: Dictionary with search criteria
            limit: Maximum results to return
            
        Returns:
            List of case records
        """
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            conditions = []
            params = []
            
            # Build dynamic query based on criteria
            if 'case_status' in query:
                conditions.append("case_status->>'current_status' = %s")
                params.append(query['case_status'])
            
            if 'case_type' in query:
                conditions.append("case_status->>'case_type' = %s")
                params.append(query['case_type'])
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            params.append(limit)
            
            sql = f"""
                SELECT * FROM cases
                WHERE {where_clause}
                ORDER BY updated_at DESC
                LIMIT %s
            """
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
    
    # ========================================================================
    # DOCUMENT OPERATIONS
    # ========================================================================
    
    def create_document(self, document_data: Dict[str, Any]) -> int:
        """
        Create a new document record
        
        Args:
            document_data: Dictionary with document fields including embedding
            
        Returns:
            document_id
        """
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            fields = []
            values = []
            
            # Handle vector embedding - store as JSONB array
            embedding = document_data.pop('document_embedding', None)
            
            for field, value in document_data.items():
                if field in ['document_metadata', 'extracted_entities']:
                    fields.append(field)
                    values.append(Json(value))
                else:
                    fields.append(field)
                    values.append(value)
            
            if embedding is not None:
                fields.append('document_embedding')
                # Store embedding as JSONB array
                values.append(Json(embedding))
            
            sql = f"""
                INSERT INTO documents ({', '.join(fields)})
                VALUES ({', '.join(['%s'] * len(fields))})
                RETURNING document_id
            """
            cursor.execute(sql, values)
            document_id = cursor.fetchone()['document_id']
            self.connection.commit()
            logger.info(f"Created document: {document_id}")
            return document_id
    
    def get_document(self, document_id: int) -> Optional[Dict[str, Any]]:
        """Get document by ID"""
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT * FROM documents WHERE document_id = %s", (document_id,))
            result = cursor.fetchone()
            if result:
                return dict(result)
            return None
    
    def find_similar_documents(self, embedding: List[float], threshold: float = 0.8, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Find similar documents using FAISS similarity search
        
        Args:
            embedding: Document embedding vector (list of floats)
            threshold: Cosine similarity threshold (0-1)
            limit: Maximum results to return
            
        Returns:
            List of similar documents with similarity scores
        """
        try:
            import faiss
            import numpy as np
        except ImportError:
            logger.error("FAISS not installed. Install with: pip install faiss-cpu")
            return []
        
        # Get all documents with embeddings
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT document_id, case_id, file_path, document_metadata, 
                       extracted_entities, confidence_score, document_embedding
                FROM documents
                WHERE document_embedding IS NOT NULL
                  AND processing_status = 'processed'
            """)
            all_docs = cursor.fetchall()
        
        if not all_docs:
            return []
        
        # Build FAISS index
        dimension = len(embedding)
        embeddings_list = []
        doc_ids = []
        
        for doc in all_docs:
            doc_embedding = doc['document_embedding']
            if doc_embedding:
                # Convert JSONB array to numpy array
                if isinstance(doc_embedding, list):
                    embeddings_list.append(doc_embedding)
                    doc_ids.append(doc['document_id'])
        
        if not embeddings_list:
            return []
        
        # Create FAISS index (L2 distance, then convert to cosine similarity)
        embeddings_array = np.array(embeddings_list, dtype=np.float32)
        query_embedding = np.array([embedding], dtype=np.float32)
        
        # Normalize for cosine similarity
        faiss.normalize_L2(embeddings_array)
        faiss.normalize_L2(query_embedding)
        
        # Create index
        index = faiss.IndexFlatIP(dimension)  # Inner product for cosine similarity
        index.add(embeddings_array)
        
        # Search
        k = min(limit * 2, len(embeddings_list))  # Get more results to filter by threshold
        similarities, indices = index.search(query_embedding, k)
        
        # Filter by threshold and build results
        results = []
        query_similarities = similarities[0]
        query_indices = indices[0]
        
        for sim, idx in zip(query_similarities, query_indices):
            if sim >= threshold:
                doc_id = doc_ids[idx]
                # Find original document
                doc = next((d for d in all_docs if d['document_id'] == doc_id), None)
                if doc:
                    result = dict(doc)
                    result['similarity'] = float(sim)
                    results.append(result)
        
        # Sort by similarity (descending) and limit
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:limit]
    
    def get_documents_by_case(self, case_id: int) -> List[Dict[str, Any]]:
        """Get all documents for a case"""
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT document_id, file_path, document_metadata, 
                       extracted_entities, confidence_score, processing_status,
                       created_at, processed_at
                FROM documents
                WHERE case_id = %s
                ORDER BY processed_at DESC, created_at DESC
            """, (case_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def update_document_case(self, document_id: int, case_id: int, confidence_score: float = None):
        """Link document to case"""
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            updates = ['case_id = %s']
            params = [case_id]
            
            if confidence_score is not None:
                updates.append('confidence_score = %s')
                params.append(confidence_score)
            
            updates.append('processed_at = NOW()')
            updates.append("processing_status = 'processed'")
            
            params.append(document_id)
            
            sql = f"""
                UPDATE documents
                SET {', '.join(updates)}
                WHERE document_id = %s
            """
            cursor.execute(sql, params)
            self.connection.commit()
            logger.info(f"Linked document {document_id} to case {case_id}")
    
    def check_duplicate_document(self, file_hash: str) -> Optional[int]:
        """Check if document with same hash already exists"""
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT document_id FROM documents WHERE file_hash = %s LIMIT 1", (file_hash,))
            result = cursor.fetchone()
            if result:
                return result['document_id']
            return None
    
    # ========================================================================
    # PROCESSING LOG OPERATIONS
    # ========================================================================
    
    def log_processing(self, file_path: str, status: str, case_id: int = None, 
                     document_id: int = None, error_message: str = None,
                     processing_time_ms: int = None, entities_extracted: int = None,
                     confidence_score: float = None):
        """Log processing result"""
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                INSERT INTO processing_log 
                (file_path, case_id, document_id, processing_status, error_message,
                 processing_time_ms, entities_extracted, confidence_score)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (file_path, case_id, document_id, status, error_message,
                  processing_time_ms, entities_extracted, confidence_score))
            self.connection.commit()
    
    def get_processing_log(self, file_path: str = None, case_id: int = None, 
                          limit: int = 100) -> List[Dict[str, Any]]:
        """Get processing log entries"""
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            conditions = []
            params = []
            
            if file_path:
                conditions.append("file_path = %s")
                params.append(file_path)
            
            if case_id:
                conditions.append("case_id = %s")
                params.append(case_id)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            params.append(limit)
            
            sql = f"""
                SELECT * FROM processing_log
                WHERE {where_clause}
                ORDER BY processing_time DESC
                LIMIT %s
            """
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]

