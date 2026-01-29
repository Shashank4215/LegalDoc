#!/bin/bash
# MongoDB Export Script
# Exports MongoDB database for migration to VM

set -e

# Configuration
DB_NAME="${MONGODB_DATABASE:-legal_cases_v2}"
DB_HOST="${MONGODB_HOST:-localhost}"
DB_PORT="${MONGODB_PORT:-27017}"
BACKUP_DIR="${BACKUP_DIR:-~/mongodb_backup}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
EXPORT_DIR="${BACKUP_DIR}/mongodb_export_${TIMESTAMP}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}MongoDB Export Script${NC}"
echo "========================"
echo "Database: ${DB_NAME}"
echo "Host: ${DB_HOST}:${DB_PORT}"
echo "Export Directory: ${EXPORT_DIR}"
echo ""

# Check if MongoDB is running
if ! mongosh --host ${DB_HOST} --port ${DB_PORT} --eval "db.adminCommand('ping')" > /dev/null 2>&1; then
    echo -e "${RED}Error: MongoDB is not running or not accessible at ${DB_HOST}:${DB_PORT}${NC}"
    exit 1
fi

# Create backup directory
mkdir -p "${BACKUP_DIR}"
echo -e "${GREEN}✓ Created backup directory: ${BACKUP_DIR}${NC}"

# Check if database exists
DB_EXISTS=$(mongosh --host ${DB_HOST} --port ${DB_PORT} --quiet --eval "db.getMongo().getDBNames().indexOf('${DB_NAME}') >= 0 ? 'true' : 'false'")

if [ "$DB_EXISTS" != "true" ]; then
    echo -e "${YELLOW}Warning: Database '${DB_NAME}' does not exist${NC}"
    exit 1
fi

# Export database
echo -e "${GREEN}Exporting database...${NC}"
if mongodump --host ${DB_HOST} --port ${DB_PORT} --db ${DB_NAME} --out "${EXPORT_DIR}"; then
    echo -e "${GREEN}✓ Export completed successfully${NC}"
else
    echo -e "${RED}✗ Export failed${NC}"
    exit 1
fi

# Create compressed archive
echo -e "${GREEN}Creating compressed archive...${NC}"
ARCHIVE_NAME="${BACKUP_DIR}/mongodb_export_${TIMESTAMP}.tar.gz"
cd "${BACKUP_DIR}"
tar -czf "${ARCHIVE_NAME}" "mongodb_export_${TIMESTAMP}"
echo -e "${GREEN}✓ Archive created: ${ARCHIVE_NAME}${NC}"

# Show export statistics
echo ""
echo -e "${GREEN}Export Statistics:${NC}"
echo "=================="
ARCHIVE_SIZE=$(du -h "${ARCHIVE_NAME}" | cut -f1)
echo "Archive size: ${ARCHIVE_SIZE}"
echo "Archive location: ${ARCHIVE_NAME}"
echo ""

# List collections exported
COLLECTIONS=$(mongosh --host ${DB_HOST} --port ${DB_PORT} --quiet --eval "db.getSiblingDB('${DB_NAME}').getCollectionNames().join('\n')")
echo -e "${GREEN}Collections exported:${NC}"
echo "$COLLECTIONS" | while read -r collection; do
    if [ ! -z "$collection" ]; then
        COUNT=$(mongosh --host ${DB_HOST} --port ${DB_PORT} --quiet --eval "db.getSiblingDB('${DB_NAME}').${collection}.countDocuments()")
        echo "  - ${collection}: ${COUNT} documents"
    fi
done

echo ""
echo -e "${GREEN}✓ Export completed!${NC}"
echo ""
echo "Next steps:"
echo "1. Transfer the archive to your VM:"
echo "   scp ${ARCHIVE_NAME} username@vm_ip:/tmp/"
echo ""
echo "2. On the VM, extract and import:"
echo "   tar -xzf /tmp/mongodb_export_${TIMESTAMP}.tar.gz"
echo "   mongorestore --db ${DB_NAME} /tmp/mongodb_export_${TIMESTAMP}/${DB_NAME}"

