"""
Document Processor for Vector-Based Legal Case Management System
Handles text extraction, embedding generation, and comprehensive entity extraction
"""

import os
import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import anthropic
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel
import pdfplumber
from docx import Document

from config import CONFIG
from document_type_schemas import get_document_type_schema, get_required_fields, get_optional_fields

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Process legal documents: extract text, generate embeddings, extract entities"""
    
    def __init__(self):
        """Initialize document processor"""
        # Initialize Arabic BERT model for embeddings
        model_name = CONFIG['embeddings']['model']
        device = CONFIG['embeddings']['device']
        
        logger.info(f"Loading Arabic BERT model: {model_name} (this may take a moment on first run)...")
        
        try:
            # Load tokenizer and model
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.bert_model = AutoModel.from_pretrained(model_name)
            
            # Set device
            if device == 'cuda' and torch.cuda.is_available():
                self.device = torch.device('cuda')
                self.bert_model = self.bert_model.to(self.device)
                logger.info("Using CUDA for embeddings")
            else:
                self.device = torch.device('cpu')
                logger.info("Using CPU for embeddings")
            
            self.bert_model.eval()  # Set to evaluation mode
            # Get actual model dimension (BERT-base is 768)
            self.embedding_dimension = self.bert_model.config.hidden_size
            # Use config dimension for storage (can be different if needed)
            self.storage_dimension = CONFIG['embeddings']['dimension']
            
            logger.info(f"Loaded Arabic BERT model: {model_name} (model dim: {self.embedding_dimension}, storage dim: {self.storage_dimension})")
            
        except Exception as e:
            logger.error(f"Failed to load Arabic BERT model: {str(e)}")
            logger.error("Make sure transformers and torch are installed: pip install transformers torch")
            raise
        
        # Initialize Anthropic client for entity extraction
        self.anthropic_client = anthropic.Anthropic(
            api_key=CONFIG['anthropic']['api_key']
        )
        logger.info("Initialized Anthropic client for entity extraction")
    
    def extract_text(self, file_path: str) -> str:
        """
        Extract text from document file
        
        Args:
            file_path: Path to document file
            
        Returns:
            Extracted text
        """
        file_path_obj = Path(file_path)
        extension = file_path_obj.suffix.lower()
        
        try:
            if extension == '.txt':
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            
            elif extension == '.pdf':
                text = ""
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                return text
            
            elif extension in ['.docx', '.doc']:
                doc = Document(file_path)
                return "\n".join([para.text for para in doc.paragraphs])
            
            else:
                raise ValueError(f"Unsupported file type: {extension}")
        
        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {str(e)}")
            raise
    
    def generate_embedding(self, text: str, max_length: int = 512) -> List[float]:
        """
        Generate vector embedding for document text using Arabic BERT
        
        Args:
            text: Document text
            max_length: Maximum sequence length for BERT (default: 512)
            
        Returns:
            Embedding vector (list of floats)
        """
        try:
            # Tokenize text
            inputs = self.tokenizer(
                text,
                return_tensors='pt',
                truncation=True,
                max_length=max_length,
                padding='max_length'
            )
            
            # Move inputs to device
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # Generate embeddings
            with torch.no_grad():
                outputs = self.bert_model(**inputs)
                # Use mean pooling of all token embeddings (CLS token + all tokens)
                # Shape: (batch_size, seq_len, hidden_size)
                embeddings = outputs.last_hidden_state
                # Mean pooling: average over sequence length dimension
                embedding = embeddings.mean(dim=1).squeeze().cpu().numpy()
            
            # Adjust dimension if needed for storage
            if len(embedding) != self.storage_dimension:
                if len(embedding) > self.storage_dimension:
                    # Truncate if larger (use first N dimensions)
                    embedding = embedding[:self.storage_dimension]
                else:
                    # Pad with zeros if smaller (shouldn't happen with BERT-base)
                    padding = np.zeros(self.storage_dimension - len(embedding))
                    embedding = np.concatenate([embedding, padding])
            
            return embedding.tolist()
            
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            # Fallback: return zero vector if error
            return [0.0] * self.storage_dimension
    
    def extract_entities(self, text: str, document_type: str = None) -> Dict[str, Any]:
        """
        Extract entities from document using Claude AI with type-specific extraction
        
        Args:
            text: Document text
            document_type: Type of document (required for type-specific extraction)
            
        Returns:
            Dictionary with extracted entities (type-specific fields only)
        """
        if not document_type:
            logger.warning("No document_type provided, using generic extraction")
            return self._extract_entities_generic(text)
        
        # Get schema for document type
        schema = get_document_type_schema(document_type)
        if not schema:
            logger.warning(f"Unknown document type: {document_type}, using generic extraction")
            return self._extract_entities_generic(text)
        
        # Build type-specific extraction prompt
        required_fields = schema.get('required_fields', [])
        optional_fields = schema.get('optional_fields', [])
        ar_name = schema.get('ar_name', document_type)
        en_name = schema.get('en_name', document_type)
        
        return self._extract_entities_type_specific(text, document_type, ar_name, en_name, required_fields, optional_fields)
    
    def _extract_entities_type_specific(self, text: str, doc_type: str, ar_name: str, en_name: str,
                                       required_fields: List[str], optional_fields: List[str]) -> Dict[str, Any]:
        """
        Extract entities using type-specific schema
        
        Args:
            text: Document text
            doc_type: Document type identifier
            ar_name: Arabic name of document type
            en_name: English name of document type
            required_fields: List of required fields to extract
            optional_fields: List of optional fields to extract
            
        Returns:
            Dictionary with extracted entities
        """
        # Build field list for prompt
        all_fields = set(required_fields + optional_fields)
        
        system_prompt = f"""You are an expert at extracting structured information from Arabic legal documents for Qatar's judicial system.

DOCUMENT TYPE: {ar_name} ({en_name})

CRITICAL: PRIORITIZE ARABIC DATA - Extract primarily Arabic text. Only use English translations if Arabic is not available in the document.
- Always extract Arabic names (name_ar) - these are the primary source. Only use name_en if Arabic name is not found.
- Always extract Arabic descriptions (description_ar) for charges, evidence, judgments, etc. Only use description_en if Arabic is not available.
- For locations (court, police_station, incident_location, etc.), extract Arabic text primarily.
- For all text fields (occupation, address, law_name, etc.), prefer Arabic over English.
- Only extract English fields when Arabic is completely absent from the document.

IMPORTANT: Extract ONLY the fields relevant to this document type. Do NOT extract fields that are not relevant.
REQUIRED FIELDS: {', '.join(required_fields)}
OPTIONAL FIELDS: {', '.join(optional_fields) if optional_fields else 'None'}

CRITICAL: Do NOT omit details that are present in the document.
- Extract ALL fields listed above IF they appear in the text.
- If a field is not found, return null (or [] for list fields) — do not guess.

Extract only distinct, meaningful entities. Do NOT extract duplicate or near-duplicate entries.

IMPORTANT LIMITS (do not exceed these reasonable limits):
- Parties: Maximum 100 distinct parties per document
- Charges: Maximum 50 distinct charges per document  
- Evidence: Maximum 100 distinct evidence items per document
- Judgments: Maximum 20 judgments per document
- Court Sessions: Maximum 50 sessions per document
- Statements: Maximum 100 statements per document

If you encounter more entities than these limits, extract only the most important/relevant ones.

Return a JSON object with ONLY the relevant fields for this document type. Use null if a field is not found or not applicable.

The JSON structure should follow this format (include only fields from the required/optional lists above):
- case_numbers: object with court, prosecution, police, internal, variations
- parties: array of objects with name_ar, name_en, personal_id, role, etc.
- dates: object with incident, report_filed, investigation, etc.
- locations: object with court, police_station, etc.
- charges: array of objects with description_ar, article_number, etc.
- evidence: array of objects with type, description_ar, etc.
- judgments: array of objects with judgment_date, verdict, sentences, etc.
- court_sessions: array of objects with session_date, judge_name, etc.
- statements: array of objects with statement_type, statement_date, etc.
- lab_results: array of objects with test_type, result, subject_party, etc.
- detention: array of objects with order_date, detention_type, duration_days, etc.
- notifications: array of objects with notification_date, recipient_party, etc.
- correspondence: array of objects with correspondence_date, from_organization, etc.
- waivers: array of objects with waiver_date, complainant_party, etc.
- legal_references: array of objects with article, law_name_ar, etc.
- document_metadata: object with document_type, document_number, etc.
- case_status: object with current_status, case_type, summary_ar, etc.

CRITICAL: Return ONLY valid JSON. Do not include any explanatory text before or after the JSON."""

        user_prompt = f"""Extract all entities from this legal document:

{text[:50000]}"""  # Limit to 50k chars for API

        try:
            message = self.anthropic_client.messages.create(
                model=CONFIG['anthropic']['model'],
                max_tokens=4096,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ]
            )
            
            # Extract JSON from response
            response_text = message.content[0].text
            
            # Try to parse JSON
            # Sometimes the response might have markdown code blocks
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            
            entities = json.loads(response_text)
            
            # Validate and limit entities to prevent excessive extraction
            entities = self._validate_and_limit_entities(entities)
            
            # Add document metadata
            entities['document_metadata'] = {
                'document_type': doc_type,
                'document_type_ar': ar_name,
                'document_type_en': en_name
            }
            
            logger.info(f"Extracted entities from {doc_type} document")
            return entities
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from entity extraction: {str(e)}")
            logger.error(f"Response was: {response_text[:500]}")
            return {}
        
        except Exception as e:
            logger.error(f"Error extracting entities: {str(e)}")
            return {}
    
    def _extract_entities_generic(self, text: str) -> Dict[str, Any]:
        """
        Generic entity extraction (fallback when document type unknown)
        
        Args:
            text: Document text
            
        Returns:
            Dictionary with extracted entities
        """
        system_prompt = """You are an expert at extracting structured information from Arabic legal documents for Qatar's judicial system.

CRITICAL: PRIORITIZE ARABIC DATA - Extract primarily Arabic text. Only use English translations if Arabic is not available in the document.
- Always extract Arabic names (name_ar) - these are the primary source. Only use name_en if Arabic name is not found.
- Always extract Arabic descriptions (description_ar) for charges, evidence, judgments, etc. Only use description_en if Arabic is not available.
- For locations (court, police_station, incident_location, etc.), extract Arabic text primarily.
- For all text fields (occupation, address, law_name, etc.), prefer Arabic over English.
- For case_status summary_ar, always extract Arabic summary. summary_en is optional.
- Only extract English fields when Arabic is completely absent from the document.

Extract important legal information and return it as valid JSON. Be thorough but reasonable - extract only distinct, meaningful entities. 
Do NOT extract duplicate or near-duplicate entries. For example, if the same party name appears multiple times, extract it only once.

IMPORTANT LIMITS (do not exceed these reasonable limits):
- Parties: Maximum 100 distinct parties per document
- Charges: Maximum 50 distinct charges per document  
- Evidence: Maximum 100 distinct evidence items per document
- Judgments: Maximum 20 judgments per document
- Court Sessions: Maximum 50 sessions per document
- Statements: Maximum 100 statements per document

If you encounter more entities than these limits, extract only the most important/relevant ones.

Return a JSON object with the following structure (include ALL fields, use null if not found):

[Full JSON schema would go here - same as in type-specific extraction]

CRITICAL: Return ONLY valid JSON. Do not include any explanatory text before or after the JSON."""

        user_prompt = f"""Extract all entities from this legal document:

{text[:50000]}"""  # Limit to 50k chars for API

        try:
            message = self.anthropic_client.messages.create(
                model=CONFIG['anthropic']['model'],
                max_tokens=4096,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ]
            )
            
            # Extract JSON from response
            response_text = message.content[0].text
            
            # Try to parse JSON
            # Sometimes the response might have markdown code blocks
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            
            entities = json.loads(response_text)
            
            # Validate and limit entities to prevent excessive extraction
            entities = self._validate_and_limit_entities(entities)
            
            logger.info(f"Extracted entities from document (generic)")
            return entities
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from entity extraction: {str(e)}")
            logger.error(f"Response was: {response_text[:500]}")
            # Return empty structure
            return {}
        
        except Exception as e:
            logger.error(f"Error extracting entities: {str(e)}")
            return {}
    
    def _validate_and_limit_entities(self, entities: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and limit entities to prevent excessive extraction
        
        Args:
            entities: Extracted entities dictionary
            
        Returns:
            Validated entities dictionary with limits applied
        """
        limits = CONFIG['processing']['entity_limits']
        
        # Limit parties
        if 'parties' in entities and isinstance(entities['parties'], list):
            original_count = len(entities['parties'])
            if original_count > limits['max_parties_per_document']:
                logger.warning(
                    f"Document extracted {original_count} parties, limiting to {limits['max_parties_per_document']}. "
                    f"This may indicate a parsing error."
                )
                entities['parties'] = entities['parties'][:limits['max_parties_per_document']]
        
        # Limit charges
        if 'charges' in entities and isinstance(entities['charges'], list):
            original_count = len(entities['charges'])
            if original_count > limits['max_charges_per_document']:
                logger.warning(
                    f"Document extracted {original_count} charges, limiting to {limits['max_charges_per_document']}. "
                    f"This may indicate a parsing error."
                )
                entities['charges'] = entities['charges'][:limits['max_charges_per_document']]
        
        # Limit evidence
        if 'evidence' in entities and isinstance(entities['evidence'], list):
            original_count = len(entities['evidence'])
            if original_count > limits['max_evidence_per_document']:
                logger.warning(
                    f"Document extracted {original_count} evidence items, limiting to {limits['max_evidence_per_document']}. "
                    f"This may indicate a parsing error."
                )
                entities['evidence'] = entities['evidence'][:limits['max_evidence_per_document']]
        
        # Limit judgments
        if 'judgments' in entities and isinstance(entities['judgments'], list):
            original_count = len(entities['judgments'])
            if original_count > limits['max_judgments_per_document']:
                logger.warning(
                    f"Document extracted {original_count} judgments, limiting to {limits['max_judgments_per_document']}. "
                    f"This may indicate a parsing error."
                )
                entities['judgments'] = entities['judgments'][:limits['max_judgments_per_document']]
        
        # Limit court sessions
        if 'court_sessions' in entities and isinstance(entities['court_sessions'], list):
            original_count = len(entities['court_sessions'])
            if original_count > limits['max_court_sessions_per_document']:
                logger.warning(
                    f"Document extracted {original_count} court sessions, limiting to {limits['max_court_sessions_per_document']}. "
                    f"This may indicate a parsing error."
                )
                entities['court_sessions'] = entities['court_sessions'][:limits['max_court_sessions_per_document']]
        
        # Limit statements
        if 'statements' in entities and isinstance(entities['statements'], list):
            original_count = len(entities['statements'])
            if original_count > limits['max_statements_per_document']:
                logger.warning(
                    f"Document extracted {original_count} statements, limiting to {limits['max_statements_per_document']}. "
                    f"This may indicate a parsing error."
                )
                entities['statements'] = entities['statements'][:limits['max_statements_per_document']]

        # Additional list limits (as schemas have been expanded)
        list_limits = {
            'witnesses': 'max_witnesses_per_document',
            'decisions': 'max_decisions_per_document',
            'lab_results': 'max_lab_results_per_document',
            'detention': 'max_detention_events_per_document',
            'notifications': 'max_notifications_per_document',
            'correspondence': 'max_correspondence_per_document',
            'waivers': 'max_waivers_per_document',
            'sentences': 'max_sentences_per_document',
            # Common “medical context” fields that may appear in multiple doc types
            'injuries': 'max_injuries_per_document',
            'hospital_transfers': 'max_hospital_transfers_per_document',
        }
        for field, limit_key in list_limits.items():
            if field in entities and isinstance(entities[field], list):
                original_count = len(entities[field])
                max_allowed = limits.get(limit_key)
                if isinstance(max_allowed, int) and original_count > max_allowed:
                    logger.warning(
                        f"Document extracted {original_count} {field}, limiting to {max_allowed}. "
                        f"This may indicate a parsing error."
                    )
                    entities[field] = entities[field][:max_allowed]
        
        return entities
    
    def _get_empty_entity_structure(self) -> Dict[str, Any]:
        """Return empty entity structure"""
        return {
            "case_numbers": {},
            "parties": [],
            "dates": {},
            "locations": {},
            "charges": [],
            "court_sessions": [],
            "judgments": [],
            "financial": {"fines": [], "damages": [], "bail": None},
            "evidence": [],
            "lab_results": [],
            "statements": [],
            "detention": [],
            "notifications": [],
            "correspondence": [],
            "waivers": [],
            "legal_references": [],
            "document_metadata": {},
            "case_status": {}
        }
    
    def calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA-256 hash of file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def process_document(self, file_path: str, document_type: str = None) -> Dict[str, Any]:
        """
        Process a single document (extracts text first)
        
        Args:
            file_path: Path to document file
            document_type: Document type (optional, will be detected if not provided)
        """
        text = self.extract_text(file_path)
        return self.process_document_with_text(file_path, text, document_type)
    
    def process_document_with_text(self, file_path: str, text: str, document_type: str = None) -> Dict[str, Any]:
        """
        Process a single document with pre-extracted text: generate embedding, extract entities
        
        Args:
            file_path: Path to document file
            text: Pre-extracted text
            document_type: Document type (optional, will be detected if not provided)
            
        Returns:
            Dictionary with processing results:
            - text: Extracted text
            - embedding: Vector embedding
            - entities: Extracted entities (type-specific)
            - file_hash: File hash
            - file_size: File size in bytes
            - document_type: Detected/classified document type
        """
        logger.info(f"Processing document: {file_path}")
        
        start_time = datetime.now()
        
        # Detect document type if not provided
        if not document_type:
            from document_type_classifier import DocumentTypeClassifier
            classifier = DocumentTypeClassifier()
            document_type, _ = classifier.classify(text)
            logger.info(f"Detected document type: {document_type}")
        
        # Generate embedding using Arabic BERT
        logger.debug("Generating embedding...")
        embedding = self.generate_embedding(text)
        logger.debug(f"Generated embedding (dimension: {len(embedding)})")
        
        # Extract entities (type-specific)
        logger.debug(f"Extracting entities for type: {document_type}")
        entities = self.extract_entities(text, document_type)
        # Handle None values from LLM (null in JSON becomes None in Python)
        parties_count = len(entities.get('parties') or [])
        charges_count = len(entities.get('charges') or [])
        logger.debug(f"Extracted {parties_count} parties, {charges_count} charges")
        
        # Calculate file hash
        file_hash = self.calculate_file_hash(file_path)
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        logger.info(f"Processed document in {processing_time:.2f}ms: {file_path}")
        
        return {
            'text': text,
            'embedding': embedding,
            'entities': entities,
            'file_hash': file_hash,
            'file_size': file_size,
            'document_type': document_type,
            'processing_time_ms': int(processing_time)
        }

