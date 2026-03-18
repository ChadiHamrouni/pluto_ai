FROM python:3.11-slim

# Install Node.js (for marp-cli)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g @marp-team/marp-cli && \
    apt-get purge -y curl && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps (separate layer for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download embedding model weights at build time so the container
# starts without needing internet access and with no cold-start delay.
ARG EMBEDDING_MODEL=nomic-ai/nomic-embed-multimodal-3b
RUN python -c "\
from colpali_engine.models import ColQwen2_5, ColQwen2_5_Processor; \
ColQwen2_5_Processor.from_pretrained('${EMBEDDING_MODEL}'); \
ColQwen2_5.from_pretrained('${EMBEDDING_MODEL}'); \
print('Embedding model cached.')"

# Copy source
COPY . .

# Create runtime data dirs
RUN mkdir -p data/notes data/slides data/embeddings data/files

ENV OPENAI_AGENTS_DISABLE_TRACING=1

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
