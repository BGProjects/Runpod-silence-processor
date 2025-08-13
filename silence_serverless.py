import runpod
import json
import os
import wave
import logging
import numpy as np
import math
import time

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SilenceProcessor:
    """
    RunPod Serverless için optimize edilmiş ses dosyası işleme sistemi
    Network volume'dan direkt dosya okuma ile yüksek performans
    """
    
    def __init__(self):
        # RunPod serverless network volume path
        self.volume_path = "/runpod-volume"
        logger.info(f"✅ SilenceProcessor başlatıldı - Volume path: {self.volume_path}")
    
    def _validate_input(self, special_folder_code):
        """
        Input parametresini doğrular
        
        Args:
            special_folder_code (str): Klasör kodu
            
        Returns:
            dict: Validation sonuçları
        """
        try:
            if not special_folder_code:
                raise ValueError("SpecialFolderCode boş olamaz")
            
            if not isinstance(special_folder_code, str):
                raise ValueError("SpecialFolderCode string olmalı")
            
            if len(special_folder_code) < 3:
                raise ValueError("SpecialFolderCode en az 3 karakter olmalı")
            
            # Klasörün varlığını kontrol et
            folder_path = os.path.join(self.volume_path, "uploads", special_folder_code)
            if not os.path.exists(folder_path):
                raise ValueError(f"Klasör bulunamadı: {folder_path}")
            
            logger.info(f"✅ Input validation başarılı: {special_folder_code}")
            return {"valid": True, "folder_path": folder_path}
            
        except Exception as e:
            logger.error(f"❌ Input validation hatası: {str(e)}")
            return {"valid": False, "error": str(e)}
    
    def _read_json_from_volume(self, file_path):
        """
        Network volume'dan JSON dosyasını okur
        
        Args:
            file_path (str): Volume'daki dosya yolu
            
        Returns:
            dict: JSON içeriği
        """
        try:
            full_path = os.path.join(self.volume_path, file_path)
            logger.info(f"📖 JSON okunuyor: {full_path}")
            
            if not os.path.exists(full_path):
                raise FileNotFoundError(f"JSON dosyası bulunamadı: {full_path}")
            
            with open(full_path, 'r', encoding='utf-8') as f:
                json_content = json.load(f)
            
            logger.info(f"✅ JSON başarıyla okundu: {len(json_content)} anahtar")
            return json_content
            
        except Exception as e:
            logger.error(f"❌ JSON okuma hatası: {str(e)}")
            raise
    
    def _detect_silence_segments_fast(self, file_path, min_silence_len_ms=500, silence_thresh_db=None, seek_step_ms=20):
        """
        Hızlı sessizlik tespiti (silence7.py algoritması bazında)
        
        Args:
            file_path (str): Volume'daki ses dosyası yolu
            min_silence_len_ms (int): Minimum sessizlik süresi (ms, varsayılan: 500)
            silence_thresh_db (float): Sessizlik eşiği dBFS (None=otomatik)
            seek_step_ms (int): Analiz adımı (ms, varsayılan: 20)
            
        Returns:
            dict: Hızlı sessizlik analizi sonuçları
        """
        try:
            full_path = os.path.join(self.volume_path, file_path)
            logger.info(f"🔍 Sessizlik analizi başlıyor: {full_path}")
            
            if not os.path.exists(full_path):
                raise FileNotFoundError(f"Ses dosyası bulunamadı: {full_path}")
            
            t_detect_start = time.perf_counter()
            
            # WAV dosyasını oku (silence7.py formatında)
            with wave.open(full_path, 'r') as wf:
                n_frames = wf.getnframes()
                sr = wf.getframerate() 
                ch = wf.getnchannels()
                sw = wf.getsampwidth()
                raw = wf.readframes(n_frames)
            
            # Audio verisini float32'ye dönüştür (silence7.py algoritması)
            if sw == 1:
                data = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
                if ch > 1:
                    n = (len(data) // ch) * ch
                    data = data[:n].reshape(-1, ch)
                else:
                    data = data.reshape(-1, 1)
                data = (data - 128.0) / 128.0
            elif sw == 2:
                data = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
                if ch > 1:
                    n = (len(data) // ch) * ch
                    data = data[:n].reshape(-1, ch)
                else:
                    data = data.reshape(-1, 1)
                data = data / 32768.0
            elif sw == 4:
                data = np.frombuffer(raw, dtype=np.int32).astype(np.float32)
                if ch > 1:
                    n = (len(data) // ch) * ch
                    data = data[:n].reshape(-1, ch)
                else:
                    data = data.reshape(-1, 1)
                data = data / 2147483648.0
            else:
                raise ValueError(f"Desteklenmeyen sample width: {sw} bayt")
            
            total_ms = int(round(len(data) / sr * 1000.0))
            
            # Mono ses için ortalama al
            x_mono = data.mean(axis=1).astype(np.float32)
            
            # Otomatik eşik hesaplama (silence7.py'den)
            def audio_dbfs(x):
                if x.size == 0: return float("-inf")
                rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
                if rms <= 0.0 or not math.isfinite(rms): return float("-inf")
                return 20.0 * math.log10(rms)
            
            audio_db = audio_dbfs(x_mono)
            if silence_thresh_db is None:
                silence_thresh_db = (-40.0 if not math.isfinite(audio_db) else (audio_db - 16.0))
            
            # Hızlı sessizlik tespiti (chunked RMS)
            def detect_silence_chunked(x_mono, sr, min_silence_len_ms, silence_thresh_db, seek_step_ms):
                if len(x_mono) == 0: return []
                
                hop = max(1, int(round(sr * (seek_step_ms / 1000.0))))
                win = hop
                
                n_hops = int(np.ceil((len(x_mono) - win) / hop)) + 1
                pad_len = (n_hops - 1) * hop + win - len(x_mono)
                if pad_len > 0:
                    x_pad = np.pad(x_mono, (0, pad_len), mode="constant")
                else:
                    x_pad = x_mono
                
                silent = []
                for i in range(n_hops):
                    start = i * hop
                    seg = x_pad[start:start + win]
                    rms = float(np.sqrt(np.mean(seg.astype(np.float64) ** 2)))
                    seg_db = float("-inf") if rms <= 0.0 else 20.0 * math.log10(rms)
                    silent.append(seg_db < silence_thresh_db)
                
                segments = []
                i = 0
                while i < n_hops:
                    if silent[i]:
                        s = i
                        while i < n_hops and silent[i]: i += 1
                        e = i
                        if (e - s) * seek_step_ms >= min_silence_len_ms:
                            segments.append([s * seek_step_ms, e * seek_step_ms])
                    else:
                        i += 1
                
                def clamp(v, lo, hi): return max(lo, min(hi, v))
                audio_ms = int(round(len(x_mono) / sr * 1000.0))
                return [[clamp(s, 0, audio_ms), clamp(e, 0, audio_ms)] for s, e in segments]
            
            spans = detect_silence_chunked(x_mono, sr, min_silence_len_ms, silence_thresh_db, seek_step_ms)
            
            # Timestamp dönüştürme fonksiyonu
            def ms_to_timestamp(ms):
                ms = int(ms); s, ms = divmod(ms, 1000); m, s = divmod(s, 60); h, m = divmod(m, 60)
                return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
            
            # Silence7.py formatında çıktı hazırla
            silences = []
            total_silence_ms = 0
            
            for i, (s, e) in enumerate(spans, 1):
                duration_ms = e - s
                total_silence_ms += duration_ms
                silences.append({
                    "index": i,
                    "start_ms": s,
                    "end_ms": e,
                    "start": ms_to_timestamp(s),
                    "end": ms_to_timestamp(e),
                    "duration_ms": duration_ms,
                    "duration": ms_to_timestamp(duration_ms)
                })
            
            # İstatistikler
            speech_ms = total_ms - total_silence_ms
            silence_percentage = (total_silence_ms / total_ms) * 100 if total_ms > 0 else 0
            speech_percentage = 100 - silence_percentage
            
            t_detect_end = time.perf_counter()
            detect_time = t_detect_end - t_detect_start
            
            logger.info(f"🔍 Hızlı sessizlik analizi: {len(silences)} segment, %{silence_percentage:.1f} sessizlik, {detect_time:.3f}s")
            
            return {
                "silences": silences,
                "audio_duration_ms": total_ms,
                "audio_duration": ms_to_timestamp(total_ms),
                "total_silence_ms": total_silence_ms,
                "speech_ms": speech_ms,
                "silence_percentage": round(silence_percentage, 1),
                "speech_percentage": round(speech_percentage, 1),
                "segment_count": len(silences),
                "detection_time_seconds": round(detect_time, 3),
                "params": {
                    "min_silence_len_ms": min_silence_len_ms,
                    "silence_thresh_dbfs": round(silence_thresh_db, 1),
                    "seek_step_ms": seek_step_ms,
                    "sr_hz": sr,
                    "channels": ch
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Sessizlik analizi hatası: {str(e)}")
            raise
    
    def _extract_and_save_metadata(self, audio_file_path, special_folder_code):
        """
        Ses dosyasının meta bilgilerini çıkarır ve meta.json olarak kaydeder
        
        Args:
            audio_file_path (str): Ses dosyası yolu
            special_folder_code (str): Klasör kodu
            
        Returns:
            dict: Meta bilgileri
        """
        try:
            full_path = os.path.join(self.volume_path, audio_file_path)
            logger.info(f"📊 Meta bilgileri çıkarılıyor: {full_path}")
            
            if not os.path.exists(full_path):
                raise FileNotFoundError(f"Ses dosyası bulunamadı: {full_path}")
            
            # WAV dosyası bilgilerini oku
            with wave.open(full_path, 'r') as audio_file:
                frame_rate = audio_file.getframerate()
                n_frames = audio_file.getnframes()
                channels = audio_file.getnchannels()
                sample_width = audio_file.getsampwidth()
                duration_seconds = n_frames / float(frame_rate)
                
            # Dosya bilgileri
            file_size = os.path.getsize(full_path)
            file_name = os.path.basename(full_path)
            file_ext = os.path.splitext(file_name)[1].lower()
            
            # Meta bilgileri hazırla
            metadata = {
                "filename": file_name,
                "file_path": audio_file_path,
                "file_extension": file_ext,
                "file_size_bytes": file_size,
                "file_size_mb": round(file_size / (1024 * 1024), 2),
                "duration_seconds": round(duration_seconds, 2),
                "duration_minutes": round(duration_seconds / 60, 2),
                "duration_formatted": self._seconds_to_timestamp(duration_seconds),
                "sample_rate_hz": frame_rate,
                "channels": channels,
                "channel_type": "mono" if channels == 1 else "stereo" if channels == 2 else f"{channels}-channel",
                "sample_width_bytes": sample_width,
                "sample_width_bits": sample_width * 8,
                "total_frames": n_frames,
                "bitrate_kbps": round((file_size * 8) / (duration_seconds * 1000), 2) if duration_seconds > 0 else 0,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                "analysis_version": "1.0"
            }
            
            # meta.json dosyasını kaydet
            meta_json_path = os.path.join(self.volume_path, "uploads", special_folder_code, "meta.json")
            
            with open(meta_json_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ Meta bilgileri kaydedildi: meta.json")
            logger.info(f"📄 Dosya: {file_name} ({metadata['file_size_mb']} MB)")
            logger.info(f"⏱️  Süre: {metadata['duration_formatted']} ({metadata['duration_seconds']}s)")
            logger.info(f"🎵 Format: {metadata['sample_rate_hz']}Hz, {metadata['channel_type']}, {metadata['sample_width_bits']}-bit")
            
            return metadata
            
        except Exception as e:
            logger.error(f"❌ Meta bilgi çıkarma hatası: {str(e)}")
            raise
    
    def _seconds_to_timestamp(self, seconds):
        """Saniyeyi HH:MM:SS.mmm formatına çevirir"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
    
    def _get_audio_duration(self, file_path):
        """
        Ses dosyasının süresini saniye cinsinden döndürür
        
        Args:
            file_path (str): Volume'daki ses dosyası yolu
            
        Returns:
            float: Ses dosyası süresi (saniye)
        """
        try:
            full_path = os.path.join(self.volume_path, file_path)
            logger.info(f"🎵 Ses dosyası analiz ediliyor: {full_path}")
            
            if not os.path.exists(full_path):
                raise FileNotFoundError(f"Ses dosyası bulunamadı: {full_path}")
            
            # Python'un built-in wave modülü ile hızlı analiz
            with wave.open(full_path, 'r') as audio_file:
                frame_rate = audio_file.getframerate()
                n_frames = audio_file.getnframes()
                duration = n_frames / float(frame_rate)
                channels = audio_file.getnchannels()
                sample_width = audio_file.getsampwidth()
            
            # Dosya bilgilerini al
            file_size = os.path.getsize(full_path)
            
            logger.info(f"✅ Ses analizi tamamlandı: {duration:.2f} saniye")
            
            return {
                "duration_seconds": round(duration, 2),
                "duration_minutes": round(duration / 60, 2),
                "frame_rate": frame_rate,
                "channels": channels,
                "sample_width_bytes": sample_width,
                "total_frames": n_frames,
                "file_size_bytes": file_size,
                "file_size_mb": round(file_size / (1024 * 1024), 2)
            }
            
        except Exception as e:
            logger.error(f"❌ Ses analizi hatası: {str(e)}")
            raise
    
    def process_special_folder(self, special_folder_code):
        """
        SpecialFolderCode'a göre ses dosyasını analiz eder
        
        Args:
            special_folder_code (str): Klasör kodu (örn: test_20250813_084422)
            
        Returns:
            dict: Analiz sonucu
        """
        try:
            logger.info(f"🚀 İşlem başlatılıyor: {special_folder_code}")
            
            # 1. Input validation
            validation_result = self._validate_input(special_folder_code)
            if not validation_result["valid"]:
                raise ValueError(validation_result["error"])
            
            # 2. run.json dosyasının yolunu oluştur
            run_json_path = f"uploads/{special_folder_code}/run.json"
            
            # 3. run.json dosyasını oku
            run_data = self._read_json_from_volume(run_json_path)
            
            # 4. IslenmemisFileName değerini al
            if 'IslenmemisFileName' not in run_data:
                raise ValueError("run.json'da 'IslenmemisFileName' anahtarı bulunamadı")
            
            islenmemis_filename = run_data['IslenmemisFileName']
            logger.info(f"📂 Analiz edilecek dosya: {islenmemis_filename}")
            
            # 5. Ses dosyasının yolunu oluştur
            audio_file_path = f"uploads/{special_folder_code}/{islenmemis_filename}"
            
            # 6. Meta bilgileri çıkar ve kaydet
            meta_info = self._extract_and_save_metadata(audio_file_path, special_folder_code)
            
            # 7. Ses dosyasını analiz et
            audio_info = self._get_audio_duration(audio_file_path)
            
            # 8. Hızlı sessizlik analizi yap
            silence_analysis = self._detect_silence_segments_fast(audio_file_path)
            
            # 9. Sonucu döndür
            result = {
                "success": True,
                "special_folder_code": special_folder_code,
                "filename": islenmemis_filename,
                "file_path": audio_file_path,
                "volume_path": f"{self.volume_path}/{audio_file_path}",
                "run_data": run_data,
                "meta_info": meta_info,
                "audio_info": audio_info,
                "silence_analysis": silence_analysis,
                "message": f"Ses dosyası, meta bilgileri ve sessizlik analizi tamamlandı: {islenmemis_filename}"
            }
            
            logger.info(f"✅ İşlem tamamlandı: {islenmemis_filename} - {audio_info['duration_seconds']}s")
            return result
            
        except Exception as e:
            error_msg = f"İşlem hatası: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "special_folder_code": special_folder_code
            }


def handler(job):
    """
    RunPod serverless handler fonksiyonu
    
    Expected input format:
    {
        "input": {
            "SpecialFolderCode": "test_20250813_084422"
        }
    }
    """
    try:
        job_input = job["input"]
        
        # Input validation
        if not job_input.get("SpecialFolderCode"):
            return {"error": "SpecialFolderCode parametresi gerekli"}
        
        special_folder_code = job_input["SpecialFolderCode"]
        
        logger.info(f"🎯 Handler başlatıldı: {special_folder_code}")
        
        # SilenceProcessor'ı başlat
        processor = SilenceProcessor()
        
        # Ses dosyasını analiz et
        result = processor.process_special_folder(special_folder_code)
        
        if result["success"]:
            # Başarılı sonucu döndür
            return {
                "success": True,
                "special_folder_code": result["special_folder_code"],
                "filename": result["filename"],
                "duration_seconds": result["audio_info"]["duration_seconds"],
                "duration_minutes": result["audio_info"]["duration_minutes"],
                "audio_details": {
                    "frame_rate": result["audio_info"]["frame_rate"],
                    "channels": result["audio_info"]["channels"],
                    "file_size_mb": result["audio_info"]["file_size_mb"]
                },
                "silence_analysis": {
                    "audio_duration_ms": result["silence_analysis"]["audio_duration_ms"],
                    "audio_duration": result["silence_analysis"]["audio_duration"],
                    "total_silence_ms": result["silence_analysis"]["total_silence_ms"],
                    "speech_ms": result["silence_analysis"]["speech_ms"],
                    "silence_percentage": result["silence_analysis"]["silence_percentage"],
                    "speech_percentage": result["silence_analysis"]["speech_percentage"],
                    "segment_count": result["silence_analysis"]["segment_count"],
                    "detection_time_seconds": result["silence_analysis"]["detection_time_seconds"],
                    "silences": result["silence_analysis"]["silences"],
                    "params": result["silence_analysis"]["params"]
                },
                "message": result["message"]
            }
        else:
            return {"error": result["error"]}
            
    except Exception as e:
        error_msg = f"Handler hatası: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return {"error": error_msg}


# RunPod serverless'i başlat
if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})