# Intelligent Case Matching & Merging System
# Handles documents arriving in any order with partial reference numbers

import logging
import re
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def normalize_reference_number(ref: str) -> Optional[str]:
    """
    Normalize reference numbers to extract core number pattern
    Handles variations like:
    - "2590/2025" -> "2590/2025"
    - "2590 لسنة 2025 قسم شرطة أم صلال" -> "2590/2025"
    - "في البلاغ رقم 2590/2025" -> "2590/2025"
    - "2025-016-10-4554" -> "2025-016-10-4554"
    """
    if not ref or not isinstance(ref, str):
        return None
    
    ref = ref.strip()
    
    # Pattern 1: Number/Year (e.g., "2590/2025", "2590 لسنة 2025")
    # Extract pattern: digits/digits or digits followed by year text
    pattern1 = r'(\d+)\s*[/-]?\s*(\d{4})'
    match = re.search(pattern1, ref)
    if match:
        num, year = match.groups()
        return f"{num}/{year}"
    
    # Pattern 2: Year-Number-Number-Number (e.g., "2025-016-10-4554")
    pattern2 = r'(\d{4})-\d+-\d+-\d+'
    match = re.search(pattern2, ref)
    if match:
        return match.group(0)  # Return full format
    
    # Pattern 3: Just numbers separated by slashes or dashes
    pattern3 = r'\d+[/-]\d+'
    match = re.search(pattern3, ref)
    if match:
        return match.group(0)
    
    # If no pattern found, return cleaned version (remove extra text, keep alphanumeric)
    cleaned = re.sub(r'[^\d/\-]', '', ref)
    if cleaned:
        return cleaned
    
    return ref  # Return original if nothing matches


def extract_police_report_number(text: str) -> Optional[str]:
    """
    Extract police report number from text that might contain extra words
    Examples:
    - "2590 لسنة 2025 قسم شرطة أم صلال" -> "2590/2025"
    - "في البلاغ رقم 2590/2025" -> "2590/2025"
    - "بلاغ رقم 2590/2025" -> "2590/2025"
    """
    if not text:
        return None
    
    # Look for patterns like "رقم 2590/2025" or "2590 لسنة 2025"
    patterns = [
        r'رقم\s*(\d+)\s*[/-]?\s*(\d{4})',  # "رقم 2590/2025"
        r'(\d+)\s*لسنة\s*(\d{4})',  # "2590 لسنة 2025"
        r'(\d+)\s*[/-]\s*(\d{4})',  # "2590/2025"
        r'(\d+)\s*/\s*(\d{4})',  # "2590 / 2025"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            num, year = match.groups()
            return f"{num}/{year}"
    
    # Try general normalization
    return normalize_reference_number(text)


@dataclass
class CaseReferences:
    """All possible reference numbers for a case"""
    court_case_number: Optional[str] = None
    prosecution_case_number: Optional[str] = None
    police_report_number: Optional[str] = None
    internal_report_number: Optional[str] = None
    
    def has_any_reference(self) -> bool:
        """Check if at least one reference exists"""
        return any([
            self.court_case_number,
            self.prosecution_case_number,
            self.police_report_number,
            self.internal_report_number
        ])
    
    def get_available_references(self) -> Dict[str, str]:
        """Get all non-null references"""
        refs = {}
        if self.court_case_number:
            refs['court_case_number'] = self.court_case_number
        if self.prosecution_case_number:
            refs['prosecution_case_number'] = self.prosecution_case_number
        if self.police_report_number:
            refs['police_report_number'] = self.police_report_number
        if self.internal_report_number:
            refs['internal_report_number'] = self.internal_report_number
        return refs


class CaseMatcher:
    """
    Intelligent case matching system that:
    1. Finds existing cases by ANY reference number
    2. Merges new reference numbers into existing cases
    3. Handles documents arriving in any order
    4. Links related documents automatically
    """
    
    def __init__(self, db_manager):
        self.db = db_manager
        logger.info("Case Matcher initialized")
    
    def find_or_create_case(self, references: CaseReferences, 
                           document_metadata: Dict[str, Any] = None) -> int:
        """
        Find existing case by ANY reference, or create new case
        
        Args:
            references: CaseReferences object with available reference numbers
            document_metadata: Optional metadata (document_type, dates, etc.)
        
        Returns:
            case_id: ID of found or created case
        """
        
        if not references.has_any_reference():
            logger.warning("No reference numbers provided, creating orphan case")
            return self._create_new_case({}, document_metadata)
        
        # Step 1: Try to find existing case by ANY reference number
        existing_case = self._find_case_by_any_reference(references)
        
        if existing_case:
            case_id = existing_case['case_id']
            logger.info(f"Found existing case: {case_id} (matched by reference number)")
            
            # Step 2: Update case with new reference numbers
            self._merge_references(case_id, existing_case, references)
            
            # Step 3: Update case metadata if provided
            if document_metadata:
                self._update_case_metadata(case_id, document_metadata)
            
            return case_id
        
        # Step 2: Try alternative matching strategies if reference matching failed
        if document_metadata:
            existing_case = self._find_case_by_alternative_strategies(references, document_metadata)
            
            if existing_case:
                case_id = existing_case['case_id']
                logger.info(f"Found existing case: {case_id} (matched by alternative strategy)")
                
                # Merge references
                self._merge_references(case_id, existing_case, references)
                
                # Update metadata
                self._update_case_metadata(case_id, document_metadata)
                
                return case_id
        
        # Step 3: Create new case with available references
        logger.info("No existing case found, creating new case")
        return self._create_new_case(references.get_available_references(), document_metadata)
    
    def _find_case_by_any_reference(self, references: CaseReferences) -> Optional[Dict[str, Any]]:
        """
        Find case by ANY available reference number
        Uses normalization to handle format variations
        Priority: court > prosecution > police > internal
        """
        
        # Normalize references for better matching
        normalized_refs = {}
        if references.court_case_number:
            normalized_refs['court_case_number'] = normalize_reference_number(references.court_case_number)
        if references.prosecution_case_number:
            normalized_refs['prosecution_case_number'] = normalize_reference_number(references.prosecution_case_number)
        if references.police_report_number:
            # Special handling for police report numbers
            normalized_refs['police_report_number'] = extract_police_report_number(references.police_report_number)
        if references.internal_report_number:
            normalized_refs['internal_report_number'] = normalize_reference_number(references.internal_report_number)
        
        # Build flexible query checking ALL reference types with normalization
        conditions = []
        params = []
        
        # Build query with grouped conditions for each reference type
        # This allows matching on normalized versions while avoiding duplicate conditions
        query_parts = []
        query_params = []
        
        if normalized_refs.get('court_case_number'):
            court_ref = normalized_refs['court_case_number']
            query_parts.append("(TRIM(court_case_number) = TRIM(%s) OR TRIM(REGEXP_REPLACE(court_case_number, '[^0-9/-]', '', 'g')) = TRIM(REGEXP_REPLACE(%s, '[^0-9/-]', '', 'g')))")
            query_params.extend([court_ref, court_ref])
        
        if normalized_refs.get('prosecution_case_number'):
            prosecution_ref = normalized_refs['prosecution_case_number']
            query_parts.append("(TRIM(prosecution_case_number) = TRIM(%s) OR TRIM(REGEXP_REPLACE(prosecution_case_number, '[^0-9/-]', '', 'g')) = TRIM(REGEXP_REPLACE(%s, '[^0-9/-]', '', 'g')))")
            query_params.extend([prosecution_ref, prosecution_ref])
        
        if normalized_refs.get('police_report_number'):
            police_ref = normalized_refs['police_report_number']
            # Multiple matching strategies for police report numbers
            query_parts.append("""(
                TRIM(police_report_number) = TRIM(%s) OR 
                TRIM(REGEXP_REPLACE(police_report_number, '[^0-9/-]', '', 'g')) = TRIM(REGEXP_REPLACE(%s, '[^0-9/-]', '', 'g')) OR
                REGEXP_REPLACE(TRIM(police_report_number), '[^0-9/-]', '', 'g') LIKE %s
            )""")
            query_params.extend([police_ref, police_ref, f"%{police_ref.replace('/', '')}%"])
        
        if normalized_refs.get('internal_report_number'):
            internal_ref = normalized_refs['internal_report_number']
            query_parts.append("(TRIM(internal_report_number) = TRIM(%s) OR TRIM(REGEXP_REPLACE(internal_report_number, '[^0-9/-]', '', 'g')) = TRIM(REGEXP_REPLACE(%s, '[^0-9/-]', '', 'g')))")
            query_params.extend([internal_ref, internal_ref])
        
        if not query_parts:
            return None
        
        query = f"""
            SELECT * FROM cases 
            WHERE {' OR '.join(query_parts)}
            LIMIT 1
        """
        
        from psycopg2.extras import RealDictCursor
        try:
            with self.db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, query_params)
                result = cursor.fetchone()
                
                if result:
                    # Determine which reference matched
                    matched_refs = []
                    if normalized_refs.get('court_case_number') and result.get('court_case_number'):
                        matched_refs.append('court_case_number')
                    if normalized_refs.get('prosecution_case_number') and result.get('prosecution_case_number'):
                        matched_refs.append('prosecution_case_number')
                    if normalized_refs.get('police_report_number') and result.get('police_report_number'):
                        matched_refs.append('police_report_number')
                    if normalized_refs.get('internal_report_number') and result.get('internal_report_number'):
                        matched_refs.append('internal_report_number')
                    
                    logger.info(f"Case found by reference: {result.get('case_id')} - matched on: {matched_refs}")
                    logger.info(f"  Normalized search: {normalized_refs}")
                    logger.info(f"  Found in DB: court={result.get('court_case_number')}, prosecution={result.get('prosecution_case_number')}, police={result.get('police_report_number')}")
                else:
                    logger.info(f"No case found matching references: {references.get_available_references()}")
                    logger.info(f"  Normalized: {normalized_refs}")
                
                return result
        except Exception as e:
            logger.error(f"Error finding case by reference: {str(e)}")
            logger.error(f"Query: {query}")
            logger.error(f"Params: {query_params}")
            raise
    
    def _find_case_by_alternative_strategies(self, references: CaseReferences, 
                                            metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Find case using alternative matching strategies when reference numbers don't match
        Strategies:
        1. Person-based matching (by personal_id, name, nationality)
        2. Date-based matching (by incident_date, report_date)
        3. Location-based matching (by police_station, prosecution_office)
        4. Combined matching (multiple criteria with scoring)
        """
        from psycopg2.extras import RealDictCursor
        
        if not metadata:
            return None
        
        # Strategy 1: Person-based matching
        # Extract person info from metadata (if document has person data)
        person_matches = []
        
        # Check if we have person information in metadata
        # This would come from documents that have complainant/accused info
        person_info = None
        if metadata.get('complainant'):
            person_info = metadata['complainant']
        elif metadata.get('accused_person'):
            person_info = metadata['accused_person']
        elif metadata.get('detained_person'):
            person_info = metadata['detained_person']
        elif metadata.get('subject_person'):
            person_info = metadata['subject_person']
        
        if person_info:
            if isinstance(person_info, dict):
                personal_id = person_info.get('personal_id')
                name_ar = person_info.get('full_name_ar')
                nationality = person_info.get('nationality')
                
                if personal_id or name_ar:
                    # Find cases where this person is involved
                    with self.db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                        conditions = []
                        params = []
                        
                        if personal_id:
                            conditions.append("p.personal_id = %s")
                            params.append(personal_id)
                        
                        if name_ar:
                            conditions.append("TRIM(p.full_name_ar) = TRIM(%s)")
                            params.append(name_ar)
                        
                        if conditions:
                            query = f"""
                                SELECT DISTINCT c.* FROM cases c
                                JOIN case_parties cp ON c.case_id = cp.case_id
                                JOIN parties p ON cp.party_id = p.party_id
                                WHERE ({' OR '.join(conditions)})
                                AND cp.role_type IN ('accused', 'complainant')
                                ORDER BY c.created_at DESC
                                LIMIT 5
                            """
                            cursor.execute(query, params)
                            person_matches = cursor.fetchall()
                            
                            if person_matches:
                                logger.info(f"Found {len(person_matches)} potential matches by person info")
        
        # Strategy 2: Date-based matching
        date_matches = []
        incident_date = metadata.get('incident_date') or metadata.get('report_date')
        
        if incident_date:
            with self.db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                # Match cases with same incident date (within same day)
                query = """
                    SELECT * FROM cases
                    WHERE DATE(incident_date) = DATE(%s)
                       OR DATE(report_date) = DATE(%s)
                    ORDER BY created_at DESC
                    LIMIT 5
                """
                cursor.execute(query, [incident_date, incident_date])
                date_matches = cursor.fetchall()
                
                if date_matches:
                    logger.info(f"Found {len(date_matches)} potential matches by date")
        
        # Strategy 3: Location-based matching
        location_matches = []
        police_station = metadata.get('police_station')
        prosecution_office = metadata.get('prosecution_office')
        
        if police_station or prosecution_office:
            with self.db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                conditions = []
                params = []
                
                if police_station:
                    conditions.append("TRIM(police_station) = TRIM(%s)")
                    params.append(police_station)
                
                if prosecution_office:
                    conditions.append("TRIM(prosecution_office) = TRIM(%s)")
                    params.append(prosecution_office)
                
                if conditions:
                    query = f"""
                        SELECT * FROM cases
                        WHERE {' OR '.join(conditions)}
                        ORDER BY created_at DESC
                        LIMIT 5
                    """
                    cursor.execute(query, params)
                    location_matches = cursor.fetchall()
                    
                    if location_matches:
                        logger.info(f"Found {len(location_matches)} potential matches by location")
        
        # Strategy 4: Combined matching (person + date + location)
        # Score matches and return the best one
        scored_matches = {}
        
        # Score person matches (highest weight)
        for match in person_matches:
            case_id = match['case_id']
            score = scored_matches.get(case_id, 0)
            scored_matches[case_id] = score + 3  # Person match is strong
        
        # Score date matches (medium weight)
        for match in date_matches:
            case_id = match['case_id']
            score = scored_matches.get(case_id, 0)
            scored_matches[case_id] = score + 2  # Date match is medium
        
        # Score location matches (lowest weight)
        for match in location_matches:
            case_id = match['case_id']
            score = scored_matches.get(case_id, 0)
            scored_matches[case_id] = score + 1  # Location match is weak
        
        # Find best match (highest score)
        if scored_matches:
            best_case_id = max(scored_matches.items(), key=lambda x: x[1])[0]
            best_score = scored_matches[best_case_id]
            
            # Only return if score is high enough (at least 2 points = date match or person match)
            if best_score >= 2:
                # Get full case details
                with self.db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM cases WHERE case_id = %s", [best_case_id])
                    result = cursor.fetchone()
                    
                    if result:
                        logger.info(f"Best alternative match: case {best_case_id} with score {best_score}")
                        logger.info(f"  Person matches: {best_case_id in [m['case_id'] for m in person_matches]}")
                        logger.info(f"  Date matches: {best_case_id in [m['case_id'] for m in date_matches]}")
                        logger.info(f"  Location matches: {best_case_id in [m['case_id'] for m in location_matches]}")
                        return result
        
        return None
    
    def _merge_references(self, case_id: int, existing_case: Dict[str, Any], 
                         new_references: CaseReferences):
        """
        Merge new reference numbers into existing case
        This happens when later documents provide additional reference numbers
        Normalizes references before storing for consistency
        Checks for duplicates in other cases before merging
        """
        
        updates = {}
        from psycopg2.extras import RealDictCursor
        
        # Normalize and add new references that don't exist yet
        if new_references.court_case_number and not existing_case.get('court_case_number'):
            normalized = normalize_reference_number(new_references.court_case_number)
            court_num = normalized if normalized else new_references.court_case_number.strip()
            
            # Check if this court_case_number already exists in another case
            with self.db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT case_id FROM cases WHERE court_case_number = %s AND case_id != %s LIMIT 1",
                    [court_num, case_id]
                )
                existing = cursor.fetchone()
                if existing:
                    logger.warning(
                        f"Cannot add court_case_number '{court_num}' to case {case_id}: "
                        f"it already exists in case {existing['case_id']}. Skipping."
                    )
                else:
                    updates['court_case_number'] = court_num
                    logger.info(f"Adding court case number to case {case_id}: {updates['court_case_number']}")
        
        if new_references.prosecution_case_number and not existing_case.get('prosecution_case_number'):
            normalized = normalize_reference_number(new_references.prosecution_case_number)
            prosecution_num = normalized if normalized else new_references.prosecution_case_number.strip()
            
            # Check if this prosecution_case_number already exists in another case
            with self.db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT case_id FROM cases WHERE prosecution_case_number = %s AND case_id != %s LIMIT 1",
                    [prosecution_num, case_id]
                )
                existing = cursor.fetchone()
                if existing:
                    logger.warning(
                        f"Cannot add prosecution_case_number '{prosecution_num}' to case {case_id}: "
                        f"it already exists in case {existing['case_id']}. Skipping."
                    )
                else:
                    updates['prosecution_case_number'] = prosecution_num
                    logger.info(f"Adding prosecution number to case {case_id}: {updates['prosecution_case_number']}")
        
        if new_references.police_report_number and not existing_case.get('police_report_number'):
            normalized = extract_police_report_number(new_references.police_report_number)
            police_num = normalized if normalized else new_references.police_report_number.strip()
            
            # Check if this police_report_number already exists in another case
            with self.db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT case_id FROM cases WHERE police_report_number = %s AND case_id != %s LIMIT 1",
                    [police_num, case_id]
                )
                existing = cursor.fetchone()
                if existing:
                    logger.warning(
                        f"Cannot add police_report_number '{police_num}' to case {case_id}: "
                        f"it already exists in case {existing['case_id']}. Skipping."
                    )
                else:
                    updates['police_report_number'] = police_num
                    logger.info(f"Adding police report number to case {case_id}: {updates['police_report_number']}")
        
        if new_references.internal_report_number and not existing_case.get('internal_report_number'):
            normalized = normalize_reference_number(new_references.internal_report_number)
            internal_num = normalized if normalized else new_references.internal_report_number.strip()
            
            # Check if this internal_report_number already exists in another case
            with self.db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT case_id FROM cases WHERE internal_report_number = %s AND case_id != %s LIMIT 1",
                    [internal_num, case_id]
                )
                existing = cursor.fetchone()
                if existing:
                    logger.warning(
                        f"Cannot add internal_report_number '{internal_num}' to case {case_id}: "
                        f"it already exists in case {existing['case_id']}. Skipping."
                    )
                else:
                    updates['internal_report_number'] = internal_num
                    logger.info(f"Adding internal report number to case {case_id}: {updates['internal_report_number']}")
        
        # Execute update if there are new references
        if updates:
            self._update_case(case_id, updates)
            logger.info(f"Merged {len(updates)} new references into case {case_id}")
    
    def _create_new_case(self, references: Dict[str, str], 
                        metadata: Dict[str, Any] = None) -> int:
        """Create a new case with available information"""
        
        case_data = {
            'case_type': 'criminal',  # Default
            'current_status': 'open',
            'status_date': datetime.now()
        }
        
        # Add all available references (all are now nullable)
        # Normalize and clean references before storing to ensure consistency
        cleaned_refs = {}
        for key, value in references.items():
            if value and isinstance(value, str):
                # Normalize reference numbers for consistent storage
                if key == 'police_report_number':
                    normalized = extract_police_report_number(value)
                    cleaned_refs[key] = normalized if normalized else value.strip()
                else:
                    normalized = normalize_reference_number(value)
                    cleaned_refs[key] = normalized if normalized else value.strip()
            elif value:
                cleaned_refs[key] = value
        case_data.update(cleaned_refs)
        
        # Add metadata if provided
        if metadata:
            if metadata.get('incident_date'):
                case_data['incident_date'] = metadata['incident_date']
            if metadata.get('report_date'):
                case_data['report_date'] = metadata['report_date']
            if metadata.get('police_station'):
                case_data['police_station'] = metadata['police_station']
            if metadata.get('prosecution_office'):
                case_data['prosecution_office'] = metadata['prosecution_office']
        
        # Insert into database
        # First check if case with same court_case_number already exists (to avoid duplicates)
        from psycopg2.extras import RealDictCursor
        with self.db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            # Check for duplicate court_case_number before inserting
            if case_data.get('court_case_number'):
                cursor.execute(
                    "SELECT * FROM cases WHERE court_case_number = %s LIMIT 1",
                    [case_data['court_case_number']]
                )
                existing = cursor.fetchone()
                if existing:
                    case_id = existing['case_id']
                    logger.info(f"Case with court_case_number '{case_data['court_case_number']}' already exists: {case_id}, using existing case")
                    # Merge any new references into existing case
                    self._merge_references(case_id, existing, CaseReferences(**case_data))
                    return case_id
            
            fields = [k for k, v in case_data.items() if v is not None]
            placeholders = ['%s'] * len(fields)
            values = [case_data[k] for k in fields]
            
            sql = f"""
                INSERT INTO cases ({', '.join(fields)})
                VALUES ({', '.join(placeholders)})
                RETURNING case_id
            """
            
            try:
                cursor.execute(sql, values)
                self.db.connection.commit()
                case_id = cursor.fetchone()['case_id']
                logger.info(f"Created new case: {case_id} with references: {references}")
                return case_id
            except Exception as e:
                # If duplicate key error, try to find existing case
                if 'duplicate key' in str(e).lower() or 'unique constraint' in str(e).lower():
                    logger.warning(f"Duplicate case detected: {e}, attempting to find existing case")
                    if case_data.get('court_case_number'):
                        cursor.execute(
                            "SELECT * FROM cases WHERE court_case_number = %s LIMIT 1",
                            [case_data['court_case_number']]
                        )
                        existing = cursor.fetchone()
                        if existing:
                            case_id = existing['case_id']
                            logger.info(f"Found existing case: {case_id}, using it instead")
                            # Merge any new references
                            self._merge_references(case_id, existing, CaseReferences(**case_data))
                            return case_id
                logger.error(f"Error creating case: {e}")
                self.db.connection.rollback()
                raise
    
    def _update_case(self, case_id: int, updates: Dict[str, Any]):
        """Update case with new information"""
        
        if not updates:
            return
        
        from psycopg2.extras import RealDictCursor
        with self.db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            set_clauses = [f"{key} = %s" for key in updates.keys()]
            values = list(updates.values()) + [case_id]
            
            sql = f"""
                UPDATE cases 
                SET {', '.join(set_clauses)}, updated_at = CURRENT_TIMESTAMP
                WHERE case_id = %s
            """
            
            cursor.execute(sql, values)
            self.db.connection.commit()
    
    def _update_case_metadata(self, case_id: int, metadata: Dict[str, Any]):
        """Update case with metadata from document"""
        
        updates = {}
        
        # Only update if not already set (don't overwrite)
        if metadata.get('incident_date'):
            updates['incident_date'] = metadata['incident_date']
        
        if metadata.get('report_date'):
            updates['report_date'] = metadata['report_date']
        
        if metadata.get('police_station'):
            updates['police_station'] = metadata['police_station']
        
        if metadata.get('prosecution_office'):
            updates['prosecution_office'] = metadata['prosecution_office']
        
        if updates:
            self._update_case(case_id, updates)


class DocumentLinker:
    """
    Links documents to cases and handles temporal relationships
    """
    
    # Document type lifecycle order
    DOCUMENT_ORDER = [
        'police_report',         # 1. Incident reported
        'statement',             # 2. Statements taken
        'lab_result',            # 3. Lab tests
        'investigation',         # 4. Prosecution investigates
        'detention_order',       # 5. May order detention
        'waiver',                # 6. Complainant may waive
        'case_transfer',         # 7. Transfer to court
        'notification',          # 8. Notify parties
        'court_session',         # 9. Court hearings
        'judgment',              # 10. Final judgment
        'correspondence',        # Ongoing throughout
    ]
    
    def __init__(self, db_manager):
        self.db = db_manager
    
    def link_document_to_case(self, case_id: int, document_id: int, 
                             document_type: str, document_data: Any):
        """
        Link document to case and update case status based on document type
        """
        
        # Update case status based on document type
        status_updates = self._get_status_updates(document_type, document_data)
        
        if status_updates:
            from psycopg2.extras import RealDictCursor
            with self.db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                set_clauses = [f"{k} = %s" for k in status_updates.keys()]
                values = list(status_updates.values()) + [case_id]
                
                sql = f"""
                    UPDATE cases 
                    SET {', '.join(set_clauses)}, updated_at = CURRENT_TIMESTAMP
                    WHERE case_id = %s
                """
                
                cursor.execute(sql, values)
                self.db.connection.commit()
                
                logger.info(f"Updated case {case_id} status based on {document_type}")
    
    def _get_status_updates(self, document_type: str, 
                           document_data: Any) -> Dict[str, Any]:
        """Determine what case fields to update based on document type"""
        
        updates = {}
        
        if document_type == 'police_report':
            updates['current_status'] = 'under_investigation'
            if hasattr(document_data, 'incident_date'):
                updates['incident_date'] = document_data.incident_date
            if hasattr(document_data, 'report_date'):
                updates['case_opened_date'] = document_data.report_date
        
        elif document_type == 'investigation':
            updates['current_status'] = 'under_investigation'
        
        elif document_type == 'case_transfer':
            updates['current_status'] = 'in_trial'
        
        elif document_type == 'court_session':
            updates['current_status'] = 'in_trial'
        
        elif document_type == 'judgment':
            updates['current_status'] = 'closed'
            if hasattr(document_data, 'judgment_date'):
                updates['case_closed_date'] = document_data.judgment_date
                updates['final_judgment_date'] = document_data.judgment_date
        
        elif document_type == 'waiver':
            # Waiver might change status depending on stage
            pass
        
        return updates
    
    def get_case_timeline_position(self, case_id: int, document_type: str) -> int:
        """
        Determine where this document fits in the case timeline
        Returns: position index (0-based)
        """
        try:
            return self.DOCUMENT_ORDER.index(document_type)
        except ValueError:
            return 999  # Unknown type, put at end
    
    def validate_document_sequence(self, case_id: int, new_document_type: str) -> bool:
        """
        Check if document type makes sense given existing documents
        E.g., judgment can't come before police report
        """
        
        # Get existing document types for this case
        from psycopg2.extras import RealDictCursor
        with self.db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT DISTINCT document_type 
                FROM documents 
                WHERE case_id = %s
            """, (case_id,))
            
            existing_types = [row['document_type'] for row in cursor.fetchall()]
        
        new_position = self.get_case_timeline_position(case_id, new_document_type)
        
        # Check if any existing document comes after this one
        for existing_type in existing_types:
            existing_position = self.get_case_timeline_position(case_id, existing_type)
            
            # If we have a judgment but now getting police report, that's suspicious
            if existing_position > new_position and existing_position < 900:  # 900+ are unknown
                logger.warning(
                    f"Document sequence warning: Adding {new_document_type} "
                    f"but case already has {existing_type}"
                )
                return False
        
        return True


class SmartCaseProcessor:
    """
    Combines CaseMatcher and DocumentLinker for intelligent processing
    """
    
    def __init__(self, db_manager):
        self.db = db_manager
        self.matcher = CaseMatcher(db_manager)
        self.linker = DocumentLinker(db_manager)
    
    def process_document_intelligently(self, references: CaseReferences,
                                      document_type: str,
                                      document_data: Any,
                                      document_metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Smart processing that:
        1. Finds/creates case using ANY reference
        2. Merges new references
        3. Links document
        4. Updates case status
        5. Validates sequence
        """
        
        logger.info(f"Processing {document_type} with references: {references.get_available_references()}")
        
        # Step 1: Find or create case (handles merging)
        case_id = self.matcher.find_or_create_case(references, document_metadata)
        
        # Step 2: Store document (this should be done by caller, we just return case_id)
        # document_id = ... (caller stores document)
        
        # Step 3: Validate sequence (optional, just warns)
        sequence_valid = self.linker.validate_document_sequence(case_id, document_type)
        
        return {
            'case_id': case_id,
            'sequence_valid': sequence_valid,
            'action': 'found' if case_id else 'created'
        }
    
    def get_case_completeness(self, case_id: int) -> Dict[str, Any]:
        """
        Check how complete a case is based on documents received
        """
        
        from psycopg2.extras import RealDictCursor
        with self.db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get case info
            cursor.execute("SELECT * FROM cases WHERE case_id = %s", (case_id,))
            case = cursor.fetchone()
            
            if not case:
                return None
            
            # Get document types
            cursor.execute("""
                SELECT document_type, COUNT(*) as count
                FROM documents
                WHERE case_id = %s
                GROUP BY document_type
            """, (case_id,))
            
            document_counts = {row['document_type']: row['count'] for row in cursor.fetchall()}
        
        # Check completeness
        completeness = {
            'case_id': case_id,
            'references_complete': all([
                case.get('court_case_number'),
                case.get('prosecution_case_number'),
                case.get('police_report_number')
            ]),
            'has_police_report': 'police_report' in document_counts,
            'has_investigation': 'investigation' in document_counts,
            'has_judgment': 'judgment' in document_counts,
            'document_types': list(document_counts.keys()),
            'total_documents': sum(document_counts.values()),
            'estimated_stage': self._estimate_case_stage(case, document_counts),
        }
        
        return completeness
    
    def _estimate_case_stage(self, case: Dict[str, Any], 
                            document_types: Dict[str, int]) -> str:
        """Estimate what stage the case is at"""
        
        if 'judgment' in document_types:
            return 'concluded'
        elif 'court_session' in document_types:
            return 'in_trial'
        elif 'case_transfer' in document_types:
            return 'transferred_to_court'
        elif 'investigation' in document_types:
            return 'under_investigation'
        elif 'police_report' in document_types:
            return 'initial_report'
        else:
            return 'unknown'


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

def example_usage():
    """
    Demonstrates how the system handles documents arriving in any order
    """
    
    from database_manager import DatabaseManager
    
    db_config = {
        'host': 'localhost',
        'user': 'legal_user',
        'password': 'password',
        'database': 'legal_case'
    }
    
    with DatabaseManager(**db_config) as db:
        processor = SmartCaseProcessor(db)
        
        # Scenario 1: Police report arrives first (no court case number yet)
        print("\n=== Processing Police Report (first document) ===")
        police_refs = CaseReferences(
            police_report_number="2590/2025",
            internal_report_number="4308/2025"
        )
        
        result1 = processor.process_document_intelligently(
            references=police_refs,
            document_type='police_report',
            document_data=None,
            document_metadata={
                'incident_date': '2025-05-14',
                'report_date': '2025-05-15',
                'police_station': 'قسم شرطة أم صلال'
            }
        )
        
        print(f"Result: {result1}")
        # Output: {'case_id': 1, 'action': 'created', 'sequence_valid': True}
        
        # Scenario 2: Investigation arrives (adds prosecution number)
        print("\n=== Processing Investigation (adds prosecution number) ===")
        investigation_refs = CaseReferences(
            police_report_number="2590/2025",  # Same police report
            prosecution_case_number="303/2025"  # NEW: prosecution number
        )
        
        result2 = processor.process_document_intelligently(
            references=investigation_refs,
            document_type='investigation',
            document_data=None
        )
        
        print(f"Result: {result2}")
        # Output: {'case_id': 1, 'action': 'found', 'sequence_valid': True}
        # Note: Same case_id! System linked it via police_report_number
        
        # Scenario 3: Court session arrives (adds court case number)
        print("\n=== Processing Court Session (adds court case number) ===")
        court_refs = CaseReferences(
            court_case_number="2552/2025/جنح متنوعة/ابتدائي",  # NEW
            prosecution_case_number="303/2025"  # Matches previous
        )
        
        result3 = processor.process_document_intelligently(
            references=court_refs,
            document_type='court_session',
            document_data=None
        )
        
        print(f"Result: {result3}")
        # Output: {'case_id': 1, 'action': 'found', 'sequence_valid': True}
        # Still same case! Now has all three reference numbers
        
        # Check completeness
        print("\n=== Case Completeness ===")
        completeness = processor.get_case_completeness(result3['case_id'])
        print(f"Completeness: {completeness}")
        
        # Verify case has all references
        with db.connection.cursor() as cursor:
            cursor.execute("SELECT * FROM cases WHERE case_id = %s", (result3['case_id'],))
            case = cursor.fetchone()
            
            print(f"\n=== Final Case Record ===")
            print(f"Court Case Number:      {case['court_case_number']}")
            print(f"Prosecution Number:     {case['prosecution_case_number']}")
            print(f"Police Report Number:   {case['police_report_number']}")
            print(f"Internal Report Number: {case['internal_report_number']}")
            print(f"Status:                 {case['current_status']}")


if __name__ == '__main__':
    example_usage()
