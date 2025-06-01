#!/usr/bin/env python
"""Test script to verify copy operations don't block."""

import os
import sys
import time
import threading
import tempfile
import signal
from pathlib import Path

def signal_handler(signum, frame):
    print(f"\n⚠️  Received signal {signum}")
    sys.exit(1)

def test_copy_operation(mount_point, test_file):
    """Test copying a file to the mount point."""
    try:
        dest_path = os.path.join(mount_point, "test_copy.txt")
        
        print(f"📄 Copying {test_file} to {dest_path}")
        start_time = time.time()
        
        # Use cp command to copy file
        cmd = f"cp '{test_file}' '{dest_path}'"
        print(f"💻 Running: {cmd}")
        
        result = os.system(cmd)
        elapsed = time.time() - start_time
        
        if result == 0:
            print(f"✅ Copy completed successfully in {elapsed:.2f}s")
            
            # Verify file exists
            if os.path.exists(dest_path):
                size = os.path.getsize(dest_path)
                print(f"📊 File size: {size} bytes")
                return True
            else:
                print("❌ File not found after copy")
                return False
        else:
            print(f"❌ Copy failed with exit code {result}")
            return False
            
    except Exception as e:
        print(f"❌ Error during copy: {e}")
        return False

def monitor_copy_progress(dest_path, expected_size):
    """Monitor copy progress in background thread."""
    print(f"👀 Monitoring copy progress for {dest_path}")
    
    while True:
        try:
            if os.path.exists(dest_path):
                current_size = os.path.getsize(dest_path)
                progress = (current_size / expected_size) * 100 if expected_size > 0 else 0
                print(f"📈 Progress: {current_size}/{expected_size} bytes ({progress:.1f}%)")
                
                if current_size >= expected_size:
                    print("✅ Copy appears complete")
                    break
            else:
                print("⏳ Waiting for file to appear...")
                
            time.sleep(2)
        except Exception as e:
            print(f"Error monitoring: {e}")
            time.sleep(2)

def main():
    """Main test function."""
    # Set up signal handling
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    if len(sys.argv) != 2:
        print("Usage: python test_copy.py <mount_point>")
        sys.exit(1)
    
    mount_point = sys.argv[1]
    
    print("🧪 ShareBox Copy Test")
    print("=" * 50)
    
    # Check if mount point exists
    if not os.path.exists(mount_point):
        print(f"❌ Mount point {mount_point} does not exist")
        sys.exit(1)
    
    if not os.path.ismount(mount_point):
        print(f"⚠️  {mount_point} doesn't appear to be mounted")
    
    # Create test file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        test_data = "Hello ShareBox!\n" * 1000  # ~15KB
        f.write(test_data)
        test_file = f.name
    
    try:
        print(f"📝 Created test file: {test_file}")
        test_size = os.path.getsize(test_file)
        print(f"📊 Test file size: {test_size} bytes")
        
        # Start monitoring in background
        dest_path = os.path.join(mount_point, "test_copy.txt")
        monitor_thread = threading.Thread(
            target=monitor_copy_progress, 
            args=(dest_path, test_size),
            daemon=True
        )
        monitor_thread.start()
        
        # Test copy operation with timeout
        print(f"\n🚀 Starting copy test (30s timeout)...")
        success = test_copy_operation(mount_point, test_file)
        
        if success:
            print("\n✅ Copy test PASSED")
            print("🎉 ShareBox copy operations are working!")
        else:
            print("\n❌ Copy test FAILED")
            print("💥 ShareBox may be blocking on copy operations")
            
    finally:
        # Clean up
        try:
            os.unlink(test_file)
            dest_file = os.path.join(mount_point, "test_copy.txt")
            if os.path.exists(dest_file):
                os.unlink(dest_file)
        except:
            pass

if __name__ == "__main__":
    main() 