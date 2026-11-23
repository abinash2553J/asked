FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (curl for health check, ffmpeg for yt-dlp if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default port 12000, can be overridden by $PORT in PaaS platforms
ENV PORT=12000
EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
