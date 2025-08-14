#!/bin/bash
# RunPod S3 Multipart Upload with curl
# Cloudflare 100s timeout için optimize edilmiş

set -e  # Exit on error

# RunPod S3 Configuration
AWS_ACCESS_KEY_ID="${RUNPOD_AWS_ACCESS_KEY_ID}"
AWS_SECRET_ACCESS_KEY="${RUNPOD_AWS_SECRET_ACCESS_KEY}"
REGION="EU-RO-1"
ENDPOINT="https://s3api-eu-ro-1.runpod.io"
BUCKET="7z79eg0uur"

# File to upload
FILE_PATH="/home/developer/İndirilenler/videoplayback.wav"
S3_KEY="uploads/test_20250813_190814/videoplayback.wav"

# Chunk size (10MB for Cloudflare timeout)
CHUNK_SIZE=$((10 * 1024 * 1024))

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 RunPod S3 Multipart Upload (curl)${NC}"
echo "=================================="

# AWS Signature v4 function
aws_sig_v4() {
    local method="$1"
    local uri="$2"
    local query="$3"
    local payload_hash="$4"
    local content_type="$5"
    
    local service="s3"
    local request="aws4_request"
    local algorithm="AWS4-HMAC-SHA256"
    
    # Current timestamp
    local timestamp=$(date -u +"%Y%m%dT%H%M%SZ")
    local datestamp=$(date -u +"%Y%m%d")
    
    # Canonical request
    local canonical_headers="host:$(echo $ENDPOINT | cut -d'/' -f3)
x-amz-content-sha256:${payload_hash}
x-amz-date:${timestamp}
"
    
    local signed_headers="host;x-amz-content-sha256;x-amz-date"
    
    local canonical_request="${method}
${uri}
${query}
${canonical_headers}
${signed_headers}
${payload_hash}"
    
    # Create signature
    local credential_scope="${datestamp}/${REGION}/${service}/${request}"
    local string_to_sign="${algorithm}
${timestamp}
${credential_scope}
$(echo -n "$canonical_request" | openssl dgst -sha256 -hex | cut -d' ' -f2)"
    
    local date_key=$(echo -n "$datestamp" | openssl dgst -sha256 -mac HMAC -macopt key:"AWS4${AWS_SECRET_ACCESS_KEY}" -binary)
    local date_region_key=$(echo -n "$REGION" | openssl dgst -sha256 -mac HMAC -macopt key:"$date_key" -binary)
    local date_region_service_key=$(echo -n "$service" | openssl dgst -sha256 -mac HMAC -macopt key:"$date_region_key" -binary)
    local signing_key=$(echo -n "$request" | openssl dgst -sha256 -mac HMAC -macopt key:"$date_region_service_key" -binary)
    local signature=$(echo -n "$string_to_sign" | openssl dgst -sha256 -mac HMAC -macopt key:"$signing_key" -hex | cut -d' ' -f2)
    
    # Authorization header
    echo "${algorithm} Credential=${AWS_ACCESS_KEY_ID}/${credential_scope}, SignedHeaders=${signed_headers}, Signature=${signature}"
}

# Step 1: Create multipart upload
echo -e "${YELLOW}📋 Step 1: Creating multipart upload...${NC}"

EMPTY_HASH="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")

AUTH_HEADER=$(aws_sig_v4 "POST" "/${S3_KEY}" "uploads=" "$EMPTY_HASH" "")

UPLOAD_RESPONSE=$(curl -s -X POST \
  -H "Host: $(echo $ENDPOINT | cut -d'/' -f3)" \
  -H "x-amz-content-sha256: $EMPTY_HASH" \
  -H "x-amz-date: $TIMESTAMP" \
  -H "Authorization: $AUTH_HEADER" \
  "$ENDPOINT/$S3_KEY?uploads=")

# Extract Upload ID
UPLOAD_ID=$(echo "$UPLOAD_RESPONSE" | grep -o '<UploadId>[^<]*</UploadId>' | sed 's/<UploadId>//g' | sed 's/<\/UploadId>//g')

if [ -z "$UPLOAD_ID" ]; then
    echo -e "${RED}❌ Upload ID alınamadı. Response:${NC}"
    echo "$UPLOAD_RESPONSE"
    exit 1
fi

echo -e "${GREEN}✅ Upload ID: $UPLOAD_ID${NC}"

# Step 2: Split file and upload parts
echo -e "${YELLOW}🔪 Step 2: Splitting and uploading parts...${NC}"

FILE_SIZE=$(stat -f%z "$FILE_PATH" 2>/dev/null || stat -c%s "$FILE_PATH")
TOTAL_PARTS=$(( ($FILE_SIZE + $CHUNK_SIZE - 1) / $CHUNK_SIZE ))

echo "📏 File size: $(($FILE_SIZE / 1024 / 1024))MB"
echo "🧩 Total parts: $TOTAL_PARTS"

PARTS_XML=""
PART_NUM=1
OFFSET=0

while [ $OFFSET -lt $FILE_SIZE ]; do
    # Calculate chunk size for this part
    REMAINING=$(($FILE_SIZE - $OFFSET))
    if [ $REMAINING -lt $CHUNK_SIZE ]; then
        CURRENT_CHUNK_SIZE=$REMAINING
    else
        CURRENT_CHUNK_SIZE=$CHUNK_SIZE
    fi
    
    echo -e "${BLUE}⬆️  Part $PART_NUM: $(($CURRENT_CHUNK_SIZE / 1024 / 1024))MB${NC}"
    
    # Create temp file for this part
    TEMP_PART="/tmp/part_${PART_NUM}"
    dd if="$FILE_PATH" of="$TEMP_PART" bs=1 skip=$OFFSET count=$CURRENT_CHUNK_SIZE 2>/dev/null
    
    # Calculate SHA256 hash for this part
    PART_HASH=$(openssl dgst -sha256 -binary "$TEMP_PART" | xxd -p -c 256)
    
    # Upload part
    PART_AUTH=$(aws_sig_v4 "PUT" "/${S3_KEY}" "partNumber=${PART_NUM}&uploadId=${UPLOAD_ID}" "$PART_HASH" "application/octet-stream")
    
    PART_RESPONSE=$(curl -s -X PUT \
      -H "Host: $(echo $ENDPOINT | cut -d'/' -f3)" \
      -H "x-amz-content-sha256: $PART_HASH" \
      -H "x-amz-date: $(date -u +"%Y%m%dT%H%M%SZ")" \
      -H "Content-Type: application/octet-stream" \
      -H "Authorization: $PART_AUTH" \
      --data-binary "@$TEMP_PART" \
      "$ENDPOINT/$S3_KEY?partNumber=${PART_NUM}&uploadId=${UPLOAD_ID}")
    
    # Extract ETag
    ETAG=$(echo "$PART_RESPONSE" | grep -i 'etag:' | cut -d':' -f2 | tr -d ' \r\n' || echo "$PART_RESPONSE" | grep -o 'ETag: "[^"]*"' | cut -d'"' -f2)
    
    if [ -z "$ETAG" ]; then
        echo -e "${RED}❌ Part $PART_NUM upload failed${NC}"
        echo "$PART_RESPONSE"
        rm -f "$TEMP_PART"
        exit 1
    fi
    
    echo -e "${GREEN}✅ Part $PART_NUM uploaded, ETag: $ETAG${NC}"
    
    # Add to parts XML
    PARTS_XML="$PARTS_XML<Part><PartNumber>$PART_NUM</PartNumber><ETag>\"$ETAG\"</ETag></Part>"
    
    # Cleanup temp file
    rm -f "$TEMP_PART"
    
    PART_NUM=$(($PART_NUM + 1))
    OFFSET=$(($OFFSET + $CURRENT_CHUNK_SIZE))
done

# Step 3: Complete multipart upload
echo -e "${YELLOW}🔗 Step 3: Completing multipart upload...${NC}"

COMPLETE_XML="<CompleteMultipartUpload>$PARTS_XML</CompleteMultipartUpload>"
COMPLETE_HASH=$(echo -n "$COMPLETE_XML" | openssl dgst -sha256 -hex | cut -d' ' -f2)

COMPLETE_AUTH=$(aws_sig_v4 "POST" "/${S3_KEY}" "uploadId=${UPLOAD_ID}" "$COMPLETE_HASH" "application/xml")

COMPLETE_RESPONSE=$(curl -s -X POST \
  -H "Host: $(echo $ENDPOINT | cut -d'/' -f3)" \
  -H "x-amz-content-sha256: $COMPLETE_HASH" \
  -H "x-amz-date: $(date -u +"%Y%m%dT%H%M%SZ")" \
  -H "Content-Type: application/xml" \
  -H "Authorization: $COMPLETE_AUTH" \
  -d "$COMPLETE_XML" \
  "$ENDPOINT/$S3_KEY?uploadId=${UPLOAD_ID}")

if echo "$COMPLETE_RESPONSE" | grep -q "CompleteMultipartUploadResult"; then
    echo -e "${GREEN}🎉 Upload başarılı!${NC}"
    echo -e "${GREEN}📁 S3 Key: $S3_KEY${NC}"
    echo -e "${GREEN}🌐 Bucket: $BUCKET${NC}"
else
    echo -e "${RED}❌ Complete multipart failed${NC}"
    echo "$COMPLETE_RESPONSE"
    exit 1
fi

echo -e "${BLUE}✨ RunPod S3 Multipart Upload tamamlandı!${NC}"