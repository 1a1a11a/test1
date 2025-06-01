#!/usr/bin/env python3
"""ShareBox - Dropbox-like File Sync with R2 Storage"""

import sys
import os
import argparse
from sharebox.app import ShareBoxApp

def main():
    parser = argparse.ArgumentParser(description='ShareBox - Dropbox-like File Sync with R2 Storage')
    parser.add_argument('--config', '-c', default='config.yaml', help='Configuration file path')
    parser.add_argument('command', choices=['mount', 'unmount', 'status', 'stop'], help='Command to execute')
    parser.add_argument('--mount-point', '-m', help='Mount point path')
    parser.add_argument('--foreground', '-f', action='store_true', help='Run in foreground')
    
    args = parser.parse_args()
    
    try:
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
            is_running = ShareBoxApp.is_running(args.config)
            print(f"ShareBox Status: {'Running' if is_running else 'Stopped'}")
            
        elif args.command == 'stop':
            if not ShareBoxApp.is_running(args.config):
                print("ShareBox is not running")
                return 0
            
            from sharebox.config import Config
            config = Config(args.config)
            pid_file = config.get('app.pid_file')
            
            if pid_file and os.path.exists(pid_file):
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                import signal
                os.kill(pid, signal.SIGTERM)
                print("Stop signal sent to ShareBox")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main()) 