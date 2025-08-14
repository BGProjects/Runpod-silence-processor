#!/usr/bin/env python3
"""
Test script for R2 integration with RunPod serverless
"""
import os
import json
from silence_serverless_r2 import SilenceProcessorR2

def test_r2_connection():
    """Test R2 connection and basic operations"""
    print("🧪 R2 Bağlantı Testi Başlıyor...")
    
    # Environment variables kontrolü
    required_vars = [
        'R2_ACCESS_KEY_ID',
        'R2_SECRET_ACCESS_KEY', 
        'R2_ENDPOINT_URL',
        'R2_BUCKET_NAME'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Eksik environment variables: {missing_vars}")
        print("💡 .env.example dosyasını kontrol edin")
        return False
    
    try:
        # Processor'ı başlat
        processor = SilenceProcessorR2()
        
        # R2 bucket listesi kontrolü
        response = processor.r2_client.list_objects_v2(
            Bucket=processor.r2_bucket,
            Prefix='audio/',
            MaxKeys=5
        )
        
        if 'Contents' in response:
            print(f"✅ R2 bağlantı başarılı!")
            print(f"📁 Bucket: {processor.r2_bucket}")
            print(f"📄 Bulunan dosyalar: {len(response['Contents'])}")
            
            for obj in response['Contents'][:3]:
                print(f"   • {obj['Key']} ({obj['Size']} bytes)")
                
            return True
        else:
            print("⚠️ R2 bağlantı başarılı ama dosya bulunamadı")
            return True
            
    except Exception as e:
        print(f"❌ R2 bağlantı hatası: {e}")
        return False

def test_mock_processing():
    """Test mock data ile processing"""
    print("\n🧪 Mock İşleme Testi...")
    
    # Mock input - using actual folder from R2
    mock_input = {
        "input": {
            "special_folder_code": "202508140826338KQKA0"  # Real folder from R2
        }
    }
    
    try:
        from silence_serverless_r2 import handler
        
        print(f"📤 Test ediliyor: {mock_input['input']['special_folder_code']}")
        result = handler(mock_input)
        
        if result.get("success"):
            print("✅ Mock işleme başarılı!")
            print(f"📄 Dosya: {result.get('filename')}")
            print(f"⏱️ Süre: {result.get('duration_seconds')}s")
            print(f"🔇 Sessizlik: %{result.get('silence_analysis', {}).get('silence_percentage', 0)}")
        else:
            print(f"❌ Mock işleme hatası: {result.get('error')}")
            
        return result.get("success", False)
        
    except Exception as e:
        print(f"❌ Mock test hatası: {e}")
        return False

def main():
    """Ana test fonksiyonu"""
    print("🚀 R2 Entegrasyon Test Süreci")
    print("=" * 50)
    
    # Environment variables ayarlama örneği
    if not os.getenv('R2_ACCESS_KEY_ID'):
        print("💡 Environment variables ayarlanmamış, .env.example'dan ayarlayın:")
        print("   export R2_ACCESS_KEY_ID=your_access_key")
        print("   export R2_SECRET_ACCESS_KEY=your_secret")
        print("   export R2_ENDPOINT_URL=your_endpoint")
        print("   export R2_BUCKET_NAME=cleanvoice-audio")
        print()
    
    # Test 1: R2 bağlantısı
    step1 = test_r2_connection()
    
    if step1:
        # Test 2: Mock processing (sadece R2 bağlantısı başarılıysa)
        step2 = test_mock_processing()
        
        if step1 and step2:
            print("\n🎉 Tüm testler başarılı! RunPod'a deploy etmeye hazır.")
        else:
            print("\n⚠️ Bazı testler başarısız. Lütfen hataları düzeltin.")
    else:
        print("\n❌ R2 bağlantısı başarısız. Environment variables kontrol edin.")

if __name__ == "__main__":
    main()