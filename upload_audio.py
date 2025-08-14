#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RunPod S3'e ses dosyası yükleme scripti
"""

import os
import boto3
import json
from pathlib import Path

def upload_to_runpod_s3():
    # RunPod S3 credentials from environment variables
    session = boto3.Session(
        aws_access_key_id=os.getenv("RUNPOD_AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("RUNPOD_AWS_SECRET_ACCESS_KEY")
    )
    
    # S3 client from session - Region sorununu çözelim
    s3 = session.client(
        's3',
        region_name='eu-ro-1',  # Küçük harf dene
        endpoint_url="https://s3api-eu-ro-1.runpod.io/"
    )
    
    bucket_name = os.getenv("RUNPOD_BUCKET_NAME", "7z79eg0uur")
    
    # Dosya yolları - Küçük test dosyası
    local_audio = "/home/developer/Müzik/silence/test_small.wav"
    local_run_json = "/home/developer/Müzik/silence/run.json"
    
    # run.json'u oku
    with open(local_run_json, 'r', encoding='utf-8') as f:
        run_data = json.load(f)
    
    folder_code = run_data['SpecialFolderCode']
    print(f"📂 Klasör: {folder_code}")
    
    try:
        # 1. Audio dosyasını yükle - Alternatif yöntem dene
        audio_s3_key = f"uploads/{folder_code}/test_small.wav"
        print(f"🎵 Audio yükleniyor: {local_audio} -> s3://{bucket_name}/{audio_s3_key}")
        
        file_size = os.path.getsize(local_audio)
        print(f"📏 Dosya boyutu: {file_size / (1024*1024):.2f} MB")
        
        try:
            # Progress callback
            class ProgressPercentage:
                def __init__(self, size):
                    self._size = size
                    self._seen_so_far = 0
                    
                def __call__(self, bytes_amount):
                    self._seen_so_far += bytes_amount
                    percentage = (self._seen_so_far / self._size) * 100
                    print(f"\r⬆️  {self._seen_so_far / (1024*1024):.1f}MB / {self._size / (1024*1024):.1f}MB ({percentage:.1f}%)", end='')
                    
            progress = ProgressPercentage(file_size)
            
            # Web search önerisi: Önce upload_file dene
            s3.upload_file(
                local_audio, 
                bucket_name, 
                audio_s3_key,
                Callback=progress
            )
            print(f"✅ Audio yüklendi (upload_file): {audio_s3_key}")
        except Exception as e1:
            print(f"❌ upload_file başarısız: {e1}")
            print("🔄 put_object yöntemi deneniyor...")
            
            # Alternatif: put_object ile dene
            with open(local_audio, 'rb') as f:
                s3.put_object(
                    Bucket=bucket_name,
                    Key=audio_s3_key,
                    Body=f,
                    ContentType='audio/wav'
                )
            print(f"✅ Audio yüklendi (put_object): {audio_s3_key}")
        
        # 2. run.json'u yükle
        run_json_s3_key = f"uploads/{folder_code}/run.json"
        print(f"📄 JSON yükleniyor: {local_run_json} -> s3://{bucket_name}/{run_json_s3_key}")
        
        # Upload statusu güncelle
        run_data['upload_status'] = 'completed'
        updated_json = json.dumps(run_data, ensure_ascii=False, indent=2)
        
        s3.put_object(
            Bucket=bucket_name,
            Key=run_json_s3_key,
            Body=updated_json.encode('utf-8'),
            ContentType='application/json'
        )
        print(f"✅ JSON yüklendi: {run_json_s3_key}")
        
        print(f"🎉 Yükleme tamamlandı: {folder_code}")
        return folder_code
        
    except Exception as e:
        print(f"❌ Hata: {e}")
        return None

if __name__ == "__main__":
    result = upload_to_runpod_s3()
    if result:
        print(f"✅ Başarılı: {result}")
    else:
        print("❌ Başarısız")