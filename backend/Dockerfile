FROM python:3.11-slim

# Install Node.js (for marp-cli) + Chromium (required by marp for PDF export)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl chromium git && \
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

# Clone CosyVoice2 (no setup.py — must be on PYTHONPATH) and install its deps
# openai-whisper==20231117 has a legacy setup.py that calls pkg_resources at build time.
# pip's isolated build env gets its own fresh setuptools that lacks pkg_resources in new versions.
# Workaround: pre-install all of whisper's build/runtime deps, then install with --no-build-isolation
# so pip reuses the system environment (which has pkg_resources via setuptools).
RUN git clone --depth=1 https://github.com/FunAudioLLM/CosyVoice.git /opt/CosyVoice && \
    pip install --no-cache-dir setuptools==67.8.0 wheel && \
    pip install --no-cache-dir \
        triton numpy torch tqdm more-itertools tiktoken \
        numba ffmpeg-python && \
    pip install --no-cache-dir --no-build-isolation openai-whisper==20231117 && \
    pip install --no-cache-dir --upgrade setuptools wheel && \
    pip install --no-cache-dir -r /opt/CosyVoice/requirements.txt
ENV PYTHONPATH=/opt/CosyVoice:${PYTHONPATH}

# Pre-download Docling layout models so first PDF conversion is instant at runtime
RUN python -c "\
from docling.document_converter import DocumentConverter; \
DocumentConverter(); \
print('Docling models cached.')"

# Pre-download TTS model into the image layer so it's available offline at runtime
ARG TTS_MODEL=FunAudioLLM/CosyVoice2-0.5B
ENV HF_HOME=/app/model_cache
RUN python -c "\
from cosyvoice.cli.cosyvoice import CosyVoice2; \
CosyVoice2('${TTS_MODEL}', load_jit=False, load_trt=False); \
print('TTS model cached.')"

# Copy source
COPY . .

# Create runtime data dirs
RUN mkdir -p data/notes data/slides data/embeddings data/files data/memory

ENV OPENAI_AGENTS_DISABLE_TRACING=1

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]