"""
Migration Script: Transform data from old schema to new JSONB-based schema
Exports existing data, transforms to JSONB format, imports to new schema
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import json

from database_manager import DatabaseManager  # Old DB manager
from .db_manager_v2 import DatabaseManagerV2  # New DB manager
from config import CONFIG

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataMigrator:
    """Migrate data from old schema to new JSONB schema"""
    
    def __init__(self):
        """Initialize migrator"""
        self.old_db_config = CONFIG['database_legacy']
        self.new_db_config = CONFIG['database']
        logger.info("Initialized DataMigrator")
    
    def export_old_cases(self) -> List[Dict[str, Any]]:
        """Export all cases from old database"""
        logger.info("Exporting cases from old database...")
        
        with DatabaseManager(**self.old_db_config) as db:
            with db.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM cases ORDER BY case_id")
                cases = cursor.fetchall()
                logger.info(f"Exported {len(cases)} cases")
                return [dict(case) for case in cases]
    
    def export_old_documents(self) -> List[Dict[str, Any]]:
        """Export all documents from old database"""
        logger.info("Exporting documents from old database...")
        
        with DatabaseManager(**self.old_db_config) as db:
            with db.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM documents ORDER BY document_id")
                documents = cursor.fetchall()
                logger.info(f"Exported {len(documents)} documents")
                return [dict(doc) for doc in documents]
    
    def export_old_parties(self) -> List[Dict[str, Any]]:
        """Export all parties from old database"""
        logger.info("Exporting parties from old database...")
        
        with DatabaseManager(**self.old_db_config) as db:
            with db.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM parties ORDER BY party_id")
                parties = cursor.fetchall()
                logger.info(f"Exported {len(parties)} parties")
                return [dict(party) for party in parties]
    
    def export_old_case_parties(self) -> List[Dict[str, Any]]:
        """Export case-party relationships"""
        logger.info("Exporting case-party relationships...")
        
        with DatabaseManager(**self.old_db_config) as db:
            with db.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM case_parties ORDER BY case_id, party_id")
                relationships = cursor.fetchall()
                logger.info(f"Exported {len(relationships)} case-party relationships")
                return [dict(rel) for rel in relationships]
    
    def export_old_charges(self) -> List[Dict[str, Any]]:
        """Export charges from old database"""
        logger.info("Exporting charges...")
        
        with DatabaseManager(**self.old_db_config) as db:
            with db.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM charges ORDER BY case_id, charge_id")
                charges = cursor.fetchall()
                logger.info(f"Exported {len(charges)} charges")
                return [dict(charge) for charge in charges]
    
    def transform_case_to_jsonb(self, old_case: Dict, parties_map: Dict[int, Dict],
                               case_parties_map: Dict[int, List[Dict]],
                               charges_map: Dict[int, List[Dict]]) -> Dict[str, Any]:
        """
        Transform old case record to new JSONB format
        
        Args:
            old_case: Old case record
            parties_map: Map of party_id -> party data
            case_parties_map: Map of case_id -> list of case_party relationships
            charges_map: Map of case_id -> list of charges
            
        Returns:
            New case data in JSONB format
        """
        case_id = old_case['case_id']
        
        # Transform case numbers
        case_numbers = {}
        if old_case.get('court_case_number'):
            case_numbers['court'] = old_case['court_case_number']
        if old_case.get('prosecution_case_number'):
            case_numbers['prosecution'] = old_case['prosecution_case_number']
        if old_case.get('police_report_number'):
            case_numbers['police'] = old_case['police_report_number']
        if old_case.get('internal_report_number'):
            case_numbers['internal'] = old_case['internal_report_number']
        
        # Generate variations
        variations = []
        for key, value in case_numbers.items():
            if value:
                variations.append(value)
                # Try reversed format
                if '/' in value:
                    parts = value.split('/')
                    if len(parts) == 2:
                        variations.append(f"{parts[1]}/{parts[0]}")
        case_numbers['variations'] = list(set(variations))
        
        # Transform parties
        parties = []
        case_party_rels = case_parties_map.get(case_id, [])
        for rel in case_party_rels:
            party_id = rel['party_id']
            party_data = parties_map.get(party_id)
            if party_data:
                party_jsonb = {
                    'party_entity_id': f"P{len(parties) + 1:03d}",
                    'name_ar': party_data.get('full_name_ar'),
                    'name_en': party_data.get('full_name_en'),
                    'personal_id': party_data.get('personal_id'),
                    'nationality': party_data.get('nationality'),
                    'age': party_data.get('age'),
                    'gender': party_data.get('gender'),
                    'role': rel.get('role_type'),
                    'roles': [rel.get('role_type')] if rel.get('role_type') else [],
                    'occupation': party_data.get('occupation'),
                    'phone': party_data.get('phone_mobile') or party_data.get('phone_landline'),
                    'address': self._build_address(party_data)
                }
                parties.append(party_jsonb)
        
        # Transform dates
        key_dates = {}
        if old_case.get('incident_date'):
            key_dates['incident'] = old_case['incident_date'].isoformat()[:10] if hasattr(old_case['incident_date'], 'isoformat') else str(old_case['incident_date'])[:10]
        if old_case.get('report_date'):
            key_dates['report_filed'] = old_case['report_date'].isoformat()[:10] if hasattr(old_case['report_date'], 'isoformat') else str(old_case['report_date'])[:10]
        if old_case.get('case_opened_date'):
            key_dates['case_transfer'] = old_case['case_opened_date'].isoformat()[:10] if hasattr(old_case['case_opened_date'], 'isoformat') else str(old_case['case_opened_date'])[:10]
        if old_case.get('final_judgment_date'):
            key_dates['judgment'] = old_case['final_judgment_date'].isoformat()[:10] if hasattr(old_case['final_judgment_date'], 'isoformat') else str(old_case['final_judgment_date'])[:10]
        
        # Transform locations
        locations = {}
        if old_case.get('court_name'):
            locations['court'] = old_case['court_name']
        if old_case.get('police_station'):
            locations['police_station'] = old_case['police_station']
        if old_case.get('prosecution_office'):
            locations['prosecution_office'] = old_case['prosecution_office']
        
        # Transform charges
        charges = []
        case_charges = charges_map.get(case_id, [])
        for i, charge in enumerate(case_charges, 1):
            charge_jsonb = {
                'charge_entity_id': f"C{i:03d}",
                'charge_number': charge.get('charge_number'),
                'description_ar': charge.get('charge_description_ar'),
                'description_en': charge.get('charge_description_en'),
                'article_number': charge.get('article_number'),
                'law_name': charge.get('law_name_ar'),
                'law_year': charge.get('law_year'),
                'status': charge.get('charge_status', 'pending')
            }
            charges.append(charge_jsonb)
        
        # Transform case status
        case_status = {
            'current_status': old_case.get('current_status', 'open'),
            'status_date': old_case.get('status_date').isoformat()[:10] if old_case.get('status_date') and hasattr(old_case['status_date'], 'isoformat') else None,
            'case_type': old_case.get('case_type', 'criminal'),
            'case_category': old_case.get('case_category'),
            'summary_ar': old_case.get('case_summary_ar'),
            'summary_en': old_case.get('case_summary_en')
        }
        
        # Build timeline
        timeline = []
        for date_key, date_value in key_dates.items():
            if date_value:
                timeline.append({
                    'date': date_value,
                    'event_type': date_key,
                    'source_document': 'migrated'
                })
        timeline.sort(key=lambda x: x.get('date', ''))
        
        return {
            'case_numbers': case_numbers,
            'parties': parties,
            'key_dates': key_dates,
            'locations': locations,
            'charges': charges,
            'judgments': [],
            'financial': {'fines': [], 'damages': [], 'bail': None},
            'evidence': [],
            'case_status': case_status,
            'legal_references': [],
            'timeline': timeline
        }
    
    def _build_address(self, party_data: Dict) -> Optional[str]:
        """Build address string from party data"""
        parts = []
        if party_data.get('area'):
            parts.append(party_data['area'])
        if party_data.get('compound'):
            parts.append(party_data['compound'])
        if party_data.get('street'):
            parts.append(party_data['street'])
        return ', '.join(parts) if parts else None
    
    def migrate(self, dry_run: bool = True):
        """
        Perform full migration from old to new schema
        
        Args:
            dry_run: If True, only show what would be migrated without actually migrating
        """
        logger.info(f"Starting migration (dry_run={dry_run})...")
        
        # Export old data
        old_cases = self.export_old_cases()
        old_documents = self.export_old_documents()
        old_parties = self.export_old_parties()
        old_case_parties = self.export_old_case_parties()
        old_charges = self.export_old_charges()
        
        # Build maps for efficient lookup
        parties_map = {p['party_id']: p for p in old_parties}
        
        case_parties_map = {}
        for rel in old_case_parties:
            case_id = rel['case_id']
            if case_id not in case_parties_map:
                case_parties_map[case_id] = []
            case_parties_map[case_id].append(rel)
        
        charges_map = {}
        for charge in old_charges:
            case_id = charge['case_id']
            if case_id not in charges_map:
                charges_map[case_id] = []
            charges_map[case_id].append(charge)
        
        # Transform and migrate cases
        migrated_cases = []
        case_id_mapping = {}  # old_case_id -> new_case_id
        
        if not dry_run:
            with DatabaseManagerV2(**self.new_db_config) as new_db:
                for old_case in old_cases:
                    try:
                        # Transform to new format
                        new_case_data = self.transform_case_to_jsonb(
                            old_case,
                            parties_map,
                            case_parties_map,
                            charges_map
                        )
                        
                        # Create in new database
                        new_case_id = new_db.create_case(new_case_data)
                        case_id_mapping[old_case['case_id']] = new_case_id
                        migrated_cases.append({
                            'old_case_id': old_case['case_id'],
                            'new_case_id': new_case_id,
                            'status': 'success'
                        })
                        
                        logger.info(f"Migrated case {old_case['case_id']} -> {new_case_id}")
                    
                    except Exception as e:
                        logger.error(f"Error migrating case {old_case['case_id']}: {str(e)}")
                        migrated_cases.append({
                            'old_case_id': old_case['case_id'],
                            'new_case_id': None,
                            'status': 'error',
                            'error': str(e)
                        })
        else:
            # Dry run - just show what would be migrated
            for old_case in old_cases:
                new_case_data = self.transform_case_to_jsonb(
                    old_case,
                    parties_map,
                    case_parties_map,
                    charges_map
                )
                migrated_cases.append({
                    'old_case_id': old_case['case_id'],
                    'new_case_data': new_case_data,
                    'status': 'would_migrate'
                })
                logger.info(f"Would migrate case {old_case['case_id']}")
        
        # Summary
        print(f"\n{'='*60}")
        print("MIGRATION SUMMARY")
        print(f"{'='*60}")
        print(f"Total cases to migrate: {len(old_cases)}")
        print(f"Successfully migrated: {len([c for c in migrated_cases if c['status'] == 'success'])}")
        print(f"Errors: {len([c for c in migrated_cases if c['status'] == 'error'])}")
        print(f"{'='*60}\n")
        
        return {
            'old_cases_count': len(old_cases),
            'migrated_cases': migrated_cases,
            'case_id_mapping': case_id_mapping
        }


def main():
    """Main migration function"""
    import sys
    
    dry_run = '--execute' not in sys.argv
    
    if dry_run:
        print("DRY RUN MODE - No changes will be made")
        print("Use --execute to perform actual migration\n")
    else:
        response = input("This will migrate data to the new schema. Continue? (y/N): ")
        if response.lower() != 'y':
            print("Migration cancelled.")
            return
    
    migrator = DataMigrator()
    results = migrator.migrate(dry_run=dry_run)
    
    if dry_run:
        print("\nDry run completed. Review the output above.")
        print("Run with --execute to perform actual migration.")


if __name__ == '__main__':
    main()

