"""
Case Linker for Vector-Based Legal Case Management System
Handles vector similarity search, case creation/merging, and intelligent entity merging
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import json
from difflib import SequenceMatcher

from .db_manager_v2 import DatabaseManagerV2
from config import CONFIG

logger = logging.getLogger(__name__)


class CaseLinker:
    """Link documents to cases using vector similarity and entity matching"""
    
    def __init__(self, db_manager: DatabaseManagerV2):
        """
        Initialize case linker
        
        Args:
            db_manager: DatabaseManagerV2 instance
        """
        self.db = db_manager
        self.similarity_threshold = CONFIG['vector_search']['similarity_threshold']
        logger.info(f"Initialized CaseLinker with similarity threshold: {self.similarity_threshold}")
    
    def find_similar_case(self, embedding: List[float]) -> Optional[Tuple[int, float]]:
        """
        Find similar case using vector similarity search
        
        Args:
            embedding: Document embedding vector
            
        Returns:
            Tuple of (case_id, similarity_score) or None
        """
        # Find similar documents
        similar_docs = self.db.find_similar_documents(
            embedding,
            threshold=self.similarity_threshold,
            limit=CONFIG['vector_search']['max_similar_documents']
        )
        
        if not similar_docs:
            return None
        
        # Get the most similar document
        best_match = similar_docs[0]
        case_id = best_match.get('case_id')
        similarity = best_match.get('similarity', 0.0)
        
        if case_id and similarity >= self.similarity_threshold:
            logger.info(f"Found similar case: {case_id} (similarity: {similarity:.3f})")
            return (case_id, similarity)
        
        return None
    
    def create_new_case(self, entities: Dict[str, Any]) -> int:
        """
        Create a new case from extracted entities
        
        Args:
            entities: Extracted entities from document
            
        Returns:
            case_id
        """
        # Prepare case data structure
        case_data = {
            'case_numbers': entities.get('case_numbers', {}),
            # Medium-term scaling: prefer normalized entity tables over large JSONB arrays
            # Keep JSONB arrays minimal; entities will be written to normalized tables when available.
            'parties': [],
            'key_dates': entities.get('dates', {}),
            'locations': entities.get('locations', {}),
            'charges': [],
            'judgments': entities.get('judgments', []),
            'financial': entities.get('financial', {}),
            'evidence': [],
            'case_status': entities.get('case_status', {}),
            'legal_references': entities.get('legal_references', []),
            'timeline': self._create_initial_timeline(entities)
        }
        
        # Optimize case data to prevent JSONB size limit errors
        case_data = self._optimize_case_data(case_data)
        
        case_id = self.db.create_case(case_data)
        logger.info(f"Created new case: {case_id}")

        # Write normalized entities (if tables exist)
        self._store_entities_normalized(case_id, entities, source_document_id=None, confidence_score=None)

        return case_id
    
    def merge_entities_into_case(self, case_id: int, new_entities: Dict[str, Any], 
                                source_document: str = None):
        """
        Merge new entities into existing case with intelligent deduplication
        
        Args:
            case_id: Case ID to merge into
            new_entities: New entities from document
            source_document: Source document path (for tracking)
        """
        # Get existing case
        existing_case = self.db.get_case(case_id)
        if not existing_case:
            raise ValueError(f"Case {case_id} not found")
        
        # Merge each entity type
        merged_data = {}
        
        # Merge case numbers
        merged_data['case_numbers'] = self._merge_case_numbers(
            existing_case.get('case_numbers', {}),
            new_entities.get('case_numbers', {})
        )
        
        # Medium-term scaling:
        # Store parties/charges/evidence in normalized tables when available.
        # Keep JSONB arrays minimal to avoid unbounded growth (and expensive queries).
        self._store_entities_normalized(case_id, new_entities, source_document_id=None, confidence_score=None)
        merged_data['parties'] = []  # replace, do not append/merge
        merged_data['charges'] = []  # replace, do not append/merge
        
        # Merge dates (keep earliest/latest as appropriate)
        merged_data['key_dates'] = self._merge_dates(
            existing_case.get('key_dates', {}),
            new_entities.get('dates', {})
        )
        
        # Merge locations (prefer non-null values)
        merged_data['locations'] = self._merge_locations(
            existing_case.get('locations', {}),
            new_entities.get('locations', {})
        )
        
        # Merge judgments (append new, keep most recent)
        merged_data['judgments'] = self._merge_judgments(
            existing_case.get('judgments', []),
            new_entities.get('judgments', [])
        )
        
        # Merge financial (sum amounts)
        merged_data['financial'] = self._merge_financial(
            existing_case.get('financial', {}),
            new_entities.get('financial', {})
        )
        
        # Evidence: stored normalized; keep JSONB minimal
        merged_data['evidence'] = []  # replace, do not append/merge
        
        # Merge timeline
        merged_data['timeline'] = self._merge_timeline(
            existing_case.get('timeline', []),
            new_entities,
            source_document
        )
        
        # Update case status if more advanced
        merged_data['case_status'] = self._merge_case_status(
            existing_case.get('case_status', {}),
            new_entities.get('case_status', {})
        )
        
        # Merge legal references
        merged_data['legal_references'] = self._merge_legal_references(
            existing_case.get('legal_references', []),
            new_entities.get('legal_references', [])
        )
        
        # Optimize merged data to prevent JSONB size limit errors
        merged_data = self._optimize_case_data(merged_data)
        
        # Update case
        self.db.update_case(case_id, merged_data)
        logger.info(f"Merged entities into case: {case_id}")

    def _store_entities_normalized(
        self,
        case_id: int,
        entities: Dict[str, Any],
        source_document_id: Optional[int] = None,
        confidence_score: Optional[float] = None,
    ) -> None:
        """
        Store parties/charges/evidence in normalized entity tables when available.
        This avoids unbounded growth of JSONB arrays in `cases`.
        """
        try:
            # Parties
            parties = entities.get("parties", []) or []
            for p in parties:
                party_id = self.db.get_or_create_party_entity(p)
                if party_id:
                    role = p.get("role")
                    # Prefer explicit role; if roles list exists, take first
                    if not role and isinstance(p.get("roles"), list) and p["roles"]:
                        role = p["roles"][0]
                    self.db.link_party_entity_to_case(
                        case_id=case_id,
                        party_id=party_id,
                        role_type=role,
                        source_document_id=source_document_id,
                        confidence_score=confidence_score,
                    )

            # Charges
            charges = entities.get("charges", []) or []
            for c in charges:
                charge_id = self.db.get_or_create_charge_entity(c)
                if charge_id:
                    self.db.link_charge_entity_to_case(
                        case_id=case_id,
                        charge_id=charge_id,
                        status=c.get("status"),
                        source_document_id=source_document_id,
                    )

            # Evidence
            ev_items = entities.get("evidence", []) or []
            for ev in ev_items:
                evidence_id = self.db.get_or_create_evidence_entity(ev)
                if evidence_id:
                    self.db.link_evidence_entity_to_case(
                        case_id=case_id,
                        evidence_id=evidence_id,
                        source_document_id=source_document_id,
                    )
        except Exception as e:
            # Never fail case merge because normalized tables are missing/misconfigured
            logger.warning(f"Normalized entity storage failed (case {case_id}): {str(e)}")
    
    def link_document_to_case(self, document_id: int, case_id: int, 
                             confidence_score: float):
        """Link document to case"""
        self.db.update_document_case(document_id, case_id, confidence_score)
    
    # ========================================================================
    # Entity Merging Methods
    # ========================================================================
    
    def _merge_case_numbers(self, existing: Dict, new: Dict) -> Dict:
        """Merge case numbers, preserving all variations"""
        merged = existing.copy() if existing else {}
        
        for key, value in new.items():
            if key == 'variations':
                # Merge variations list
                existing_vars = set(merged.get('variations', []))
                new_vars = set(value) if isinstance(value, list) else {value}
                merged['variations'] = sorted(list(existing_vars | new_vars))
            elif value and (not merged.get(key) or len(str(value)) > len(str(merged.get(key, '')))):
                # Prefer longer/more complete values
                merged[key] = value
        
        return merged
    
    def _merge_parties(self, existing: List[Dict], new: List[Dict], 
                      source_doc: str = None) -> List[Dict]:
        """Merge parties with entity ID assignment and deduplication"""
        merged = existing.copy() if existing else []
        limits = CONFIG['processing']['entity_limits']
        max_parties = limits['max_parties_per_case']
        
        # STEP 1: Pre-deduplicate the new parties list itself
        # This prevents processing duplicates from the same document
        original_new_count = len(new)
        new = self._deduplicate_party_list(new)
        if original_new_count > len(new):
            logger.info(
                f"Pre-deduplication: {original_new_count} -> {len(new)} unique parties "
                f"from {source_doc or 'document'}"
            )
        
        # Check if existing parties already exceed limit
        if len(merged) >= max_parties:
            logger.warning(
                f"Case already has {len(merged)} parties (limit: {max_parties}). "
                f"Skipping merge of {len(new)} new parties from {source_doc or 'unknown document'}"
            )
            return merged
        
        # STEP 2: Create lookup index for faster matching (O(1) instead of O(n))
        existing_index = self._create_party_index(merged)
        
        # Assign entity IDs to existing parties if not present
        next_id = 1
        for party in merged:
            if 'party_entity_id' not in party:
                party['party_entity_id'] = f"P{next_id:03d}"
                next_id += 1
            else:
                # Extract number from existing ID
                try:
                    id_num = int(party['party_entity_id'][1:])
                    next_id = max(next_id, id_num + 1)
                except:
                    pass
        
        # STEP 3: Process new parties with indexed lookup
        parties_added = 0
        for new_party in new:
            # Stop if we've reached the limit
            if len(merged) >= max_parties:
                logger.warning(
                    f"Reached party limit ({max_parties}) while merging. "
                    f"Skipping remaining {len(new) - parties_added} parties from {source_doc or 'unknown document'}"
                )
                break
            
            # Use indexed lookup for faster matching
            matched_party = self._find_matching_party_indexed(new_party, existing_index, merged)
            
            if matched_party:
                # Merge into existing party
                self._merge_party_details(matched_party, new_party, source_doc)
            else:
                # New party - assign entity ID
                new_party['party_entity_id'] = f"P{next_id:03d}"
                next_id += 1
                if source_doc:
                    new_party['source_documents'] = [source_doc]
                merged.append(new_party)
                # Update index
                self._add_party_to_index(new_party, existing_index, len(merged) - 1)
                parties_added += 1
        
        # Final validation - ensure we don't exceed limit
        if len(merged) > max_parties:
            logger.error(
                f"ERROR: Merged parties ({len(merged)}) exceed limit ({max_parties}). "
                f"Truncating to limit."
            )
            merged = merged[:max_parties]
        
        return merged
    
    def _deduplicate_party_list(self, parties: List[Dict]) -> List[Dict]:
        """Deduplicate parties within a list before merging"""
        seen = set()
        unique_parties = []
        
        for party in parties:
            # Create a unique key for this party
            party_key = self._get_party_key(party)
            
            if party_key and party_key not in seen:
                seen.add(party_key)
                unique_parties.append(party)
            else:
                logger.debug(f"Skipping duplicate party: {party.get('name_ar') or party.get('name_en')}")
        
        duplicates_removed = len(parties) - len(unique_parties)
        if duplicates_removed > 0:
            logger.debug(f"Removed {duplicates_removed} duplicate parties from new list")
        
        return unique_parties
    
    def _get_party_key(self, party: Dict) -> Optional[str]:
        """Create a unique key for party matching - prioritize Arabic"""
        # Priority: personal_id > Arabic name > English name
        personal_id = party.get('personal_id')
        if personal_id:
            return f"id:{personal_id.strip()}"
        
        # Normalize names for matching - prioritize Arabic
        name_ar = self._normalize_name(party.get('name_ar', ''))
        name_en = self._normalize_name(party.get('name_en', ''))
        
        if name_ar:
            return f"ar:{name_ar}"
        elif name_en:
            return f"en:{name_en}"
        
        return None
    
    def _normalize_name(self, name: str) -> str:
        """Normalize name for better matching"""
        if not name:
            return ""
        
        # Remove extra whitespace, convert to lowercase
        normalized = ' '.join(name.strip().split()).lower()
        
        # Remove common prefixes/suffixes that might vary
        # (You could add Arabic-specific normalization here)
        
        return normalized
    
    def _create_party_index(self, parties: List[Dict]) -> Dict[str, int]:
        """Create an index for fast party lookup"""
        index = {}
        for idx, party in enumerate(parties):
            party_key = self._get_party_key(party)
            if party_key:
                # Store index of party in merged list
                if party_key not in index:
                    index[party_key] = idx
                # Also index by personal_id if available
                personal_id = party.get('personal_id')
                if personal_id:
                    id_key = f"id:{personal_id.strip()}"
                    index[id_key] = idx
        return index
    
    def _add_party_to_index(self, party: Dict, index: Dict[str, int], position: int):
        """Add party to index"""
        party_key = self._get_party_key(party)
        if party_key:
            index[party_key] = position
            personal_id = party.get('personal_id')
            if personal_id:
                index[f"id:{personal_id.strip()}"] = position
    
    def _find_matching_party_indexed(self, new_party: Dict, index: Dict[str, int], 
                                    merged: List[Dict]) -> Optional[Dict]:
        """Find matching party using index (fast)"""
        # Try exact key match first
        party_key = self._get_party_key(new_party)
        if party_key and party_key in index:
            return merged[index[party_key]]
        
        # Fallback to fuzzy matching if exact match fails
        # (for cases where names are similar but not identical)
        for existing_party in merged:
            if self._parties_match(existing_party, new_party):
                return existing_party
        
        return None
    
    def _parties_match(self, party1: Dict, party2: Dict) -> bool:
        """Check if two parties are the same person - prioritize Arabic matching"""
        # Match by personal_id (strongest)
        if party1.get('personal_id') and party2.get('personal_id'):
            if party1['personal_id'] == party2['personal_id']:
                return True
        
        # Match by normalized Arabic name first (prioritize Arabic)
        name1_ar = self._normalize_name(party1.get('name_ar', ''))
        name2_ar = self._normalize_name(party2.get('name_ar', ''))
        if name1_ar and name2_ar:
            # First try exact match after normalization
            if name1_ar == name2_ar:
                return True
            # Then try fuzzy match
            similarity = SequenceMatcher(None, name1_ar, name2_ar).ratio()
            if similarity > 0.85:  # 85% similarity threshold
                return True
        
        # Fallback to English name matching only if Arabic not available
        name1_en = self._normalize_name(party1.get('name_en', ''))
        name2_en = self._normalize_name(party2.get('name_en', ''))
        if name1_en and name2_en:
            # First try exact match after normalization
            if name1_en == name2_en:
                return True
            # Then try fuzzy match
            similarity = SequenceMatcher(None, name1_en, name2_en).ratio()
            if similarity > 0.85:
                return True
        
        return False
    
    def _merge_party_details(self, existing: Dict, new: Dict, source_doc: str = None):
        """Merge new party details into existing party - prioritize Arabic"""
        # Merge roles
        existing_roles = set(existing.get('roles', []) if isinstance(existing.get('roles'), list) else [existing.get('role')])
        new_role = new.get('role') or (new.get('roles', [])[0] if new.get('roles') else None)
        if new_role:
            existing_roles.add(new_role)
        existing['roles'] = list(existing_roles) if existing_roles else [existing.get('role')]
        
        # Update other fields - prioritize Arabic over English
        for key, value in new.items():
            if key not in ['party_entity_id', 'roles', 'role'] and value:
                # For Arabic/English pairs, prefer Arabic
                if key == 'name_en' and existing.get('name_ar'):
                    # Don't overwrite Arabic name with English
                    continue
                elif key == 'name_ar':
                    # Always prefer Arabic name
                    existing[key] = value
                elif key == 'description_en' and existing.get('description_ar'):
                    # Don't overwrite Arabic description with English
                    continue
                elif key == 'description_ar':
                    # Always prefer Arabic description
                    existing[key] = value
                elif not existing.get(key):
                    # For other fields, update if missing
                    existing[key] = value
        
        # Track source documents
        if source_doc:
            if 'source_documents' not in existing:
                existing['source_documents'] = []
            if source_doc not in existing['source_documents']:
                existing['source_documents'].append(source_doc)
    
    def _normalize_parties(self, parties: List[Dict]) -> List[Dict]:
        """Normalize parties and assign entity IDs"""
        normalized = []
        for i, party in enumerate(parties, 1):
            party['party_entity_id'] = f"P{i:03d}"
            if 'role' in party and 'roles' not in party:
                party['roles'] = [party['role']]
            normalized.append(party)
        return normalized
    
    def _merge_charges(self, existing: List[Dict], new: List[Dict], 
                      source_doc: str = None) -> List[Dict]:
        """Merge charges with entity ID assignment"""
        merged = existing.copy() if existing else []
        limits = CONFIG['processing']['entity_limits']
        max_charges = limits['max_charges_per_case']
        
        # STEP 1: Pre-deduplicate the new charges list itself
        original_new_count = len(new)
        new = self._deduplicate_charge_list(new)
        if original_new_count > len(new):
            logger.info(
                f"Pre-deduplication: {original_new_count} -> {len(new)} unique charges "
                f"from {source_doc or 'document'}"
            )
        
        # Check if existing charges already exceed limit
        if len(merged) >= max_charges:
            logger.warning(
                f"Case already has {len(merged)} charges (limit: {max_charges}). "
                f"Skipping merge of {len(new)} new charges from {source_doc or 'unknown document'}"
            )
            return merged
        
        # STEP 2: Create lookup index for faster matching
        existing_index = self._create_charge_index(merged)
        
        # Assign entity IDs to existing charges
        next_id = 1
        for charge in merged:
            if 'charge_entity_id' not in charge:
                charge['charge_entity_id'] = f"C{next_id:03d}"
                next_id += 1
            else:
                try:
                    id_num = int(charge['charge_entity_id'][1:])
                    next_id = max(next_id, id_num + 1)
                except:
                    pass
        
        # STEP 3: Process new charges with indexed lookup
        charges_added = 0
        for new_charge in new:
            # Stop if we've reached the limit
            if len(merged) >= max_charges:
                logger.warning(
                    f"Reached charge limit ({max_charges}) while merging. "
                    f"Skipping remaining {len(new) - charges_added} charges from {source_doc or 'unknown document'}"
                )
                break
            
            # Use indexed lookup for faster matching
            matched_charge = self._find_matching_charge_indexed(new_charge, existing_index, merged)
            
            if matched_charge:
                # Merge into existing charge
                self._merge_charge_details(matched_charge, new_charge, source_doc)
            else:
                # New charge
                new_charge['charge_entity_id'] = f"C{next_id:03d}"
                next_id += 1
                if source_doc:
                    new_charge['source_documents'] = [source_doc]
                merged.append(new_charge)
                # Update index
                self._add_charge_to_index(new_charge, existing_index, len(merged) - 1)
                charges_added += 1
        
        # Final validation - ensure we don't exceed limit
        if len(merged) > max_charges:
            logger.error(
                f"ERROR: Merged charges ({len(merged)}) exceed limit ({max_charges}). "
                f"Truncating to limit."
            )
            merged = merged[:max_charges]
        
        return merged
    
    def _deduplicate_charge_list(self, charges: List[Dict]) -> List[Dict]:
        """Deduplicate charges within a list before merging"""
        seen = set()
        unique_charges = []
        
        for charge in charges:
            charge_key = self._get_charge_key(charge)
            
            if charge_key and charge_key not in seen:
                seen.add(charge_key)
                unique_charges.append(charge)
            else:
                logger.debug(f"Skipping duplicate charge: {charge.get('article_number')} - {charge.get('description_ar', '')[:50]}")
        
        duplicates_removed = len(charges) - len(unique_charges)
        if duplicates_removed > 0:
            logger.debug(f"Removed {duplicates_removed} duplicate charges from new list")
        
        return unique_charges
    
    def _get_charge_key(self, charge: Dict) -> Optional[str]:
        """Create a unique key for charge matching - prioritize Arabic"""
        article = (charge.get('article_number') or '').strip()
        desc_ar = self._normalize_name(charge.get('description_ar', ''))
        desc_en = self._normalize_name(charge.get('description_en', ''))
        
        # Priority: article number > Arabic description > English description
        if article:
            return f"art:{article}"
        elif desc_ar:
            return f"desc_ar:{desc_ar}"
        elif desc_en:
            return f"desc_en:{desc_en}"
        
        return None
    
    def _create_charge_index(self, charges: List[Dict]) -> Dict[str, int]:
        """Create an index for fast charge lookup"""
        index = {}
        for idx, charge in enumerate(charges):
            charge_key = self._get_charge_key(charge)
            if charge_key:
                if charge_key not in index:
                    index[charge_key] = idx
        return index
    
    def _add_charge_to_index(self, charge: Dict, index: Dict[str, int], position: int):
        """Add charge to index"""
        charge_key = self._get_charge_key(charge)
        if charge_key:
            index[charge_key] = position
    
    def _find_matching_charge_indexed(self, new_charge: Dict, index: Dict[str, int], 
                                      merged: List[Dict]) -> Optional[Dict]:
        """Find matching charge using index (fast)"""
        # Try exact key match first
        charge_key = self._get_charge_key(new_charge)
        if charge_key and charge_key in index:
            return merged[index[charge_key]]
        
        # Fallback to fuzzy matching
        for existing_charge in merged:
            if self._charges_match(existing_charge, new_charge):
                return existing_charge
        
        return None
    
    def _charges_match(self, charge1: Dict, charge2: Dict) -> bool:
        """Check if two charges are the same - prioritize Arabic matching"""
        # Match by article number (strongest)
        art1 = (charge1.get('article_number') or '').strip()
        art2 = (charge2.get('article_number') or '').strip()
        
        # Exact article match
        if art1 and art2 and art1 == art2:
            return True
        
        # Match by normalized Arabic description first (prioritize Arabic)
        desc1_ar = self._normalize_name(charge1.get('description_ar', ''))
        desc2_ar = self._normalize_name(charge2.get('description_ar', ''))
        if desc1_ar and desc2_ar:
            if desc1_ar == desc2_ar:
                return True
            similarity = SequenceMatcher(None, desc1_ar, desc2_ar).ratio()
            if similarity > 0.8:
                return True
        
        # Fallback to English description matching only if Arabic not available
        desc1_en = self._normalize_name(charge1.get('description_en', ''))
        desc2_en = self._normalize_name(charge2.get('description_en', ''))
        if desc1_en and desc2_en:
            if desc1_en == desc2_en:
                return True
            similarity = SequenceMatcher(None, desc1_en, desc2_en).ratio()
            if similarity > 0.8:
                return True
        
        return False
    
    def _merge_charge_details(self, existing: Dict, new: Dict, source_doc: str = None):
        """Merge charge details, track status evolution - prioritize Arabic"""
        # Update status if more advanced
        status_priority = {'pending': 1, 'dismissed': 2, 'acquitted': 3, 'convicted': 4}
        existing_status = existing.get('status', 'pending')
        new_status = new.get('status', 'pending')
        
        if status_priority.get(new_status, 0) > status_priority.get(existing_status, 0):
            existing['status'] = new_status
        
        # Track status evolution
        if 'status_evolution' not in existing:
            existing['status_evolution'] = []
        
        if source_doc:
            existing['status_evolution'].append({
                'date': new.get('status_date') or datetime.now().isoformat()[:10],
                'status': new_status,
                'source': source_doc
            })
        
        # Update other fields - prioritize Arabic over English
        for key, value in new.items():
            if key not in ['charge_entity_id', 'status', 'status_evolution'] and value:
                # For Arabic/English pairs, prefer Arabic
                if key == 'description_en' and existing.get('description_ar'):
                    # Don't overwrite Arabic description with English
                    continue
                elif key == 'description_ar':
                    # Always prefer Arabic description
                    existing[key] = value
                elif key == 'law_name_en' and existing.get('law_name_ar'):
                    # Don't overwrite Arabic law name with English
                    continue
                elif key == 'law_name_ar':
                    # Always prefer Arabic law name
                    existing[key] = value
                elif not existing.get(key):
                    # For other fields, update if missing
                    existing[key] = value
    
    def _normalize_charges(self, charges: List[Dict]) -> List[Dict]:
        """Normalize charges and assign entity IDs"""
        normalized = []
        for i, charge in enumerate(charges, 1):
            charge['charge_entity_id'] = f"C{i:03d}"
            normalized.append(charge)
        return normalized
    
    def _merge_dates(self, existing: Dict, new: Dict) -> Dict:
        """Merge dates, keeping earliest for start dates, latest for end dates"""
        merged = existing.copy() if existing else {}
        
        start_date_keys = ['incident', 'report_filed', 'investigation', 'case_transfer', 'first_hearing']
        end_date_keys = ['judgment', 'appeal_deadline']
        
        for key, value in new.items():
            if not value:
                continue
            
            if key in start_date_keys:
                # Keep earliest date
                if not merged.get(key) or value < merged[key]:
                    merged[key] = value
            elif key in end_date_keys:
                # Keep latest date
                if not merged.get(key) or value > merged[key]:
                    merged[key] = value
            else:
                # Keep if not present
                if not merged.get(key):
                    merged[key] = value
        
        return merged
    
    def _merge_locations(self, existing: Dict, new: Dict) -> Dict:
        """Merge locations, prefer non-null values"""
        merged = existing.copy() if existing else {}
        
        for key, value in new.items():
            if value and not merged.get(key):
                merged[key] = value
        
        return merged
    
    def _merge_judgments(self, existing: List[Dict], new: List[Dict]) -> List[Dict]:
        """Merge judgments, append new ones"""
        merged = existing.copy() if existing else []
        merged.extend(new)
        # Sort by date (most recent first)
        merged.sort(key=lambda x: x.get('judgment_date', ''), reverse=True)
        return merged
    
    def _merge_financial(self, existing: Dict, new: Dict) -> Dict:
        """Merge financial data"""
        merged = existing.copy() if existing else {'fines': [], 'damages': [], 'bail': None}
        
        # Merge fines
        if new.get('fines'):
            merged['fines'].extend(new['fines'])
        
        # Merge damages
        if new.get('damages'):
            merged['damages'].extend(new['damages'])
        
        # Update bail if higher
        if new.get('bail'):
            if not merged.get('bail') or new['bail'] > merged['bail']:
                merged['bail'] = new['bail']
        
        return merged
    
    def _merge_evidence(self, existing: List[Dict], new: List[Dict]) -> List[Dict]:
        """Merge evidence, deduplicate by description"""
        merged = existing.copy() if existing else []
        limits = CONFIG['processing']['entity_limits']
        max_evidence = limits['max_evidence_per_case']
        
        # STEP 1: Pre-deduplicate the new evidence list itself
        original_new_count = len(new)
        new = self._deduplicate_evidence_list(new)
        if original_new_count > len(new):
            logger.info(
                f"Pre-deduplication: {original_new_count} -> {len(new)} unique evidence items"
            )
        
        # Check if existing evidence already exceeds limit
        if len(merged) >= max_evidence:
            logger.warning(
                f"Case already has {len(merged)} evidence items (limit: {max_evidence}). "
                f"Skipping merge of {len(new)} new evidence items"
            )
            return merged
        
        # STEP 2: Create lookup index for faster matching
        existing_index = self._create_evidence_index(merged)
        
        evidence_added = 0
        for new_ev in new:
            # Stop if we've reached the limit
            if len(merged) >= max_evidence:
                logger.warning(
                    f"Reached evidence limit ({max_evidence}) while merging. "
                    f"Skipping remaining {len(new) - evidence_added} evidence items"
                )
                break
            
            # Use indexed lookup for faster matching
            matched_ev = self._find_matching_evidence_indexed(new_ev, existing_index, merged)
            
            if not matched_ev:
                merged.append(new_ev)
                # Update index
                self._add_evidence_to_index(new_ev, existing_index, len(merged) - 1)
                evidence_added += 1
        
        # Final validation - ensure we don't exceed limit
        if len(merged) > max_evidence:
            logger.error(
                f"ERROR: Merged evidence ({len(merged)}) exceed limit ({max_evidence}). "
                f"Truncating to limit."
            )
            merged = merged[:max_evidence]
        
        return merged
    
    def _deduplicate_evidence_list(self, evidence: List[Dict]) -> List[Dict]:
        """Deduplicate evidence within a list before merging"""
        seen = set()
        unique_evidence = []
        
        for ev in evidence:
            ev_key = self._get_evidence_key(ev)
            
            if ev_key and ev_key not in seen:
                seen.add(ev_key)
                unique_evidence.append(ev)
            else:
                logger.debug(f"Skipping duplicate evidence: {ev.get('type')} - {ev.get('description_ar', '')[:50]}")
        
        duplicates_removed = len(evidence) - len(unique_evidence)
        if duplicates_removed > 0:
            logger.debug(f"Removed {duplicates_removed} duplicate evidence items from new list")
        
        return unique_evidence
    
    def _get_evidence_key(self, evidence: Dict) -> Optional[str]:
        """Create a unique key for evidence matching - prioritize Arabic"""
        ev_type = (evidence.get('type') or '').strip()
        desc_ar = self._normalize_name(evidence.get('description_ar', ''))
        desc_en = self._normalize_name(evidence.get('description_en', ''))
        
        # Use type + description for key - prioritize Arabic
        if ev_type and desc_ar:
            return f"{ev_type}:{desc_ar}"
        elif ev_type and desc_en:
            return f"{ev_type}:{desc_en}"
        elif desc_ar:
            return f"desc_ar:{desc_ar}"
        elif desc_en:
            return f"desc_en:{desc_en}"
        
        return None
    
    def _create_evidence_index(self, evidence: List[Dict]) -> Dict[str, int]:
        """Create an index for fast evidence lookup"""
        index = {}
        for idx, ev in enumerate(evidence):
            ev_key = self._get_evidence_key(ev)
            if ev_key:
                if ev_key not in index:
                    index[ev_key] = idx
        return index
    
    def _add_evidence_to_index(self, evidence: Dict, index: Dict[str, int], position: int):
        """Add evidence to index"""
        ev_key = self._get_evidence_key(evidence)
        if ev_key:
            index[ev_key] = position
    
    def _find_matching_evidence_indexed(self, new_ev: Dict, index: Dict[str, int], 
                                       merged: List[Dict]) -> Optional[Dict]:
        """Find matching evidence using index (fast)"""
        # Try exact key match first
        ev_key = self._get_evidence_key(new_ev)
        if ev_key and ev_key in index:
            return merged[index[ev_key]]
        
        # Fallback to fuzzy matching
        for existing_ev in merged:
            if self._evidence_match(existing_ev, new_ev):
                return existing_ev
        
        return None
    
    def _evidence_match(self, ev1: Dict, ev2: Dict) -> bool:
        """Check if two evidence items are the same - prioritize Arabic matching"""
        desc1_ar = self._normalize_name(ev1.get('description_ar', ''))
        desc2_ar = self._normalize_name(ev2.get('description_ar', ''))
        desc1_en = self._normalize_name(ev1.get('description_en', ''))
        desc2_en = self._normalize_name(ev2.get('description_en', ''))
        
        # Match by normalized Arabic description first (prioritize Arabic)
        if desc1_ar and desc2_ar:
            if desc1_ar == desc2_ar:
                return True
            similarity = SequenceMatcher(None, desc1_ar, desc2_ar).ratio()
            if similarity > 0.85:
                return True
        
        # Fallback to English description matching only if Arabic not available
        if desc1_en and desc2_en:
            if desc1_en == desc2_en:
                return True
            similarity = SequenceMatcher(None, desc1_en, desc2_en).ratio()
            if similarity > 0.85:
                return True
        
        return False
    
    def _merge_timeline(self, existing: List[Dict], new_entities: Dict, 
                       source_doc: str = None) -> List[Dict]:
        """Merge timeline events"""
        timeline = existing.copy() if existing else []
        
        # Add events from new entities
        dates = new_entities.get('dates', {})
        for date_type, date_value in dates.items():
            if date_value:
                timeline.append({
                    'date': date_value,
                    'event_type': date_type,
                    'source_document': source_doc or 'unknown'
                })
        
        # Sort by date
        timeline.sort(key=lambda x: x.get('date', ''))
        return timeline
    
    def _merge_case_status(self, existing: Dict, new: Dict) -> Dict:
        """Merge case status, prefer more advanced status"""
        status_priority = {
            'open': 1,
            'in_trial': 2,
            'closed': 3,
            'dismissed': 4,
            'appealed': 5
        }
        
        merged = existing.copy() if existing else {}
        
        existing_status = existing.get('current_status', 'open')
        new_status = new.get('current_status', 'open')
        
        if status_priority.get(new_status, 0) > status_priority.get(existing_status, 0):
            merged['current_status'] = new_status
            merged['status_date'] = new.get('status_date') or datetime.now().isoformat()[:10]
        
        # Update other fields
        for key, value in new.items():
            if value and not merged.get(key):
                merged[key] = value
        
        return merged
    
    def _merge_legal_references(self, existing: List[Dict], new: List[Dict]) -> List[Dict]:
        """Merge legal references, deduplicate"""
        merged = existing.copy() if existing else []
        
        for new_ref in new:
            is_duplicate = False
            for existing_ref in merged:
                if (existing_ref.get('article') == new_ref.get('article') and
                    existing_ref.get('law_year') == new_ref.get('law_year')):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                merged.append(new_ref)
        
        return merged
    
    def _create_initial_timeline(self, entities: Dict) -> List[Dict]:
        """Create initial timeline from entities"""
        timeline = []
        dates = entities.get('dates', {})
        
        for date_type, date_value in dates.items():
            if date_value:
                timeline.append({
                    'date': date_value,
                    'event_type': date_type,
                    'source_document': 'initial'
                })
        
        timeline.sort(key=lambda x: x.get('date', ''))
        return timeline
    
    # ========================================================================
    # Data Optimization Methods (to prevent JSONB size limit errors)
    # ========================================================================
    
    def _optimize_case_data(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Optimize case data to prevent JSONB size limit errors
        Truncates long text fields and limits array sizes
        
        Args:
            case_data: Case data dictionary
            
        Returns:
            Optimized case data
        """
        MAX_TEXT_LENGTH = 10000  # 10KB per text field
        MAX_ARRAY_SIZE = 1000  # Max items in arrays
        
        optimized = {}
        
        for key, value in case_data.items():
            if isinstance(value, dict):
                optimized[key] = self._optimize_dict(value, MAX_TEXT_LENGTH)
            elif isinstance(value, list):
                # Limit array size
                if len(value) > MAX_ARRAY_SIZE:
                    logger.warning(f"Truncating {key} array from {len(value)} to {MAX_ARRAY_SIZE} items")
                    value = value[:MAX_ARRAY_SIZE]
                optimized[key] = [self._optimize_dict(item, MAX_TEXT_LENGTH) if isinstance(item, dict) else item 
                                 for item in value]
            else:
                optimized[key] = value
        
        return optimized
    
    def _optimize_dict(self, data: Dict, max_length: int) -> Dict:
        """
        Optimize dictionary by truncating long text fields
        
        Args:
            data: Dictionary to optimize
            max_length: Maximum length for text fields
            
        Returns:
            Optimized dictionary
        """
        optimized = {}
        for key, value in data.items():
            if isinstance(value, str) and len(value) > max_length:
                optimized[key] = value[:max_length] + "...[truncated]"
                logger.debug(f"Truncated {key} from {len(value)} to {max_length} chars")
            elif isinstance(value, dict):
                optimized[key] = self._optimize_dict(value, max_length)
            elif isinstance(value, list):
                optimized[key] = [self._optimize_dict(item, max_length) if isinstance(item, dict) else item 
                                 for item in value]
            else:
                optimized[key] = value
        return optimized

