#!/usr/bin/env python3
"""
Case Cleanup and Merger Tool
Fixes the existing duplicate cases in the database
Merges multiple case records that should be one case
"""

import json
import logging
from typing import Dict, List, Any, Set
from datetime import datetime
from database_manager import DatabaseManager
from enhanced_case_matcher import enhanced_normalize_reference_number, extract_core_case_numbers

logger = logging.getLogger(__name__)

class CaseCleanupTool:
    """
    Tool to identify and merge duplicate cases
    """
    
    def __init__(self, db_config: Dict[str, Any]):
        self.db_config = db_config
    
    def analyze_duplicate_cases(self) -> Dict[str, Any]:
        """
        Analyze all cases and identify duplicates
        """
        with DatabaseManager(**self.db_config) as db:
            # Get all cases
            cases = db.execute_query("SELECT * FROM cases ORDER BY case_id")
            
            print(f"📊 Analyzing {len(cases)} cases for duplicates...")
            
            # Group cases by potential matches
            case_groups = self._group_cases_by_similarity(cases)
            
            # Analyze results
            analysis = {
                'total_cases': len(cases),
                'unique_case_groups': len(case_groups),
                'duplicate_groups': [group for group in case_groups if len(group) > 1],
                'orphan_cases': [case for case in cases if case.get('is_orphan', False)],
                'cases_with_all_references': [case for case in cases if all([
                    case.get('court_case_number'),
                    case.get('prosecution_case_number'), 
                    case.get('police_report_number')
                ])]
            }
            
            return analysis, case_groups
    
    def _group_cases_by_similarity(self, cases: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """
        Group cases that likely represent the same case
        """
        case_groups = []
        processed_case_ids = set()
        
        for case in cases:
            if case['case_id'] in processed_case_ids:
                continue
            
            # Find all cases that could match this one
            matching_cases = [case]
            processed_case_ids.add(case['case_id'])
            
            # Get all reference variations for this case
            case_variations = self._get_all_case_variations(case)
            
            # Check other cases for matches
            for other_case in cases:
                if (other_case['case_id'] != case['case_id'] and 
                    other_case['case_id'] not in processed_case_ids):
                    
                    other_variations = self._get_all_case_variations(other_case)
                    
                    # Check for any overlap in variations
                    if self._variations_overlap(case_variations, other_variations):
                        matching_cases.append(other_case)
                        processed_case_ids.add(other_case['case_id'])
            
            case_groups.append(matching_cases)
        
        return case_groups
    
    def _get_all_case_variations(self, case: Dict[str, Any]) -> Set[str]:
        """
        Get all possible variations for a case's reference numbers
        """
        variations = set()
        
        reference_fields = ['court_case_number', 'prosecution_case_number', 'police_report_number', 'internal_report_number']
        
        for field in reference_fields:
            value = case.get(field)
            if value:
                field_variations = enhanced_normalize_reference_number(value)
                variations.update(field_variations)
        
        return variations
    
    def _variations_overlap(self, variations1: Set[str], variations2: Set[str]) -> bool:
        """
        Check if two sets of variations have any overlap
        """
        # Direct overlap
        if variations1 & variations2:
            return True
        
        # Check for core number matches (more flexible)
        for var1 in variations1:
            for var2 in variations2:
                if self._core_numbers_match(var1, var2):
                    return True
        
        return False
    
    def _core_numbers_match(self, ref1: str, ref2: str) -> bool:
        """
        Check if two references share core numbers
        """
        import re
        
        # Extract numbers from both
        nums1 = re.findall(r'\d+', ref1)
        nums2 = re.findall(r'\d+', ref2)
        
        # Check for shared numbers
        for num1 in nums1:
            for num2 in nums2:
                if num1 == num2 and len(num1) >= 3:  # Only meaningful numbers (3+ digits)
                    return True
        
        return False
    
    def merge_duplicate_cases(self, duplicate_groups: List[List[Dict[str, Any]]], dry_run: bool = True) -> Dict[str, Any]:
        """
        Merge duplicate case groups into single cases
        """
        results = {
            'groups_processed': 0,
            'cases_merged': 0,
            'primary_cases': [],
            'merged_case_ids': []
        }
        
        with DatabaseManager(**self.db_config) as db:
            for group in duplicate_groups:
                if len(group) <= 1:
                    continue
                
                print(f"\n🔄 Processing duplicate group with {len(group)} cases:")
                for case in group:
                    print(f"  - Case {case['case_id']}: court={case.get('court_case_number')}, police={case.get('police_report_number')}")
                
                # Choose primary case (most complete)
                primary_case = self._choose_primary_case(group)
                duplicate_cases = [c for c in group if c['case_id'] != primary_case['case_id']]
                
                print(f"  ✅ Primary: Case {primary_case['case_id']}")
                print(f"  🔀 Merging: {[c['case_id'] for c in duplicate_cases]}")
                
                if not dry_run:
                    duplicate_case_ids = [c['case_id'] for c in duplicate_cases]
                    
                    # Step 1: Update related records to point to primary case
                    self._update_related_records(db, duplicate_case_ids, primary_case['case_id'])
                    
                    # Step 2: Clear reference numbers from duplicate cases (to avoid unique constraint violations)
                    self._clear_duplicate_references(db, duplicate_case_ids)
                    
                    # Step 3: Merge the cases (now safe to update primary with merged references)
                    merged_case = self._merge_case_data(primary_case, duplicate_cases)
                    self._update_case_in_db(db, primary_case['case_id'], merged_case)
                    
                    # Step 4: Mark duplicate cases as merged
                    self._mark_cases_as_merged(db, duplicate_case_ids, primary_case['case_id'])
                
                results['groups_processed'] += 1
                results['cases_merged'] += len(duplicate_cases)
                results['primary_cases'].append(primary_case['case_id'])
                results['merged_case_ids'].extend([c['case_id'] for c in duplicate_cases])
        
        return results
    
    def _choose_primary_case(self, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Choose which case should be the primary (most complete/recent)
        """
        scored_cases = []
        
        for case in cases:
            score = 0
            
            # Prefer cases with more reference numbers
            if case.get('court_case_number'):
                score += 10
            if case.get('prosecution_case_number'):
                score += 8
            if case.get('police_report_number'):
                score += 6
            if case.get('internal_report_number'):
                score += 4
            
            # Prefer cases with more metadata
            metadata_fields = ['incident_date', 'report_date', 'court_name', 'police_station', 'current_status']
            for field in metadata_fields:
                if case.get(field):
                    score += 2
            
            # Prefer non-orphan cases
            if not case.get('is_orphan', False):
                score += 5
            
            # Prefer more recently updated cases
            if case.get('updated_at'):
                score += 1
            
            # Prefer cases with meaningful status
            if case.get('current_status') and case.get('current_status') not in ['open', 'unknown']:
                score += 3
            
            scored_cases.append((score, case))
        
        # Return highest scoring case
        scored_cases.sort(key=lambda x: x[0], reverse=True)
        return scored_cases[0][1]
    
    def _merge_case_data(self, primary_case: Dict[str, Any], duplicate_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merge data from duplicate cases into primary case
        """
        merged_case = dict(primary_case)
        
        # Merge reference numbers (take most complete)
        reference_fields = ['court_case_number', 'prosecution_case_number', 'police_report_number', 'internal_report_number']
        
        for field in reference_fields:
            if not merged_case.get(field):
                # Primary doesn't have this field, look for it in duplicates
                for dup_case in duplicate_cases:
                    if dup_case.get(field):
                        merged_case[field] = dup_case[field]
                        break
            elif merged_case.get(field):
                # Primary has field, but check if duplicates have longer/better version
                for dup_case in duplicate_cases:
                    dup_value = dup_case.get(field)
                    if dup_value and len(dup_value) > len(merged_case[field]):
                        merged_case[field] = dup_value
        
        # Merge metadata (take non-null values)
        metadata_fields = ['incident_date', 'report_date', 'case_opened_date', 'case_closed_date', 
                          'final_judgment_date', 'court_name', 'police_station', 'prosecution_office']
        
        for field in metadata_fields:
            if not merged_case.get(field):
                for dup_case in duplicate_cases:
                    if dup_case.get(field):
                        merged_case[field] = dup_case[field]
                        break
        
        # Handle status (prefer more advanced status)
        status_priority = {
            'closed': 10,
            'concluded': 9,
            'judgment': 8,
            'in_trial': 7,
            'transferred': 6,
            'investigation': 5,
            'open': 3,
            'unknown': 1
        }
        
        best_status = merged_case.get('current_status', 'unknown')
        best_priority = status_priority.get(best_status.lower(), 0)
        
        for dup_case in duplicate_cases:
            dup_status = dup_case.get('current_status', 'unknown')
            dup_priority = status_priority.get(dup_status.lower(), 0)
            if dup_priority > best_priority:
                best_status = dup_status
                best_priority = dup_priority
                merged_case['status_date'] = dup_case.get('status_date')
        
        merged_case['current_status'] = best_status
        merged_case['updated_at'] = datetime.now()
        
        return merged_case
    
    def _update_case_in_db(self, db, case_id: int, merged_case: Dict[str, Any]):
        """Update case in database with merged data"""
        
        # Exclude columns that cannot be updated:
        # - case_id: primary key
        # - created_at: should not be changed
        # - reference_completeness: GENERATED ALWAYS AS column (computed automatically)
        # - synthetic_reference: auto-generated by trigger (will be updated automatically)
        excluded_fields = [
            'case_id', 
            'created_at', 
            'reference_completeness',
            'synthetic_reference'  # Auto-generated by trigger, will update automatically
        ]
        
        # Reference fields that have unique constraints - need conflict checking
        unique_reference_fields = [
            'court_case_number',
            'prosecution_case_number', 
            'police_report_number',
            'internal_report_number'
        ]
        
        from psycopg2.extras import RealDictCursor
        with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            # Check for conflicts with unique reference fields
            safe_update_fields = {}
            for field, value in merged_case.items():
                if field in excluded_fields or value is None:
                    continue
                
                # For unique reference fields, check if value already exists in another case
                if field in unique_reference_fields:
                    # Check if this reference number already exists in a different case
                    cursor.execute(
                        f"SELECT case_id FROM cases WHERE {field} = %s AND case_id != %s LIMIT 1",
                        (value, case_id)
                    )
                    existing = cursor.fetchone()
                    
                    if existing:
                        logger.warning(
                            f"Skipping {field}='{value}' - already exists in case {existing['case_id']}"
                        )
                        continue
                
                safe_update_fields[field] = value
            
            if not safe_update_fields:
                logger.info(f"No safe fields to update for case {case_id}")
                return
            
            # Perform the update
            fields = list(safe_update_fields.keys())
            values = list(safe_update_fields.values())
            set_clause = ', '.join([f"{f} = %s" for f in fields])
            
            sql = f"UPDATE cases SET {set_clause} WHERE case_id = %s"
            cursor.execute(sql, values + [case_id])
            db.connection.commit()
            logger.info(f"Updated case {case_id} with fields: {fields}")
    
    def _update_related_records(self, db, duplicate_case_ids: List[int], primary_case_id: int):
        """Update all related records to point to the primary case"""
        
        from psycopg2.extras import RealDictCursor
        with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            updated_count = 0
            
            # Update documents
            cursor.execute(
                "UPDATE documents SET case_id = %s WHERE case_id = ANY(%s)",
                (primary_case_id, duplicate_case_ids)
            )
            doc_count = cursor.rowcount
            if doc_count > 0:
                updated_count += doc_count
                logger.info(f"  📄 Updated {doc_count} documents to point to case {primary_case_id}")
            
            # Update case_parties - SIMPLE AND BULLETPROOF APPROACH
            # Step 1: Get all existing parties in primary case
            cursor.execute(
                "SELECT party_id, role_type FROM case_parties WHERE case_id = %s",
                (primary_case_id,)
            )
            existing_combinations = {(row['party_id'], row['role_type']) for row in cursor.fetchall()}
            
            # Step 2: Get all parties from duplicate cases
            cursor.execute(
                "SELECT case_id, party_id, role_type FROM case_parties WHERE case_id = ANY(%s)",
                (duplicate_case_ids,)
            )
            duplicate_parties = cursor.fetchall()
            
            # Step 3: Delete ALL case_parties from duplicate cases (we'll re-add non-conflicting ones)
            cursor.execute(
                "DELETE FROM case_parties WHERE case_id = ANY(%s)",
                (duplicate_case_ids,)
            )
            total_deleted = cursor.rowcount
            db.connection.commit()  # Commit the delete immediately
            
            # Step 4: Insert only non-conflicting parties back with primary case_id
            inserted_count = 0
            skipped_count = 0
            for party in duplicate_parties:
                party_id = party['party_id']
                role_type = party['role_type']
                
                # Skip if this combination already exists in primary case
                if (party_id, role_type) in existing_combinations:
                    skipped_count += 1
                    continue
                
                # Insert into primary case (created_at will be set automatically)
                try:
                    cursor.execute("""
                        INSERT INTO case_parties (case_id, party_id, role_type)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (case_id, party_id, role_type) DO NOTHING
                    """, (primary_case_id, party_id, role_type))
                    if cursor.rowcount > 0:
                        inserted_count += 1
                except Exception as e:
                    # Log error but continue - ON CONFLICT should prevent most issues
                    logger.warning(f"  ⚠️  Skipped party: case_id={primary_case_id}, party_id={party_id}, role={role_type}: {str(e)}")
                    skipped_count += 1
                    # Don't break - continue with other parties
                    continue
            
            db.connection.commit()  # Commit the inserts
            
            deleted_conflicts = total_deleted - inserted_count
            if inserted_count > 0 or deleted_conflicts > 0 or skipped_count > 0:
                updated_count += inserted_count
                logger.info(f"  👥 Inserted {inserted_count} case-party links to case {primary_case_id} (skipped {skipped_count} duplicates, removed {deleted_conflicts} total)")
            
            # Update charges
            cursor.execute(
                "UPDATE charges SET case_id = %s WHERE case_id = ANY(%s)",
                (primary_case_id, duplicate_case_ids)
            )
            charge_count = cursor.rowcount
            if charge_count > 0:
                updated_count += charge_count
                logger.info(f"  ⚖️  Updated {charge_count} charges to point to case {primary_case_id}")
            
            # Update court_sessions
            cursor.execute(
                "UPDATE court_sessions SET case_id = %s WHERE case_id = ANY(%s)",
                (primary_case_id, duplicate_case_ids)
            )
            session_count = cursor.rowcount
            if session_count > 0:
                updated_count += session_count
                logger.info(f"  🏛️  Updated {session_count} court sessions to point to case {primary_case_id}")
            
            # Update judgments
            cursor.execute(
                "UPDATE judgments SET case_id = %s WHERE case_id = ANY(%s)",
                (primary_case_id, duplicate_case_ids)
            )
            judgment_count = cursor.rowcount
            if judgment_count > 0:
                updated_count += judgment_count
                logger.info(f"  📜 Updated {judgment_count} judgments to point to case {primary_case_id}")
            
            # Update case_events
            cursor.execute(
                "UPDATE case_events SET case_id = %s WHERE case_id = ANY(%s)",
                (primary_case_id, duplicate_case_ids)
            )
            event_count = cursor.rowcount
            if event_count > 0:
                updated_count += event_count
                logger.info(f"  📅 Updated {event_count} case events to point to case {primary_case_id}")
            
            # Update other related tables
            related_tables = [
                'detention_records', 'notifications', 'waivers', 
                'correspondence', 'statements', 'evidence', 'lab_results'
            ]
            
            for table in related_tables:
                try:
                    cursor.execute(
                        f"UPDATE {table} SET case_id = %s WHERE case_id = ANY(%s)",
                        (primary_case_id, duplicate_case_ids)
                    )
                    if cursor.rowcount > 0:
                        updated_count += cursor.rowcount
                        logger.info(f"  📋 Updated {cursor.rowcount} {table} records to point to case {primary_case_id}")
                except Exception as e:
                    logger.warning(f"  ⚠️  Could not update {table}: {str(e)}")
            
            db.connection.commit()
            print(f"  ✅ Updated {updated_count} related records to point to primary case {primary_case_id}")
    
    def _clear_duplicate_references(self, db, duplicate_case_ids: List[int]):
        """Clear reference numbers from duplicate cases to avoid unique constraint violations"""
        
        from psycopg2.extras import RealDictCursor
        with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            # Clear all reference numbers from duplicate cases
            # This allows us to safely merge them into the primary case
            reference_fields = ['court_case_number', 'prosecution_case_number', 'police_report_number', 'internal_report_number']
            
            for field in reference_fields:
                cursor.execute(
                    f"UPDATE cases SET {field} = NULL WHERE case_id = ANY(%s)",
                    (duplicate_case_ids,)
                )
            
            db.connection.commit()
            logger.info(f"  🧹 Cleared reference numbers from {len(duplicate_case_ids)} duplicate cases")
    
    def _mark_cases_as_merged(self, db, merged_case_ids: List[int], primary_case_id: int):
        """Mark cases as merged/duplicates"""
        
        from psycopg2.extras import RealDictCursor
        with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            for case_id in merged_case_ids:
                cursor.execute("""
                    UPDATE cases 
                    SET case_summary_ar = %s,
                        case_summary_en = %s,
                        current_status = 'merged',
                        updated_at = NOW()
                    WHERE case_id = %s
                """, (
                    f"تم دمج هذه القضية مع القضية رقم {primary_case_id}",
                    f"This case was merged into case {primary_case_id}",
                    case_id
                ))
            db.connection.commit()
            print(f"  ✅ Marked {len(merged_case_ids)} cases as merged")

    def print_analysis_report(self, analysis: Dict[str, Any], case_groups: List[List[Dict[str, Any]]]):
        """Print detailed analysis report"""
        
        print("\n" + "="*80)
        print("🔍 CASE DUPLICATE ANALYSIS REPORT")
        print("="*80)
        
        print(f"\n📊 SUMMARY:")
        print(f"  • Total cases in database: {analysis['total_cases']}")
        print(f"  • Unique case groups found: {analysis['unique_case_groups']}")
        print(f"  • Groups with duplicates: {len(analysis['duplicate_groups'])}")
        print(f"  • Orphan cases: {len(analysis['orphan_cases'])}")
        print(f"  • Cases with all references: {len(analysis['cases_with_all_references'])}")
        
        print(f"\n🚨 DUPLICATE GROUPS:")
        for i, group in enumerate(analysis['duplicate_groups'], 1):
            print(f"\n  Group {i}: {len(group)} cases")
            for case in group:
                refs = []
                if case.get('court_case_number'):
                    refs.append(f"court={case['court_case_number']}")
                if case.get('prosecution_case_number'):
                    refs.append(f"prosecution={case['prosecution_case_number']}")
                if case.get('police_report_number'):
                    refs.append(f"police={case['police_report_number']}")
                if case.get('internal_report_number'):
                    refs.append(f"internal={case['internal_report_number']}")
                
                ref_str = ", ".join(refs) if refs else "NO REFERENCES"
                status = case.get('current_status', 'unknown')
                print(f"    - Case {case['case_id']}: {ref_str} (status: {status})")
        
        print(f"\n👻 ORPHAN CASES:")
        for case in analysis['orphan_cases']:
            print(f"  - Case {case['case_id']}: {case.get('synthetic_reference', 'NO REF')}")
        
        estimated_correct = len([g for g in case_groups if len(g) == 1 and not g[0].get('is_orphan')])
        print(f"\n✅ ESTIMATED CORRECT CASES: {estimated_correct}")
        print(f"❌ CASES NEEDING CLEANUP: {analysis['total_cases'] - estimated_correct}")


def main():
    """Main cleanup process"""
    
    # Database configuration
    db_config = {
        'host': 'localhost',
        'user': 'postgres', 
        'password': 'postgres',
        'database': 'legal_case'
    }
    
    print("🧹 CASE CLEANUP TOOL")
    print("="*50)
    
    try:
        cleanup = CaseCleanupTool(db_config)
        
        # Step 1: Analyze duplicates
        print("\n📊 Step 1: Analyzing duplicate cases...")
        analysis, case_groups = cleanup.analyze_duplicate_cases()
        
        # Step 2: Print report
        cleanup.print_analysis_report(analysis, case_groups)
        
        # Step 3: Ask for confirmation
        duplicate_groups = analysis['duplicate_groups']
        if duplicate_groups:
            print(f"\n🤔 Found {len(duplicate_groups)} groups with duplicates.")
            
            # First do a dry run
            print("\n🔍 DRY RUN - Showing what would be merged:")
            dry_results = cleanup.merge_duplicate_cases(duplicate_groups, dry_run=True)
            
            print(f"\nDry run results:")
            print(f"  • Groups to process: {dry_results['groups_processed']}")
            print(f"  • Cases to merge: {dry_results['cases_merged']}")
            print(f"  • Primary cases: {dry_results['primary_cases']}")
            
            response = input("\n❓ Proceed with actual merge? (y/N): ").strip().lower()
            if response == 'y':
                print("\n🔄 Performing actual merge...")
                real_results = cleanup.merge_duplicate_cases(duplicate_groups, dry_run=False)
                print("✅ Merge completed!")
                print(f"  • Processed {real_results['groups_processed']} groups")
                print(f"  • Merged {real_results['cases_merged']} duplicate cases")
            else:
                print("❌ Merge cancelled.")
        else:
            print("✅ No duplicates found!")
    
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
