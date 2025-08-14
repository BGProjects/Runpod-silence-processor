# RunPod FlashBoot & Performance Notes

## RunPod Queue ve Ücretlendirme

### API Response Fields
- **delayTime**: İsteğin kuyrukta bekleme süresi (millisaniye) - **ÜCRETSİZ**
- **executionTime**: Gerçek işlem süresi (kodun çalıştığı süre) - **ÜCRETLİ**
- **detection_time_seconds**: Sessizlik tespit algoritmasının süresi

### Ücretlendirme Kuralları
✅ **ÜCRETE SAYILMAZ**:
- Queue bekleme süresi (delayTime)

❌ **ÜCRETE SAYILIR**:
- Cold start süresi (worker başlatma)
- Execution time (kodun çalışma süresi)
- Idle timeout (işlem sonrası bekleme)

### Test Sonuçlarımız
```
Test 1: delayTime: 4.05s (ÜCRETSİZ) + executionTime: 3.02s (ÜCRETLİ)
Test 2: delayTime: 6.23s (ÜCRETSİZ) + executionTime: 0.72s (ÜCRETLİ) 
Test 3: delayTime: 1.48s (ÜCRETSİZ) + executionTime: 0.72s (ÜCRETLİ)
```

## FlashBoot Teknolojisi

### FlashBoot Nedir?
RunPod'un soğuk başlatma (cold start) sürelerini optimize etmek için geliştirdiği teknoloji.

### Nasıl Çalışır?
- Worker kaynaklarını kapattıktan sonra bir süre bellekte tutar
- Sonraki isteklerde hızlı yeniden başlatma sağlar
- Probabilistik olarak çalışır (trafik yoğunluğuna bağlı)
- Popüler image'lar daha fazla cache'lenir

### Performans İyileştirmeleri
- ⚡ Cold start: **500ms-2 saniye** (normal: 10-30 saniye)
- 🏆 RunPod'un %48'i **200ms altında** cold start
- 📈 Tutarlı trafik varsa **1 saniye altı** mümkün
- 🎯 En iyi performans 3+ worker ile

### Nasıl Aktif Edilir?
1. RunPod Console → Endpoint ayarları
2. Sağ tarafta **FlashBoot** toggle'ını aç
3. **Varsayılan**: Kapalı (manuel açman gerekiyor)

### Maliyet ve Öneriler
- **Maliyet**: **Ücretsiz!** Hiç ek ücret yok
- **Öneri**: Her zaman açık bırak, zararı yok
- **Dikkat**: Az trafikli endpoint'lerde etkisi sınırlı

## Sessizlik Tespit Performance

### Algoritma Optimizasyonu
- **Önceki algoritma**: Sample-by-sample analiz → 18.6s
- **Yeni algoritma**: Chunked RMS (silence7.py based) → 0.62s
- **Hız artışı**: **708x daha hızlı** gerçek zamandan

### Test Sonuçları (439s ses dosyası)
```
Cold Start (Test 1): detection_time: 2.929s
Warm Container (Test 2-3): detection_time: ~0.62s
```

### Algoritma Parametreleri
```python
min_silence_len_ms: 500      # Minimum sessizlik süresi
silence_thresh_dbfs: -29     # Otomatik eşik (audio_dBFS - 16)
seek_step_ms: 20            # Analiz adımı (performans anahtarı)
```

## Optimizasyon Önerileri

### Endpoint Ayarları
1. **FlashBoot**: Mutlaka aktif et
2. **Worker Count**: Tutarlı trafik için 3+ worker
3. **Idle Timeout**: Default bırak (maliyet kontrolü)

### Kod Optimizasyonu
- NumPy operasyonları kullan (vectorized)
- Chunked processing (büyük dosyalar için)
- Container warm-up stratejisi

### Maliyet Optimizasyonu
- Queue time ücretsiz, sadece execution time ücretli
- FlashBoot ile cold start maliyetini minimize et
- Idle timeout'u dikkatli ayarla

## Tespit Edilen Sessizlik Alanları

### Test Dosyası: input.wav (439.87 saniye / 7:19.873)

**Toplam 7 Sessizlik Segmenti Tespit Edildi:**

| # | Başlangıç | Bitiş | Süre | Timestamp Format |
|---|-----------|-------|------|------------------|
| 1 | 50.080s | 51.060s | 0.98s | `00:00:50.080 → 00:00:51.060` |
| 2 | 83.280s | 84.920s | 1.64s | `00:01:23.280 → 00:01:24.920` |
| 3 | 85.600s | 86.260s | 0.66s | `00:01:25.600 → 00:01:26.260` |
| 4 | 126.300s | 127.120s | 0.82s | `00:02:06.300 → 00:02:07.120` |
| 5 | 233.360s | 233.860s | 0.50s | `00:03:53.360 → 00:03:53.860` |
| 6 | 319.260s | 319.780s | 0.52s | `00:05:19.260 → 00:05:19.780` |
| 7 | 366.540s | 367.500s | 0.96s | `00:06:06.540 → 00:06:07.500` |

### İstatistikler
- **Toplam Sessizlik**: 6.08 saniye (%1.4)
- **Konuşma Süresi**: 433.79 saniye (%98.6)
- **Ortalama Sessizlik**: 0.87 saniye/segment
- **En Uzun Sessizlik**: 1.64s (segment #2)
- **En Kısa Sessizlik**: 0.50s (segment #5)

### Analiz Parametreleri
```json
{
  "min_silence_len_ms": 500,
  "silence_thresh_dbfs": -29,
  "seek_step_ms": 20,
  "sr_hz": 48000,
  "channels": 2
}
```

### Çıktı Formatı (JSON)
```json
{
  "silences": [
    {
      "index": 1,
      "start_ms": 50080,
      "end_ms": 51060,
      "start": "00:00:50.080",
      "end": "00:00:51.060", 
      "duration_ms": 980,
      "duration": "00:00:00.980"
    }
    // ... diğer segmentler
  ]
}
```

---
*Son güncelleme: 2025-01-13*
*Endpoint: 3g608tv8j80kj7*