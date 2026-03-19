from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Union

import numpy as np

from helpers.core.logger import get_logger
from helpers.tools.embedder import embed

logger = get_logger(__name__)


def chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """
    Split *text* into overlapping chunks of ~*chunk_size* characters with
    *overlap* characters of overlap between consecutive chunks.

    Splitting is done on whitespace boundaries to avoid cutting words.
    """
    if not text:
        return []

    words = text.split()
    chunks: List[str] = []
    start = 0

    while start < len(words):
        current_words: List[str] = []
        current_chars = 0

        for i in range(start, len(words)):
            word = words[i]
            if current_chars + len(word) + (1 if current_words else 0) > chunk_size and current_words:
                break
            current_words.append(word)
            current_chars += len(word) + (1 if len(current_words) > 1 else 0)

        chunk = " ".join(current_words)
        chunks.append(chunk)

        advance_chars = max(chunk_size - overlap, 1)
        consumed = 0
        step = 0
        for w in current_words:
            consumed += len(w) + (1 if step > 0 else 0)
            step += 1
            if consumed >= advance_chars:
                break

        start += max(step, 1)

    return [c for c in chunks if c.strip()]


def compute_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Cosine similarity between two L2-normalised embedding vectors.
    Returns a float in [-1, 1].
    """
    a = np.array(vec1, dtype=np.float32)
    b = np.array(vec2, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def store_embedding(
    entry_id: int,
    content: Union[str, Path],
    embeddings_path: str,
) -> None:
    """
    Embed *content* (text, image path, or PIL Image) and persist the vector
    as a NumPy ``.npy`` file with a JSON sidecar for debugging.
    """
    os.makedirs(embeddings_path, exist_ok=True)

    vector = embed(content)

    npy_path = os.path.join(embeddings_path, f"{entry_id}.npy")
    meta_path = os.path.join(embeddings_path, f"{entry_id}.json")

    np.save(npy_path, np.array(vector, dtype=np.float32))

    preview = str(content)[:200]
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"entry_id": entry_id, "preview": preview}, f)

    logger.debug("Stored embedding for entry %d at %s", entry_id, npy_path)


def search_embeddings(
    query: Union[str, Path],
    top_k: int,
    embeddings_path: str,
    similarity_threshold: float,
) -> List[int]:
    """
    Search all stored embeddings for entries most similar to *query*.

    *query* can be text, an image path, or a PIL Image — anything the
    embedder understands.

    Returns up to *top_k* entry IDs whose similarity exceeds
    *similarity_threshold*, sorted by descending similarity.
    """
    if not os.path.isdir(embeddings_path):
        logger.warning("Embeddings directory does not exist: %s", embeddings_path)
        return []

    query_vec = embed(query)
    scores: List[tuple[float, int]] = []

    for filename in os.listdir(embeddings_path):
        if not filename.endswith(".npy"):
            continue
        try:
            entry_id = int(filename[:-4])
        except ValueError:
            continue

        stored_vec = np.load(os.path.join(embeddings_path, filename)).tolist()
        sim = compute_similarity(query_vec, stored_vec)

        if sim >= similarity_threshold:
            scores.append((sim, entry_id))

    scores.sort(key=lambda x: x[0], reverse=True)
    return [entry_id for _, entry_id in scores[:top_k]]
