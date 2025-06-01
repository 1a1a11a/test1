# ShareBox - Dropbox-like File Sync with R2 Storage

ShareBox is a Linux application that provides Dropbox-like functionality using Cloudflare R2 object storage. It uses FUSE to mount a virtual filesystem that automatically syncs files across devices.

## Features

- **FUSE Filesystem**: Mount a virtual directory that syncs with R2 storage
- **Real-time Sync**: Automatic file synchronization across devices
- **No Registration**: Use your own R2 credentials - no account creation needed
- **Conflict Resolution**: Handles file conflicts intelligently
- **Encryption**: Optional client-side encryption for sensitive files
- **Cross-platform**: Works on any Linux system with FUSE support

## Requirements

- Linux with FUSE support
- Python 3.8+
- Cloudflare R2 account and credentials

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd sharebox
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install FUSE (if not already installed):
```bash
# Ubuntu/Debian
sudo apt-get install fuse

# CentOS/RHEL
sudo yum install fuse
```

## Configuration

1. Create a configuration file:
```bash
cp config.example.yaml config.yaml
```

2. Edit `config.yaml` with your R2 credentials:
```yaml
r2:
  access_key_id: "your-r2-access-key"
  secret_access_key: "your-r2-secret-key"
  endpoint_url: "https://your-account-id.r2.cloudflarestorage.com"
  bucket_name: "your-bucket-name"
  region: "auto"

sync:
  local_cache_dir: "~/.sharebox/cache"
  mount_point: "~/ShareBox"
  sync_interval: 30  # seconds
  
encryption:
  enabled: false
  password: ""  # Leave empty to prompt
```

## Usage

### Basic Usage

1. Mount the ShareBox filesystem:
```bash
python sharebox.py mount
```

2. Access your files in the mounted directory (default: `~/ShareBox`)

3. Files will automatically sync to R2 and other devices

### Advanced Usage

```bash
# Mount with custom mount point
python sharebox.py mount --mount-point /path/to/mount

# Mount with encryption enabled
python sharebox.py mount --encrypt

# Unmount the filesystem
python sharebox.py unmount

# Force sync all files
python sharebox.py sync

# View sync status
python sharebox.py status
```

## How It Works

1. **FUSE Layer**: Intercepts filesystem operations on the mount point
2. **Local Cache**: Maintains a local copy of files for performance
3. **R2 Sync**: Uploads/downloads files to/from R2 storage
4. **Conflict Detection**: Detects and resolves file conflicts across devices
5. **Metadata Tracking**: Tracks file versions and sync status

## Security

- Files can be encrypted client-side before upload to R2
- R2 credentials are stored locally and never transmitted
- All communication with R2 uses HTTPS
- Optional password-based encryption for sensitive files

## Troubleshooting

### Common Issues

1. **Permission denied when mounting**:
   - Ensure your user is in the `fuse` group: `sudo usermod -a -G fuse $USER`
   - Log out and log back in

2. **Mount point busy**:
   - Unmount first: `python sharebox.py unmount`
   - Or use: `fusermount -u ~/ShareBox`

3. **R2 connection issues**:
   - Verify your credentials in `config.yaml`
   - Check internet connectivity
   - Ensure bucket exists and is accessible

### Logs

Logs are stored in `~/.sharebox/logs/sharebox.log`

## Contributing

Feel free to submit issues and pull requests!

## License

MIT License 