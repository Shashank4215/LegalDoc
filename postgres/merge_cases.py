"""
Script to merge multiple cases into a primary case
"""

import logging
from .db_manager_v2 import DatabaseManagerV2
from case_linker import CaseLinker
from config import CONFIG

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def merge_cases(primary_case_id: int, case_ids_to_merge: list[int], dry_run: bool = False):
    """
    Merge multiple cases into a primary case
    
    Args:
        primary_case_id: The case ID to merge into (will be kept)
        case_ids_to_merge: List of case IDs to merge into the primary case
        dry_run: If True, only show what would be done without making changes
    """
    logger.info(f"{'='*60}")
    logger.info(f"Starting case merge operation")
    logger.info(f"Primary case ID: {primary_case_id}")
    logger.info(f"Cases to merge: {case_ids_to_merge}")
    logger.info(f"Dry run mode: {dry_run}")
    logger.info(f"{'='*60}")
    
    with DatabaseManagerV2(**CONFIG['database']) as db:
        logger.info("Database connection established")
        case_linker = CaseLinker(db)
        logger.info("CaseLinker initialized")
        
        # Get primary case
        logger.info(f"Fetching primary case {primary_case_id}...")
        primary_case = db.get_case(primary_case_id)
        if not primary_case:
            logger.error(f"Primary case {primary_case_id} not found")
            return False
        
        # Log primary case info
        primary_parties = len(primary_case.get('parties', [])) if isinstance(primary_case.get('parties'), list) else 0
        primary_charges = len(primary_case.get('charges', [])) if isinstance(primary_case.get('charges'), list) else 0
        logger.info(f"Primary case {primary_case_id} found: {primary_parties} parties, {primary_charges} charges")
        
        logger.info(f"{'[DRY RUN] ' if dry_run else ''}Merging cases {case_ids_to_merge} into case {primary_case_id}")
        
        if not dry_run:
            # Merge each case into the primary case (one at a time)
            for idx, case_id in enumerate(case_ids_to_merge, 1):
                logger.info(f"\n{'='*60}")
                logger.info(f"Processing case {idx}/{len(case_ids_to_merge)}: Case ID {case_id}")
                logger.info(f"{'='*60}")
                
                if case_id == primary_case_id:
                    logger.warning(f"Skipping case {case_id} (same as primary case)")
                    continue
                
                try:
                    # Check connection before each operation
                    logger.debug("Checking database connection...")
                    try:
                        db.connection.cursor().execute("SELECT 1")
                        logger.debug("Connection is active")
                    except:
                        logger.warning("Connection lost, reconnecting...")
                        db.connect()
                        logger.info("Reconnected successfully")
                    
                    logger.info(f"Fetching case {case_id}...")
                    case_to_merge = db.get_case(case_id)
                    if not case_to_merge:
                        logger.warning(f"Case {case_id} not found, skipping")
                        continue
                    
                    # Log case info
                    merge_parties = len(case_to_merge.get('parties', [])) if isinstance(case_to_merge.get('parties'), list) else 0
                    merge_charges = len(case_to_merge.get('charges', [])) if isinstance(case_to_merge.get('charges'), list) else 0
                    logger.info(f"Case {case_id} found: {merge_parties} parties, {merge_charges} charges")
                    
                    logger.info(f"Starting merge of case {case_id} into case {primary_case_id}...")
                    
                    # Get all documents from the case to merge
                    logger.info(f"Fetching documents from case {case_id}...")
                    documents = db.get_documents_by_case(case_id)
                    logger.info(f"Found {len(documents)} documents in case {case_id}")
                    
                    # Merge entities from the case to merge
                    logger.info(f"Extracting entities from case {case_id}...")
                    entities_to_merge = {
                        'case_numbers': case_to_merge.get('case_numbers', {}),
                        'parties': case_to_merge.get('parties', []),
                        'dates': case_to_merge.get('key_dates', {}),
                        'locations': case_to_merge.get('locations', {}),
                        'charges': case_to_merge.get('charges', []),
                        'judgments': case_to_merge.get('judgments', []),
                        'financial': case_to_merge.get('financial', {}),
                        'evidence': case_to_merge.get('evidence', []),
                        'case_status': case_to_merge.get('case_status', {}),
                        'legal_references': case_to_merge.get('legal_references', [])
                    }
                    
                    # Count entities
                    entity_counts = {
                        'parties': len(entities_to_merge.get('parties', [])),
                        'charges': len(entities_to_merge.get('charges', [])),
                        'judgments': len(entities_to_merge.get('judgments', [])),
                        'evidence': len(entities_to_merge.get('evidence', []))
                    }
                    logger.info(f"Extracted entities: {entity_counts}")
                    
                    # Merge entities into primary case (this may take time)
                    logger.info(f"Merging entities into primary case {primary_case_id}...")
                    logger.info("This may take a moment if there are many entities...")
                    case_linker.merge_entities_into_case(
                        primary_case_id,
                        entities_to_merge,
                        source_document=f"merged_from_case_{case_id}"
                    )
                    logger.info(f"✓ Entity merge completed for case {case_id}")
                    
                    # Update all documents to point to primary case
                    logger.info(f"Linking {len(documents)} documents to case {primary_case_id}...")
                    linked_count = 0
                    for doc_idx, doc in enumerate(documents, 1):
                        try:
                            db.connection.cursor().execute("SELECT 1")
                        except:
                            logger.warning("Connection lost during document linking, reconnecting...")
                            db.connect()
                            logger.info("Reconnected successfully")
                        
                        db.update_document_case(doc['document_id'], primary_case_id, confidence_score=0.95)
                        linked_count += 1
                        if doc_idx % 5 == 0 or doc_idx == len(documents):
                            logger.info(f"  Linked {linked_count}/{len(documents)} documents...")
                    
                    logger.info(f"✓ All {len(documents)} documents linked to case {primary_case_id}")
                    
                    # Delete the merged case (only after successful merge)
                    logger.info(f"Deleting merged case {case_id}...")
                    try:
                        db.connection.cursor().execute("SELECT 1")
                    except:
                        logger.warning("Connection lost before deletion, reconnecting...")
                        db.connect()
                        logger.info("Reconnected successfully")
                    
                    try:
                        with db.connection.cursor() as cursor:
                            cursor.execute("DELETE FROM cases WHERE case_id = %s", (case_id,))
                            db.connection.commit()
                            logger.info(f"✓ Deleted merged case {case_id}")
                    except Exception as e:
                        logger.error(f"Error deleting case {case_id}: {str(e)}")
                        # Don't fail the whole operation if deletion fails
                    
                    logger.info(f"✓ Successfully merged case {case_id} into case {primary_case_id}")
                
                except Exception as e:
                    logger.error(f"✗ Error merging case {case_id}: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
                    # Try to reconnect for next case
                    try:
                        logger.info("Attempting to reconnect...")
                        db.connect()
                        logger.info("Reconnected successfully")
                    except Exception as reconnect_error:
                        logger.error(f"Failed to reconnect: {str(reconnect_error)}")
                    # Continue with next case
                    continue
            
            logger.info(f"\n{'='*60}")
            logger.info(f"✓ Successfully merged all cases {case_ids_to_merge} into case {primary_case_id}")
            logger.info(f"{'='*60}")
        else:
            # Dry run - just show what would be done
            logger.info("DRY RUN MODE - No changes will be made")
            logger.info(f"\nAnalyzing cases to merge...")
            
            for idx, case_id in enumerate(case_ids_to_merge, 1):
                logger.info(f"\n  Case {idx}/{len(case_ids_to_merge)}: Case ID {case_id}")
                if case_id == primary_case_id:
                    logger.warning(f"    ⚠ Skipping (same as primary case)")
                    continue
                
                logger.info(f"    Fetching case {case_id}...")
                case_to_merge = db.get_case(case_id)
                if not case_to_merge:
                    logger.warning(f"    ⚠ Case {case_id} not found")
                    continue
                
                documents = db.get_documents_by_case(case_id)
                parties_count = len(case_to_merge.get('parties', [])) if isinstance(case_to_merge.get('parties'), list) else 0
                charges_count = len(case_to_merge.get('charges', [])) if isinstance(case_to_merge.get('charges'), list) else 0
                
                logger.info(f"    ✓ Case {case_id} found:")
                logger.info(f"      - Documents: {len(documents)}")
                logger.info(f"      - Parties: {parties_count}")
                logger.info(f"      - Charges: {charges_count}")
                logger.info(f"    → Would merge into case {primary_case_id}")
        
        logger.info(f"\n{'='*60}")
        logger.info("Merge operation completed")
        logger.info(f"{'='*60}\n")
        return True


def main():
    """Main function"""
    import sys
    
    # Default: merge cases 2 and 3 into case 1
    primary_case_id = 1
    cases_to_merge = [2, 3]
    
    # Check for command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == '--dry-run':
            dry_run = True
        else:
            primary_case_id = int(sys.argv[1])
            cases_to_merge = [int(x) for x in sys.argv[2:]] if len(sys.argv) > 2 else [2, 3]
            dry_run = '--dry-run' in sys.argv
    else:
        dry_run = False
    
    print(f"\n{'='*60}")
    print(f"CASE MERGE OPERATION")
    print(f"{'='*60}")
    print(f"Primary case: {primary_case_id}")
    print(f"Cases to merge: {cases_to_merge}")
    print(f"Dry run: {dry_run}")
    print(f"{'='*60}\n")
    
    if not dry_run:
        response = input("Are you sure you want to merge these cases? (yes/no): ")
        if response.lower() != 'yes':
            print("Merge cancelled.")
            return
    
    merge_cases(primary_case_id, cases_to_merge, dry_run=dry_run)
    
    print(f"\n{'='*60}")
    print("MERGE COMPLETE")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()

