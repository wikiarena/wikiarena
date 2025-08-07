"""
EBS Volume Mounting and S3 Database Download for Elastic Beanstalk

This module handles mounting the EBS volume and downloading the SQLite database
from S3 if it doesn't exist locally.
"""

import os
import subprocess
import logging
import gzip
import shutil
import asyncio
from pathlib import Path
from typing import Optional
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

class EBSVolumeManager:
    """Manages EBS volume mounting and S3 database download."""
    
    def __init__(self):
        self.volume_id = os.getenv('EBS_VOLUME_ID')
        self.aws_region = os.getenv('AWS_REGION', 'us-west-2')
        self.mount_point = Path('/var/app/database')
        self.db_path = self.mount_point / 'wiki_graph.sqlite'
        
        # S3 configuration
        self.s3_bucket = os.getenv('DATABASE_S3_BUCKET')
        self.s3_key = 'wiki_graph.sqlite.gz'
        self.temp_gz_path = Path('/tmp/wiki_graph.sqlite.gz')
        
    async def ensure_database_available(self) -> bool:
        """
        Ensure database is available by mounting EBS volume and downloading from S3 if needed.
        
        Returns:
            bool: True if database is available, False otherwise
        """
        try:
            # First mount the EBS volume (scratch space)
            if not self._mount_ebs_volume():
                logger.error("Failed to mount EBS volume")
                return False
            
            # Check if database already exists
            if self.db_path.exists():
                logger.info(f"Database already exists at {self.db_path}. Size: {self.db_path.stat().st_size / (1024*1024):.1f} MB")
                return True
            
            # Database doesn't exist, download from S3
            logger.info("Database not found locally, downloading from S3...")
            return await self._download_database_from_s3()
            
        except Exception as e:
            logger.error(f"Error ensuring database availability: {e}")
            return False

    def _mount_ebs_volume(self) -> bool:
        """
        Mount the EBS volume as scratch space.
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.volume_id:
            logger.warning("EBS_VOLUME_ID not set, skipping volume mount")
            return False
            
        try:
            logger.info(f"Mounting EBS volume {self.volume_id}")
            
            # Create mount point
            self.mount_point.mkdir(parents=True, exist_ok=True)
            
            # Find the attached volume device
            device_path = self._find_volume_device()
            if not device_path:
                logger.error("Could not find attached EBS volume device")
                return False
                
            # Mount the volume
            result = subprocess.run([
                'sudo', 'mount', str(device_path), str(self.mount_point)
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Failed to mount volume: {result.stderr}")
                return False
                
            logger.info(f"Successfully mounted EBS volume at {self.mount_point}")
            return True
            
        except Exception as e:
            logger.error(f"Error mounting EBS volume: {e}")
            return False
    
    def _find_volume_device(self) -> Optional[Path]:
        """Find the device path for the attached EBS volume."""
        try:
            # List block devices
            result = subprocess.run(['lsblk', '-J'], capture_output=True, text=True)
            if result.returncode != 0:
                logger.error("Failed to list block devices")
                return None
                
            import json
            devices = json.loads(result.stdout)
            
            # Look for the EBS volume (usually /dev/xvdf or /dev/sdf)
            for device in devices.get('blockdevices', []):
                if device.get('name') in ['xvdf', 'sdf']:
                    return Path(f"/dev/{device['name']}")
                    
            logger.error("Could not find EBS volume device")
            return None
            
        except Exception as e:
            logger.error(f"Error finding volume device: {e}")
            return None
    
    def get_database_path(self) -> Path:
        """Get the path to the SQLite database file."""
        return self.db_path
    
    def is_mounted(self) -> bool:
        """Check if the EBS volume is mounted."""
        return self.mount_point.exists() and self.mount_point.is_mount()
    
    async def _download_database_from_s3(self) -> bool:
        """
        Download compressed database from S3 and decompress it.
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.s3_bucket:
            logger.error("DATABASE_S3_BUCKET not configured")
            return False
        
        try:
            # Download compressed database from S3
            logger.info(f"Downloading {self.s3_key} from S3 bucket {self.s3_bucket}...")
            if not await self._s3_download():
                return False
            
            # Decompress to final location
            logger.info(f"Decompressing database to {self.db_path}...")
            if not self._decompress_database():
                return False
            
            # Verify database file
            if not self.db_path.exists():
                logger.error("Database file not found after decompression")
                return False
            
            db_size_mb = self.db_path.stat().st_size / (1024*1024)
            logger.info(f"Successfully downloaded and decompressed database. Size: {db_size_mb:.1f} MB")
            
            # Clean up temporary file
            if self.temp_gz_path.exists():
                self.temp_gz_path.unlink()
            
            return True
            
        except Exception as e:
            logger.error(f"Error downloading database from S3: {e}")
            return False
    
    async def _s3_download(self) -> bool:
        """
        Download compressed database file from S3.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            s3_client = boto3.client('s3', region_name=self.aws_region)
            
            # Download file
            s3_client.download_file(
                Bucket=self.s3_bucket,
                Key=self.s3_key,
                Filename=str(self.temp_gz_path)
            )
            
            if not self.temp_gz_path.exists():
                logger.error(f"Downloaded file not found at {self.temp_gz_path}")
                return False
            
            file_size_mb = self.temp_gz_path.stat().st_size / (1024*1024)
            logger.info(f"Successfully downloaded compressed database. Size: {file_size_mb:.1f} MB")
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                logger.error(f"Database file {self.s3_key} not found in bucket {self.s3_bucket}")
            elif error_code == 'NoSuchBucket':
                logger.error(f"S3 bucket {self.s3_bucket} not found")
            else:
                logger.error(f"AWS S3 error: {e}")
            return False
        except Exception as e:
            logger.error(f"Error downloading from S3: {e}")
            return False
    
    def _decompress_database(self) -> bool:
        """
        Decompress the downloaded gzip file to the final database location.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with gzip.open(self.temp_gz_path, 'rb') as f_in:
                with open(self.db_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            logger.info(f"Successfully decompressed database to {self.db_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error decompressing database: {e}")
            return False

async def mount_database_volume() -> Optional[Path]:
    """
    Ensure database is available and return the database path.
    
    Returns:
        Optional[Path]: Path to the database file, or None if setup failed
    """
    manager = EBSVolumeManager()
    
    if await manager.ensure_database_available():
        return manager.get_database_path()
    else:
        logger.warning("Database setup failed, using local database path")
        # Fallback to local path for development
        return Path("database/wiki_graph.sqlite") 