"""Main ShareBox application."""

import os
import sys
import signal
import time
import threading
from pathlib import Path
from typing import Optional

from fuse import FUSE

from .config import Config
from .logging_config import setup_logging, get_logger
from .r2_client import R2Client
from .sync_manager import SyncManager
from .filesystem import ShareBoxFS


logger = get_logger(__name__)


class ShareBoxApp:
    """Main ShareBox application."""
    
    def __init__(self, config_path: str = "config.yaml"):
        """Initialize ShareBox application.
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = config_path
        self.config = None
        self.r2_client = None
        self.sync_manager = None
        self.filesystem = None
        self.fuse = None
        self.running = False
        
        # PID file for process management
        self.pid_file = None
        
        # Signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
    
    def initialize(self):
        """Initialize all components."""
        try:
            # Load configuration
            self.config = Config(self.config_path)
            self.config.ensure_directories()
            
            # Setup logging
            setup_logging(
                log_level=self.config.get('app.log_level', 'INFO'),
                log_file=self.config.get('app.log_file'),
                colorize=True
            )
            
            logger.info("ShareBox starting up...")
            
            # Initialize R2 client
            r2_config = self.config.get_r2_config()
            self.r2_client = R2Client(r2_config)
            
            # Initialize sync manager
            sync_config = self.config.get_sync_config()
            sync_config.update({
                'device_name': self.config.get('app.device_name'),
                'encryption': self.config.get_encryption_config(),
                'excluded_patterns': self.config.get_excluded_patterns()
            })
            self.sync_manager = SyncManager(self.r2_client, sync_config)
            
            # Initialize filesystem
            cache_dir = self.config.get('sync.local_cache_dir')
            self.filesystem = ShareBoxFS(self.sync_manager, cache_dir)
            
            logger.info("ShareBox initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize ShareBox: {e}")
            raise
    
    def mount(self, mount_point: Optional[str] = None, foreground: bool = False):
        """Mount the ShareBox filesystem.
        
        Args:
            mount_point: Mount point path (uses config default if None)
            foreground: Run in foreground mode
        """
        if not mount_point:
            mount_point = self.config.get('sync.mount_point')
        
        # Expand user path
        mount_point = os.path.expanduser(mount_point)
        
        # Ensure mount point exists
        Path(mount_point).mkdir(parents=True, exist_ok=True)
        
        # Check if already mounted
        if self._is_mounted(mount_point):
            logger.error(f"Mount point already in use: {mount_point}")
            return False
        
        try:
            # Write PID file
            self._write_pid_file()
            
            # Start sync manager
            self.sync_manager.start()
            
            # FUSE options
            fuse_config = self.config.get_fuse_config()
            fuse_options = {
                'foreground': foreground or fuse_config.get('foreground', False),
                'allow_other': fuse_config.get('allow_other', False),
                'allow_root': fuse_config.get('allow_root', False),
                'default_permissions': fuse_config.get('default_permissions', True)
            }
            
            logger.info(f"Mounting ShareBox at: {mount_point}")
            
            # Mount filesystem
            self.fuse = FUSE(
                self.filesystem,
                mount_point,
                **fuse_options
            )
            
            self.running = True
            logger.info("ShareBox mounted successfully")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to mount ShareBox: {e}")
            self.stop()
            return False
    
    def unmount(self, mount_point: Optional[str] = None):
        """Unmount the ShareBox filesystem.
        
        Args:
            mount_point: Mount point path (uses config default if None)
        """
        if not mount_point:
            mount_point = self.config.get('sync.mount_point')
        
        mount_point = os.path.expanduser(mount_point)
        
        try:
            # Try fusermount first
            import subprocess
            result = subprocess.run(['fusermount', '-u', mount_point], 
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Unmounted ShareBox from: {mount_point}")
                return True
            else:
                # Try umount as fallback
                result = subprocess.run(['umount', mount_point], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    logger.info(f"Unmounted ShareBox from: {mount_point}")
                    return True
                else:
                    logger.error(f"Failed to unmount: {result.stderr}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to unmount ShareBox: {e}")
            return False
    
    def stop(self):
        """Stop ShareBox application."""
        if not self.running:
            return
        
        logger.info("Stopping ShareBox...")
        self.running = False
        
        # Stop sync manager
        if self.sync_manager:
            self.sync_manager.stop()
        
        # Remove PID file
        self._remove_pid_file()
        
        logger.info("ShareBox stopped")
    
    def force_sync(self):
        """Force synchronization of all files."""
        if not self.sync_manager:
            logger.error("Sync manager not initialized")
            return False
        
        logger.info("Starting forced sync...")
        
        # Queue initial sync
        self.sync_manager.queue_initial_sync()
        
        # Wait for sync to complete
        max_wait = 300  # 5 minutes
        start_time = time.time()
        
        while (time.time() - start_time) < max_wait:
            status = self.sync_manager.get_sync_status()
            if status['queue_size'] == 0:
                logger.info("Forced sync completed")
                return True
            
            time.sleep(1)
        
        logger.warning("Forced sync timed out")
        return False
    
    def get_status(self) -> dict:
        """Get ShareBox status.
        
        Returns:
            Status dictionary
        """
        status = {
            'running': self.running,
            'config_path': self.config_path,
            'mount_point': None,
            'cache_dir': None,
            'sync_status': None
        }
        
        if self.config:
            status['mount_point'] = self.config.get('sync.mount_point')
            status['cache_dir'] = self.config.get('sync.local_cache_dir')
        
        if self.sync_manager:
            status['sync_status'] = self.sync_manager.get_sync_status()
        
        return status
    
    def _is_mounted(self, mount_point: str) -> bool:
        """Check if filesystem is already mounted at the given point."""
        try:
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == mount_point:
                        return True
            return False
        except Exception:
            return False
    
    def _write_pid_file(self):
        """Write PID file for process management."""
        if not self.config:
            return
        
        pid_file = self.config.get('app.pid_file')
        if pid_file:
            try:
                Path(pid_file).parent.mkdir(parents=True, exist_ok=True)
                with open(pid_file, 'w') as f:
                    f.write(str(os.getpid()))
                self.pid_file = pid_file
                logger.debug(f"PID file written: {pid_file}")
            except Exception as e:
                logger.warning(f"Failed to write PID file: {e}")
    
    def _remove_pid_file(self):
        """Remove PID file."""
        if self.pid_file and os.path.exists(self.pid_file):
            try:
                os.unlink(self.pid_file)
                logger.debug(f"PID file removed: {self.pid_file}")
            except Exception as e:
                logger.warning(f"Failed to remove PID file: {e}")
        self.pid_file = None
    
    @classmethod
    def is_running(cls, config_path: str = "config.yaml") -> bool:
        """Check if ShareBox is already running.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            True if running, False otherwise
        """
        try:
            config = Config(config_path)
            pid_file = config.get('app.pid_file')
            
            if not pid_file or not os.path.exists(pid_file):
                return False
            
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            # Check if process is still running
            try:
                os.kill(pid, 0)  # Signal 0 just checks if process exists
                return True
            except OSError:
                # Process doesn't exist, remove stale PID file
                os.unlink(pid_file)
                return False
                
        except Exception:
            return False 