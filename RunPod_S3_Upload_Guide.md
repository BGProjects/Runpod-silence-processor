# RunPod S3 Upload Guide

## 🎯 Başarılı Upload Çözümü

Bu dokümantasyon RunPod Network Volume'a S3 API ile dosya yükleme sorunlarının çözümünü içerir.

## ❌ Yaygın Hatalar ve Çözümleri

### 1. **Bucket Name Hatası**
```bash
# ❌ YANLIŞ - "runpod-volume-" prefix kullanma
aws s3 cp file.wav s3://runpod-volume-7z79eg0uur/uploads/folder/file.wav

# ✅ DOĞRU - Sadece Volume ID kullan
aws s3 cp file.wav s3://7z79eg0uur/uploads/folder/file.wav
```

### 2. **Region Case-Sensitivity**
```bash
# ❌ YANLIŞ - Küçük harf
--region eu-ro-1

# ✅ DOĞRU - Büyük harf (Case-sensitive!)
--region EU-RO-1
```

### 3. **Credentials Ayarlama**
```bash
# Environment variables (her seferinde ayarla)
export AWS_ACCESS_KEY_ID="${RUNPOD_AWS_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${RUNPOD_AWS_SECRET_ACCESS_KEY}"
```

## 📋 Doğru Upload Komutu

### AWS CLI ile Upload
```bash
# 1. Credentials ayarla
export AWS_ACCESS_KEY_ID="${RUNPOD_AWS_ACCESS_KEY_ID}"  
export AWS_SECRET_ACCESS_KEY="${RUNPOD_AWS_SECRET_ACCESS_KEY}"

# 2. Upload komutu
aws s3 cp dosya.wav s3://7z79eg0uur/uploads/klasor_adi/dosya.wav \
  --endpoint-url https://s3api-eu-ro-1.runpod.io/ \
  --region EU-RO-1
```

### Başarılı Upload Örneği
```bash
$ aws s3 cp test_small.wav s3://7z79eg0uur/uploads/test_20250813_181550/test_small.wav \
  --endpoint-url https://s3api-eu-ro-1.runpod.io/ \
  --region EU-RO-1

Completed 1.0 MiB/9.5 MiB (1.4 MiB/s) with 1 file(s) remaining
Completed 9.5 MiB/9.5 MiB (1.7 MiB/s) with 1 file(s) remaining
upload: ./test_small.wav to s3://7z79eg0uur/uploads/test_20250813_181550/test_small.wav
```

## 🔧 Python Boto3 Çözümü

### Doğru Boto3 Konfigürasyonu
```python
import boto3

# Session-based authentication
session = boto3.Session(
    aws_access_key_id=os.getenv("RUNPOD_AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("RUNPOD_AWS_SECRET_ACCESS_KEY")
)

# S3 client 
s3 = session.client(
    's3',
    region_name='EU-RO-1',  # Case-sensitive!
    endpoint_url="https://s3api-eu-ro-1.runpod.io/"
)

# Upload
bucket_name = '7z79eg0uur'  # Volume ID only, no prefix
s3.upload_file(
    'local_file.wav',
    bucket_name,
    'uploads/folder/file.wav'
)
```

## 🌍 RunPod Datacenters

| Datacenter | Region | Endpoint URL |
|------------|---------|--------------|
| EU-RO-1 | EU-RO-1 | https://s3api-eu-ro-1.runpod.io/ |
| EUR-IS-1 | EUR-IS-1 | https://s3api-eur-is-1.runpod.io/ |
| EU-CZ-1 | EU-CZ-1 | https://s3api-eu-cz-1.runpod.io/ |
| US-KS-2 | US-KS-2 | https://s3api-us-ks-2.runpod.io/ |

## 🚨 Önemli Notlar

1. **Bucket Name**: Volume ID'yi direkt kullan (`7z79eg0uur`), prefix ekleme
2. **Region**: Case-sensitive, büyük harf kullan (`EU-RO-1`)
3. **Credentials**: Her terminal session'da environment variable'ları ayarla
4. **Endpoint**: Datacenter'a göre doğru endpoint kullan
5. **Path**: `uploads/klasor_adi/dosya.ext` formatında yol kullan

## ✅ Test Komutu

Bağlantıyı test etmek için:
```bash
# Bucket'ları listele
aws s3 ls --endpoint-url https://s3api-eu-ro-1.runpod.io/ --region EU-RO-1

# İçeriği listele  
aws s3 ls s3://7z79eg0uur/uploads/ --endpoint-url https://s3api-eu-ro-1.runpod.io/ --region EU-RO-1
```

## 📊 Başarılı Upload Sonucu

Upload sonrası `list_s3_files.py` ile kontrol:
```
📄 uploads/test_20250813_181550/test_small.wav
   💾 Boyut: 9.54 MB (10,000,000 bytes)
   📅 Değiştirilme: 2025-08-13 15:46:34

📄 uploads/test_20250813_181550/run.json  
   💾 Boyut: 0.00 MB (241 bytes)
   📅 Değiştirilme: 2025-08-13 15:47:09
```

---

**Son güncelleme:** 2025-08-13  
**Test edildi:** ✅ AWS CLI, ❌ Boto3 (aynı hatalar)  
**Çalışan yöntem:** AWS CLI + doğru bucket name + case-sensitive region