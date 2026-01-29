#!/usr/bin/env python3
"""
IMPROVED Case Matching & Merging System
Fixes the data linking and conflict resolution issues
Handles documents arriving in any order with partial reference numbers
"""

import logging
import re
from typing import Dict, Any, Optional, List, Set, Tuple
from dataclasses import dataclass
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def enhanced_normalize_reference_number(ref: str) -> List[str]:
    """
    Enhanced normalization that returns ALL possible variations
    This fixes the bidirectional matching issue (2025/2552 ↔ 2552/2025)
    """
    if not ref or not isinstance(ref, str):
        return []
    
    ref = ref.strip()
    variations = []
    
    # Extract all digit sequences
    digits = re.findall(r'\d+', ref)
    if len(digits) >= 2:
        num1, num2 = digits[0], digits[1]
        
        # Add both orders
        variations.append(f"{num1}/{num2}")
        variations.append(f"{num2}/{num1}")
        
        # Add without separator
        variations.append(f"{num1}{num2}")
        variations.append(f"{num2}{num1}")
        
        # Add with dash
        variations.append(f"{num1}-{num2}")
        variations.append(f"{num2}-{num1}")
    
    # Add original cleaned version
    cleaned = re.sub(r'[^\d/\-]', '', ref)
    if cleaned and cleaned not in variations:
        variations.append(cleaned)
    
    # Add core number only (first digit sequence)
    if digits:
        variations.append(digits[0])
    
    # Remove duplicates while preserving order
    seen = set()
    result = []
    for var in variations:
        if var and var not in seen:
            seen.add(var)
            result.append(var)
    
    return result


def extract_core_case_numbers(ref: str) -> Dict[str, List[str]]:
    """
    Extract core identifying numbers from complex reference strings
    Returns multiple possible variations for better matching
    """
    if not ref:
        return {}
    
    result = {
        'core_numbers': [],
        'year': None,
        'variations': []
    }
    
    # Extract year
    year_match = re.search(r'(20\d{2})', ref)
    if year_match:
        result['year'] = year_match.group(1)
    
    # Extract all numbers
    numbers = re.findall(r'\d+', ref)
    
    if numbers:
        # Core number is usually the first or largest
        result['core_numbers'] = numbers
        
        # Generate variations
        if len(numbers) >= 2:
            for i in range(len(numbers)):
                for j in range(i + 1, len(numbers)):
                    result['variations'].extend([
                        f"{numbers[i]}/{numbers[j]}",
                        f"{numbers[j]}/{numbers[i]}"
                    ])
    
    return result


class EnhancedCaseMatcher:
    """
    Enhanced case matching with better normalization and conflict resolution
    """
    
    def __init__(self, db_manager):
        self.db = db_manager
        logger.info("Enhanced Case Matcher initialized")
    
    def find_or_create_case(self, references, document_metadata: Dict[str, Any] = None) -> int:
        """
        Enhanced case finding with better matching and merging
        """
        
        if not self._has_any_reference(references):
            logger.warning("No reference numbers provided, creating orphan case")
            return self._create_new_case({}, document_metadata)
        
        # Step 1: Try multiple matching strategies
        existing_cases = self._find_all_potential_matches(references)
        
        if existing_cases:
            # Step 2: If multiple potential matches, merge them
            primary_case = self._resolve_multiple_matches(existing_cases, references)
            
            logger.info(f"Found existing case: {primary_case['case_id']}")
            
            # Step 3: Update with new references
            self._merge_references(primary_case['case_id'], primary_case, references)
            
            # Step 4: Update metadata
            if document_metadata:
                self._update_case_metadata(primary_case['case_id'], document_metadata)
            
            return primary_case['case_id']
        
        # Step 3: Create new case
        logger.info("No existing case found, creating new case")
        return self._create_new_case(self._get_available_references(references), document_metadata)
    
    def _has_any_reference(self, references) -> bool:
        """Check if any reference exists"""
        return any([
            getattr(references, 'court_case_number', None),
            getattr(references, 'prosecution_case_number', None),
            getattr(references, 'police_report_number', None),
            getattr(references, 'internal_report_number', None)
        ])
    
    def _get_available_references(self, references) -> Dict[str, str]:
        """Get all non-null references"""
        refs = {}
        for field in ['court_case_number', 'prosecution_case_number', 'police_report_number', 'internal_report_number']:
            value = getattr(references, field, None)
            if value:
                refs[field] = value
        return refs
    
    def _find_all_potential_matches(self, references) -> List[Dict[str, Any]]:
        """
        Find ALL potential case matches using enhanced matching
        """
        potential_matches = []
        
        # Get all reference variations
        all_variations = {}
        
        for field in ['court_case_number', 'prosecution_case_number', 'police_report_number', 'internal_report_number']:
            value = getattr(references, field, None)
            if value:
                all_variations[field] = enhanced_normalize_reference_number(value)
        
        # Build comprehensive query
        query_parts = []
        query_params = []
        
        for field, variations in all_variations.items():
            if variations:
                # Create OR conditions for all variations
                field_conditions = []
                for variation in variations[:10]:  # Limit to first 10 variations to avoid huge queries
                    field_conditions.extend([
                        f"TRIM({field}) = TRIM(%s)",
                        f"TRIM(REGEXP_REPLACE({field}, '[^0-9/-]', '', 'g')) = TRIM(%s)",
                        f"TRIM({field}) LIKE %s",
                        f"TRIM({field}) LIKE %s"
                    ])
                    query_params.extend([
                        variation,
                        variation,
                        f"%{variation}%",
                        f"%{variation.replace('/', '')}%"
                    ])
                
                if field_conditions:
                    query_parts.append(f"({' OR '.join(field_conditions)})")
        
        if not query_parts:
            return []
        
        query = f"""
            SELECT DISTINCT * FROM cases 
            WHERE ({' OR '.join(query_parts)})
            AND is_orphan = FALSE
            ORDER BY created_at ASC
        """
        
        from psycopg2.extras import RealDictCursor
        try:
            with self.db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, query_params)
                results = cursor.fetchall()
                
                logger.info(f"Found {len(results)} potential case matches")
                for result in results:
                    logger.info(f"  - Case {result['case_id']}: court={result.get('court_case_number')}, prosecution={result.get('prosecution_case_number')}, police={result.get('police_report_number')}")
                
                return results
                
        except Exception as e:
            logger.error(f"Error in case matching query: {str(e)}")
            return []
    
    def _resolve_multiple_matches(self, matches: List[Dict[str, Any]], references) -> Dict[str, Any]:
        """
        When multiple cases match, determine which one to use as primary
        and mark others for merging
        """
        if len(matches) == 1:
            return matches[0]
        
        logger.warning(f"Found {len(matches)} potential case matches - resolving conflicts")
        
        # Scoring system to find the best primary case
        scored_matches = []
        
        for match in matches:
            score = 0
            
            # Prefer cases with more complete information
            if match.get('court_case_number'):
                score += 10
            if match.get('prosecution_case_number'):
                score += 8  
            if match.get('police_report_number'):
                score += 6
            if match.get('internal_report_number'):
                score += 4
            
            # Prefer newer cases (they might have more complete info)
            if match.get('updated_at'):
                # More recent = higher score
                score += 1
            
            # Prefer non-orphan cases
            if not match.get('is_orphan', False):
                score += 5
            
            # Prefer cases with status information
            if match.get('current_status') and match.get('current_status') != 'open':
                score += 3
            
            scored_matches.append((score, match))
        
        # Sort by score (highest first)
        scored_matches.sort(key=lambda x: x[0], reverse=True)
        primary_case = scored_matches[0][1]
        
        logger.info(f"Selected case {primary_case['case_id']} as primary (score: {scored_matches[0][0]})")
        
        # TODO: Mark other cases for merging/deletion
        duplicate_cases = [match for score, match in scored_matches[1:]]
        if duplicate_cases:
            self._mark_cases_for_merging(primary_case['case_id'], duplicate_cases)
        
        return primary_case
    
    def _mark_cases_for_merging(self, primary_case_id: int, duplicate_cases: List[Dict[str, Any]]):
        """
        Mark duplicate cases for merging - for now just log them
        In production, you'd want to merge data and mark duplicates
        """
        duplicate_ids = [case['case_id'] for case in duplicate_cases]
        logger.warning(f"DUPLICATE CASES DETECTED: Primary={primary_case_id}, Duplicates={duplicate_ids}")
        
        # For now, just log. In production you'd:
        # 1. Copy any missing data from duplicates to primary
        # 2. Update all documents/parties to point to primary case
        # 3. Mark duplicates as merged/deleted
        
        # Simple approach: mark duplicates with a flag
        try:
            from psycopg2.extras import RealDictCursor
            with self.db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                for dup_id in duplicate_ids:
                    cursor.execute(
                        "UPDATE cases SET case_summary_ar = %s, updated_at = NOW() WHERE case_id = %s",
                        (f"DUPLICATE OF CASE {primary_case_id} - NEEDS MERGING", dup_id)
                    )
                self.db.connection.commit()
                logger.info(f"Marked {len(duplicate_ids)} cases as duplicates")
        except Exception as e:
            logger.error(f"Error marking duplicates: {str(e)}")
    
    def _merge_references(self, case_id: int, existing_case: Dict[str, Any], new_references):
        """
        Merge new reference numbers into existing case
        """
        updates = {}
        
        # Merge each reference type
        for field in ['court_case_number', 'prosecution_case_number', 'police_report_number', 'internal_report_number']:
            existing_value = existing_case.get(field)
            new_value = getattr(new_references, field, None)
            
            if new_value and not existing_value:
                # Add missing reference
                updates[field] = new_value
                logger.info(f"Adding missing {field}: {new_value}")
            elif new_value and existing_value and existing_value != new_value:
                # Handle conflict - for now, keep more complete version
                if len(new_value) > len(existing_value):
                    updates[field] = new_value
                    logger.info(f"Updating {field} with more complete version: {existing_value} -> {new_value}")
        
        if updates:
            self._update_case(case_id, updates)
    
    def _update_case(self, case_id: int, updates: Dict[str, Any]):
        """Update case with new information"""
        if not updates:
            return
            
        updates['updated_at'] = datetime.now()
        
        from psycopg2.extras import RealDictCursor
        with self.db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            fields = list(updates.keys())
            values = list(updates.values())
            set_clause = ', '.join([f"{f} = %s" for f in fields])
            
            sql = f"UPDATE cases SET {set_clause} WHERE case_id = %s"
            cursor.execute(sql, values + [case_id])
            self.db.connection.commit()
            logger.info(f"Updated case {case_id} with: {list(updates.keys())}")
    
    def _update_case_metadata(self, case_id: int, metadata: Dict[str, Any]):
        """Update case with metadata from documents"""
        updates = {}
        
        # Extract useful metadata
        if metadata.get('incident_date') and not updates.get('incident_date'):
            updates['incident_date'] = metadata['incident_date']
        
        if metadata.get('report_date') and not updates.get('report_date'):
            updates['report_date'] = metadata['report_date']
        
        if metadata.get('court_name') and not updates.get('court_name'):
            updates['court_name'] = metadata['court_name']
        
        if metadata.get('police_station') and not updates.get('police_station'):
            updates['police_station'] = metadata['police_station']
        
        if metadata.get('case_status') and metadata['case_status'] != 'open':
            updates['current_status'] = metadata['case_status']
            updates['status_date'] = datetime.now()
        
        if updates:
            self._update_case(case_id, updates)
    
    def _create_new_case(self, references: Dict[str, str], metadata: Dict[str, Any] = None) -> int:
        """Create new case with references and metadata"""
        case_data = {
            'case_type': 'criminal',
            'current_status': 'open',
            'status_date': datetime.now(),
            'created_at': datetime.now(),
            'updated_at': datetime.now(),
            'is_orphan': False
        }
        
        # Add references
        case_data.update(references)
        
        # Add metadata if available
        if metadata:
            if metadata.get('incident_date'):
                case_data['incident_date'] = metadata['incident_date']
            if metadata.get('report_date'):
                case_data['report_date'] = metadata['report_date']
            if metadata.get('court_name'):
                case_data['court_name'] = metadata['court_name']
            if metadata.get('police_station'):
                case_data['police_station'] = metadata['police_station']
            if metadata.get('case_status') and metadata['case_status'] != 'open':
                case_data['current_status'] = metadata['case_status']
        
        # Insert case
        from psycopg2.extras import RealDictCursor
        with self.db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            fields = [k for k, v in case_data.items() if v is not None]
            values = [case_data[k] for k in fields]
            placeholders = ', '.join(['%s'] * len(fields))
            
            sql = f"""
                INSERT INTO cases ({', '.join(fields)})
                VALUES ({placeholders})
                RETURNING case_id
            """
            cursor.execute(sql, values)
            case_id = cursor.fetchone()['case_id']
            self.db.connection.commit()
            
            logger.info(f"Created new case: {case_id}")
            return case_id


def test_enhanced_normalization():
    """Test the enhanced normalization function"""
    test_cases = [
        "2552/2025/جنح متنوعة/ابتدائي",
        "2025/2552",
        "303/2025/نيابة الشمال", 
        "2590/2025/مركز ام صلال",
        "10/4554",
        "4308/2025"
    ]
    
    print("=== Enhanced Normalization Test ===")
    for test_case in test_cases:
        variations = enhanced_normalize_reference_number(test_case)
        print(f"'{test_case}' -> {variations}")


if __name__ == '__main__':
    test_enhanced_normalization()
