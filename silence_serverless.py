import runpod
import json
import os
import wave
import logging
import numpy as np
import struct

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
    
    def _detect_silence_segments(self, file_path, silence_threshold=0.01, min_silence_duration=0.5):
        """
        Ses dosyasındaki sessizlik bölümlerini tespit eder
        
        Args:
            file_path (str): Volume'daki ses dosyası yolu
            silence_threshold (float): Sessizlik eşiği (0-1 arası, varsayılan: 0.01)
            min_silence_duration (float): Minimum sessizlik süresi (saniye, varsayılan: 0.5)
            
        Returns:
            dict: Sessizlik analizi sonuçları
        """
        try:
            full_path = os.path.join(self.volume_path, file_path)
            logger.info(f"🔍 Sessizlik analizi başlıyor: {full_path}")
            
            if not os.path.exists(full_path):
                raise FileNotFoundError(f"Ses dosyası bulunamadı: {full_path}")
            
            silence_segments = []
            
            with wave.open(full_path, 'r') as audio_file:
                frame_rate = audio_file.getframerate()
                n_frames = audio_file.getnframes()
                duration = n_frames / float(frame_rate)
                channels = audio_file.getnchannels()
                sample_width = audio_file.getsampwidth()
                
                # Ses verisini oku
                raw_audio = audio_file.readframes(n_frames)
                
            # Raw audio verisini numpy array'e dönüştür
            if sample_width == 1:
                # 8-bit unsigned
                audio_data = np.frombuffer(raw_audio, dtype=np.uint8).astype(np.float32)
                audio_data = (audio_data - 128) / 128.0  # -1 ile 1 arasına normalize et
            elif sample_width == 2:
                # 16-bit signed
                audio_data = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32)
                audio_data = audio_data / 32768.0  # -1 ile 1 arasına normalize et
            elif sample_width == 3:
                # 24-bit signed (daha kompleks)
                audio_bytes = np.frombuffer(raw_audio, dtype=np.uint8)
                # 24-bit'i 32-bit'e dönüştür
                audio_24bit = []
                for i in range(0, len(audio_bytes), 3):
                    if i + 2 < len(audio_bytes):
                        # Little-endian 24-bit'i oku
                        sample = audio_bytes[i] | (audio_bytes[i+1] << 8) | (audio_bytes[i+2] << 16)
                        # Sign extension
                        if sample & 0x800000:
                            sample |= 0xFF000000
                        audio_24bit.append(sample)
                audio_data = np.array(audio_24bit, dtype=np.float32) / (2**23)
            elif sample_width == 4:
                # 32-bit signed
                audio_data = np.frombuffer(raw_audio, dtype=np.int32).astype(np.float32)
                audio_data = audio_data / (2**31)
            else:
                raise ValueError(f"Desteklenmeyen sample width: {sample_width}")
            
            # Multi-channel ise ortalama al
            if channels > 1:
                audio_data = audio_data.reshape(-1, channels)
                audio_data = np.mean(audio_data, axis=1)
            
            # Mutlak değer al (amplitüd)
            audio_amplitude = np.abs(audio_data)
            
            # Sessizlik tespiti
            min_silence_samples = int(min_silence_duration * frame_rate)
            silence_mask = audio_amplitude < silence_threshold
            
            # Ardışık sessizlik bölümlerini bul
            in_silence = False
            silence_start = 0
            total_silence_duration = 0
            
            for i in range(len(silence_mask)):
                if silence_mask[i] and not in_silence:
                    # Sessizlik başlıyor
                    silence_start = i
                    in_silence = True
                elif not silence_mask[i] and in_silence:
                    # Sessizlik bitiyor
                    silence_length = i - silence_start
                    if silence_length >= min_silence_samples:
                        start_time = silence_start / frame_rate
                        end_time = i / frame_rate
                        duration = end_time - start_time
                        
                        silence_segments.append({
                            "start_time": round(start_time, 3),
                            "end_time": round(end_time, 3),
                            "duration": round(duration, 3)
                        })
                        total_silence_duration += duration
                    
                    in_silence = False
            
            # Son segment kontrol et
            if in_silence:
                silence_length = len(silence_mask) - silence_start
                if silence_length >= min_silence_samples:
                    start_time = silence_start / frame_rate
                    end_time = duration
                    segment_duration = end_time - start_time
                    
                    silence_segments.append({
                        "start_time": round(start_time, 3),
                        "end_time": round(end_time, 3),
                        "duration": round(segment_duration, 3)
                    })
                    total_silence_duration += segment_duration
            
            # İstatistikler
            silence_percentage = (total_silence_duration / duration) * 100 if duration > 0 else 0
            speech_duration = duration - total_silence_duration
            
            logger.info(f"🔍 Sessizlik analizi tamamlandı: {len(silence_segments)} segment, %{silence_percentage:.1f} sessizlik")
            
            return {
                "silence_segments": silence_segments,
                "total_silence_duration": round(total_silence_duration, 2),
                "speech_duration": round(speech_duration, 2),
                "silence_percentage": round(silence_percentage, 1),
                "speech_percentage": round(100 - silence_percentage, 1),
                "segment_count": len(silence_segments),
                "settings": {
                    "silence_threshold": silence_threshold,
                    "min_silence_duration": min_silence_duration
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Sessizlik analizi hatası: {str(e)}")
            raise
    
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
            
            # 1. talimatname.json dosyasının yolunu oluştur
            talimat_path = f"uploads/{special_folder_code}/talimatname.json"
            
            # 2. JSON dosyasını oku
            talimat_data = self._read_json_from_volume(talimat_path)
            
            # 3. IslenmemisFileName değerini al
            if 'IslenmemisFileName' not in talimat_data:
                raise ValueError("talimatname.json'da 'IslenmemisFileName' anahtarı bulunamadı")
            
            islenmemis_filename = talimat_data['IslenmemisFileName']
            logger.info(f"📂 Analiz edilecek dosya: {islenmemis_filename}")
            
            # 4. Asıl dosyanın yolunu oluştur
            audio_file_path = f"uploads/{special_folder_code}/{islenmemis_filename}"
            
            # 5. Ses dosyasını analiz et
            audio_info = self._get_audio_duration(audio_file_path)
            
            # 6. Sessizlik analizi yap
            silence_analysis = self._detect_silence_segments(audio_file_path)
            
            # 7. Sonucu döndür
            result = {
                "success": True,
                "special_folder_code": special_folder_code,
                "filename": islenmemis_filename,
                "file_path": audio_file_path,
                "volume_path": f"{self.volume_path}/{audio_file_path}",
                "talimat_data": talimat_data,
                "audio_info": audio_info,
                "silence_analysis": silence_analysis,
                "message": f"Ses dosyası ve sessizlik analizi tamamlandı: {islenmemis_filename}"
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
                    "total_silence_duration": result["silence_analysis"]["total_silence_duration"],
                    "speech_duration": result["silence_analysis"]["speech_duration"],
                    "silence_percentage": result["silence_analysis"]["silence_percentage"],
                    "speech_percentage": result["silence_analysis"]["speech_percentage"],
                    "segment_count": result["silence_analysis"]["segment_count"],
                    "silence_segments": result["silence_analysis"]["silence_segments"]
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