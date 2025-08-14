# RunPod Audio Processing Scripts

This repository contains scripts for audio processing using RunPod infrastructure with S3 storage.

## Security Notice

⚠️ **IMPORTANT**: This repository has been cleaned of hardcoded credentials. All credentials are now loaded from environment variables.

## Setup

1. **Environment Variables**: Copy the example environment file and fill in your credentials:
   ```bash
   cp .env.example .env
   ```

2. **Configure Credentials**: Edit `.env` file with your actual RunPod credentials:
   ```env
   RUNPOD_AWS_ACCESS_KEY_ID=your_actual_access_key
   RUNPOD_AWS_SECRET_ACCESS_KEY=your_actual_secret_key
   ```

3. **Load Environment**: Before running any scripts, load the environment variables:
   ```bash
   source .env
   # or
   export $(cat .env | xargs)
   ```

## Scripts Overview

### Python Scripts
- `check_meta.py` - Checks metadata files in S3
- `cleanup_s3.py` - Cleans up S3 storage
- `list_s3_files.py` - Lists files in S3 storage
- `upload_audio.py` - Uploads audio files to S3

### Shell Scripts
- `runpod_curl_multipart.sh` - Multipart upload using curl
- `simple_runpod_curl.sh` - Simple upload using curl

### Core Scripts
- `silence_serverless.py` - Main serverless function
- `audio_splitter.py` - Audio splitting functionality

## Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `RUNPOD_AWS_ACCESS_KEY_ID` | RunPod access key | `user_xxxxx...` |
| `RUNPOD_AWS_SECRET_ACCESS_KEY` | RunPod secret key | `rps_xxxxx...` |
| `RUNPOD_S3_ENDPOINT` | S3 endpoint URL | `https://s3api-eu-ro-1.runpod.io/` |
| `RUNPOD_REGION` | Region code | `EU-RO-1` |
| `RUNPOD_NETWORK_VOLUME_ID` | Network volume ID | `7z79eg0uur` |

## Security Best Practices

1. **Never commit `.env` files** - They are excluded in `.gitignore`
2. **Rotate credentials regularly** - Update your RunPod credentials periodically
3. **Use minimal permissions** - Only grant necessary S3 permissions
4. **Audit access logs** - Monitor S3 access patterns

## Usage Examples

### Check S3 Files
```bash
source .env
python3 check_meta.py
```

### Upload Audio File
```bash
source .env
python3 upload_audio.py
```

### Clean S3 Storage
```bash
source .env
python3 cleanup_s3.py
```

## Dependencies

Install required Python packages:
```bash
pip install -r requirements.txt
```

## Git Safety

Before committing to GitHub:
1. Ensure `.env` is in `.gitignore`
2. Check that no credentials are hardcoded:
   ```bash
   grep -r "user_" . --exclude-dir=.git
   grep -r "rps_" . --exclude-dir=.git
   ```
3. Verify environment variables are used:
   ```bash
   grep -r "os.getenv" *.py
   ```

## Support

For issues related to RunPod infrastructure, consult the RunPod documentation or support channels.