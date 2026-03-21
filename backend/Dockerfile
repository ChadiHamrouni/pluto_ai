FROM python:3.11-slim

# Install Node.js (for marp-cli) + Chromium (required by marp for PDF export) + sox (required by qwen-tts)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl chromium git sox libsox-fmt-all && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g @marp-team/marp-cli && \
    apt-get purge -y curl && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

ENV CHROME_PATH=/usr/bin/chromium

WORKDIR /app

# Install Python deps (separate layer for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download Docling layout models so first PDF conversion is instant at runtime
RUN python -c "\
from docling.document_converter import DocumentConverter; \
DocumentConverter(); \
print('Docling models cached.')"

# TTS model download — disabled for now, handle manually
# ARG TTS_MODEL=Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice
# ENV HF_HOME=/app/model_cache
# RUN huggingface-cli download ${TTS_MODEL} && echo "TTS weights downloaded."

# Copy source
COPY . .

# Create runtime data dirs
RUN mkdir -p data/notes data/slides data/embeddings data/files data/memory

ENV OPENAI_AGENTS_DISABLE_TRACING=1

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]