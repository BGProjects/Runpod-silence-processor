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
    
    def _create_silence_json(self, silence_segments, special_folder_code):
        """
        silence.json dosyasını oluşturur (sessizlik noktaları)
        
        Args:
            silence_segments (list): Sessizlik segmentleri
            special_folder_code (str): Klasör kodu
        """
        try:
            silence_json_path = os.path.join(self.volume_path, "uploads", special_folder_code, "silence.json")
            
            silence_data = {
                "silences": silence_segments,
                "total_segments": len(silence_segments),
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                "analysis_version": "1.0"
            }
            
            with open(silence_json_path, 'w', encoding='utf-8') as f:
                json.dump(silence_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ silence.json oluşturuldu: {len(silence_segments)} sessizlik segmenti")
            return silence_data
            
        except Exception as e:
            logger.error(f"❌ silence.json oluşturma hatası: {str(e)}")
            raise

    def _calculate_intelligent_split_plan(self, total_duration_minutes, silence_segments, special_folder_code):
        """
        Akıllı parçalama planı oluşturur ve parts.json kaydeder (silence7/8 stratejisi)
        
        Args:
            total_duration_minutes (float): Toplam ses süresi (dakika)
            silence_segments (list): Sessizlik segmentleri
            special_folder_code (str): Klasör kodu
            
        Returns:
            dict: Parçalama planı
        """
        try:
            logger.info(f"🤖 Akıllı parçalama planı hesaplanıyor: {total_duration_minutes:.2f} dakika")
            
            # Hedef parça süresi: 5 dakika (test için düşürüldü)
            target_segment_minutes = 5
            
            # Parça sayısını hesapla
            if total_duration_minutes <= 20:
                # 20 dakika ve altı: bölme
                num_pieces = 1
                logger.info(f"📝 {total_duration_minutes:.1f} dakika ≤ 20dk → Bölme gerek yok")
            else:
                # 20 dakikadan fazla: 15'er dakikalık parçalara böl
                num_pieces = max(2, round(total_duration_minutes / target_segment_minutes))
                logger.info(f"📝 {total_duration_minutes:.1f} dakika > 20dk → {num_pieces} parçaya böl")
            
            if num_pieces == 1:
                # Tek parça - parts.json yine de oluştur
                single_piece_plan = {
                    "split_needed": False,
                    "total_duration_minutes": total_duration_minutes,
                    "target_segment_minutes": target_segment_minutes,
                    "recommended_pieces": 1,
                    "pieces": [
                        {
                            "piece_index": 1,
                            "start_ms": 0,
                            "end_ms": int(total_duration_minutes * 60 * 1000),
                            "start_formatted": "00:00:00.000",
                            "end_formatted": self._seconds_to_timestamp(total_duration_minutes * 60),
                            "duration_ms": int(total_duration_minutes * 60 * 1000),
                            "duration_minutes": total_duration_minutes,
                            "trim_leading_ms": 0
                        }
                    ],
                    "split_points": [],
                    "message": f"Ses dosyası {total_duration_minutes:.1f} dakika - bölme gerek yok"
                }
                
                # parts.json kaydet
                self._create_parts_json(single_piece_plan, special_folder_code)
                return single_piece_plan
            
            # Hedef bölme noktalarını hesapla (dakika cinsinden)
            target_minutes = []
            for i in range(1, num_pieces):
                target = (total_duration_minutes / num_pieces) * i
                target_minutes.append(target)
            
            logger.info(f"🎯 Hedef bölme noktaları: {[f'{t:.1f}dk' for t in target_minutes]}")
            
            # Her hedef noktaya en yakın sessizliği bul
            selected_silences = []
            
            for target_min in target_minutes:
                target_seconds = target_min * 60
                
                # En yakın sessizliği bul
                best_silence = None
                best_distance = float('inf')
                
                for silence in silence_segments:
                    # Sessizliğin ortası
                    silence_middle_ms = (silence['start_ms'] + silence['end_ms']) / 2
                    silence_middle_seconds = silence_middle_ms / 1000
                    
                    distance = abs(silence_middle_seconds - target_seconds)
                    
                    if distance < best_distance:
                        best_distance = distance
                        best_silence = silence
                
                if best_silence:
                    selected_silences.append([best_silence['start_ms'], best_silence['end_ms']])
                    logger.info(f"✅ Hedef {target_min:.1f}dk → Sessizlik #{best_silence['index']}")
                else:
                    logger.warning(f"⚠️  Hedef {target_min:.1f}dk için uygun sessizlik bulunamadı")
            
            # Silence7/8 stratejisi ile parçaları oluştur
            pieces = self._make_piece_plan_silence7_strategy(selected_silences, int(total_duration_minutes * 60 * 1000))
            
            logger.info(f"🎉 Silence7 stratejisi ile {len(pieces)} parça oluşturuldu")
            
            split_plan = {
                "split_needed": True,
                "total_duration_minutes": total_duration_minutes,
                "target_segment_minutes": target_segment_minutes,
                "recommended_pieces": num_pieces,
                "selected_silences": selected_silences,
                "pieces": pieces,
                "strategy": "silence7_overlapping_segments",
                "message": f"Ses dosyası {num_pieces} parçaya bölünecek (Silence7 stratejisi, {target_segment_minutes}dk hedefi)"
            }
            
            # parts.json kaydet
            self._create_parts_json(split_plan, special_folder_code)
            return split_plan
            
        except Exception as e:
            logger.error(f"❌ Parçalama planı hatası: {str(e)}")
            raise
    
    def _make_piece_plan_silence7_strategy(self, silences_ms, total_ms):
        """
        Silence7/8 stratejisi ile parça planı oluşturur
        
        Args:
            silences_ms (list): Seçilen sessizlik segmentleri [[start_ms, end_ms], ...]
            total_ms (int): Toplam ses süresi (ms)
            
        Returns:
            list: Parça planı
        """
        pieces = []
        
        if not silences_ms:
            pieces.append({
                "piece_index": 1,
                "start_ms": 0,
                "end_ms": total_ms,
                "start_formatted": self._ms_to_timestamp(0),
                "end_formatted": self._ms_to_timestamp(total_ms),
                "duration_ms": total_ms,
                "duration_minutes": round(total_ms / 60000, 2),
                "trim_leading_ms": 0
            })
            return pieces
        
        # P1 = [0, b1] (ilk sessizliğin bitişine kadar)
        a1, b1 = silences_ms[0]
        pieces.append({
            "piece_index": 1,
            "start_ms": 0,
            "end_ms": b1,
            "start_formatted": self._ms_to_timestamp(0),
            "end_formatted": self._ms_to_timestamp(b1),
            "duration_ms": b1,
            "duration_minutes": round(b1 / 60000, 2),
            "trim_leading_ms": 0
        })
        
        # Pi = [a_{i-1}, b_i] (i>=2) (önceki sessizliğin başından, şu anki sessizliğin bitişine)
        for i in range(1, len(silences_ms)):
            a_prev, b_prev = silences_ms[i-1]
            a_i, b_i = silences_ms[i]
            
            pieces.append({
                "piece_index": i + 1,
                "start_ms": a_prev,
                "end_ms": b_i,
                "start_formatted": self._ms_to_timestamp(a_prev),
                "end_formatted": self._ms_to_timestamp(b_i),
                "duration_ms": b_i - a_prev,
                "duration_minutes": round((b_i - a_prev) / 60000, 2),
                "trim_leading_ms": max(0, b_prev - a_prev)
            })
        
        # P(n+1) = [a_n, total_ms] (son sessizliğin başından dosya sonuna)
        a_last, b_last = silences_ms[-1]
        pieces.append({
            "piece_index": len(silences_ms) + 1,
            "start_ms": a_last,
            "end_ms": total_ms,
            "start_formatted": self._ms_to_timestamp(a_last),
            "end_formatted": self._ms_to_timestamp(total_ms),
            "duration_ms": total_ms - a_last,
            "duration_minutes": round((total_ms - a_last) / 60000, 2),
            "trim_leading_ms": max(0, b_last - a_last)
        })
        
        return pieces
    
    def _create_parts_json(self, split_plan, special_folder_code):
        """
        parts.json dosyasını oluşturur
        
        Args:
            split_plan (dict): Parçalama planı
            special_folder_code (str): Klasör kodu
        """
        try:
            parts_json_path = os.path.join(self.volume_path, "uploads", special_folder_code, "parts.json")
            
            parts_data = {
                "split_plan": split_plan,
                "total_pieces": len(split_plan["pieces"]),
                "strategy": split_plan.get("strategy", "intelligent_splitting"),
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                "analysis_version": "1.0"
            }
            
            with open(parts_json_path, 'w', encoding='utf-8') as f:
                json.dump(parts_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ parts.json oluşturuldu: {len(split_plan['pieces'])} parça planı")
            return parts_data
            
        except Exception as e:
            logger.error(f"❌ parts.json oluşturma hatası: {str(e)}")
            raise
    
    def _ms_to_timestamp(self, ms):
        """Milisaniyeyi HH:MM:SS.mmm formatına çevirir"""
        seconds = ms / 1000
        return self._seconds_to_timestamp(seconds)
    
    def _seconds_to_timestamp(self, seconds):
        """Saniyeyi HH:MM:SS.mmm formatına çevirir"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
    
    def _split_audio_from_parts_json(self, special_folder_code):
        """
        parts.json dosyasına göre ses dosyasını parçalara ayırır
        
        Args:
            special_folder_code (str): Klasör kodu
            
        Returns:
            dict: Parçalama sonucu
        """
        try:
            logger.info(f"🔪 Inline parçalama başlatılıyor: {special_folder_code}")
            
            # Import torch/torchaudio here for splitting
            try:
                import torch
                import torchaudio
                import torchaudio.functional as F
            except ImportError:
                return {
                    "success": False,
                    "error": "torch/torchaudio bulunamadı - parçalama devre dışı",
                    "special_folder_code": special_folder_code
                }
            
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
            target_sr = 48000
            if orig_sr != target_sr:
                logger.info(f"🔄 Yeniden örnekleme: {orig_sr}Hz → {target_sr}Hz")
                audio = F.resample(audio, orig_freq=orig_sr, new_freq=target_sr)
            
            # 6. Her parçayı kes ve kaydet
            split_results = []
            
            for piece in pieces:
                piece_index = piece["piece_index"]
                start_ms = piece["start_ms"]
                end_ms = piece["end_ms"]
                trim_leading_ms = piece.get("trim_leading_ms", 0)
                
                # Millisecond'yi sample'a çevir
                start_sample = int((start_ms / 1000.0) * target_sr)
                end_sample = int((end_ms / 1000.0) * target_sr)
                
                # Trim uygula (Silence7 örtüşme stratejisi)
                if trim_leading_ms > 0:
                    trim_samples = int((trim_leading_ms / 1000.0) * target_sr)
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
                    target_sr,
                    encoding="PCM_S",
                    bits_per_sample=16
                )
                
                # Kayıt bilgilerini al
                piece_size = os.path.getsize(piece_path)
                piece_duration = piece_audio.shape[1] / target_sr
                
                split_results.append({
                    "piece_index": piece_index,
                    "filename": piece_filename,
                    "file_path": f"uploads/{special_folder_code}/Parts/{piece_filename}",
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "actual_start_ms": int(start_sample / target_sr * 1000),
                    "actual_end_ms": int(end_sample / target_sr * 1000),
                    "trim_leading_ms": trim_leading_ms,
                    "duration_seconds": round(piece_duration, 2),
                    "file_size_bytes": piece_size,
                    "file_size_mb": round(piece_size / (1024 * 1024), 2),
                    "sample_rate": target_sr,
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
                    "sample_rate": target_sr,
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
            
            logger.info(f"🎉 Inline parçalama tamamlandı: {total_pieces} parça, {total_duration:.1f}s, {total_size_mb:.1f}MB")
            return result
            
        except Exception as e:
            error_msg = f"Parçalama hatası: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "special_folder_code": special_folder_code
            }
    
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
    
    def process_special_folder(self, special_folder_code, split_audio=False):
        """
        SpecialFolderCode'a göre ses dosyasını analiz eder ve isteğe bağlı parçalar
        
        Args:
            special_folder_code (str): Klasör kodu (örn: test_20250813_084422)
            split_audio (bool): True ise parçalara ayır, False ise sadece analiz
            
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
            
            # 9. silence.json oluştur
            silence_json_data = self._create_silence_json(silence_analysis["silences"], special_folder_code)
            
            # 10. Akıllı parçalama planı oluştur ve parts.json kaydet
            split_plan = self._calculate_intelligent_split_plan(
                audio_info["duration_minutes"], 
                silence_analysis["silences"],
                special_folder_code
            )
            
            # 12. İsteğe bağlı parçalama işlemi
            split_result = None
            if split_audio:
                logger.info("🔪 Parçalama işlemi başlatılıyor...")
                split_result = self._split_audio_from_parts_json(special_folder_code)
            
            # 13. Sonucu döndür
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
                "silence_json_created": True,
                "split_plan": split_plan,
                "parts_json_created": True,
                "split_audio": split_audio,
                "split_result": split_result,
                "message": f"Ses dosyası, meta bilgileri, sessizlik analizi, JSON dosyaları{', parçalama' if split_audio else ''} ve Silence7 planı tamamlandı: {islenmemis_filename}"
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
        split_audio = job_input.get("split_audio", False)  # Yeni parametre
        
        logger.info(f"🎯 Handler başlatıldı: {special_folder_code}")
        
        # SilenceProcessor'ı başlat
        processor = SilenceProcessor()
        
        # Ses dosyasını analiz et
        result = processor.process_special_folder(special_folder_code, split_audio)
        
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
                "split_plan": result["split_plan"],
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