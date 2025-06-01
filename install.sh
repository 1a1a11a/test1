#!/bin/bash
set -e

echo "Installing ShareBox dependencies..."

# Check if we're in a virtual environment
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo "Using virtual environment: $VIRTUAL_ENV"
    PIP="pip"
else
    echo "Using system Python. Consider using a virtual environment."
    PIP="pip3"
fi

# Install system dependencies for FUSE
echo "Checking system dependencies..."
if command -v apt-get >/dev/null 2>&1; then
    echo "Detected Debian/Ubuntu system"
    echo "You may need to run: sudo apt-get install fuse libfuse-dev pkg-config"
elif command -v yum >/dev/null 2>&1; then
    echo "Detected RedHat/CentOS system"
    echo "You may need to run: sudo yum install fuse fuse-devel pkgconfig"
elif command -v dnf >/dev/null 2>&1; then
    echo "Detected Fedora system" 
    echo "You may need to run: sudo dnf install fuse fuse-devel pkgconfig"
fi

# Install Python dependencies
echo "Installing Python dependencies..."
$PIP install --upgrade pip

# Install dependencies one by one to handle failures gracefully
declare -a deps=(
    "pyyaml"
    "boto3"
    "python-dateutil"
    "requests"
    "colorlog"
    "watchdog"
    "cryptography"
    "fusepy"
)

for dep in "${deps[@]}"; do
    echo "Installing $dep..."
    if ! $PIP install "$dep"; then
        echo "Warning: Failed to install $dep. Some features may not work."
    fi
done

echo "Installation complete!"
echo ""
echo "To use ShareBox:"
echo "1. Copy config.example.yaml to config.yaml"
echo "2. Edit config.yaml with your R2 credentials"
echo "3. Run: python3 sharebox.py status" 