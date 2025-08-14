#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RunPod S3 Optimized Multipart Upload
Cloudflare 100s timeout çözümü ile 10MB chunks
"""

import boto3
import os
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
import time

def create_runpod_s3_client():
    """RunPod S3 client with optimized timeout settings"""
    
    # Credentials from environment
    aws_access_key_id = os.getenv("RUNPOD_AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.getenv("RUNPOD_AWS_SECRET_ACCESS_KEY")
    
    # Configure with extended timeouts but realistic for chunks
    config = Config(
        read_timeout=300,  # 5 minutes per chunk (was 7200)
        connect_timeout=60,
        retries={'max_attempts': 5, 'mode': 'adaptive'}
    )
    
    return boto3.client(
        's3',
        region_name='EU-RO-1',
        endpoint_url="https://s3api-eu-ro-1.runpod.io/",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        config=config
    )

class ProgressCallback:
    """Progress tracker with ETA calculation"""
    
    def __init__(self, file_path):
        self._file_path = os.path.basename(file_path)
        self._size = os.path.getsize(file_path)
        self._seen_so_far = 0
        self._start_time = time.time()
        
    def __call__(self, bytes_amount):
        self._seen_so_far += bytes_amount
        percentage = (self._seen_so_far / self._size) * 100
        
        elapsed = time.time() - self._start_time
        if self._seen_so_far > 0:
            eta = (elapsed / self._seen_so_far) * (self._size - self._seen_so_far)
            eta_min = eta / 60
        else:
            eta_min = 0
            
        print(f"⬆️  {self._file_path}: {percentage:.1f}% "
              f"({self._seen_so_far / (1024*1024):.1f}MB/"
              f"{self._size / (1024*1024):.1f}MB) "
              f"ETA: {eta_min:.1f}min", end='\r')

def upload_large_file_optimized(file_path, bucket_name, key_name):
    """
    RunPod S3 optimized upload with 10MB chunks
    Cloudflare 100s timeout çözümü
    """
    
    print(f"🚀 RunPod S3 Optimized Upload başlıyor...")
    print(f"📂 Dosya: {file_path}")
    print(f"📏 Boyut: {os.path.getsize(file_path) / (1024*1024):.1f} MB")
    
    s3_client = create_runpod_s3_client()
    
    # CRITICAL: 10MB chunks for Cloudflare 100s timeout
    transfer_config = TransferConfig(
        multipart_threshold=1024 * 1024 * 5,   # 5MB threshold
        multipart_chunksize=1024 * 1024 * 10,  # 10MB chunks (Cloudflare safe)
        max_concurrency=3,  # Reduced concurrency for stability
        use_threads=True,
        io_chunksize=1024 * 256  # 256KB IO chunks
    )
    
    try:
        print(f"🔧 Konfigürasyon: 10MB chunks, 3 concurrent threads")
        
        s3_client.upload_file(
            file_path,
            bucket_name,
            key_name,
            Config=transfer_config,
            Callback=ProgressCallback(file_path)
        )
        
        print(f"\n✅ Upload başarılı: {key_name}")
        return True
        
    except Exception as e:
        print(f"\n❌ Upload başarısız: {str(e)}")
        return False

def manual_multipart_upload(file_path, bucket_name, key_name):
    """
    Manuel multipart upload with 10MB chunks
    Daha fazla kontrol için
    """
    
    print(f"🔧 Manuel multipart upload başlıyor...")
    
    s3_client = create_runpod_s3_client()
    chunk_size = 10 * 1024 * 1024  # 10MB chunks
    
    # Initiate multipart upload
    response = s3_client.create_multipart_upload(
        Bucket=bucket_name,
        Key=key_name,
        ContentType='audio/wav'
    )
    upload_id = response['UploadId']
    
    parts = []
    part_number = 1
    file_size = os.path.getsize(file_path)
    
    print(f"📋 Upload ID: {upload_id}")
    
    try:
        with open(file_path, 'rb') as file:
            while True:
                chunk = file.read(chunk_size)
                if not chunk:
                    break
                
                chunk_mb = len(chunk) / (1024 * 1024)
                print(f"⬆️  Part {part_number}: {chunk_mb:.1f}MB uploading...")
                
                # Upload part with retry logic
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        start_time = time.time()
                        
                        response = s3_client.upload_part(
                            Bucket=bucket_name,
                            Key=key_name,
                            PartNumber=part_number,
                            UploadId=upload_id,
                            Body=chunk
                        )
                        
                        upload_time = time.time() - start_time
                        speed = chunk_mb / upload_time if upload_time > 0 else 0
                        
                        parts.append({
                            'ETag': response['ETag'],
                            'PartNumber': part_number
                        })
                        
                        print(f"✅ Part {part_number}: {upload_time:.1f}s, {speed:.1f}MB/s")
                        break
                        
                    except Exception as e:
                        if attempt < max_retries - 1:
                            print(f"⚠️  Part {part_number} retry {attempt + 1}/{max_retries}: {str(e)}")
                            time.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        else:
                            raise e
                
                part_number += 1
        
        print(f"🔗 Completing multipart upload...")
        
        # Complete multipart upload
        s3_client.complete_multipart_upload(
            Bucket=bucket_name,
            Key=key_name,
            UploadId=upload_id,
            MultipartUpload={'Parts': parts}
        )
        
        print(f"✅ Manuel multipart upload tamamlandı: {key_name}")
        print(f"📊 Toplam {len(parts)} parça upload edildi")
        return True
        
    except Exception as e:
        print(f"❌ Manuel upload başarısız: {str(e)}")
        
        # Abort multipart upload on failure
        try:
            s3_client.abort_multipart_upload(
                Bucket=bucket_name,
                Key=key_name,
                UploadId=upload_id
            )
            print(f"🗑️  Multipart upload iptal edildi")
        except:
            pass
            
        return False

if __name__ == "__main__":
    # Test parameters
    file_path = "/home/developer/İndirilenler/videoplayback.wav"
    bucket_name = os.getenv("RUNPOD_BUCKET_NAME", "7z79eg0uur")
    key_name = "uploads/test_20250813_190814/videoplayback.wav"
    
    print("🎯 RunPod S3 Cloudflare Timeout Çözümü")
    print("=" * 50)
    
    # Method 1: High-level API with TransferConfig
    print("\n🚀 Method 1: TransferConfig ile optimized upload")
    success1 = upload_large_file_optimized(file_path, bucket_name, key_name)
    
    if not success1:
        print("\n🔧 Method 2: Manuel multipart upload deneniyor...")
        success2 = manual_multipart_upload(file_path, bucket_name, key_name)
        
        if success2:
            print("✅ Manuel upload başarılı!")
        else:
            print("❌ Tüm yöntemler başarısız")
    else:
        print("✅ İlk yöntem başarılı!")