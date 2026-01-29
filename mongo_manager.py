"""
MongoDB Manager for Legal Case Management System
Handles MongoDB connection and CRUD operations for all collections
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from bson import ObjectId
from bson.errors import InvalidId

from config import CONFIG

logger = logging.getLogger(__name__)


class MongoManager:
    """MongoDB manager with context manager support"""
    
    def __init__(self, host: str = None, port: int = None, database: str = None,
                 username: str = None, password: str = None):
        """
        Initialize MongoDB manager
        
        Args:
            host: MongoDB host (default from config)
            port: MongoDB port (default from config)
            database: Database name (default from config)
            username: Username (optional)
            password: Password (optional)
        """
        mongo_config = CONFIG.get('mongodb', {})
        self.config = {
            'host': host or mongo_config.get('host', 'localhost'),
            'port': port or mongo_config.get('port', 27017),
            'database': database or mongo_config.get('database', 'legal_cases_v2'),
            'username': username or mongo_config.get('username'),
            'password': password or mongo_config.get('password')
        }
        self.client: Optional[MongoClient] = None
        self.db: Optional[Database] = None
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
        return False
    
    def connect(self):
        """Establish MongoDB connection"""
        try:
            connection_string = f"mongodb://{self.config['host']}:{self.config['port']}"
            if self.config.get('username') and self.config.get('password'):
                connection_string = f"mongodb://{self.config['username']}:{self.config['password']}@{self.config['host']}:{self.config['port']}"
            
            self.client = MongoClient(connection_string)
            self.db = self.client[self.config['database']]
            
            # Test connection
            self.client.admin.command('ping')
            logger.info(f"Connected to MongoDB: {self.config['database']}")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            raise
    
    def close(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")
    
    # ========================================================================
    # DOCUMENT OPERATIONS
    # ========================================================================
    
    def create_document(self, document_data: Dict[str, Any]) -> str:
        """
        Create a new document record
        
        Args:
            document_data: Document data dictionary
            
        Returns:
            document_id (ObjectId as string)
        """
        collection = self.db['documents']
        
        # Add timestamps
        document_data['created_at'] = datetime.now()
        if 'processed_at' not in document_data:
            document_data['processed_at'] = None
        
        # Ensure case_id is None initially
        if 'case_id' not in document_data:
            document_data['case_id'] = None
        
        result = collection.insert_one(document_data)
        logger.info(f"Created document: {result.inserted_id}")
        return str(result.inserted_id)
    
    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID"""
        collection = self.db['documents']
        try:
            doc = collection.find_one({'_id': ObjectId(document_id)})
            if doc:
                doc['_id'] = str(doc['_id'])
                if 'case_id' in doc and doc['case_id']:
                    doc['case_id'] = str(doc['case_id'])
            return doc
        except InvalidId:
            return None
    
    def get_documents_by_case(self, case_id: str) -> List[Dict[str, Any]]:
        """Get all documents for a case"""
        collection = self.db['documents']
        try:
            docs = list(collection.find({'case_id': ObjectId(case_id)}))
            for doc in docs:
                doc['_id'] = str(doc['_id'])
                if 'case_id' in doc:
                    doc['case_id'] = str(doc['case_id'])
            return docs
        except InvalidId:
            return []
    
    def update_document(self, document_id: str, document_data: Dict[str, Any]):
        """
        Update an existing document with new data.
        Preserves created_at timestamp, updates all other fields.
        """
        collection = self.db['documents']
        try:
            # Remove created_at from update data to preserve original timestamp
            update_data = {k: v for k, v in document_data.items() if k != 'created_at'}
            update_data['updated_at'] = datetime.now()
            
            collection.update_one(
                {'_id': ObjectId(document_id)},
                {'$set': update_data}
            )
            logger.info(f"Updated document: {document_id}")
        except InvalidId as e:
            logger.error(f"Invalid ID in update_document: {str(e)}")
            raise
    
    def update_document_case(self, document_id: str, case_id: str, confidence_score: float = None):
        """Link document to case"""
        collection = self.db['documents']
        try:
            update_data = {
                'case_id': ObjectId(case_id),
                'processed_at': datetime.now(),
                'processing_status': 'processed'
            }
            if confidence_score is not None:
                update_data['confidence_score'] = confidence_score
            
            collection.update_one(
                {'_id': ObjectId(document_id)},
                {'$set': update_data}
            )
            logger.info(f"Linked document {document_id} to case {case_id}")
        except InvalidId as e:
            logger.error(f"Invalid ID in update_document_case: {str(e)}")
    
    def check_duplicate_document(self, file_hash: str) -> Optional[str]:
        """Check if document with same hash already exists"""
        collection = self.db['documents']
        doc = collection.find_one({'file_hash': file_hash})
        if doc:
            return str(doc['_id'])
        return None
    
    def find_similar_documents(self, embedding: List[float], threshold: float = 0.8, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Find similar documents using vector similarity
        
        Note: MongoDB doesn't have built-in vector search in basic setup.
        This is a placeholder - in production, use MongoDB Atlas Vector Search
        or store embeddings and compute similarity in application layer.
        
        Args:
            embedding: Document embedding vector
            threshold: Similarity threshold
            limit: Maximum results
            
        Returns:
            List of similar documents with similarity scores
        """
        # TODO: Implement vector similarity search
        # For now, return empty list - will be implemented with proper vector search
        logger.warning("Vector similarity search not yet implemented for MongoDB")
        return []
    
    # ========================================================================
    # CHAT SESSION & MESSAGE OPERATIONS
    # ========================================================================

    def create_chat_session(self, user_id: Optional[str] = None, title: Optional[str] = None) -> str:
        """
        Create a new chat session.
        
        Args:
            user_id: Optional identifier for the user (can be None for now)
            title: Optional initial title; if not provided, frontend can infer from first message
        
        Returns:
            session_id (ObjectId as string)
        """
        collection = self.db['chat_sessions']
        now = datetime.now()
        session_data: Dict[str, Any] = {
            'user_id': user_id,
            'title': title or 'New Chat',
            'created_at': now,
            'updated_at': now
        }
        result = collection.insert_one(session_data)
        logger.info(f"Created chat session: {result.inserted_id}")
        return str(result.inserted_id)

    def get_chat_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a single chat session by ID."""
        collection = self.db['chat_sessions']
        try:
            session = collection.find_one({'_id': ObjectId(session_id)})
            if session:
                session['_id'] = str(session['_id'])
            return session
        except InvalidId:
            return None

    def list_chat_sessions(self, user_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        List chat sessions, optionally filtered by user_id.
        
        Most recently updated sessions are returned first.
        """
        collection = self.db['chat_sessions']
        query: Dict[str, Any] = {}
        if user_id is not None:
            query['user_id'] = user_id

        cursor = collection.find(query).sort('updated_at', -1).limit(limit)
        sessions: List[Dict[str, Any]] = []
        for session in cursor:
            session['_id'] = str(session['_id'])
            sessions.append(session)
        return sessions

    def delete_chat_session(self, session_id: str):
        """
        Delete a chat session and all of its messages.
        """
        sessions_col = self.db['chat_sessions']
        messages_col = self.db['chat_messages']
        try:
            oid = ObjectId(session_id)
        except InvalidId:
            logger.error(f"Invalid session_id in delete_chat_session: {session_id}")
            return

        sessions_col.delete_one({'_id': oid})
        messages_col.delete_many({'session_id': oid})
        logger.info(f"Deleted chat session {session_id} and its messages")

    def append_chat_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Append a single chat message to a session.
        
        Args:
            session_id: ID of the chat session
            role: 'user' or 'assistant'
            content: Message text
            metadata: Optional structured metadata (e.g., related case/document ids)
        
        Returns:
            message_id (ObjectId as string)
        """
        if role not in ('user', 'assistant'):
            raise ValueError(f"Invalid chat message role: {role}")

        messages_col = self.db['chat_messages']
        sessions_col = self.db['chat_sessions']

        try:
            session_oid = ObjectId(session_id)
        except InvalidId:
            logger.error(f"Invalid session_id in append_chat_message: {session_id}")
            raise

        message_doc: Dict[str, Any] = {
            'session_id': session_oid,
            'role': role,
            'content': content,
            'timestamp': datetime.now(),
        }
        if metadata:
            message_doc['metadata'] = metadata

        result = messages_col.insert_one(message_doc)
        # Update session's updated_at
        sessions_col.update_one(
            {'_id': session_oid},
            {'$set': {'updated_at': datetime.now()}}
        )
        logger.info(f"Appended {role} message to session {session_id}: {result.inserted_id}")
        return str(result.inserted_id)

    def get_session_messages(self, session_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        """
        Get messages for a chat session ordered by timestamp ascending.
        """
        messages_col = self.db['chat_messages']
        try:
            session_oid = ObjectId(session_id)
        except InvalidId:
            logger.error(f"Invalid session_id in get_session_messages: {session_id}")
            return []

        cursor = (
            messages_col
            .find({'session_id': session_oid})
            .sort('timestamp', 1)
            .limit(limit)
        )
        messages: List[Dict[str, Any]] = []
        for msg in cursor:
            msg['_id'] = str(msg['_id'])
            msg['session_id'] = str(msg['session_id'])
            messages.append(msg)
        return messages
    
    # ========================================================================
    # CASE OPERATIONS
    # ========================================================================
    
    def create_case(self, case_data: Dict[str, Any]) -> str:
        """
        Create a new case record
        
        Args:
            case_data: Case data dictionary
            
        Returns:
            case_id (ObjectId as string)
        """
        collection = self.db['cases']
        
        # Add timestamps
        case_data['created_at'] = datetime.now()
        case_data['updated_at'] = datetime.now()
        
        result = collection.insert_one(case_data)
        logger.info(f"Created case: {result.inserted_id}")
        return str(result.inserted_id)
    
    def get_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        """Get case by ID"""
        collection = self.db['cases']
        try:
            case = collection.find_one({'_id': ObjectId(case_id)})
            if case:
                case['_id'] = str(case['_id'])
            return case
        except InvalidId:
            return None
    
    def update_case(self, case_id: str, updates: Dict[str, Any]):
        """Update case with new data"""
        collection = self.db['cases']
        try:
            updates['updated_at'] = datetime.now()
            collection.update_one(
                {'_id': ObjectId(case_id)},
                {'$set': updates}
            )
            logger.info(f"Updated case: {case_id}")
        except InvalidId as e:
            logger.error(f"Invalid case_id in update_case: {str(e)}")
    
    def find_case_by_reference(self, reference_type: str, reference_value: str) -> Optional[str]:
        """
        Find case by reference number
        
        Args:
            reference_type: 'court', 'prosecution', 'police', 'internal'
            reference_value: Reference number value
            
        Returns:
            case_id or None
        """
        collection = self.db['cases']
        
        # Search in case_numbers field
        query = {
            f'case_numbers.{reference_type}': reference_value
        }
        case = collection.find_one(query)
        
        if case:
            return str(case['_id'])
        
        # Also search in variations array
        query_variations = {
            'case_numbers.variations': reference_value
        }
        case = collection.find_one(query_variations)
        
        if case:
            return str(case['_id'])
        
        return None
    
    # ========================================================================
    # PARTY OPERATIONS
    # ========================================================================
    
    def get_or_create_party(self, party_data: Dict[str, Any]) -> str:
        """
        Get existing party or create new one based on deduplication signature
        
        Args:
            party_data: Party data dictionary
            
        Returns:
            party_id (ObjectId as string)
        """
        from arabic_normalizer import ArabicNormalizer
        
        collection = self.db['parties']
        
        # Generate signature
        signature = ArabicNormalizer.generate_party_signature(party_data)
        if not signature:
            # If no signature can be generated, create new party
            party_data['created_at'] = datetime.now()
            result = collection.insert_one(party_data)
            return str(result.inserted_id)
        
        # Check if party with same signature exists
        existing = collection.find_one({'deduplication_signature': signature})
        if existing:
            # Update existing party with any new information (prefer Arabic)
            update_data = {}
            for key, value in party_data.items():
                if key not in ['deduplication_signature', '_id', 'created_at']:
                    # Prefer Arabic over English
                    if key.endswith('_ar') and value:
                        update_data[key] = value
                    elif key.endswith('_en') and value:
                        # Only update English if Arabic not present
                        ar_key = key.replace('_en', '_ar')
                        if not existing.get(ar_key):
                            update_data[key] = value
                    elif value and not existing.get(key):
                        update_data[key] = value
            
            if update_data:
                update_data['updated_at'] = datetime.now()
                collection.update_one(
                    {'_id': existing['_id']},
                    {'$set': update_data}
                )
            
            return str(existing['_id'])
        
        # Create new party
        party_data['deduplication_signature'] = signature
        party_data['created_at'] = datetime.now()
        result = collection.insert_one(party_data)
        return str(result.inserted_id)
    
    def link_party_to_case(self, case_id: str, party_id: str, role_type: str, 
                          source_document_id: str = None, confidence: float = None):
        """Link party to case with specific role"""
        collection = self.db['case_parties']
        
        link_data = {
            'case_id': ObjectId(case_id),
            'party_id': ObjectId(party_id),
            'role_type': role_type,
            'assigned_date': datetime.now(),
            'status': 'active'
        }
        
        if source_document_id:
            link_data['source_document_id'] = ObjectId(source_document_id)
        if confidence is not None:
            link_data['confidence'] = confidence
        
        # Use upsert to avoid duplicates
        collection.update_one(
            {'case_id': ObjectId(case_id), 'party_id': ObjectId(party_id), 'role_type': role_type},
            {'$set': link_data},
            upsert=True
        )
        logger.info(f"Linked party {party_id} to case {case_id} as {role_type}")
    
    # ========================================================================
    # CHARGE OPERATIONS
    # ========================================================================
    
    def get_or_create_charge(self, charge_data: Dict[str, Any]) -> str:
        """Get existing charge or create new one"""
        from arabic_normalizer import ArabicNormalizer
        
        collection = self.db['charges']
        
        signature = ArabicNormalizer.generate_charge_signature(charge_data)
        if not signature:
            charge_data['created_at'] = datetime.now()
            result = collection.insert_one(charge_data)
            return str(result.inserted_id)
        
        existing = collection.find_one({'deduplication_signature': signature})
        if existing:
            # Update with new info (prefer Arabic)
            update_data = {}
            for key, value in charge_data.items():
                if key not in ['deduplication_signature', '_id', 'created_at']:
                    if key.endswith('_ar') and value:
                        update_data[key] = value
                    elif key.endswith('_en') and value:
                        ar_key = key.replace('_en', '_ar')
                        if not existing.get(ar_key):
                            update_data[key] = value
                    elif value and not existing.get(key):
                        update_data[key] = value
            
            if update_data:
                update_data['updated_at'] = datetime.now()
                collection.update_one(
                    {'_id': existing['_id']},
                    {'$set': update_data}
                )
            
            return str(existing['_id'])
        
        charge_data['deduplication_signature'] = signature
        charge_data['created_at'] = datetime.now()
        result = collection.insert_one(charge_data)
        return str(result.inserted_id)
    
    def link_charge_to_case(self, case_id: str, charge_id: str, 
                           source_document_id: str = None, confidence: float = None):
        """Link charge to case"""
        collection = self.db['case_charges']
        
        link_data = {
            'case_id': ObjectId(case_id),
            'charge_id': ObjectId(charge_id),
            'assigned_date': datetime.now()
        }
        
        if source_document_id:
            link_data['source_document_id'] = ObjectId(source_document_id)
        if confidence is not None:
            link_data['confidence'] = confidence
        
        collection.update_one(
            {'case_id': ObjectId(case_id), 'charge_id': ObjectId(charge_id)},
            {'$set': link_data},
            upsert=True
        )
    
    # ========================================================================
    # EVIDENCE OPERATIONS
    # ========================================================================
    
    def get_or_create_evidence(self, evidence_data: Dict[str, Any]) -> str:
        """Get existing evidence or create new one"""
        from arabic_normalizer import ArabicNormalizer
        
        collection = self.db['evidence_items']
        
        signature = ArabicNormalizer.generate_evidence_signature(evidence_data)
        if not signature:
            evidence_data['created_at'] = datetime.now()
            result = collection.insert_one(evidence_data)
            return str(result.inserted_id)
        
        existing = collection.find_one({'deduplication_signature': signature})
        if existing:
            # Update with new info (prefer Arabic)
            update_data = {}
            for key, value in evidence_data.items():
                if key not in ['deduplication_signature', '_id', 'created_at']:
                    if key.endswith('_ar') and value:
                        update_data[key] = value
                    elif key.endswith('_en') and value:
                        ar_key = key.replace('_en', '_ar')
                        if not existing.get(ar_key):
                            update_data[key] = value
                    elif value and not existing.get(key):
                        update_data[key] = value
            
            if update_data:
                update_data['updated_at'] = datetime.now()
                collection.update_one(
                    {'_id': existing['_id']},
                    {'$set': update_data}
                )
            
            return str(existing['_id'])
        
        evidence_data['deduplication_signature'] = signature
        evidence_data['created_at'] = datetime.now()
        result = collection.insert_one(evidence_data)
        return str(result.inserted_id)
    
    def link_evidence_to_case(self, case_id: str, evidence_id: str,
                              source_document_id: str = None, confidence: float = None):
        """Link evidence to case"""
        collection = self.db['case_evidence']
        
        link_data = {
            'case_id': ObjectId(case_id),
            'evidence_id': ObjectId(evidence_id),
            'assigned_date': datetime.now()
        }
        
        if source_document_id:
            link_data['source_document_id'] = ObjectId(source_document_id)
        if confidence is not None:
            link_data['confidence'] = confidence
        
        collection.update_one(
            {'case_id': ObjectId(case_id), 'evidence_id': ObjectId(evidence_id)},
            {'$set': link_data},
            upsert=True
        )
    
    # ========================================================================
    # CASE-DOCUMENT LINKING
    # ========================================================================
    
    def link_document_to_case(self, case_id: str, document_id: str, 
                              confidence_score: float, linking_params: Dict[str, Any] = None):
        """
        Link document to case with confidence and linking parameters
        
        Args:
            case_id: Case ID
            document_id: Document ID
            confidence_score: Confidence score (0-1)
            linking_params: Dictionary of parameters used for linking
        """
        collection = self.db['case_documents']
        
        link_data = {
            'case_id': ObjectId(case_id),
            'document_id': ObjectId(document_id),
            'confidence': confidence_score,
            'linked_at': datetime.now()
        }
        
        if linking_params:
            link_data['linking_params'] = linking_params
        
        collection.update_one(
            {'case_id': ObjectId(case_id), 'document_id': ObjectId(document_id)},
            {'$set': link_data},
            upsert=True
        )
        
        # Also update document's case_id
        self.update_document_case(document_id, case_id, confidence_score)
        logger.info(f"Linked document {document_id} to case {case_id} with confidence {confidence_score}")

