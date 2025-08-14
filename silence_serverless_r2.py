import runpod
import json
import os
import wave
import logging
import numpy as np
import math
import time
import boto3
import tempfile
import shutil
from botocore.exceptions import ClientError

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SilenceProcessorR2:
    """
    RunPod Serverless için R2 entegrasyonlu ses dosyası işleme sistemi
    Cloudflare R2'den dosya indirme ve temp klasörde işleme
    """
    
    def __init__(self):
        # R2 client setup
        self.r2_client = boto3.client(
            's3',
            region_name='auto',
            endpoint_url=os.getenv('R2_ENDPOINT_URL'),
            aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY')
        )
        self.r2_bucket = os.getenv('R2_BUCKET_NAME', 'cleanvoice-audio')
        
        # Temp directory for processing
        self.temp_dir = "/tmp/audio_processing"
        os.makedirs(self.temp_dir, exist_ok=True)
        
        logger.info(f"✅ SilenceProcessorR2 başlatıldı - R2 Bucket: {self.r2_bucket}")
        logger.info(f"📁 Temp directory: {self.temp_dir}")
    
    def _download_from_r2(self, r2_key, local_path):
        """
        R2'den dosyayı yerel temp klasöre indirir
        
        Args:
            r2_key (str): R2'deki dosya anahtarı
            local_path (str): Yerel dosya yolu
            
        Returns:
            bool: İndirme başarısı
        """
        try:
            logger.info(f"📥 R2'den indiriliyor: {r2_key} → {local_path}")
            start_time = time.perf_counter()
            
            # R2'den dosyayı indir
            response = self.r2_client.get_object(Bucket=self.r2_bucket, Key=r2_key)
            
            # Yerel dosyaya yaz
            with open(local_path, 'wb') as f:
                f.write(response['Body'].read())
            
            download_time = time.perf_counter() - start_time
            file_size = os.path.getsize(local_path)
            
            logger.info(f"✅ İndirme tamamlandı: {file_size/1024/1024:.2f}MB, {download_time:.2f}s")
            return True
            
        except ClientError as e:
            logger.error(f"❌ R2 indirme hatası: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Genel indirme hatası: {e}")
            return False
    
    def _upload_to_r2(self, local_path, r2_key):
        """
        Yerel dosyayı R2'ye yükler
        
        Args:
            local_path (str): Yerel dosya yolu
            r2_key (str): R2'deki hedef anahtar
            
        Returns:
            bool: Yükleme başarısı
        """
        try:
            logger.info(f"📤 R2'ye yükleniyor: {local_path} → {r2_key}")
            start_time = time.perf_counter()
            
            # Dosyayı R2'ye yükle
            with open(local_path, 'rb') as f:
                self.r2_client.put_object(
                    Bucket=self.r2_bucket,
                    Key=r2_key,
                    Body=f,
                    ContentType='application/json' if r2_key.endswith('.json') else 'audio/wav'
                )
            
            upload_time = time.perf_counter() - start_time
            file_size = os.path.getsize(local_path)
            
            logger.info(f"✅ Yükleme tamamlandı: {file_size/1024/1024:.2f}MB, {upload_time:.2f}s")
            return True
            
        except Exception as e:
            logger.error(f"❌ R2 yükleme hatası: {e}")
            return False
    
    def _read_json_from_r2(self, r2_key):
        """
        R2'den JSON dosyasını okur
        
        Args:
            r2_key (str): R2'deki JSON dosya anahtarı
            
        Returns:
            dict: JSON içeriği
        """
        try:
            logger.info(f"📖 R2'den JSON okunuyor: {r2_key}")
            
            response = self.r2_client.get_object(Bucket=self.r2_bucket, Key=r2_key)
            json_content = json.loads(response['Body'].read().decode('utf-8'))
            
            logger.info(f"✅ JSON başarıyla okundu: {len(json_content)} anahtar")
            return json_content
            
        except Exception as e:
            logger.error(f"❌ R2 JSON okuma hatası: {e}")
            raise
    
    def _validate_input(self, special_folder_code):
        """
        Input parametresini doğrular ve R2'de dosyaların varlığını kontrol eder
        
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
            
            # R2'de run.json dosyasının varlığını kontrol et
            run_json_key = f"audio/{special_folder_code}/run.json"
            
            try:
                self.r2_client.head_object(Bucket=self.r2_bucket, Key=run_json_key)
                logger.info(f"✅ Input validation başarılı: {special_folder_code}")
                return {"valid": True, "run_json_key": run_json_key}
            except ClientError:
                raise ValueError(f"R2'de run.json bulunamadı: {run_json_key}")
            
        except Exception as e:
            logger.error(f"❌ Input validation hatası: {str(e)}")
            return {"valid": False, "error": str(e)}
    
    def _extract_and_save_metadata(self, audio_file_path, special_folder_code):
        """
        Ses dosyasının meta bilgilerini çıkarır ve meta.json olarak R2'ye kaydeder
        
        Args:
            audio_file_path (str): Yerel ses dosyası yolu
            special_folder_code (str): Klasör kodu
            
        Returns:
            dict: Meta bilgileri
        """
        try:
            logger.info(f"📊 Meta bilgileri çıkarılıyor: {audio_file_path}")
            
            if not os.path.exists(audio_file_path):
                raise FileNotFoundError(f"Ses dosyası bulunamadı: {audio_file_path}")
            
            # WAV dosyası bilgilerini oku
            with wave.open(audio_file_path, 'r') as audio_file:
                frame_rate = audio_file.getframerate()
                n_frames = audio_file.getnframes()
                channels = audio_file.getnchannels()
                sample_width = audio_file.getsampwidth()
                duration_seconds = n_frames / float(frame_rate)
                
            # Dosya bilgileri
            file_size = os.path.getsize(audio_file_path)
            file_name = os.path.basename(audio_file_path)
            file_ext = os.path.splitext(file_name)[1].lower()
            
            # Meta bilgileri hazırla
            metadata = {
                "filename": file_name,
                "file_path": f"audio/{special_folder_code}/{file_name}",
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
            
            # meta.json dosyasını temp'e yaz ve R2'ye yükle
            meta_json_path = os.path.join(self.temp_dir, "meta.json")
            with open(meta_json_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            # R2'ye yükle
            r2_meta_key = f"audio/{special_folder_code}/meta.json"
            self._upload_to_r2(meta_json_path, r2_meta_key)
            
            logger.info(f"✅ Meta bilgileri R2'ye kaydedildi: meta.json")
            logger.info(f"📄 Dosya: {file_name} ({metadata['file_size_mb']} MB)")
            logger.info(f"⏱️  Süre: {metadata['duration_formatted']} ({metadata['duration_seconds']}s)")
            logger.info(f"🎵 Format: {metadata['sample_rate_hz']}Hz, {metadata['channel_type']}, {metadata['sample_width_bits']}-bit")
            
            return metadata
            
        except Exception as e:
            logger.error(f"❌ Meta bilgi çıkarma hatası: {str(e)}")
            raise
    
    def _detect_silence_segments_fast(self, file_path, min_silence_len_ms=500, silence_thresh_db=None, seek_step_ms=20):
        """
        Hızlı sessizlik tespiti (orijinal silence7.py algoritması)
        
        Args:
            file_path (str): Yerel ses dosyası yolu
            min_silence_len_ms (int): Minimum sessizlik süresi (ms)
            silence_thresh_db (float): Sessizlik eşiği dBFS
            seek_step_ms (int): Analiz adımı (ms)
            
        Returns:
            dict: Sessizlik analizi sonuçları
        """
        try:
            logger.info(f"🔍 Sessizlik analizi başlıyor: {file_path}")
            
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Ses dosyası bulunamadı: {file_path}")
            
            t_detect_start = time.perf_counter()
            
            # WAV dosyasını oku (silence7.py formatında)
            with wave.open(file_path, 'r') as wf:
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
            
            logger.info(f"🔍 Sessizlik analizi: {len(silences)} segment, %{silence_percentage:.1f} sessizlik, {detect_time:.3f}s")
            
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
    
    def _create_silence_json(self, silence_segments, special_folder_code):
        """
        silence.json dosyasını oluşturur ve R2'ye yükler
        
        Args:
            silence_segments (list): Sessizlik segmentleri
            special_folder_code (str): Klasör kodu
        """
        try:
            silence_json_path = os.path.join(self.temp_dir, "silence.json")
            
            silence_data = {
                "silences": silence_segments,
                "total_segments": len(silence_segments),
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                "analysis_version": "1.0"
            }
            
            with open(silence_json_path, 'w', encoding='utf-8') as f:
                json.dump(silence_data, f, ensure_ascii=False, indent=2)
            
            # R2'ye yükle
            r2_silence_key = f"audio/{special_folder_code}/silence.json"
            self._upload_to_r2(silence_json_path, r2_silence_key)
            
            logger.info(f"✅ silence.json R2'ye oluşturuldu: {len(silence_segments)} sessizlik segmenti")
            return silence_data
            
        except Exception as e:
            logger.error(f"❌ silence.json oluşturma hatası: {str(e)}")
            raise
    
    def _seconds_to_timestamp(self, seconds):
        """Saniyeyi HH:MM:SS.mmm formatına çevirir"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
    
    def _cleanup_temp_files(self):
        """Temp dosyalarını temizler"""
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                os.makedirs(self.temp_dir, exist_ok=True)
                logger.info("🧹 Temp dosyalar temizlendi")
        except Exception as e:
            logger.warning(f"⚠️ Temp dosya temizleme hatası: {e}")
    
    def process_special_folder(self, special_folder_code):
        """
        SpecialFolderCode'a göre R2'den ses dosyasını indirip analiz eder
        
        Args:
            special_folder_code (str): Klasör kodu (örn: 20250814021530AB12CD)
            
        Returns:
            dict: Analiz sonucu
        """
        try:
            logger.info(f"🚀 R2 işlem başlatılıyor: {special_folder_code}")
            
            # 1. Input validation
            validation_result = self._validate_input(special_folder_code)
            if not validation_result["valid"]:
                raise ValueError(validation_result["error"])
            
            # 2. R2'den run.json'u oku
            run_json_key = f"audio/{special_folder_code}/run.json"
            run_data = self._read_json_from_r2(run_json_key)
            
            # 3. IslenmemisFileName değerini al
            if 'IslenmemisFileName' not in run_data:
                raise ValueError("run.json'da 'IslenmemisFileName' anahtarı bulunamadı")
            
            islenmemis_filename = run_data['IslenmemisFileName']
            logger.info(f"📂 Analiz edilecek dosya: {islenmemis_filename}")
            
            # 4. R2'den ses dosyasını temp'e indir
            audio_r2_key = f"audio/{special_folder_code}/{islenmemis_filename}"
            temp_audio_path = os.path.join(self.temp_dir, islenmemis_filename)
            
            if not self._download_from_r2(audio_r2_key, temp_audio_path):
                raise Exception("Ses dosyası R2'den indirilemedi")
            
            # 5. Meta bilgileri çıkar ve kaydet
            meta_info = self._extract_and_save_metadata(temp_audio_path, special_folder_code)
            
            # 6. Hızlı sessizlik analizi yap
            silence_analysis = self._detect_silence_segments_fast(temp_audio_path)
            
            # 7. silence.json oluştur ve R2'ye kaydet
            silence_json_data = self._create_silence_json(silence_analysis["silences"], special_folder_code)
            
            # 8. Temp dosyaları temizle
            self._cleanup_temp_files()
            
            # 9. Sonucu döndür
            result = {
                "success": True,
                "special_folder_code": special_folder_code,
                "filename": islenmemis_filename,
                "r2_path": audio_r2_key,
                "run_data": run_data,
                "meta_info": meta_info,
                "silence_analysis": silence_analysis,
                "silence_json_created": True,
                "message": f"R2'den ses dosyası analizi tamamlandı: {islenmemis_filename} - {meta_info['duration_seconds']}s"
            }
            
            logger.info(f"✅ R2 işlem tamamlandı: {islenmemis_filename} - {meta_info['duration_seconds']}s")
            return result
            
        except Exception as e:
            error_msg = f"R2 işlem hatası: {str(e)}"
            logger.error(f"❌ {error_msg}")
            
            # Hata durumunda temp dosyaları temizle
            self._cleanup_temp_files()
            
            return {
                "success": False,
                "error": error_msg,
                "special_folder_code": special_folder_code
            }


def handler(job):
    """
    RunPod serverless handler fonksiyonu - R2 entegrasyonlu
    
    Expected input format:
    {
        "input": {
            "SpecialFolderCode": "20250814021530AB12CD"
        }
    }
    """
    try:
        job_input = job["input"]
        
        # Input validation
        if not job_input.get("SpecialFolderCode"):
            return {"error": "SpecialFolderCode parametresi gerekli"}
        
        special_folder_code = job_input["SpecialFolderCode"]
        
        logger.info(f"🎯 R2 Handler başlatıldı: {special_folder_code}")
        
        # SilenceProcessorR2'ı başlat
        processor = SilenceProcessorR2()
        
        # R2'den ses dosyasını analiz et
        result = processor.process_special_folder(special_folder_code)
        
        if result["success"]:
            # Başarılı sonucu döndür
            return {
                "success": True,
                "special_folder_code": result["special_folder_code"],
                "filename": result["filename"],
                "r2_path": result["r2_path"],
                "duration_seconds": result["meta_info"]["duration_seconds"],
                "duration_minutes": result["meta_info"]["duration_minutes"],
                "audio_details": {
                    "frame_rate": result["meta_info"]["sample_rate_hz"],
                    "channels": result["meta_info"]["channels"],
                    "file_size_mb": result["meta_info"]["file_size_mb"]
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
        error_msg = f"R2 Handler hatası: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return {"error": error_msg}


# RunPod serverless'i başlat
if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})