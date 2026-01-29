"""
Case Linker for MongoDB-based Legal Case Management System
Multi-parameter case linking with confidence scoring
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import numpy as np
from difflib import SequenceMatcher

from mongo_manager import MongoManager
from arabic_normalizer import ArabicNormalizer
from config import CONFIG

logger = logging.getLogger(__name__)


class CaseLinkerMongo:
    """Link documents to cases using multi-parameter matching"""
    
    def __init__(self, mongo_manager: MongoManager):
        """
        Initialize case linker
        
        Args:
            mongo_manager: MongoManager instance
        """
        self.db = mongo_manager
        self.linking_params = CONFIG.get('linking_parameters', {
            'case_number_weight': 1.0,
            'party_name_weight': 0.8,
            'personal_id_weight': 1.0,
            'charge_weight': 0.7,
            'date_weight': 0.6,
            'location_weight': 0.5,
            'vector_similarity_weight': 0.4,
            'min_confidence': 0.7
        })
        logger.info("Initialized CaseLinkerMongo")
    
    def find_or_create_case(self, document_data: Dict[str, Any], 
                           extracted_entities: Dict[str, Any]) -> Tuple[str, float, bool]:
        """
        Find existing case or create new one based on multi-parameter matching
        
        Args:
            document_data: Document data with embedding
            extracted_entities: Extracted entities from document
            
        Returns:
            Tuple of (case_id, confidence_score, was_created)
            - was_created: True if new case was created, False if existing case was found
        """
        # Try to find existing case
        match_result = self._find_matching_case(document_data, extracted_entities)
        
        if match_result:
            case_id, confidence = match_result
            logger.info(f"Found matching case: {case_id} (confidence: {confidence:.3f})")
            return (case_id, confidence, False)  # Found existing case
        
        # Create new case
        case_id = self._create_new_case(extracted_entities)
        logger.info(f"Created new case: {case_id}")
        return (case_id, 1.0, True)  # Created new case
    
    def _find_matching_case(self, document_data: Dict[str, Any],
                           extracted_entities: Dict[str, Any]) -> Optional[Tuple[str, float]]:
        """
        Find matching case using multi-parameter matching
        
        Args:
            document_data: Document data
            extracted_entities: Extracted entities
            
        Returns:
            Tuple of (case_id, confidence) or None
        """
        # Get all existing cases
        cases_collection = self.db.db['cases']
        all_cases = list(cases_collection.find({}))
        
        if not all_cases:
            return None
        
        best_match = None
        best_confidence = 0.0
        
        for case in all_cases:
            confidence = self._calculate_match_confidence(
                case, document_data, extracted_entities
            )
            
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = str(case['_id'])
        
        # Check if confidence meets minimum threshold
        min_confidence = self.linking_params.get('min_confidence', 0.7)
        if best_confidence >= min_confidence:
            return (best_match, best_confidence)
        
        return None
    
    def _calculate_match_confidence(self, case: Dict[str, Any],
                                   document_data: Dict[str, Any],
                                   extracted_entities: Dict[str, Any]) -> float:
        """
        Calculate confidence score for matching document to case
        
        Uses multiple parameters with weights:
        1. Case numbers (strong match)
        2. Personal IDs (strong match)
        3. Party names + dates (medium match)
        4. Charges + locations (medium match)
        5. Party names + charges (medium match)
        6. Vector similarity (weak match)
        
        Args:
            case: Existing case document
            document_data: New document data
            extracted_entities: Extracted entities from new document
            
        Returns:
            Confidence score (0.0-1.0)
        """
        confidence = 0.0
        match_details = {}
        
        # 1. STRONG MATCHES (any one creates high confidence)
        
        # Case number match
        case_numbers_match = self._match_case_numbers(
            case.get('case_numbers') or {},
            extracted_entities.get('case_numbers') or {}
        )
        if case_numbers_match:
            weight = self.linking_params.get('case_number_weight', 1.0)
            confidence += 0.95 * weight
            match_details['case_numbers'] = True
        
        # Personal ID match
        personal_id_match = self._match_personal_ids(case, extracted_entities)
        if personal_id_match:
            weight = self.linking_params.get('personal_id_weight', 1.0)
            confidence += 0.95 * weight
            match_details['personal_ids'] = True
        
        # If we have a strong match, return early
        if confidence >= 0.9:
            return min(1.0, confidence)
        
        # 2. MEDIUM MATCHES (require multiple)
        
        # Party name + date match
        party_date_match = self._match_party_names_and_dates(case, extracted_entities)
        if party_date_match:
            weight = self.linking_params.get('party_name_weight', 0.8) * \
                    self.linking_params.get('date_weight', 0.6)
            confidence += 0.80 * weight
            match_details['party_date'] = True
        
        # Charge + location match
        charge_location_match = self._match_charges_and_locations(case, extracted_entities)
        if charge_location_match:
            weight = self.linking_params.get('charge_weight', 0.7) * \
                    self.linking_params.get('location_weight', 0.5)
            confidence += 0.80 * weight
            match_details['charge_location'] = True
        
        # Party name + charge match
        party_charge_match = self._match_party_names_and_charges(case, extracted_entities)
        if party_charge_match:
            weight = self.linking_params.get('party_name_weight', 0.8) * \
                    self.linking_params.get('charge_weight', 0.7)
            confidence += 0.80 * weight
            match_details['party_charge'] = True
        
        # 3. WEAK MATCHES (fallback)
        
        # Vector similarity (if embedding available)
        if document_data.get('embedding'):
            vector_match = self._match_vector_similarity(case, document_data)
            if vector_match:
                weight = self.linking_params.get('vector_similarity_weight', 0.4)
                confidence += 0.70 * weight
                match_details['vector_similarity'] = True
        
        logger.debug(f"Match confidence: {confidence:.3f}, details: {match_details}")
        return min(1.0, confidence)
    
    def _match_case_numbers(self, case_numbers: Dict, new_numbers: Dict) -> bool:
        """Check if case numbers match"""
        if not case_numbers or not new_numbers:
            return False
        
        # Check each type
        for ref_type in ['court', 'prosecution', 'police', 'internal']:
            case_val = case_numbers.get(ref_type)
            new_val = new_numbers.get(ref_type)
            
            if case_val and new_val and case_val == new_val:
                return True
        
        # Check variations
        # Note: LLM may return null for variations; handle None explicitly
        case_variations = set(case_numbers.get('variations') or [])
        new_variations = set(new_numbers.get('variations') or [])
        
        if case_variations and new_variations:
            if case_variations.intersection(new_variations):
                return True
        
        return False
    
    def _match_personal_ids(self, case: Dict, extracted_entities: Dict) -> bool:
        """Check if personal IDs match"""
        # Get parties from case (via case_parties collection)
        case_parties_collection = self.db.db['case_parties']
        parties_collection = self.db.db['parties']
        
        # Get party IDs linked to case
        case_party_links = list(case_parties_collection.find({'case_id': case['_id']}))
        case_party_ids = [link['party_id'] for link in case_party_links]
        
        # Get personal IDs from case parties
        case_personal_ids = set()
        for party_id in case_party_ids:
            party = parties_collection.find_one({'_id': party_id})
            if party and party.get('personal_id'):
                case_personal_ids.add(str(party['personal_id']).strip())
        
        # Get personal IDs from new document
        new_parties = extracted_entities.get('parties') or []
        if not isinstance(new_parties, list):
            new_parties = []
        new_personal_ids = set()
        for party in new_parties:
            if party and isinstance(party, dict) and party.get('personal_id'):
                new_personal_ids.add(str(party['personal_id']).strip())
        
        # Check for matches
        if case_personal_ids and new_personal_ids:
            return bool(case_personal_ids.intersection(new_personal_ids))
        
        return False
    
    def _match_party_names_and_dates(self, case: Dict, extracted_entities: Dict) -> bool:
        """Check if party names and dates match"""
        # Get normalized party names from case
        case_parties_collection = self.db.db['case_parties']
        parties_collection = self.db.db['parties']
        
        case_party_links = list(case_parties_collection.find({'case_id': case['_id']}))
        case_party_ids = [link['party_id'] for link in case_party_links]
        
        case_party_names = set()
        for party_id in case_party_ids:
            party = parties_collection.find_one({'_id': party_id})
            if party:
                name_ar = party.get('name_ar', '')
                if name_ar:
                    normalized = ArabicNormalizer.normalize_name(name_ar)
                    if normalized:
                        case_party_names.add(normalized)
        
        # Get normalized party names from new document
        new_parties = extracted_entities.get('parties') or []
        if not isinstance(new_parties, list):
            new_parties = []
        new_party_names = set()
        for party in new_parties:
            if party and isinstance(party, dict):
                name_ar = party.get('name_ar', '')
                if name_ar:
                    normalized = ArabicNormalizer.normalize_name(name_ar)
                    if normalized:
                        new_party_names.add(normalized)
        
        # Check for name matches
        name_match = bool(case_party_names.intersection(new_party_names)) if case_party_names and new_party_names else False
        
        # Check for date matches (within 30 days)
        case_dates = case.get('key_dates') or {}
        if not isinstance(case_dates, dict):
            case_dates = {}
        new_dates = extracted_entities.get('dates') or {}
        if not isinstance(new_dates, dict):
            new_dates = {}
        
        date_match = False
        for date_key in ['incident', 'report_filed', 'investigation', 'first_hearing']:
            case_date = case_dates.get(date_key)
            new_date = new_dates.get(date_key)
            
            if case_date and new_date:
                try:
                    from datetime import datetime as dt
                    case_dt = dt.fromisoformat(case_date) if isinstance(case_date, str) else case_date
                    new_dt = dt.fromisoformat(new_date) if isinstance(new_date, str) else new_date
                    
                    days_diff = abs((case_dt - new_dt).days)
                    if days_diff <= 30:
                        date_match = True
                        break
                except:
                    pass
        
        return name_match and date_match
    
    def _match_charges_and_locations(self, case: Dict, extracted_entities: Dict) -> bool:
        """Check if charges and locations match"""
        # Get charges from case
        case_charges_collection = self.db.db['case_charges']
        charges_collection = self.db.db['charges']
        
        case_charge_links = list(case_charges_collection.find({'case_id': case['_id']}))
        case_charge_ids = [link['charge_id'] for link in case_charge_links]
        
        case_article_numbers = set()
        for charge_id in case_charge_ids:
            charge = charges_collection.find_one({'_id': charge_id})
            if charge and charge.get('article_number'):
                case_article_numbers.add(str(charge['article_number']).strip())
        
        # Get article numbers from new document
        new_charges = extracted_entities.get('charges') or []
        if not isinstance(new_charges, list):
            new_charges = []
        new_article_numbers = set()
        for charge in new_charges:
            if charge and isinstance(charge, dict) and charge.get('article_number'):
                new_article_numbers.add(str(charge['article_number']).strip())
        
        charge_match = bool(case_article_numbers.intersection(new_article_numbers)) if case_article_numbers and new_article_numbers else False
        
        # Check location match
        case_locations = case.get('locations') or {}
        if not isinstance(case_locations, dict):
            case_locations = {}
        new_locations = extracted_entities.get('locations') or {}
        if not isinstance(new_locations, dict):
            new_locations = {}
        
        location_match = False
        for loc_key in ['court', 'police_station', 'prosecution_office']:
            case_loc = case_locations.get(loc_key)
            new_loc = new_locations.get(loc_key)
            
            if case_loc and new_loc:
                # Normalize and compare
                case_loc_norm = ArabicNormalizer.normalize_name(case_loc)
                new_loc_norm = ArabicNormalizer.normalize_name(new_loc)
                
                if case_loc_norm == new_loc_norm:
                    location_match = True
                    break
        
        return charge_match and location_match
    
    def _match_party_names_and_charges(self, case: Dict, extracted_entities: Dict) -> bool:
        """Check if party names and charges match"""
        # Get party names (same as in _match_party_names_and_dates)
        case_parties_collection = self.db.db['case_parties']
        parties_collection = self.db.db['parties']
        
        case_party_links = list(case_parties_collection.find({'case_id': case['_id']}))
        case_party_ids = [link['party_id'] for link in case_party_links]
        
        case_party_names = set()
        for party_id in case_party_ids:
            party = parties_collection.find_one({'_id': party_id})
            if party:
                name_ar = party.get('name_ar', '')
                if name_ar:
                    normalized = ArabicNormalizer.normalize_name(name_ar)
                    if normalized:
                        case_party_names.add(normalized)
        
        new_parties = extracted_entities.get('parties') or []
        if not isinstance(new_parties, list):
            new_parties = []
        new_party_names = set()
        for party in new_parties:
            if party and isinstance(party, dict):
                name_ar = party.get('name_ar', '')
                if name_ar:
                    normalized = ArabicNormalizer.normalize_name(name_ar)
                    if normalized:
                        new_party_names.add(normalized)
        
        name_match = bool(case_party_names.intersection(new_party_names)) if case_party_names and new_party_names else False
        
        # Get charges (same as in _match_charges_and_locations)
        case_charges_collection = self.db.db['case_charges']
        charges_collection = self.db.db['charges']
        
        case_charge_links = list(case_charges_collection.find({'case_id': case['_id']}))
        case_charge_ids = [link['charge_id'] for link in case_charge_links]
        
        case_article_numbers = set()
        for charge_id in case_charge_ids:
            charge = charges_collection.find_one({'_id': charge_id})
            if charge and charge.get('article_number'):
                case_article_numbers.add(str(charge['article_number']).strip())
        
        new_charges = extracted_entities.get('charges') or []
        if not isinstance(new_charges, list):
            new_charges = []
        new_article_numbers = set()
        for charge in new_charges:
            if charge and isinstance(charge, dict) and charge.get('article_number'):
                new_article_numbers.add(str(charge['article_number']).strip())
        
        charge_match = bool(case_article_numbers.intersection(new_article_numbers)) if case_article_numbers and new_article_numbers else False
        
        return name_match and charge_match
    
    def _match_vector_similarity(self, case: Dict, document_data: Dict) -> bool:
        """Check vector similarity (placeholder - requires proper vector search)"""
        # TODO: Implement proper vector similarity search
        # For now, return False
        return False
    
    def _create_new_case(self, extracted_entities: Dict[str, Any]) -> str:
        """
        Create a new case from extracted entities
        
        Args:
            extracted_entities: Extracted entities from document
            
        Returns:
            case_id
        """
        # Prepare case data (minimal - entities stored separately)
        # Handle None values from LLM (null in JSON becomes None in Python)
        case_data = {
            'case_numbers': extracted_entities.get('case_numbers') or {},
            'key_dates': extracted_entities.get('dates') or {},
            'locations': extracted_entities.get('locations') or {},
            'case_status': extracted_entities.get('case_status') or {},
            'legal_references': extracted_entities.get('legal_references') or [],
            'timeline': self._create_initial_timeline(extracted_entities)
        }
        
        case_id = self.db.create_case(case_data)
        
        # Store entities in normalized collections
        self._store_entities_normalized(case_id, extracted_entities, source_document_id=None)
        
        return case_id
    
    def _store_entities_normalized(self, case_id: str, extracted_entities: Dict[str, Any],
                                   source_document_id: str = None):
        """Store entities in normalized collections"""
        # Store parties - handle None values
        parties = extracted_entities.get('parties') or []
        if not isinstance(parties, list):
            parties = []
        for party in parties:
            if party and isinstance(party, dict):
                try:
                    party_id = self.db.get_or_create_party(party)
                    role = party.get('role') or (party.get('roles', [])[0] if party.get('roles') else 'unknown')
                    self.db.link_party_to_case(case_id, party_id, role, source_document_id)
                except Exception as e:
                    logger.warning(f"Error storing party: {str(e)}")
        
        # Store charges - handle None values
        charges = extracted_entities.get('charges') or []
        if not isinstance(charges, list):
            charges = []
        for charge in charges:
            if charge and isinstance(charge, dict):
                try:
                    charge_id = self.db.get_or_create_charge(charge)
                    self.db.link_charge_to_case(case_id, charge_id, source_document_id)
                except Exception as e:
                    logger.warning(f"Error storing charge: {str(e)}")
        
        # Store evidence - handle None values
        evidence = extracted_entities.get('evidence') or []
        if not isinstance(evidence, list):
            evidence = []
        for ev in evidence:
            if ev and isinstance(ev, dict):
                try:
                    evidence_id = self.db.get_or_create_evidence(ev)
                    self.db.link_evidence_to_case(case_id, evidence_id, source_document_id)
                except Exception as e:
                    logger.warning(f"Error storing evidence: {str(e)}")
    
    def _create_initial_timeline(self, entities: Dict) -> List[Dict]:
        """Create initial timeline from entities"""
        timeline = []
        dates = entities.get('dates') or {}
        if not isinstance(dates, dict):
            dates = {}
        
        for date_type, date_value in dates.items():
            if date_value:
                timeline.append({
                    'date': date_value,
                    'event_type': date_type,
                    'source_document': 'initial'
                })
        
        timeline.sort(key=lambda x: x.get('date', ''))
        return timeline
    
    def link_document_to_case(self, case_id: str, document_id: str,
                              confidence_score: float, linking_params: Dict[str, Any] = None):
        """Link document to case with confidence and parameters"""
        self.db.link_document_to_case(case_id, document_id, confidence_score, linking_params)

