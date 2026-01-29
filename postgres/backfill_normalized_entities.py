"""
Backfill normalized entity tables (parties/charges/evidence) from documents.extracted_entities.

Why:
- Existing cases may have corrupted/duplicated JSONB arrays.
- documents.extracted_entities is usually much cleaner (per-document bounded extraction).

This script:
- Requires the normalized tables to exist (run apply_schema_v2.py first).
- Iterates documents with a case_id and extracted_entities
- Inserts/links parties/charges/evidence into normalized tables
"""

from __future__ import annotations

from typing import Any, Dict

from psycopg2.extras import RealDictCursor

from config import CONFIG
from .db_manager_v2 import DatabaseManagerV2


def main() -> int:
    db_cfg = CONFIG["database"]
    with DatabaseManagerV2(**db_cfg) as db:
        required_tables = ["parties", "case_parties", "charges", "case_charges", "evidence_items", "case_evidence"]
        missing = [t for t in required_tables if not db.table_exists(t)]
        if missing:
            print(f"ERROR: missing tables: {missing}. Run apply_schema_v2.py first.")
            return 1

        with db.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT document_id, case_id, file_path, extracted_entities
                FROM documents
                WHERE case_id IS NOT NULL
                  AND extracted_entities IS NOT NULL
                  AND processing_status = 'processed'
                ORDER BY document_id ASC
                """
            )
            docs = cursor.fetchall()

        print(f"Backfilling from {len(docs)} documents...")

        for d in docs:
            document_id = d["document_id"]
            case_id = d["case_id"]
            entities: Dict[str, Any] = d.get("extracted_entities") or {}

            parties = entities.get("parties", []) or []
            for p in parties:
                pid = db.get_or_create_party_entity(p)
                if pid:
                    role = p.get("role")
                    if not role and isinstance(p.get("roles"), list) and p["roles"]:
                        role = p["roles"][0]
                    db.link_party_entity_to_case(
                        case_id=case_id,
                        party_id=pid,
                        role_type=role,
                        source_document_id=document_id,
                        confidence_score=None,
                    )

            charges = entities.get("charges", []) or []
            for c in charges:
                cid = db.get_or_create_charge_entity(c)
                if cid:
                    db.link_charge_entity_to_case(
                        case_id=case_id,
                        charge_id=cid,
                        status=c.get("status"),
                        source_document_id=document_id,
                    )

            evidence = entities.get("evidence", []) or []
            for ev in evidence:
                evid = db.get_or_create_evidence_entity(ev)
                if evid:
                    db.link_evidence_entity_to_case(
                        case_id=case_id,
                        evidence_id=evid,
                        source_document_id=document_id,
                    )

            if document_id % 25 == 0:
                print(f"... processed document_id={document_id}")

        print("Backfill complete.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())


