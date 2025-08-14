#!/usr/bin/env python3
import boto3
from botocore.client import Config
import os

def list_network_volume_files():
    """RunPod network volume'deki dosyaları listeler"""
    
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
    
    try:
        print("🔍 RunPod Network Volume Dosya Listesi")
        print("=" * 50)
        
        # Tüm dosyaları listele
        response = s3_client.list_objects_v2(Bucket=network_volume_id)
        
        if 'Contents' not in response:
            print("❌ Dosya bulunamadı!")
            return
        
        files = response['Contents']
        total_size = 0
        
        # Dosyaları kategorize et
        folders = {}
        
        for obj in files:
            key = obj['Key']
            size = obj['Size']
            modified = obj['LastModified']
            total_size += size
            
            # Klasöre göre grupla
            if '/' in key:
                folder = key.split('/')[0]
                if folder not in folders:
                    folders[folder] = []
                folders[folder].append({
                    'name': key,
                    'size': size,
                    'modified': modified
                })
            else:
                if 'root' not in folders:
                    folders['root'] = []
                folders['root'].append({
                    'name': key,
                    'size': size,
                    'modified': modified
                })
        
        # Klasör bazında göster
        for folder_name, folder_files in folders.items():
            print(f"\n📁 {folder_name.upper()}/")
            print("-" * 30)
            
            for file_info in folder_files:
                size_mb = file_info['size'] / (1024 * 1024)
                print(f"📄 {file_info['name']}")
                print(f"   💾 Boyut: {size_mb:.2f} MB ({file_info['size']:,} bytes)")
                print(f"   📅 Değiştirilme: {file_info['modified'].strftime('%Y-%m-%d %H:%M:%S')}")
                print()
        
        print("=" * 50)
        print(f"📊 ÖZET:")
        print(f"   📁 Toplam klasör: {len(folders)}")
        print(f"   📄 Toplam dosya: {len(files)}")
        print(f"   💾 Toplam boyut: {total_size / (1024 * 1024):.2f} MB")
        print(f"   🌐 Volume ID: {network_volume_id}")
        
    except Exception as e:
        print(f"❌ Hata: {str(e)}")

if __name__ == "__main__":
    list_network_volume_files()