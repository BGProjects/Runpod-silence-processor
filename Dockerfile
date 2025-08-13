FROM python:3.11-slim

# Çalışma dizinini ayarla
WORKDIR /

# System packages (audio processing için gerekli)
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Python requirements'ı kopyala ve yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Handler kodunu kopyala
COPY silence_serverless.py .

# Container başlatıldığında çalışacak komut
CMD ["python", "-u", "silence_serverless.py"]