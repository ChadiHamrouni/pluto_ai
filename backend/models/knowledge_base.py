from __future__ import annotations

from pydantic import BaseModel, Field


class KnowledgeChunk(BaseModel):
    """A single retrieved chunk from the knowledge base."""

    content: str
    source: str
    chunk_index: int
    semantic_score: float = Field(default=0.0, description="Cosine similarity from ChromaDB")
    bm25_score: float = Field(default=0.0, description="Normalised BM25 score")
    rrf_score: float = Field(default=0.0, description="Reciprocal Rank Fusion combined score")
