#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audio Splitter Module - RunPod Serverless için modüler ses parçalama sistemi
"""

import os
import json
import time
import logging
import torch
import torchaudio
import torchaudio.functional as F

logger = logging.getLogger(__name__)

class AudioSplitter:
    """
    Ses dosyalarını parts.json planına göre parçalara ayıran sınıf
    """
    
    def __init__(self, volume_path="/runpod-volume"):
        self.volume_path = volume_path
        self.target_sr = 48000  # DeepFilterNet3 için 48kHz
        logger.info(f"🔪 AudioSplitter başlatıldı - Volume: {volume_path}")
    
    def split_audio_from_parts_json(self, special_folder_code):
        """
        parts.json dosyasına göre ses dosyasını parçalara ayırır
        
        Args:
            special_folder_code (str): Klasör kodu
            
        Returns:
            dict: Parçalama sonucu
        """
        try:
            logger.info(f"🔪 Parçalama başlatılıyor: {special_folder_code}")
            
            # 1. parts.json dosyasını oku
            parts_json_path = os.path.join(self.volume_path, "uploads", special_folder_code, "parts.json")
            
            if not os.path.exists(parts_json_path):
                raise FileNotFoundError(f"parts.json bulunamadı: {parts_json_path}")
            
            with open(parts_json_path, 'r', encoding='utf-8') as f:
                parts_data = json.load(f)
            
            split_plan = parts_data["split_plan"]
            pieces = split_plan["pieces"]
            
            logger.info(f"📋 {len(pieces)} parça planı yüklendi")
            
            # 2. run.json'dan ses dosyası adını al
            run_json_path = os.path.join(self.volume_path, "uploads", special_folder_code, "run.json")
            
            with open(run_json_path, 'r', encoding='utf-8') as f:
                run_data = json.load(f)
            
            audio_filename = run_data['IslenmemisFileName']
            audio_file_path = os.path.join(self.volume_path, "uploads", special_folder_code, audio_filename)
            
            if not os.path.exists(audio_file_path):
                raise FileNotFoundError(f"Ses dosyası bulunamadı: {audio_file_path}")
            
            logger.info(f"🎵 Kaynak dosya: {audio_filename}")
            
            # 3. Parts klasörünü oluştur
            parts_folder = os.path.join(self.volume_path, "uploads", special_folder_code, "Parts")
            os.makedirs(parts_folder, exist_ok=True)
            
            # 4. Ses dosyasını yükle
            audio, orig_sr = torchaudio.load(audio_file_path)
            logger.info(f"📊 Orijinal: {orig_sr}Hz, {audio.shape[0]} kanal, {audio.shape[1]} sample")
            
            # 5. 48kHz'e dönüştür (gerekirse)
            if orig_sr != self.target_sr:
                logger.info(f"🔄 Yeniden örnekleme: {orig_sr}Hz → {self.target_sr}Hz")
                audio = F.resample(audio, orig_freq=orig_sr, new_freq=self.target_sr)
            
            # 6. Her parçayı kes ve kaydet
            split_results = []
            
            for piece in pieces:
                piece_index = piece["piece_index"]
                start_ms = piece["start_ms"]
                end_ms = piece["end_ms"]
                trim_leading_ms = piece["trim_leading_ms"]
                
                # Millisecond'yi sample'a çevir
                start_sample = int((start_ms / 1000.0) * self.target_sr)
                end_sample = int((end_ms / 1000.0) * self.target_sr)
                
                # Trim uygula (Silence7 örtüşme stratejisi)
                if trim_leading_ms > 0:
                    trim_samples = int((trim_leading_ms / 1000.0) * self.target_sr)
                    start_sample += trim_samples
                    logger.info(f"✂️  Parça {piece_index}: {trim_leading_ms}ms trim uygulandı")
                
                # Sınırları kontrol et
                start_sample = max(0, start_sample)
                end_sample = min(audio.shape[1], end_sample)
                
                if start_sample >= end_sample:
                    logger.warning(f"⚠️  Parça {piece_index}: Geçersiz aralık, atlanıyor")
                    continue
                
                # Parçayı kes
                piece_audio = audio[:, start_sample:end_sample]
                
                # Dosya adı ve yolu
                piece_filename = f"{piece_index}.wav"
                piece_path = os.path.join(parts_folder, piece_filename)
                
                # Normalizasyon (clipping önleme)
                if piece_audio.numel() > 0:
                    peak = float(torch.max(torch.abs(piece_audio)))
                    if peak > 1.0:
                        piece_audio = piece_audio / (peak + 1e-9)
                
                # WAV olarak kaydet (16-bit PCM, 48kHz, stereo)
                torchaudio.save(
                    piece_path,
                    piece_audio,
                    self.target_sr,
                    encoding="PCM_S",
                    bits_per_sample=16
                )
                
                # Kayıt bilgilerini al
                piece_size = os.path.getsize(piece_path)
                piece_duration = piece_audio.shape[1] / self.target_sr
                
                split_results.append({
                    "piece_index": piece_index,
                    "filename": piece_filename,
                    "file_path": f"uploads/{special_folder_code}/Parts/{piece_filename}",
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "actual_start_ms": int(start_sample / self.target_sr * 1000),
                    "actual_end_ms": int(end_sample / self.target_sr * 1000),
                    "trim_leading_ms": trim_leading_ms,
                    "duration_seconds": round(piece_duration, 2),
                    "file_size_bytes": piece_size,
                    "file_size_mb": round(piece_size / (1024 * 1024), 2),
                    "sample_rate": self.target_sr,
                    "channels": piece_audio.shape[0],
                    "samples": piece_audio.shape[1]
                })
                
                logger.info(f"✅ Parça {piece_index}: {piece_filename} ({piece_duration:.2f}s, {piece_size/1024/1024:.2f}MB)")
            
            # 7. Sonuç özeti
            total_pieces = len(split_results)
            total_size_mb = sum(r["file_size_mb"] for r in split_results)
            total_duration = sum(r["duration_seconds"] for r in split_results)
            
            result = {
                "success": True,
                "special_folder_code": special_folder_code,
                "parts_folder": f"uploads/{special_folder_code}/Parts",
                "total_pieces": total_pieces,
                "total_duration_seconds": round(total_duration, 2),
                "total_size_mb": round(total_size_mb, 2),
                "audio_format": {
                    "sample_rate": self.target_sr,
                    "channels": audio.shape[0],
                    "encoding": "PCM_S",
                    "bits_per_sample": 16,
                    "format": "WAV"
                },
                "pieces": split_results,
                "strategy": "silence7_overlapping_with_trim",
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                "message": f"{total_pieces} parça başarıyla oluşturuldu (Toplam: {total_duration:.1f}s, {total_size_mb:.1f}MB)"
            }
            
            logger.info(f"🎉 Parçalama tamamlandı: {total_pieces} parça, {total_duration:.1f}s, {total_size_mb:.1f}MB")
            return result
            
        except Exception as e:
            error_msg = f"Parçalama hatası: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "special_folder_code": special_folder_code
            }

if __name__ == "__main__":
    # Test için
    splitter = AudioSplitter("/runpod-volume")
    result = splitter.split_audio_from_parts_json("test_20250813_084422")
    print(json.dumps(result, ensure_ascii=False, indent=2))