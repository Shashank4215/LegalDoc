#!/bin/bash
# MongoDB Import Script
# Imports MongoDB database on VM

set -e

# Configuration
DB_NAME="${MONGODB_DATABASE:-legal_cases_v2}"
DB_HOST="${MONGODB_HOST:-localhost}"
DB_PORT="${MONGODB_PORT:-27017}"
IMPORT_DIR="${1:-/tmp/mongodb_export_*}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}MongoDB Import Script${NC}"
echo "========================"
echo "Database: ${DB_NAME}"
echo "Host: ${DB_HOST}:${DB_PORT}"
echo "Import Directory: ${IMPORT_DIR}"
echo ""

# Check if MongoDB is running
if ! mongosh --host ${DB_HOST} --port ${DB_PORT} --eval "db.adminCommand('ping')" > /dev/null 2>&1; then
    echo -e "${RED}Error: MongoDB is not running or not accessible at ${DB_HOST}:${DB_PORT}${NC}"
    echo "Start MongoDB with: sudo systemctl start mongod"
    exit 1
fi

# Check if import directory exists
if [ ! -d "${IMPORT_DIR}" ]; then
    echo -e "${RED}Error: Import directory not found: ${IMPORT_DIR}${NC}"
    echo "Usage: $0 /path/to/mongodb_export_directory"
    exit 1
fi

# Check if database directory exists in export
DB_EXPORT_DIR="${IMPORT_DIR}/${DB_NAME}"
if [ ! -d "${DB_EXPORT_DIR}" ]; then
    echo -e "${RED}Error: Database directory not found: ${DB_EXPORT_DIR}${NC}"
    exit 1
fi

# Ask for confirmation
echo -e "${YELLOW}Warning: This will import data into database '${DB_NAME}'${NC}"
if [ -n "${MONGODB_DROP_EXISTING}" ] && [ "${MONGODB_DROP_EXISTING}" = "true" ]; then
    echo -e "${YELLOW}Existing database will be dropped!${NC}"
    read -p "Continue? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Import cancelled"
        exit 0
    fi
    
    # Drop existing database
    echo -e "${YELLOW}Dropping existing database...${NC}"
    mongosh --host ${DB_HOST} --port ${DB_PORT} --eval "db.getSiblingDB('${DB_NAME}').dropDatabase()"
fi

# Import database
echo -e "${GREEN}Importing database...${NC}"
if mongorestore --host ${DB_HOST} --port ${DB_PORT} --db ${DB_NAME} "${DB_EXPORT_DIR}"; then
    echo -e "${GREEN}✓ Import completed successfully${NC}"
else
    echo -e "${RED}✗ Import failed${NC}"
    exit 1
fi

# Verify import
echo ""
echo -e "${GREEN}Verifying import...${NC}"
COLLECTIONS=$(mongosh --host ${DB_HOST} --port ${DB_PORT} --quiet --eval "db.getSiblingDB('${DB_NAME}').getCollectionNames().join('\n')")
echo -e "${GREEN}Collections imported:${NC}"
echo "$COLLECTIONS" | while read -r collection; do
    if [ ! -z "$collection" ]; then
        COUNT=$(mongosh --host ${DB_HOST} --port ${DB_PORT} --quiet --eval "db.getSiblingDB('${DB_NAME}').${collection}.countDocuments()")
        echo "  - ${collection}: ${COUNT} documents"
    fi
done

echo ""
echo -e "${GREEN}✓ Import completed successfully!${NC}"

