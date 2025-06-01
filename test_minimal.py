#!/usr/bin/env python
"""Minimal test for ShareBox functionality"""

import sys
import os

def test_basic_imports():
    """Test basic ShareBox imports without external dependencies"""
    print("Testing ShareBox imports...")
    
    try:
        # Test config module
        from sharebox.config import Config
        print("✓ Config import OK")
        
        # Test logging config
        from sharebox.logging_config import setup_logging, get_logger
        print("✓ Logging config import OK")
        
        # Test that we can create a basic config (this will fail gracefully)
        try:
            config = Config('config.example.yaml')
            print("✓ Config creation OK")
        except FileNotFoundError:
            print("- Config file not found (expected)")
        except Exception as e:
            print(f"- Config creation issue: {e}")
        
        print("\nBasic imports successful!")
        return True
        
    except Exception as e:
        print(f"Import error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_with_dependencies():
    """Test imports that require external dependencies"""
    print("\nTesting external dependencies...")
    
    # Test each dependency individually
    deps = {
        'yaml': lambda: __import__('yaml'),
        'boto3': lambda: __import__('boto3'), 
        'fuse': lambda: __import__('fuse'),
        'watchdog': lambda: __import__('watchdog'),
        'cryptography': lambda: __import__('cryptography')
    }
    
    available_deps = []
    missing_deps = []
    
    for name, import_func in deps.items():
        try:
            import_func()
            available_deps.append(name)
            print(f"✓ {name} available")
        except ImportError:
            missing_deps.append(name)
            print(f"✗ {name} missing")
    
    print(f"\nSummary:")
    print(f"Available: {', '.join(available_deps) if available_deps else 'None'}")
    print(f"Missing: {', '.join(missing_deps) if missing_deps else 'None'}")
    
    return len(missing_deps) == 0

def main():
    print("ShareBox Diagnostic Tool")
    print("=" * 30)
    
    # Test basic functionality
    basic_ok = test_basic_imports()
    deps_ok = test_with_dependencies()
    
    print("\n" + "=" * 30)
    if basic_ok and deps_ok:
        print("✓ All tests passed! ShareBox should work correctly.")
        print("Run: python3 sharebox.py status")
    elif basic_ok:
        print("⚠ Basic functionality OK, but some dependencies missing.")
        print("Install missing dependencies and try again.")
        print("Run: pip3 install -r requirements.txt")
    else:
        print("✗ Basic imports failed. Check Python installation.")
    
    return 0 if basic_ok else 1

if __name__ == "__main__":
    sys.exit(main()) 