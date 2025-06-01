"""FUSE filesystem implementation for ShareBox."""

import os
import stat
import errno
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List

try:
    from fuse import FUSE, FuseOSError, Operations
except ImportError:
    # Create dummy classes for when FUSE is not available
    class FuseOSError(Exception):
        def __init__(self, errno):
            self.errno = errno
            super().__init__(f"FUSE error: {errno}")
    
    class Operations:
        pass
    
    FUSE = None

from .logging_config import get_logger
from .sync_manager import SyncManager


logger = get_logger(__name__)


class ShareBoxFS(Operations):
    """FUSE filesystem for ShareBox."""
    
    def __init__(self, sync_manager: SyncManager, cache_dir: str):
        """Initialize ShareBox filesystem.
        
        Args:
            sync_manager: Sync manager instance
            cache_dir: Local cache directory path
        """
        self.sync_manager = sync_manager
        self.cache_dir = cache_dir
        self.fd_counter = 0
        self.open_files = {}  # file descriptor -> file info
        self.lock = threading.Lock()
        
        # Ensure cache directory exists
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        
        logger.info(f"ShareBox filesystem initialized with cache: {cache_dir}")
    
    def _get_cache_path(self, path: str) -> str:
        """Get local cache path for a given virtual path."""
        # Remove leading slash and normalize
        path = path.lstrip('/')
        return os.path.join(self.cache_dir, path)
    
    def _ensure_cache_dir(self, path: str):
        """Ensure cache directory exists for the given path."""
        cache_path = self._get_cache_path(path)
        cache_dir = os.path.dirname(cache_path)
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
    
    # Filesystem metadata operations
    
    def getattr(self, path, fh=None):
        """Get file attributes."""
        try:
            # Handle root directory specially
            if path == '/':
                return {
                    'st_mode': stat.S_IFDIR | 0o755,
                    'st_nlink': 2,
                    'st_size': 0,
                    'st_ctime': time.time(),
                    'st_mtime': time.time(),
                    'st_atime': time.time(),
                    'st_uid': os.getuid(),
                    'st_gid': os.getgid()
                }
            
            cache_path = self._get_cache_path(path)
            
            # Check if file exists in cache
            if os.path.exists(cache_path):
                try:
                    st = os.lstat(cache_path)
                    return dict((key, getattr(st, key)) for key in (
                        'st_atime', 'st_ctime', 'st_gid', 'st_mode', 'st_mtime',
                        'st_nlink', 'st_size', 'st_uid'
                    ))
                except OSError as e:
                    logger.warning(f"Failed to stat cache file {cache_path}: {e}")
                    # Fall through to check remote
            
            # Check if file exists in remote storage
            try:
                if self.sync_manager.file_exists_remote(path):
                    # File exists remotely but not in cache - download it
                    if self.sync_manager.download_file(path):
                        if os.path.exists(cache_path):
                            st = os.lstat(cache_path)
                            return dict((key, getattr(st, key)) for key in (
                                'st_atime', 'st_ctime', 'st_gid', 'st_mode', 'st_mtime',
                                'st_nlink', 'st_size', 'st_uid'
                            ))
                    
                    # If download failed, return default file attributes
                    return {
                        'st_mode': stat.S_IFREG | 0o644,
                        'st_nlink': 1,
                        'st_size': 0,
                        'st_ctime': time.time(),
                        'st_mtime': time.time(),
                        'st_atime': time.time(),
                        'st_uid': os.getuid(),
                        'st_gid': os.getgid()
                    }
            except Exception as e:
                logger.warning(f"Failed to check remote file {path}: {e}")
            
            # File doesn't exist
            raise FuseOSError(errno.ENOENT)
            
        except FuseOSError:
            # Re-raise FUSE errors
            raise
        except Exception as e:
            logger.error(f"Error getting attributes for {path}: {e}")
            raise FuseOSError(errno.EIO)
    
    def readdir(self, path, fh):
        """Read directory contents."""
        try:
            entries = ['.', '..']
            
            # Get files from cache
            cache_path = self._get_cache_path(path)
            if os.path.isdir(cache_path):
                entries.extend(os.listdir(cache_path))
            
            # Get files from remote storage
            remote_files = self.sync_manager.list_remote_files(path)
            for remote_file in remote_files:
                rel_path = os.path.relpath(remote_file, path.lstrip('/'))
                if '/' not in rel_path and rel_path not in entries:
                    entries.append(rel_path)
            
            return entries
            
        except Exception as e:
            logger.error(f"Error reading directory {path}: {e}")
            raise FuseOSError(errno.EIO)
    
    # File operations
    
    def create(self, path, mode, fi=None):
        """Create a new file."""
        try:
            cache_path = self._get_cache_path(path)
            self._ensure_cache_dir(path)
            
            # Create file in cache
            fd = os.open(cache_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
            
            # Store file descriptor info
            with self.lock:
                self.fd_counter += 1
                fh = self.fd_counter
                self.open_files[fh] = {
                    'path': path,
                    'cache_path': cache_path,
                    'fd': fd,
                    'mode': 'w',
                    'dirty': True
                }
            
            logger.debug(f"Created file: {path}")
            return fh
            
        except Exception as e:
            logger.error(f"Error creating file {path}: {e}")
            raise FuseOSError(errno.EIO)
    
    def open(self, path, flags):
        """Open a file."""
        try:
            cache_path = self._get_cache_path(path)
            
            # Download file if it doesn't exist in cache (with timeout)
            if not os.path.exists(cache_path):
                logger.debug(f"Cache miss for {path}, attempting download")
                # Try to download but don't block forever
                try:
                    success = self.sync_manager.download_file(path)
                    if not success:
                        logger.warning(f"Failed to download {path}, may be a new file")
                except Exception as e:
                    logger.warning(f"Download failed for {path}: {e}")
                    # Continue anyway - might be a new file being created
            
            # Try to open file, create if it doesn't exist and we're writing
            try:
                if os.path.exists(cache_path):
                    fd = os.open(cache_path, flags)
                elif flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
                    # Create file if we're writing and it doesn't exist
                    self._ensure_cache_dir(path)
                    fd = os.open(cache_path, flags | os.O_CREAT, 0o644)
                else:
                    # File doesn't exist and we're not creating it
                    raise FuseOSError(errno.ENOENT)
            except OSError as e:
                if e.errno == errno.ENOENT:
                    raise FuseOSError(errno.ENOENT)
                else:
                    logger.error(f"OS error opening {path}: {e}")
                    raise FuseOSError(errno.EIO)
            
            # Store file descriptor info
            with self.lock:
                self.fd_counter += 1
                fh = self.fd_counter
                self.open_files[fh] = {
                    'path': path,
                    'cache_path': cache_path,
                    'fd': fd,
                    'mode': 'r' if flags == os.O_RDONLY else 'w',
                    'dirty': False
                }
            
            logger.debug(f"Opened file: {path} (fd={fh})")
            return fh
            
        except FuseOSError:
            # Re-raise FUSE errors
            raise
        except Exception as e:
            logger.error(f"Unexpected error opening file {path}: {e}")
            raise FuseOSError(errno.EIO)
    
    def read(self, path, length, offset, fh):
        """Read from a file."""
        try:
            if fh in self.open_files:
                fd = self.open_files[fh]['fd']
                os.lseek(fd, offset, os.SEEK_SET)
                return os.read(fd, length)
            
            # Fallback: direct read from cache
            cache_path = self._get_cache_path(path)
            if not os.path.exists(cache_path):
                self.sync_manager.download_file(path)
            
            with open(cache_path, 'rb') as f:
                f.seek(offset)
                return f.read(length)
                
        except Exception as e:
            logger.error(f"Error reading file {path}: {e}")
            raise FuseOSError(errno.EIO)
    
    def write(self, path, buf, offset, fh):
        """Write to a file."""
        try:
            if fh not in self.open_files:
                raise FuseOSError(errno.EBADF)
            
            fd = self.open_files[fh]['fd']
            
            # Perform the write operation
            try:
                os.lseek(fd, offset, os.SEEK_SET)
                written = os.write(fd, buf)
                
                # Mark file as dirty for sync (non-blocking)
                self.open_files[fh]['dirty'] = True
                
                # Log write progress for large files
                if len(buf) > 1024 * 1024:  # > 1MB
                    logger.debug(f"Wrote {len(buf)} bytes to {path} at offset {offset}")
                
                return written
                
            except OSError as e:
                if e.errno == errno.ENOSPC:
                    logger.error(f"No space left on device for {path}")
                    raise FuseOSError(errno.ENOSPC)
                elif e.errno == errno.EIO:
                    logger.error(f"I/O error writing to {path}")
                    raise FuseOSError(errno.EIO)
                else:
                    logger.error(f"OS error writing to {path}: {e}")
                    raise FuseOSError(errno.EIO)
            
        except FuseOSError:
            # Re-raise FUSE errors
            raise
        except Exception as e:
            logger.error(f"Unexpected error writing to file {path}: {e}")
            raise FuseOSError(errno.EIO)
    
    def flush(self, path, fh):
        """Flush file data."""
        try:
            if fh in self.open_files:
                fd = self.open_files[fh]['fd']
                os.fsync(fd)
                
                # Trigger async sync if file is dirty
                if self.open_files[fh]['dirty']:
                    # Queue for upload but don't wait - this prevents blocking
                    self.sync_manager.queue_upload(path)
                    self.open_files[fh]['dirty'] = False
                    logger.debug(f"Queued upload for {path}")
            
        except Exception as e:
            logger.error(f"Error flushing file {path}: {e}")
            # Don't raise error for flush - it should be non-blocking
            pass
    
    def release(self, path, fh):
        """Close a file."""
        try:
            if fh in self.open_files:
                file_info = self.open_files[fh]
                fd = file_info['fd']
                
                # Sync file if dirty (async)
                if file_info['dirty']:
                    try:
                        os.fsync(fd)
                        # Queue for async upload - don't block on this
                        self.sync_manager.queue_upload(path)
                        logger.debug(f"Queued upload on release for {path}")
                    except Exception as e:
                        logger.warning(f"Failed to sync file {path} on release: {e}")
                
                # Close file descriptor
                try:
                    os.close(fd)
                except OSError as e:
                    logger.warning(f"Error closing file descriptor for {path}: {e}")
                
                # Remove from open files
                with self.lock:
                    if fh in self.open_files:
                        del self.open_files[fh]
                
                logger.debug(f"Released file: {path}")
            
        except Exception as e:
            logger.error(f"Error releasing file {path}: {e}")
            # Don't raise error for release - it should complete gracefully
            pass
    
    def unlink(self, path):
        """Delete a file."""
        try:
            cache_path = self._get_cache_path(path)
            
            # Remove from cache
            if os.path.exists(cache_path):
                os.unlink(cache_path)
            
            # Queue for remote deletion
            self.sync_manager.queue_delete(path)
            
            logger.debug(f"Deleted file: {path}")
            
        except Exception as e:
            logger.error(f"Error deleting file {path}: {e}")
            raise FuseOSError(errno.EIO)
    
    def mkdir(self, path, mode):
        """Create a directory."""
        try:
            cache_path = self._get_cache_path(path)
            os.makedirs(cache_path, mode=mode, exist_ok=True)
            
            logger.debug(f"Created directory: {path}")
            
        except Exception as e:
            logger.error(f"Error creating directory {path}: {e}")
            raise FuseOSError(errno.EIO)
    
    def rmdir(self, path):
        """Remove a directory."""
        try:
            cache_path = self._get_cache_path(path)
            
            if os.path.exists(cache_path):
                os.rmdir(cache_path)
            
            # Queue remote files in directory for deletion
            remote_files = self.sync_manager.list_remote_files(path)
            for remote_file in remote_files:
                self.sync_manager.queue_delete(remote_file)
            
            logger.debug(f"Removed directory: {path}")
            
        except Exception as e:
            logger.error(f"Error removing directory {path}: {e}")
            raise FuseOSError(errno.EIO)
    
    def rename(self, old, new):
        """Rename a file or directory."""
        try:
            old_cache_path = self._get_cache_path(old)
            new_cache_path = self._get_cache_path(new)
            
            # Ensure destination directory exists
            self._ensure_cache_dir(new)
            
            # Rename in cache
            if os.path.exists(old_cache_path):
                os.rename(old_cache_path, new_cache_path)
            
            # Queue operations for remote sync
            self.sync_manager.queue_delete(old)
            self.sync_manager.queue_upload(new)
            
            logger.debug(f"Renamed: {old} -> {new}")
            
        except Exception as e:
            logger.error(f"Error renaming {old} to {new}: {e}")
            raise FuseOSError(errno.EIO)
    
    def chmod(self, path, mode):
        """Change file permissions."""
        try:
            cache_path = self._get_cache_path(path)
            if os.path.exists(cache_path):
                os.chmod(cache_path, mode)
            
        except Exception as e:
            logger.error(f"Error changing permissions for {path}: {e}")
            raise FuseOSError(errno.EIO)
    
    def chown(self, path, uid, gid):
        """Change file ownership."""
        try:
            cache_path = self._get_cache_path(path)
            if os.path.exists(cache_path):
                os.chown(cache_path, uid, gid)
            
        except Exception as e:
            logger.error(f"Error changing ownership for {path}: {e}")
            raise FuseOSError(errno.EIO)
    
    def utimens(self, path, times=None):
        """Update file access and modification times."""
        try:
            cache_path = self._get_cache_path(path)
            if os.path.exists(cache_path):
                os.utime(cache_path, times)
            
        except Exception as e:
            logger.error(f"Error updating times for {path}: {e}")
            raise FuseOSError(errno.EIO) 