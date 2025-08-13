import runpod
import json
import os
import wave
import logging

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
            
            # 6. Sonucu döndür
            result = {
                "success": True,
                "special_folder_code": special_folder_code,
                "filename": islenmemis_filename,
                "file_path": audio_file_path,
                "volume_path": f"{self.volume_path}/{audio_file_path}",
                "talimat_data": talimat_data,
                "audio_info": audio_info,
                "message": f"Ses dosyası başarıyla analiz edildi: {islenmemis_filename}"
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