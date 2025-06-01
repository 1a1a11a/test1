"""Configuration management for ShareBox."""

import os
import yaml
import socket
from pathlib import Path
from typing import Dict, Any, List


class Config:
    """Configuration manager for ShareBox."""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self._config = {}
        self.load_config()
    
    def load_config(self):
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, 'r') as f:
                self._config = yaml.safe_load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML configuration: {e}")
        
        # Expand user paths
        self._expand_paths()
        
        # Set default device name if not provided
        if not self._config.get('app', {}).get('device_name'):
            self._config.setdefault('app', {})['device_name'] = socket.gethostname()
    
    def _expand_paths(self):
        """Expand user paths (~) in configuration."""
        paths_to_expand = [
            ['sync', 'local_cache_dir'],
            ['sync', 'mount_point'],
            ['app', 'log_file'],
            ['app', 'pid_file']
        ]
        
        for path_keys in paths_to_expand:
            try:
                config_section = self._config
                for key in path_keys[:-1]:
                    config_section = config_section[key]
                
                if path_keys[-1] in config_section:
                    config_section[path_keys[-1]] = os.path.expanduser(
                        config_section[path_keys[-1]]
                    )
            except KeyError:
                pass
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation."""
        keys = key.split('.')
        value = self._config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except KeyError:
            return default
    
    def get_r2_config(self) -> Dict[str, str]:
        """Get R2 configuration."""
        r2_config = self.get('r2', {})
        required_keys = ['access_key_id', 'secret_access_key', 'endpoint_url', 'bucket_name']
        
        for key in required_keys:
            if not r2_config.get(key):
                raise ValueError(f"Missing required R2 configuration: {key}")
        
        return r2_config
    
    def get_sync_config(self) -> Dict[str, Any]:
        """Get synchronization configuration."""
        return self.get('sync', {})
    
    def get_encryption_config(self) -> Dict[str, Any]:
        """Get encryption configuration."""
        return self.get('encryption', {})
    
    def get_fuse_config(self) -> Dict[str, Any]:
        """Get FUSE configuration."""
        return self.get('fuse', {})
    
    def get_excluded_patterns(self) -> List[str]:
        """Get file patterns to exclude from sync."""
        return self.get('sync.excluded_patterns', [])
    
    def ensure_directories(self):
        """Ensure required directories exist."""
        directories = [
            self.get('sync.local_cache_dir'),
            os.path.dirname(self.get('app.log_file')),
            os.path.dirname(self.get('app.pid_file'))
        ]
        
        for directory in directories:
            if directory:
                Path(directory).mkdir(parents=True, exist_ok=True) 