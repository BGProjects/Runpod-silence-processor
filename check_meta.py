#!/usr/bin/env python3
import boto3
from botocore.client import Config
import json
import os

def check_meta_json():
    """meta.json dosyasını kontrol eder"""
    
    # S3 client
    s3_client = boto3.client(
        's3',
        endpoint_url=os.getenv("RUNPOD_S3_ENDPOINT", "https://s3api-eu-ro-1.runpod.io/"),
        aws_access_key_id=os.getenv("RUNPOD_AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("RUNPOD_AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("RUNPOD_REGION", "EU-RO-1"),
        config=Config(signature_version='s3v4')
    )
    
    network_volume_id = os.getenv("RUNPOD_BUCKET_NAME", "7z79eg0uur")
    meta_key = "uploads/test_20250813_084422/meta.json"
    
    try:
        print("📄 meta.json dosyasını kontrol ediliyor...")
        
        # meta.json dosyasını oku
        response = s3_client.get_object(Bucket=network_volume_id, Key=meta_key)
        meta_content = response['Body'].read().decode('utf-8')
        
        print("✅ meta.json bulundu!")
        print("🔍 İçerik:")
        print("-" * 50)
        
        # JSON'u pretty print yap
        meta_data = json.loads(meta_content)
        print(json.dumps(meta_data, ensure_ascii=False, indent=2))
        
        print("-" * 50)
        print(f"📊 Dosya boyutu: {len(meta_content)} bytes")
        
    except Exception as e:
        print(f"❌ meta.json okunamadı: {str(e)}")

if __name__ == "__main__":
    check_meta_json()