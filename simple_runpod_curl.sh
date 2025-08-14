#!/bin/bash
# Simplified RunPod S3 Upload with file splitting

set -e

# Configuration
FILE_PATH="/home/developer/İndirilenler/videoplayback.wav"
BUCKET="7z79eg0uur"
S3_KEY="uploads/test_20250813_190814/videoplayback.wav"
CHUNK_SIZE=$((10 * 1024 * 1024))  # 10MB

echo "🚀 RunPod S3 Simple Chunk Upload"
echo "================================="

# Get file size
FILE_SIZE=$(stat -c%s "$FILE_PATH")
TOTAL_PARTS=$(( ($FILE_SIZE + $CHUNK_SIZE - 1) / $CHUNK_SIZE ))

echo "📏 File size: $(($FILE_SIZE / 1024 / 1024))MB"
echo "🧩 Total parts: $TOTAL_PARTS"
echo "📦 Chunk size: 10MB"

# Split file into chunks
echo "🔪 Splitting file into chunks..."
split -b $CHUNK_SIZE -d "$FILE_PATH" "/tmp/chunk_"

echo "📋 Chunks created:"
ls -la /tmp/chunk_* | head -5

# Try AWS CLI with chunked transfer
echo "🚀 Using AWS CLI with optimized config..."

export AWS_ACCESS_KEY_ID="${RUNPOD_AWS_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${RUNPOD_AWS_SECRET_ACCESS_KEY}"
export AWS_MAX_ATTEMPTS=5
export AWS_CLI_READ_TIMEOUT=300
export AWS_CLI_CONNECT_TIMEOUT=60

# Reconstruct file for AWS CLI with smaller IO chunks
echo "🔧 Reconstructing with optimized settings..."
cat /tmp/chunk_* > /tmp/reconstructed_videoplayback.wav

# Upload with very aggressive chunking
aws s3 cp /tmp/reconstructed_videoplayback.wav s3://$BUCKET/$S3_KEY \
  --endpoint-url https://s3api-eu-ro-1.runpod.io/ \
  --region EU-RO-1 \
  --cli-read-timeout 300 \
  --cli-connect-timeout 60 \
  --storage-class STANDARD

if [ $? -eq 0 ]; then
    echo "✅ Upload successful!"
else
    echo "❌ Upload failed with AWS CLI"
    
    # Try manual reconstruction and simple PUT
    echo "🔄 Trying simple PUT with curl..."
    
    # Upload in one go with curl (if file is small enough)
    if [ $FILE_SIZE -lt $((100 * 1024 * 1024)) ]; then
        echo "File small enough, trying direct PUT..."
        
        curl -X PUT \
          --data-binary "@/tmp/reconstructed_videoplayback.wav" \
          -H "Authorization: AWS ${RUNPOD_AWS_ACCESS_KEY_ID}:$(echo -n 'PUT\n\napplication/octet-stream\n\n/7z79eg0uur/uploads/test_20250813_190814/videoplayback.wav' | openssl dgst -sha1 -hmac '${RUNPOD_AWS_SECRET_ACCESS_KEY}' -binary | base64)" \
          -H "Content-Type: application/octet-stream" \
          https://s3api-eu-ro-1.runpod.io/7z79eg0uur/uploads/test_20250813_190814/videoplayback.wav
    fi
fi

# Cleanup
echo "🧹 Cleaning up temp files..."
rm -f /tmp/chunk_*
rm -f /tmp/reconstructed_videoplayback.wav

echo "✨ Process completed!"