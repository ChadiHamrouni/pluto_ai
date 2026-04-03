from __future__ import annotations

from agents import function_tool

from helpers.core.config_loader import load_config
from helpers.core.knowledge_base import search_knowledge as _search_knowledge
from helpers.core.logger import get_logger
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

    results: list[KnowledgeChunk] = _search_knowledge(query, top_k=top_k)

    if not results:
        return "No relevant results found in the knowledge base for this query."

    lines = [f"Found {len(results)} relevant passage(s) from the knowledge base:\n"]
    for chunk in results:
        lines.append(
            f"[source: {chunk.source}, chunk {chunk.chunk_index}, "
            f"relevance: {chunk.rrf_score:.4f}]\n{chunk.content.strip()}\n"
        )

    return "\n".join(lines)
