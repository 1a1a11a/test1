"""R2 client for ShareBox."""

import os
import json
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, BinaryIO
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from .logging_config import get_logger


logger = get_logger(__name__)


class R2Client:
    """Client for interacting with Cloudflare R2 storage."""
    
    def __init__(self, config: Dict[str, str]):
        """Initialize R2 client with configuration.
        
        Args:
            config: R2 configuration dictionary
        """
        self.config = config
        self.bucket_name = config['bucket_name']
        
        # Initialize boto3 client for R2
        self.client = boto3.client(
            's3',
            endpoint_url=config['endpoint_url'],
            aws_access_key_id=config['access_key_id'],
            aws_secret_access_key=config['secret_access_key'],
            region_name=config.get('region', 'auto')
        )
        
        # Test connection
        self._test_connection()
    
    def _test_connection(self):
        """Test connection to R2 bucket."""
        try:
            self.client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"Successfully connected to R2 bucket: {self.bucket_name}")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                logger.error(f"R2 bucket not found: {self.bucket_name}")
                raise ValueError(f"R2 bucket not found: {self.bucket_name}")
            else:
                logger.error(f"Failed to connect to R2: {e}")
                raise
        except NoCredentialsError:
            logger.error("Invalid R2 credentials")
            raise ValueError("Invalid R2 credentials")
    
    def upload_file(self, local_path: str, remote_path: str, metadata: Dict[str, str] = None) -> bool:
        """Upload a file to R2.
        
        Args:
            local_path: Local file path
            remote_path: Remote file path in R2
            metadata: Additional metadata to store with the file
            
        Returns:
            True if upload successful, False otherwise
        """
        try:
            # Calculate file hash
            file_hash = self._calculate_file_hash(local_path)
            
            # Prepare metadata
            upload_metadata = {
                'upload-time': datetime.now(timezone.utc).isoformat(),
                'file-hash': file_hash,
                'local-path': local_path
            }
            if metadata:
                upload_metadata.update(metadata)
            
            # Upload file
            with open(local_path, 'rb') as f:
                self.client.upload_fileobj(
                    f,
                    self.bucket_name,
                    remote_path,
                    ExtraArgs={'Metadata': upload_metadata}
                )
            
            logger.debug(f"Uploaded file: {local_path} -> {remote_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upload file {local_path}: {e}")
            return False
    
    def download_file(self, remote_path: str, local_path: str) -> bool:
        """Download a file from R2.
        
        Args:
            remote_path: Remote file path in R2
            local_path: Local file path to save to
            
        Returns:
            True if download successful, False otherwise
        """
        try:
            # Ensure local directory exists
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # Download file
            self.client.download_file(self.bucket_name, remote_path, local_path)
            
            logger.debug(f"Downloaded file: {remote_path} -> {local_path}")
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.warning(f"File not found in R2: {remote_path}")
            else:
                logger.error(f"Failed to download file {remote_path}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to download file {remote_path}: {e}")
            return False
    
    def delete_file(self, remote_path: str) -> bool:
        """Delete a file from R2.
        
        Args:
            remote_path: Remote file path in R2
            
        Returns:
            True if deletion successful, False otherwise
        """
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=remote_path)
            logger.debug(f"Deleted file from R2: {remote_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete file {remote_path}: {e}")
            return False
    
    def file_exists(self, remote_path: str) -> bool:
        """Check if a file exists in R2.
        
        Args:
            remote_path: Remote file path in R2
            
        Returns:
            True if file exists, False otherwise
        """
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=remote_path)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            else:
                logger.error(f"Error checking file existence {remote_path}: {e}")
                return False
    
    def get_file_metadata(self, remote_path: str) -> Optional[Dict[str, Any]]:
        """Get file metadata from R2.
        
        Args:
            remote_path: Remote file path in R2
            
        Returns:
            File metadata dictionary or None if file doesn't exist
        """
        try:
            response = self.client.head_object(Bucket=self.bucket_name, Key=remote_path)
            
            metadata = {
                'size': response['ContentLength'],
                'last_modified': response['LastModified'],
                'etag': response['ETag'].strip('"'),
                'metadata': response.get('Metadata', {})
            }
            
            return metadata
            
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return None
            else:
                logger.error(f"Error getting file metadata {remote_path}: {e}")
                return None
    
    def list_files(self, prefix: str = "", max_keys: int = 1000) -> List[Dict[str, Any]]:
        """List files in R2 bucket with optional prefix.
        
        Args:
            prefix: Prefix to filter files
            max_keys: Maximum number of files to return
            
        Returns:
            List of file information dictionaries
        """
        try:
            response = self.client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=max_keys
            )
            
            files = []
            for obj in response.get('Contents', []):
                files.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'],
                    'etag': obj['ETag'].strip('"')
                })
            
            return files
            
        except Exception as e:
            logger.error(f"Failed to list files with prefix {prefix}: {e}")
            return []
    
    def get_file_content(self, remote_path: str) -> Optional[bytes]:
        """Get file content from R2.
        
        Args:
            remote_path: Remote file path in R2
            
        Returns:
            File content as bytes or None if file doesn't exist
        """
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=remote_path)
            return response['Body'].read()
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return None
            else:
                logger.error(f"Error getting file content {remote_path}: {e}")
                return None
    
    def put_file_content(self, remote_path: str, content: bytes, metadata: Dict[str, str] = None) -> bool:
        """Put file content to R2.
        
        Args:
            remote_path: Remote file path in R2
            content: File content as bytes
            metadata: Additional metadata to store with the file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Prepare metadata
            upload_metadata = {
                'upload-time': datetime.now(timezone.utc).isoformat(),
                'content-hash': hashlib.sha256(content).hexdigest()
            }
            if metadata:
                upload_metadata.update(metadata)
            
            # Upload content
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=remote_path,
                Body=content,
                Metadata=upload_metadata
            )
            
            logger.debug(f"Uploaded content to R2: {remote_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upload content to {remote_path}: {e}")
            return False
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA256 hash of a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            SHA256 hash as hex string
        """
        hash_sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest() 