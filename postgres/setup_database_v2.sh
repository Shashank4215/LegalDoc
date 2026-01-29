#!/bin/bash
# Setup script for PostgreSQL v2 database with pgvector extension

set -e

echo "=========================================="
echo "Setting up Legal Case Database v2"
echo "=========================================="

# Database configuration (update these if needed)
DB_NAME="legal_case_v2"
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-postgres}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

echo "Database: $DB_NAME"
echo "User: $DB_USER"
echo "Host: $DB_HOST"
echo "Port: $DB_PORT"
echo ""

# Check if psql is available
if ! command -v psql &> /dev/null; then
    echo "ERROR: psql command not found"
    echo "Please install PostgreSQL client tools or use pgAdmin4"
    echo ""
    echo "To use pgAdmin4:"
    echo "1. Open pgAdmin4"
    echo "2. Connect to your PostgreSQL server"
    echo "3. Create a new database named: $DB_NAME"
    echo "4. Run the SQL from schema_minimal.sql in the Query Tool"
    exit 1
fi

# Set PGPASSWORD environment variable
export PGPASSWORD="$DB_PASSWORD"

echo "Step 1: Creating database..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME;" 2>/dev/null || true
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "CREATE DATABASE $DB_NAME;" || {
    echo "ERROR: Failed to create database"
    exit 1
}

echo "Step 2: Database ready (using FAISS for vector similarity - no extension needed)"

echo "Step 3: Creating schema..."
if [ -f "schema_minimal.sql" ]; then
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f schema_minimal.sql || {
        echo "ERROR: Failed to create schema"
        exit 1
    }
    echo "Schema created successfully!"
else
    echo "ERROR: schema_minimal.sql not found"
    exit 1
fi

echo ""
echo "=========================================="
echo "Database setup completed!"
echo "=========================================="
echo "Database: $DB_NAME"
echo "You can now use the new vector-based architecture"
echo ""

