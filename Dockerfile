FROM python:3.9-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    aria2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
RUN mkdir -p downloads

CMD gunicorn app:app & python3 main.py
