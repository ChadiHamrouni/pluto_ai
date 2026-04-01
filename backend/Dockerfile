FROM python:3.11-slim

# Install Node.js (for marp-cli) + Chromium (required by marp for PDF export) + sox (required by qwen-tts)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl chromium git sox libsox-fmt-all && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g @marp-team/marp-cli @mermaid-js/mermaid-cli && \
    apt-get purge -y curl && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

ENV CHROME_PATH=/usr/bin/chromium
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV CHROMIUM_FLAGS="--no-sandbox --disable-setuid-sandbox"

WORKDIR /app

# Install Python deps (separate layer for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# TTS model download — disabled for now, handle manually
# ARG TTS_MODEL=Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice
# ENV HF_HOME=/app/model_cache
# RUN huggingface-cli download ${TTS_MODEL} && echo "TTS weights downloaded."

# Copy source
COPY . .

# Create runtime data dirs
RUN mkdir -p data/notes data/slides data/diagrams data/embeddings data/files data/memory

ENV OPENAI_AGENTS_DISABLE_TRACING=1

# Run as non-root (Chromium/Puppeteer refuse --no-sandbox as root)
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]