from __future__ import annotations

from typing import List

import numpy as np
from agents import function_tool

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from helpers.tools import knowledge_base as kb
from models.knowledge_base import KnowledgeChunk

logger = get_logger(__name__)


@function_tool
def search_knowledge(query: str) -> str:
    """Search the user's personal knowledge base for information relevant to a query.
    Use this when the user asks about documents, files, papers, or notes they have
    previously added to their knowledge base (e.g. 'what did that paper say about X',
    'find in my documents', 'what's in my knowledge base about Y').
    Do NOT use this for general questions — only for the user's own ingested files."""
    cfg = load_config()
    top_k = cfg["rag"].get("top_k", 5)

    results: list[KnowledgeChunk] = kb.search_knowledge(query, top_k=top_k)

    if not results:
        return "No relevant results found in the knowledge base for this query."

    lines = [f"Found {len(results)} relevant passage(s) from the knowledge base:\n"]
    for chunk in results:
        lines.append(
            f"[source: {chunk.source}, chunk {chunk.chunk_index}, "
            f"relevance: {chunk.rrf_score:.4f}]\n{chunk.content.strip()}\n"
        )

    return "\n".join(lines)


def chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Split text into overlapping character-bounded chunks on word boundaries.

    Used during knowledge base ingestion to break large documents into
    embeddable segments.

    Args:
        text:       The raw text to split. Returns an empty list if blank.
        chunk_size: Target maximum character length per chunk.
        overlap:    Number of characters to re-include from the end of the previous chunk.

    Returns:
        List of non-empty chunk strings.
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
            if (
                current_chars + len(word) + (1 if current_words else 0) > chunk_size
                and current_words
            ):
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
    """Cosine similarity between two L2-normalised embedding vectors. Returns a float in [-1, 1]."""
    a = np.array(vec1, dtype=np.float32)
    b = np.array(vec2, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
