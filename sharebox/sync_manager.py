"""Sync manager for ShareBox."""

import os
import json
import hashlib
import threading
import time
import queue
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass
from fnmatch import fnmatch

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .logging_config import get_logger
from .r2_client import R2Client


logger = get_logger(__name__)


@dataclass
class SyncOperation:
    """Represents a sync operation."""
    operation: str  # 'upload', 'download', 'delete'
    path: str
    priority: int = 0  # Higher number = higher priority
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class LocalFileWatcher(FileSystemEventHandler):
    """File system event handler for watching local changes."""
    
    def __init__(self, sync_manager):
        self.sync_manager = sync_manager
        super().__init__()
    
    def on_modified(self, event):
        if not event.is_directory:
            self.sync_manager.queue_upload(event.src_path, priority=1)
    
    def on_created(self, event):
        if not event.is_directory:
            self.sync_manager.queue_upload(event.src_path, priority=2)
    
    def on_deleted(self, event):
        if not event.is_directory:
            self.sync_manager.queue_delete(event.src_path, priority=1)
    
    def on_moved(self, event):
        if not event.is_directory:
            self.sync_manager.queue_delete(event.src_path, priority=1)
            self.sync_manager.queue_upload(event.dest_path, priority=2)


class SyncManager:
    """Manages file synchronization between local cache and R2 storage."""
    
    def __init__(self, r2_client: R2Client, config: Dict[str, Any]):
        """Initialize sync manager.
        
        Args:
            r2_client: R2 client instance
            config: Sync configuration
        """
        self.r2_client = r2_client
        self.config = config
        self.cache_dir = config.get('local_cache_dir')
        self.sync_interval = config.get('sync_interval', 30)
        self.max_file_size = config.get('max_file_size', 1073741824)  # 1GB
        self.excluded_patterns = config.get('excluded_patterns', [])
        
        # Sync state
        self.sync_queue = queue.PriorityQueue()
        self.file_metadata = {}  # path -> metadata
        self.sync_lock = threading.Lock()
        self.running = False
        
        # Threads
        self.sync_thread = None
        self.watcher_thread = None
        self.observer = None
        
        # Encryption
        encryption_config = config.get('encryption', {})
        if encryption_config.get('enabled', False):
            try:
                from .encryption import EncryptionManager
                self.encryption = EncryptionManager(encryption_config)
            except ImportError as e:
                logger.warning(f"Encryption not available: {e}")
                self.encryption = None
        else:
            self.encryption = None
        
        # Load metadata
        self._load_metadata()
        
        logger.info("Sync manager initialized")
    
    def start(self):
        """Start sync manager."""
        if self.running:
            return
        
        self.running = True
        
        # Start sync thread
        self.sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self.sync_thread.start()
        
        # Start file watcher
        self._start_file_watcher()
        
        # Initial sync
        self.queue_initial_sync()
        
        logger.info("Sync manager started")
    
    def stop(self):
        """Stop sync manager."""
        if not self.running:
            return
        
        self.running = False
        
        # Stop file watcher
        if self.observer:
            self.observer.stop()
            self.observer.join()
        
        # Wait for sync thread to finish
        if self.sync_thread:
            self.sync_thread.join(timeout=5)
        
        # Save metadata
        self._save_metadata()
        
        logger.info("Sync manager stopped")
    
    def _start_file_watcher(self):
        """Start file system watcher."""
        try:
            self.observer = Observer()
            event_handler = LocalFileWatcher(self)
            self.observer.schedule(event_handler, self.cache_dir, recursive=True)
            self.observer.start()
            logger.info(f"File watcher started for: {self.cache_dir}")
        except Exception as e:
            logger.error(f"Failed to start file watcher: {e}")
    
    def _sync_loop(self):
        """Main sync loop."""
        logger.info("Sync loop started")
        
        while self.running:
            try:
                # Process sync queue
                self._process_sync_queue()
                
                # Periodic remote sync check
                if time.time() % self.sync_interval < 1:
                    self._check_remote_changes()
                
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in sync loop: {e}")
                time.sleep(5)
        
        logger.info("Sync loop stopped")
    
    def _process_sync_queue(self):
        """Process sync operations from queue."""
        try:
            # Get operation with timeout - this returns (priority, operation)
            queue_item = self.sync_queue.get(timeout=1)
            
            # Extract the actual operation from the tuple
            if isinstance(queue_item, tuple):
                priority, operation = queue_item
            else:
                # Fallback for backwards compatibility
                operation = queue_item
            
            # Validate operation object
            if not hasattr(operation, 'operation') or not hasattr(operation, 'path'):
                logger.error(f"Invalid operation object: {operation}")
                self.sync_queue.task_done()
                return
            
            with self.sync_lock:
                try:
                    logger.debug(f"Processing sync operation: {operation.operation} for {operation.path}")
                    
                    if operation.operation == 'upload':
                        self._upload_file(operation.path)
                    elif operation.operation == 'download':
                        self._download_file(operation.path)
                    elif operation.operation == 'delete':
                        self._delete_file(operation.path)
                    else:
                        logger.warning(f"Unknown sync operation: {operation.operation}")
                    
                    self.sync_queue.task_done()
                    
                except Exception as e:
                    logger.error(f"Error processing sync operation {operation.operation} for {operation.path}: {e}")
                    import traceback
                    logger.debug(f"Sync error traceback: {traceback.format_exc()}")
                    self.sync_queue.task_done()
                    
        except queue.Empty:
            pass
        except Exception as e:
            logger.error(f"Unexpected error in sync queue processing: {e}")
            import traceback
            logger.debug(f"Sync queue error traceback: {traceback.format_exc()}")
            # Try to clean up the queue item if possible
            try:
                self.sync_queue.task_done()
            except:
                pass
    
    def queue_upload(self, path: str, priority: int = 0):
        """Queue file for upload.
        
        Args:
            path: File path (virtual or cache path)
            priority: Operation priority
        """
        # Convert to virtual path if needed
        virtual_path = self._to_virtual_path(path)
        
        # Check if file should be excluded
        if self._should_exclude_file(virtual_path):
            return
        
        operation = SyncOperation('upload', virtual_path, priority)
        self.sync_queue.put((100 - priority, operation))
        logger.debug(f"Queued upload: {virtual_path}")
    
    def queue_download(self, path: str, priority: int = 0):
        """Queue file for download.
        
        Args:
            path: Virtual file path
            priority: Operation priority
        """
        operation = SyncOperation('download', path, priority)
        self.sync_queue.put((100 - priority, operation))
        logger.debug(f"Queued download: {path}")
    
    def queue_delete(self, path: str, priority: int = 0):
        """Queue file for deletion.
        
        Args:
            path: File path (virtual or cache path)
            priority: Operation priority
        """
        # Convert to virtual path if needed
        virtual_path = self._to_virtual_path(path)
        
        operation = SyncOperation('delete', virtual_path, priority)
        self.sync_queue.put((100 - priority, operation))
        logger.debug(f"Queued delete: {virtual_path}")
    
    def download_file(self, path: str, timeout: float = 30.0) -> bool:
        """Download file immediately (synchronous).
        
        Args:
            path: Virtual file path
            timeout: Maximum time to wait for download
            
        Returns:
            True if successful, False otherwise
        """
        import threading
        import time
        
        result = [False]  # Use list to allow modification in nested function
        exception = [None]
        
        def download_worker():
            try:
                with self.sync_lock:
                    result[0] = self._download_file(path)
            except Exception as e:
                exception[0] = e
        
        # Run download in separate thread with timeout
        thread = threading.Thread(target=download_worker, daemon=True)
        thread.start()
        thread.join(timeout=timeout)
        
        if thread.is_alive():
            logger.warning(f"Download timeout for {path} after {timeout}s")
            return False
        
        if exception[0]:
            logger.error(f"Download error for {path}: {exception[0]}")
            return False
        
        return result[0]
    
    def upload_file(self, path: str) -> bool:
        """Upload file immediately (synchronous).
        
        Args:
            path: Virtual file path
            
        Returns:
            True if successful, False otherwise
        """
        with self.sync_lock:
            return self._upload_file(path)
    
    def _upload_file(self, virtual_path: str) -> bool:
        """Upload file to R2.
        
        Args:
            virtual_path: Virtual file path
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cache_path = self._to_cache_path(virtual_path)
            
            if not os.path.exists(cache_path):
                logger.warning(f"File not found for upload: {cache_path}")
                return False
            
            # Check file size
            file_size = os.path.getsize(cache_path)
            if file_size > self.max_file_size:
                logger.warning(f"File too large for upload: {cache_path} ({file_size} bytes)")
                return False
            
            # Calculate file hash
            file_hash = self._calculate_file_hash(cache_path)
            
            # Check if file has changed
            if virtual_path in self.file_metadata:
                if self.file_metadata[virtual_path].get('hash') == file_hash:
                    logger.debug(f"File unchanged, skipping upload: {virtual_path}")
                    return True
            
            # Prepare file content
            with open(cache_path, 'rb') as f:
                content = f.read()
            
            # Encrypt if needed
            if self.encryption:
                content = self.encryption.encrypt(content)
            
            # Upload to R2
            remote_path = virtual_path.lstrip('/')
            metadata = {
                'device': self.config.get('device_name', 'unknown'),
                'encrypted': str(self.encryption is not None),
                'original_size': str(file_size)
            }
            
            success = self.r2_client.put_file_content(remote_path, content, metadata)
            
            if success:
                # Update metadata
                self.file_metadata[virtual_path] = {
                    'hash': file_hash,
                    'size': file_size,
                    'modified': os.path.getmtime(cache_path),
                    'uploaded': time.time()
                }
                logger.info(f"Uploaded file: {virtual_path}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to upload file {virtual_path}: {e}")
            return False
    
    def _download_file(self, virtual_path: str) -> bool:
        """Download file from R2.
        
        Args:
            virtual_path: Virtual file path
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cache_path = self._to_cache_path(virtual_path)
            remote_path = virtual_path.lstrip('/')
            
            # Get file content from R2
            content = self.r2_client.get_file_content(remote_path)
            if content is None:
                logger.warning(f"File not found in R2: {remote_path}")
                return False
            
            # Get metadata
            r2_metadata = self.r2_client.get_file_metadata(remote_path)
            if not r2_metadata:
                logger.warning(f"No metadata found for file: {remote_path}")
                return False
            
            # Decrypt if needed
            if self.encryption and r2_metadata.get('metadata', {}).get('encrypted') == 'True':
                content = self.encryption.decrypt(content)
            
            # Ensure cache directory exists
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            
            # Write file to cache
            with open(cache_path, 'wb') as f:
                f.write(content)
            
            # Update metadata
            file_hash = self._calculate_file_hash(cache_path)
            self.file_metadata[virtual_path] = {
                'hash': file_hash,
                'size': len(content),
                'modified': os.path.getmtime(cache_path),
                'downloaded': time.time()
            }
            
            logger.info(f"Downloaded file: {virtual_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to download file {virtual_path}: {e}")
            return False
    
    def _delete_file(self, virtual_path: str) -> bool:
        """Delete file from R2.
        
        Args:
            virtual_path: Virtual file path
            
        Returns:
            True if successful, False otherwise
        """
        try:
            remote_path = virtual_path.lstrip('/')
            
            # Delete from R2
            success = self.r2_client.delete_file(remote_path)
            
            if success:
                # Remove from metadata
                if virtual_path in self.file_metadata:
                    del self.file_metadata[virtual_path]
                
                logger.info(f"Deleted file: {virtual_path}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to delete file {virtual_path}: {e}")
            return False
    
    def file_exists_remote(self, virtual_path: str) -> bool:
        """Check if file exists in R2.
        
        Args:
            virtual_path: Virtual file path
            
        Returns:
            True if file exists in R2, False otherwise
        """
        remote_path = virtual_path.lstrip('/')
        return self.r2_client.file_exists(remote_path)
    
    def list_remote_files(self, prefix: str = "") -> List[str]:
        """List files in R2 with optional prefix.
        
        Args:
            prefix: Path prefix to filter files
            
        Returns:
            List of virtual file paths
        """
        remote_prefix = prefix.lstrip('/')
        files = self.r2_client.list_files(remote_prefix)
        return ['/' + f['key'] for f in files]
    
    def queue_initial_sync(self):
        """Queue initial sync operations."""
        logger.info("Starting initial sync")
        
        # Download all remote files that don't exist locally
        try:
            remote_files = self.list_remote_files()
            for remote_file in remote_files:
                cache_path = self._to_cache_path(remote_file)
                if not os.path.exists(cache_path):
                    self.queue_download(remote_file, priority=0)
        except Exception as e:
            logger.error(f"Error during initial sync: {e}")
    
    def _check_remote_changes(self):
        """Check for remote changes periodically."""
        try:
            remote_files = self.r2_client.list_files()
            
            for file_info in remote_files:
                virtual_path = '/' + file_info['key']
                cache_path = self._to_cache_path(virtual_path)
                
                # Check if local file is older
                if os.path.exists(cache_path):
                    local_mtime = os.path.getmtime(cache_path)
                    remote_mtime = file_info['last_modified'].timestamp()
                    
                    if remote_mtime > local_mtime:
                        self.queue_download(virtual_path, priority=1)
                else:
                    # File doesn't exist locally
                    self.queue_download(virtual_path, priority=0)
                    
        except Exception as e:
            logger.error(f"Error checking remote changes: {e}")
    
    def _to_cache_path(self, virtual_path: str) -> str:
        """Convert virtual path to cache path."""
        path = virtual_path.lstrip('/')
        return os.path.join(self.cache_dir, path)
    
    def _to_virtual_path(self, path: str) -> str:
        """Convert cache path to virtual path."""
        if path.startswith(self.cache_dir):
            rel_path = os.path.relpath(path, self.cache_dir)
            return '/' + rel_path
        else:
            # Assume it's already a virtual path
            return path if path.startswith('/') else '/' + path
    
    def _should_exclude_file(self, path: str) -> bool:
        """Check if file should be excluded from sync."""
        filename = os.path.basename(path)
        
        for pattern in self.excluded_patterns:
            if fnmatch(filename, pattern):
                return True
        
        return False
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA256 hash of a file."""
        hash_sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    
    def _load_metadata(self):
        """Load sync metadata from cache."""
        metadata_file = os.path.join(self.cache_dir, '.sharebox_metadata.json')
        
        try:
            if os.path.exists(metadata_file):
                with open(metadata_file, 'r') as f:
                    self.file_metadata = json.load(f)
                logger.debug(f"Loaded metadata for {len(self.file_metadata)} files")
        except Exception as e:
            logger.warning(f"Failed to load metadata: {e}")
            self.file_metadata = {}
    
    def _save_metadata(self):
        """Save sync metadata to cache."""
        metadata_file = os.path.join(self.cache_dir, '.sharebox_metadata.json')
        
        try:
            os.makedirs(os.path.dirname(metadata_file), exist_ok=True)
            with open(metadata_file, 'w') as f:
                json.dump(self.file_metadata, f, indent=2)
            logger.debug(f"Saved metadata for {len(self.file_metadata)} files")
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status."""
        return {
            'running': self.running,
            'queue_size': self.sync_queue.qsize(),
            'files_tracked': len(self.file_metadata),
            'cache_dir': self.cache_dir,
            'last_sync': max([meta.get('uploaded', 0) for meta in self.file_metadata.values()] + [0])
        } 