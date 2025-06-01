#!/usr/bin/env python
"""ShareBox - Dropbox-like File Sync with R2 Storage"""

import sys
import os
import argparse

try:
    from sharebox.app import ShareBoxApp
except ImportError as e:
    print(f"Error importing ShareBox modules: {e}")
    print("Please run: ./install.sh or pip install -r requirements.txt")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='ShareBox - Dropbox-like File Sync with R2 Storage')
    parser.add_argument('--config', '-c', default='config.yaml', help='Configuration file path')
    parser.add_argument('command', choices=['mount', 'unmount', 'status', 'stop', 'test', 'fix'], help='Command to execute')
    parser.add_argument('--mount-point', '-m', help='Mount point path')
    parser.add_argument('--foreground', '-f', action='store_true', help='Run in foreground')
    
    args = parser.parse_args()
    
    try:
        if args.command == 'test':
            # Test mode - check dependencies
            print("Testing ShareBox dependencies...")
            
            # Test basic imports
            try:
                from sharebox.config import Config
                print("✓ Config module OK")
            except Exception as e:
                print(f"✗ Config module failed: {e}")
                return 1
            
            # Test external dependencies
            deps = ['yaml', 'boto3', 'fuse', 'watchdog', 'cryptography']
            missing = []
            
            for dep in deps:
                try:
                    __import__(dep)
                    print(f"✓ {dep} available")
                except ImportError:
                    print(f"✗ {dep} missing")
                    missing.append(dep)
            
            if missing:
                print(f"\nMissing dependencies: {', '.join(missing)}")
                print("Install with: pip install " + " ".join(missing))
                return 1
            else:
                print("\n✓ All dependencies available!")
                return 0
        
        elif args.command == 'fix':
            # Fix mount issues
            print("Running ShareBox mount recovery...")
            
            # Import here to avoid dependency issues
            import subprocess
            
            # Check if fix_mount.sh exists
            if os.path.exists('./fix_mount.sh'):
                result = subprocess.run(['./fix_mount.sh'], capture_output=True, text=True)
                if result.returncode == 0:
                    print("✓ Mount recovery completed successfully")
                    return 0
                else:
                    print(f"✗ Mount recovery failed: {result.stderr}")
                    return 1
            else:
                # Inline fix if script is not available
                mount_point = os.path.expanduser("~/ShareBox")
                
                print(f"Checking mount point: {mount_point}")
                
                # Try to unmount if mounted
                try:
                    subprocess.run(['fusermount', '-u', mount_point], 
                                 capture_output=True, text=True, timeout=10)
                except:
                    pass
                
                # Ensure directory exists and is writable
                try:
                    os.makedirs(mount_point, exist_ok=True)
                    # Test write access
                    test_file = os.path.join(mount_point, '.test')
                    with open(test_file, 'w') as f:
                        f.write('test')
                    os.unlink(test_file)
                    print("✓ Mount point is ready")
                    return 0
                except Exception as e:
                    print(f"✗ Mount point issue: {e}")
                    return 1
        
        app = ShareBoxApp(args.config)
        
        if args.command == 'mount':
            if ShareBoxApp.is_running(args.config):
                print("ShareBox is already running", file=sys.stderr)
                return 1
            
            app.initialize()
            success = app.mount(args.mount_point, args.foreground)
            if not success:
                print("Failed to mount ShareBox", file=sys.stderr)
                return 1
            print("ShareBox mounted successfully")
            
        elif args.command == 'unmount':
            app.initialize()
            success = app.unmount(args.mount_point)
            if success:
                print("ShareBox unmounted successfully")
            else:
                print("Failed to unmount ShareBox", file=sys.stderr)
                return 1
                
        elif args.command == 'status':
            try:
                is_running = ShareBoxApp.is_running(args.config)
                print(f"ShareBox Status: {'Running' if is_running else 'Stopped'}")
            except Exception as e:
                print(f"Status check failed: {e}")
                return 1
            
        elif args.command == 'stop':
            if not ShareBoxApp.is_running(args.config):
                print("ShareBox is not running")
                return 0
            
            try:
                from sharebox.config import Config
                config = Config(args.config)
                pid_file = config.get('app.pid_file')
                
                if pid_file and os.path.exists(pid_file):
                    with open(pid_file, 'r') as f:
                        pid = int(f.read().strip())
                    import signal
                    os.kill(pid, signal.SIGTERM)
                    print("Stop signal sent to ShareBox")
                else:
                    print("No PID file found")
            except Exception as e:
                print(f"Failed to stop ShareBox: {e}")
                return 1
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main()) 