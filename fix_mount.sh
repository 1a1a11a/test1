#!/bin/bash
# ShareBox Mount Recovery Script

echo "ShareBox Mount Recovery Tool"
echo "=========================="

MOUNT_POINT="/users/juncheng/ShareBox"

# Function to check if a directory is a mount point
is_mounted() {
    mountpoint -q "$1" 2>/dev/null
}

# Function to force unmount
force_unmount() {
    local mount_point="$1"
    echo "Attempting to unmount $mount_point..."
    
    # Try fusermount first
    if fusermount -u "$mount_point" 2>/dev/null; then
        echo "✓ Unmounted with fusermount"
        return 0
    fi
    
    # Try fusermount with lazy unmount
    if fusermount -uz "$mount_point" 2>/dev/null; then
        echo "✓ Lazy unmounted with fusermount"
        return 0
    fi
    
    # Try regular umount
    if umount "$mount_point" 2>/dev/null; then
        echo "✓ Unmounted with umount"
        return 0
    fi
    
    # Try lazy umount
    if umount -l "$mount_point" 2>/dev/null; then
        echo "✓ Lazy unmounted with umount"
        return 0
    fi
    
    # Try force umount (requires sudo)
    if sudo umount -f "$mount_point" 2>/dev/null; then
        echo "✓ Force unmounted with sudo"
        return 0
    fi
    
    echo "✗ Failed to unmount $mount_point"
    return 1
}

# Main recovery process
echo "1. Checking mount status..."
if is_mounted "$MOUNT_POINT"; then
    echo "✗ $MOUNT_POINT is mounted (possibly stale)"
    force_unmount "$MOUNT_POINT"
else
    echo "✓ $MOUNT_POINT is not mounted"
fi

echo ""
echo "2. Testing directory access..."
if [ -d "$MOUNT_POINT" ]; then
    if touch "$MOUNT_POINT/.test" 2>/dev/null && rm "$MOUNT_POINT/.test" 2>/dev/null; then
        echo "✓ $MOUNT_POINT is accessible"
    else
        echo "✗ $MOUNT_POINT has access issues"
        
        # Try to fix permissions
        echo "  Attempting to fix permissions..."
        chmod 755 "$MOUNT_POINT" 2>/dev/null && echo "  ✓ Permissions fixed"
    fi
else
    echo "- Creating mount point directory..."
    mkdir -p "$MOUNT_POINT" && echo "✓ Created $MOUNT_POINT"
fi

echo ""
echo "3. Checking for ShareBox processes..."
SHAREBOX_PIDS=$(pgrep -f "sharebox" 2>/dev/null)
if [ -n "$SHAREBOX_PIDS" ]; then
    echo "✗ Found running ShareBox processes: $SHAREBOX_PIDS"
    echo "  Stopping ShareBox processes..."
    echo "$SHAREBOX_PIDS" | xargs kill -TERM 2>/dev/null
    sleep 2
    
    # Check if any are still running
    REMAINING_PIDS=$(pgrep -f "sharebox" 2>/dev/null)
    if [ -n "$REMAINING_PIDS" ]; then
        echo "  Force killing remaining processes: $REMAINING_PIDS"
        echo "$REMAINING_PIDS" | xargs kill -KILL 2>/dev/null
    fi
    echo "  ✓ ShareBox processes stopped"
else
    echo "✓ No running ShareBox processes found"
fi

echo ""
echo "4. Final verification..."
if [ -d "$MOUNT_POINT" ] && [ -w "$MOUNT_POINT" ]; then
    echo "✓ Mount point is ready"
    echo ""
    echo "Recovery complete! You can now:"
    echo "  - Run: python sharebox.py mount"
    echo "  - Or copy files to: $MOUNT_POINT"
    exit 0
else
    echo "✗ Mount point still has issues"
    echo ""
    echo "Manual steps needed:"
    echo "  1. Check disk space: df -h"
    echo "  2. Check permissions: ls -la $(dirname $MOUNT_POINT)"
    echo "  3. Try: sudo mkdir -p $MOUNT_POINT && sudo chown $USER:$USER $MOUNT_POINT"
    exit 1
fi 