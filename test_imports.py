#!/usr/bin/env python3
"""Test script to identify import issues"""

def test_imports():
    try:
        print("Testing basic imports...")
        
        print("1. Testing standard library imports...")
        import os, sys, json, threading, time
        print("   ✓ Standard library OK")
        
        print("2. Testing third-party imports...")
        try:
            import yaml
            print("   ✓ yaml OK")
        except ImportError as e:
            print(f"   ✗ yaml failed: {e}")
        
        try:
            import boto3
            print("   ✓ boto3 OK")
        except ImportError as e:
            print(f"   ✗ boto3 failed: {e}")
        
        try:
            from fuse import FUSE, Operations
            print("   ✓ fuse OK")
        except ImportError as e:
            print(f"   ✗ fuse failed: {e}")
        
        try:
            from watchdog.observers import Observer
            print("   ✓ watchdog OK")
        except ImportError as e:
            print(f"   ✗ watchdog failed: {e}")
        
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher
            print("   ✓ cryptography OK")
        except ImportError as e:
            print(f"   ✗ cryptography failed: {e}")
        
        print("3. Testing ShareBox imports...")
        try:
            from sharebox.config import Config
            print("   ✓ sharebox.config OK")
        except Exception as e:
            print(f"   ✗ sharebox.config failed: {e}")
            
        try:
            from sharebox.logging_config import setup_logging
            print("   ✓ sharebox.logging_config OK")
        except Exception as e:
            print(f"   ✗ sharebox.logging_config failed: {e}")
            
        try:
            from sharebox.r2_client import R2Client
            print("   ✓ sharebox.r2_client OK")
        except Exception as e:
            print(f"   ✗ sharebox.r2_client failed: {e}")
            
        try:
            from sharebox.sync_manager import SyncManager
            print("   ✓ sharebox.sync_manager OK")
        except Exception as e:
            print(f"   ✗ sharebox.sync_manager failed: {e}")
            
        try:
            from sharebox.filesystem import ShareBoxFS
            print("   ✓ sharebox.filesystem OK")
        except Exception as e:
            print(f"   ✗ sharebox.filesystem failed: {e}")
            
        try:
            from sharebox.app import ShareBoxApp
            print("   ✓ sharebox.app OK")
        except Exception as e:
            print(f"   ✗ sharebox.app failed: {e}")
            import traceback
            traceback.print_exc()
        
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_imports() 