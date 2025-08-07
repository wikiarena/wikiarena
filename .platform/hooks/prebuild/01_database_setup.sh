#!/bin/bash
# Platform Hook: Database Setup for Wiki Arena
# 
# This script runs during Elastic Beanstalk deployment BEFORE the application starts.
# It downloads the 33GB Wikipedia graph database from S3 and sets it up for the application.
# 
# Platform Hook benefits:
# - Runs as root (no permission issues)
# - Access to EB environment variables (DATABASE_S3_BUCKET)
# - Fails deployment if database setup fails (safer than ignoring errors)
# - Deployed with application code (version controlled)
# - Only runs during deployments (not every app restart)

set -e  # Exit on any error
exec > >(tee /var/log/wiki-arena-database-setup.log) 2>&1  # Log everything

echo "=== Wiki Arena Database Setup Started at $(date) ==="

# Get environment variables from Elastic Beanstalk
# Use EB's get-config utility to access environment variables
DATABASE_S3_BUCKET=$(/opt/elasticbeanstalk/bin/get-config environment -k DATABASE_S3_BUCKET)
DATABASE_PATH="/var/app/database/wiki_graph.sqlite"
DATABASE_DIR="/var/app/database"
TEMP_GZ="/tmp/wiki_graph.sqlite.gz"

echo "Setting up database from S3 bucket: $DATABASE_S3_BUCKET"

# Create database directory with proper permissions for webapp user
echo "Creating database directory: $DATABASE_DIR"
mkdir -p "$DATABASE_DIR"
chown webapp:webapp "$DATABASE_DIR"
chmod 755 "$DATABASE_DIR"

# Check if database already exists (handles instance restarts and redeployments)
if [ -f "$DATABASE_PATH" ]; then
    DB_SIZE=$(du -h "$DATABASE_PATH" | cut -f1)
    echo "Database already exists at $DATABASE_PATH (Size: $DB_SIZE)"
    echo "Skipping download - using existing database"
    exit 0
fi

echo "Database not found locally - downloading from S3..."

# Validate S3 bucket is configured
if [ -z "$DATABASE_S3_BUCKET" ]; then
    echo "ERROR: DATABASE_S3_BUCKET environment variable not set"
    echo "Check Elastic Beanstalk environment configuration"
    exit 1
fi

# Download compressed database from S3
echo "Downloading compressed database from s3://$DATABASE_S3_BUCKET/wiki_graph.sqlite.gz..."
if ! aws s3 cp "s3://$DATABASE_S3_BUCKET/wiki_graph.sqlite.gz" "$TEMP_GZ"; then
    echo "ERROR: Failed to download database from S3"
    echo "Check:"
    echo "  1. S3 bucket exists: $DATABASE_S3_BUCKET"
    echo "  2. File exists: s3://$DATABASE_S3_BUCKET/wiki_graph.sqlite.gz"
    echo "  3. EC2 instance has S3 read permissions"
    exit 1
fi

# Verify download
if [ ! -f "$TEMP_GZ" ]; then
    echo "ERROR: Downloaded file not found at $TEMP_GZ"
    exit 1
fi

COMPRESSED_SIZE=$(du -h "$TEMP_GZ" | cut -f1)
echo "Downloaded compressed database: $COMPRESSED_SIZE"

# Decompress database to final location
echo "Decompressing database to $DATABASE_PATH..."
if ! gunzip -c "$TEMP_GZ" > "$DATABASE_PATH"; then
    echo "ERROR: Failed to decompress database"
    rm -f "$TEMP_GZ" "$DATABASE_PATH"
    exit 1
fi

# Set proper ownership and permissions
chown webapp:webapp "$DATABASE_PATH"
chmod 644 "$DATABASE_PATH"

# Verify final database
if [ ! -f "$DATABASE_PATH" ]; then
    echo "ERROR: Database file not found after decompression"
    exit 1
fi

FINAL_SIZE=$(du -h "$DATABASE_PATH" | cut -f1)
echo "Database decompression complete. Final size: $FINAL_SIZE"

# Clean up temporary files
rm -f "$TEMP_GZ"

# Verify database integrity (basic SQLite check)
echo "Performing basic database integrity check..."
if ! sqlite3 "$DATABASE_PATH" "PRAGMA quick_check;" > /dev/null 2>&1; then
    echo "WARNING: Database integrity check failed - database may be corrupted"
    # Don't exit here - let the application handle the error
else
    echo "Database integrity check passed"
fi

echo "=== Database setup completed successfully at $(date) ==="
echo "Database ready at: $DATABASE_PATH"
echo "Application can now start and use the database"