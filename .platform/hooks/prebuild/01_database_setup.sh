#!/bin/bash
# Platform Hook: EBS Database Mount for Wiki Arena
# 
# This script runs during Elastic Beanstalk deployment BEFORE the application starts.
# It mounts the pre-existing EBS volume containing the Wikipedia database.
# 
# NEW APPROACH: Database is pre-loaded in an EBS snapshot, so we just mount it.
# This eliminates the 30+ minute download time that was causing deployment timeouts.
# 
# Platform Hook benefits:
# - Runs as root (no permission issues)
# - Fails deployment if database mount fails (safer than ignoring errors)
# - Deployed with application code (version controlled)
# - FAST: 10 seconds vs 30+ minutes for S3 download

set -e  # Exit on any error
exec > >(tee /var/log/wiki-arena-database-setup.log) 2>&1  # Log everything

echo "=== Wiki Arena EBS Database Mount Started at $(date) ==="

# Get environment variables from Elastic Beanstalk
EBS_VOLUME_ID=$(/opt/elasticbeanstalk/bin/get-config environment -k EBS_VOLUME_ID)
DATABASE_PATH="/var/app/database/wiki_graph.sqlite"
MOUNT_POINT="/var/app/database"

echo "Mounting EBS volume: $EBS_VOLUME_ID"

# Validate EBS volume ID is configured
if [ -z "$EBS_VOLUME_ID" ]; then
    echo "ERROR: EBS_VOLUME_ID environment variable not set"
    echo "Check Elastic Beanstalk environment configuration"
    exit 1
fi

# Create mount point with proper permissions
echo "Creating mount point: $MOUNT_POINT"
mkdir -p "$MOUNT_POINT"
chown webapp:webapp "$MOUNT_POINT"
chmod 755 "$MOUNT_POINT"

# Check if database is already mounted and accessible
if [ -f "$DATABASE_PATH" ]; then
    DB_SIZE=$(du -h "$DATABASE_PATH" | cut -f1)
    echo "Database already mounted at $DATABASE_PATH (Size: $DB_SIZE)"
    echo "Verifying database accessibility..."
    
    # Quick verification that database is readable
    if sqlite3 "$DATABASE_PATH" "PRAGMA quick_check;" > /dev/null 2>&1; then
        echo "Database verification passed - setup complete"
        exit 0
    else
        echo "WARNING: Existing database failed verification - remounting..."
        umount "$MOUNT_POINT" 2>/dev/null || true
    fi
fi

# Wait for EBS device to be available (both traditional and NVMe naming)
echo "Waiting for EBS device to be available..."
DEVICE_PATH=""
for i in {1..30}; do
    # Check for traditional naming first
    if [ -b "/dev/xvdf" ]; then
        DEVICE_PATH="/dev/xvdf"
        echo "EBS device found at: $DEVICE_PATH"
        break
    # Check for NVMe naming (modern instance types)
    elif [ -b "/dev/nvme1n1" ]; then
        DEVICE_PATH="/dev/nvme1n1"
        echo "EBS device found at: $DEVICE_PATH (NVMe interface)"
        break
    fi
    
    if [ $i -eq 30 ]; then
        echo "ERROR: EBS device not found after 5 minutes"
        echo "Checked: /dev/xvdf and /dev/nvme1n1"
        echo "Available block devices:"
        lsblk
        echo "Check that EBS volume $EBS_VOLUME_ID is properly attached"
        exit 1
    fi
    sleep 10
done

# Mount the EBS volume
echo "Mounting EBS volume from $DEVICE_PATH to $MOUNT_POINT..."
if ! mount "$DEVICE_PATH" "$MOUNT_POINT"; then
    echo "ERROR: Failed to mount EBS volume"
    echo "Device: $DEVICE_PATH"
    echo "Mount point: $MOUNT_POINT"
    echo "EBS Volume ID: $EBS_VOLUME_ID"
    exit 1
fi

# Verify the database file exists on the mounted volume
if [ ! -f "$DATABASE_PATH" ]; then
    echo "ERROR: Database file not found at $DATABASE_PATH after mounting"
    echo "This indicates the EBS snapshot may not contain the database"
    echo "Check that the snapshot was created correctly"
    umount "$MOUNT_POINT" || true
    exit 1
fi

# Set proper ownership for the database file
chown webapp:webapp "$DATABASE_PATH"
chmod 644 "$DATABASE_PATH"

# Verify database integrity
echo "Performing database integrity check..."
if ! sqlite3 "$DATABASE_PATH" "PRAGMA quick_check;" > /dev/null 2>&1; then
    echo "ERROR: Database integrity check failed"
    echo "The database may be corrupted or incomplete"
    umount "$MOUNT_POINT" || true
    exit 1
fi

# Get final database size for confirmation
FINAL_SIZE=$(du -h "$DATABASE_PATH" | cut -f1)
MOUNT_INFO=$(df -h "$MOUNT_POINT" | tail -1)

echo "Database integrity check passed"
echo "Database size: $FINAL_SIZE"
echo "Mount info: $MOUNT_INFO"

echo "=== EBS Database mount completed successfully at $(date) ==="
echo "Database ready at: $DATABASE_PATH"
echo "Mount point: $MOUNT_POINT"
echo "EBS Volume: $EBS_VOLUME_ID"
echo "Application can now start and use the database"