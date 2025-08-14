#!/usr/bin/env python3
import boto3
from botocore.client import Config
import os

def cleanup_network_volume():
    """RunPod network volume'de temizlik yapar"""
    
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
        print("🧹 RunPod Network Volume Temizlik İşlemi")
        print("=" * 50)
        
        # 1. u123 klasörünü ve içeriğini sil
        print("🗑️  u123 klasörü siliniyor...")
        
        # u123 klasöründeki dosyaları bul
        response = s3_client.list_objects_v2(Bucket=network_volume_id, Prefix="uploads/u123/")
        
        if 'Contents' in response:
            for obj in response['Contents']:
                key = obj['Key']
                print(f"   🗑️  Siliniyor: {key}")
                s3_client.delete_object(Bucket=network_volume_id, Key=key)
            print(f"✅ u123 klasörü temizlendi ({len(response['Contents'])} dosya silindi)")
        else:
            print("ℹ️  u123 klasörü zaten boş")
        
        # 2. manual_talimatname.json'u sil
        manual_json_key = "uploads/test_20250813_084422/manual_talimatname.json"
        print(f"\n🗑️  {manual_json_key} siliniyor...")
        
        try:
            s3_client.delete_object(Bucket=network_volume_id, Key=manual_json_key)
            print("✅ manual_talimatname.json silindi")
        except Exception as e:
            print(f"⚠️  manual_talimatname.json silinemedi: {str(e)}")
        
        # 3. talimatname.json'u run.json olarak yeniden adlandır
        old_key = "uploads/test_20250813_084422/talimatname.json" 
        new_key = "uploads/test_20250813_084422/run.json"
        
        print(f"\n📝 {old_key} -> {new_key} yeniden adlandırılıyor...")
        
        try:
            # Dosyayı kopyala
            s3_client.copy_object(
                Bucket=network_volume_id,
                CopySource={'Bucket': network_volume_id, 'Key': old_key},
                Key=new_key
            )
            
            # Eski dosyayı sil
            s3_client.delete_object(Bucket=network_volume_id, Key=old_key)
            
            print("✅ talimatname.json -> run.json olarak yeniden adlandırıldı")
            
        except Exception as e:
            print(f"⚠️  Yeniden adlandırma başarısız: {str(e)}")
        
        print("\n" + "=" * 50)
        print("🎉 Temizlik işlemi tamamlandı!")
        
        # Son durum kontrolü
        print("\n🔍 Güncel dosya listesi:")
        response = s3_client.list_objects_v2(Bucket=network_volume_id)
        
        if 'Contents' in response:
            for obj in response['Contents']:
                key = obj['Key']
                size_mb = obj['Size'] / (1024 * 1024)
                print(f"   📄 {key} ({size_mb:.2f} MB)")
        
    except Exception as e:
        print(f"❌ Hata: {str(e)}")

if __name__ == "__main__":
    cleanup_network_volume()