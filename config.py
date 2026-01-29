"""
Configuration file for Legal Case Management System (Vector-Based Architecture)
"""

import os
from typing import Dict

# Database Configuration (PostgreSQL v2) - HARDCODED
DATABASE_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres'),
    'database': 'legal_case_v2_1',  # HARDCODED - always use v2 database
    'charset': 'utf8',
    'port': int(os.getenv('DB_PORT', '5432'))
}

# Legacy Database (for migration)
DATABASE_CONFIG_LEGACY = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres'),
    'database': os.getenv('DB_NAME_LEGACY', 'legal_case'),  # Old database
    'charset': 'utf8',
    'port': int(os.getenv('DB_PORT', '5432'))
}

# Anthropic API Configuration
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
ANTHROPIC_MODEL = os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')

# Groq API Configuration (for query agent)
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
GROQ_MODEL = os.getenv('GROQ_MODEL', 'qwen/qwen3-32b')

# Local LLM Configuration (for Qwen3-14B or other local models)
LOCAL_LLM_ENABLED = os.getenv('LOCAL_LLM_ENABLED', 'False').lower() == 'true'
LOCAL_MODEL_PATH = os.getenv('LOCAL_MODEL_PATH', './models/qwen3-14b-instruct')
LOCAL_MODEL_NAME = os.getenv('LOCAL_MODEL_NAME', 'Qwen/Qwen3-14B-Instruct')  # HuggingFace repo ID
LOCAL_LLM_BACKEND = os.getenv('LOCAL_LLM_BACKEND', 'vllm')  # 'vllm' or 'transformers'
LOCAL_LLM_DEVICE = os.getenv('LOCAL_LLM_DEVICE', 'cuda')  # 'cuda' or 'cpu'
LOCAL_LLM_TENSOR_PARALLEL_SIZE = int(os.getenv('LOCAL_LLM_TENSOR_PARALLEL_SIZE', '1'))  # For multi-GPU
LOCAL_LLM_MAX_MODEL_LEN = int(os.getenv('LOCAL_LLM_MAX_MODEL_LEN', '8192'))  # Max context length
LOCAL_LLM_GPU_MEMORY_UTILIZATION = float(os.getenv('LOCAL_LLM_GPU_MEMORY_UTILIZATION', '0.9'))  # GPU memory usage

# Vector Embedding Configuration (Arabic BERT)
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'aubmindlab/bert-base-arabert')
EMBEDDING_DIMENSION = int(os.getenv('EMBEDDING_DIMENSION', '768'))  # Dimension for BERT-base models (768)
EMBEDDING_DEVICE = os.getenv('EMBEDDING_DEVICE', 'cpu')  # 'cpu' or 'cuda'

# Vector Similarity Search Configuration
SIMILARITY_THRESHOLD = float(os.getenv('SIMILARITY_THRESHOLD', '0.8'))  # Cosine similarity threshold for document linking
MAX_SIMILAR_DOCUMENTS = int(os.getenv('MAX_SIMILAR_DOCUMENTS', '10'))  # Max similar documents to return

# Storage Configuration
STORAGE_PATH = os.getenv('STORAGE_PATH', './storage')
DOCUMENTS_PATH = os.getenv('DOCUMENTS_PATH', './documents')
ALLOWED_EXTENSIONS = {'.txt', '.pdf', '.docx', '.doc'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Application Configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

# Document Processing Configuration
PARSER_VERSION = '2.0.0'  # New version for vector-based architecture
DEFAULT_CASE_STATUS = 'open'
DEFAULT_CASE_TYPE = 'criminal'

# Entity Extraction Configuration
ENTITY_EXTRACTION_CONFIDENCE_THRESHOLD = float(os.getenv('ENTITY_CONFIDENCE_THRESHOLD', '0.7'))
BATCH_PROCESSING_ENABLED = os.getenv('BATCH_PROCESSING', 'True').lower() == 'true'

# Entity Limits (to prevent excessive extraction)
MAX_PARTIES_PER_DOCUMENT = int(os.getenv('MAX_PARTIES_PER_DOCUMENT', '100'))  # Max parties per document
MAX_CHARGES_PER_DOCUMENT = int(os.getenv('MAX_CHARGES_PER_DOCUMENT', '50'))  # Max charges per document
MAX_EVIDENCE_PER_DOCUMENT = int(os.getenv('MAX_EVIDENCE_PER_DOCUMENT', '100'))  # Max evidence items per document
MAX_JUDGMENTS_PER_DOCUMENT = int(os.getenv('MAX_JUDGMENTS_PER_DOCUMENT', '20'))  # Max judgments per document
MAX_COURT_SESSIONS_PER_DOCUMENT = int(os.getenv('MAX_COURT_SESSIONS_PER_DOCUMENT', '50'))  # Max court sessions per document
MAX_STATEMENTS_PER_DOCUMENT = int(os.getenv('MAX_STATEMENTS_PER_DOCUMENT', '100'))  # Max statements per document
# Additional list limits (to prevent over-extraction as we expand schemas)
MAX_WITNESSES_PER_DOCUMENT = int(os.getenv('MAX_WITNESSES_PER_DOCUMENT', '50'))
MAX_DECISIONS_PER_DOCUMENT = int(os.getenv('MAX_DECISIONS_PER_DOCUMENT', '100'))
MAX_LAB_RESULTS_PER_DOCUMENT = int(os.getenv('MAX_LAB_RESULTS_PER_DOCUMENT', '50'))
MAX_DETENTION_EVENTS_PER_DOCUMENT = int(os.getenv('MAX_DETENTION_EVENTS_PER_DOCUMENT', '50'))
MAX_NOTIFICATIONS_PER_DOCUMENT = int(os.getenv('MAX_NOTIFICATIONS_PER_DOCUMENT', '50'))
MAX_CORRESPONDENCE_PER_DOCUMENT = int(os.getenv('MAX_CORRESPONDENCE_PER_DOCUMENT', '50'))
MAX_WAIVERS_PER_DOCUMENT = int(os.getenv('MAX_WAIVERS_PER_DOCUMENT', '20'))
MAX_SENTENCES_PER_DOCUMENT = int(os.getenv('MAX_SENTENCES_PER_DOCUMENT', '50'))
MAX_INJURIES_PER_DOCUMENT = int(os.getenv('MAX_INJURIES_PER_DOCUMENT', '50'))
MAX_HOSPITAL_TRANSFERS_PER_DOCUMENT = int(os.getenv('MAX_HOSPITAL_TRANSFERS_PER_DOCUMENT', '50'))
MAX_PARTIES_PER_CASE = int(os.getenv('MAX_PARTIES_PER_CASE', '200'))  # Max parties per case (after merging)
MAX_CHARGES_PER_CASE = int(os.getenv('MAX_CHARGES_PER_CASE', '100'))  # Max charges per case (after merging)
MAX_EVIDENCE_PER_CASE = int(os.getenv('MAX_EVIDENCE_PER_CASE', '200'))  # Max evidence items per case (after merging)

# MongoDB Configuration
MONGODB_CONFIG = {
    'host': os.getenv('MONGODB_HOST', 'localhost'),
    'port': int(os.getenv('MONGODB_PORT', '27017')),
    'database': os.getenv('MONGODB_DATABASE', 'legal_cases_v2'),
    'username': os.getenv('MONGODB_USERNAME', None),
    'password': os.getenv('MONGODB_PASSWORD', None)
}

# Linking Parameters for Case Matching
LINKING_PARAMETERS = {
    'case_number_weight': float(os.getenv('LINKING_CASE_NUMBER_WEIGHT', '1.0')),
    'party_name_weight': float(os.getenv('LINKING_PARTY_NAME_WEIGHT', '0.8')),
    'personal_id_weight': float(os.getenv('LINKING_PERSONAL_ID_WEIGHT', '1.0')),
    'charge_weight': float(os.getenv('LINKING_CHARGE_WEIGHT', '0.7')),
    'date_weight': float(os.getenv('LINKING_DATE_WEIGHT', '0.6')),
    'location_weight': float(os.getenv('LINKING_LOCATION_WEIGHT', '0.5')),
    'vector_similarity_weight': float(os.getenv('LINKING_VECTOR_SIMILARITY_WEIGHT', '0.4')),
    'min_confidence': float(os.getenv('LINKING_MIN_CONFIDENCE', '0.7'))
}

# Full configuration dictionary
CONFIG = {
    'database': DATABASE_CONFIG,
    'database_legacy': DATABASE_CONFIG_LEGACY,
    'mongodb': MONGODB_CONFIG,
    'anthropic': {
        'api_key': ANTHROPIC_API_KEY,
        'model': ANTHROPIC_MODEL
    },
    'groq': {
        'api_key': GROQ_API_KEY,
        'model': GROQ_MODEL
    },
    'local_llm': {
        'enabled': LOCAL_LLM_ENABLED,
        'model_path': LOCAL_MODEL_PATH,
        'model_name': LOCAL_MODEL_NAME,
        'backend': LOCAL_LLM_BACKEND,
        'device': LOCAL_LLM_DEVICE,
        'tensor_parallel_size': LOCAL_LLM_TENSOR_PARALLEL_SIZE,
        'max_model_len': LOCAL_LLM_MAX_MODEL_LEN,
        'gpu_memory_utilization': LOCAL_LLM_GPU_MEMORY_UTILIZATION
    },
    'embeddings': {
        'model': EMBEDDING_MODEL,
        'dimension': EMBEDDING_DIMENSION,
        'device': EMBEDDING_DEVICE
    },
    'vector_search': {
        'similarity_threshold': SIMILARITY_THRESHOLD,
        'max_similar_documents': MAX_SIMILAR_DOCUMENTS
    },
    'storage': {
        'path': STORAGE_PATH,
        'documents_path': DOCUMENTS_PATH,
        'allowed_extensions': ALLOWED_EXTENSIONS,
        'max_file_size': MAX_FILE_SIZE
    },
    'app': {
        'log_level': LOG_LEVEL,
        'debug': DEBUG
    },
    'processing': {
        'parser_version': PARSER_VERSION,
        'default_case_status': DEFAULT_CASE_STATUS,
        'default_case_type': DEFAULT_CASE_TYPE,
        'entity_confidence_threshold': ENTITY_EXTRACTION_CONFIDENCE_THRESHOLD,
        'batch_processing': BATCH_PROCESSING_ENABLED,
        'entity_limits': {
            'max_parties_per_document': MAX_PARTIES_PER_DOCUMENT,
            'max_charges_per_document': MAX_CHARGES_PER_DOCUMENT,
            'max_evidence_per_document': MAX_EVIDENCE_PER_DOCUMENT,
            'max_judgments_per_document': MAX_JUDGMENTS_PER_DOCUMENT,
            'max_court_sessions_per_document': MAX_COURT_SESSIONS_PER_DOCUMENT,
            'max_statements_per_document': MAX_STATEMENTS_PER_DOCUMENT,
            'max_witnesses_per_document': MAX_WITNESSES_PER_DOCUMENT,
            'max_decisions_per_document': MAX_DECISIONS_PER_DOCUMENT,
            'max_lab_results_per_document': MAX_LAB_RESULTS_PER_DOCUMENT,
            'max_detention_events_per_document': MAX_DETENTION_EVENTS_PER_DOCUMENT,
            'max_notifications_per_document': MAX_NOTIFICATIONS_PER_DOCUMENT,
            'max_correspondence_per_document': MAX_CORRESPONDENCE_PER_DOCUMENT,
            'max_waivers_per_document': MAX_WAIVERS_PER_DOCUMENT,
            'max_sentences_per_document': MAX_SENTENCES_PER_DOCUMENT,
            'max_injuries_per_document': MAX_INJURIES_PER_DOCUMENT,
            'max_hospital_transfers_per_document': MAX_HOSPITAL_TRANSFERS_PER_DOCUMENT,
            'max_parties_per_case': MAX_PARTIES_PER_CASE,
            'max_charges_per_case': MAX_CHARGES_PER_CASE,
            'max_evidence_per_case': MAX_EVIDENCE_PER_CASE
        }
    },
    'linking_parameters': LINKING_PARAMETERS
}

