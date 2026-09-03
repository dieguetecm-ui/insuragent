"""Recuperación aumentada sobre las condiciones generales (PRD §4.2)."""

from insuragent.rag.embeddings import get_embedder
from insuragent.rag.index import ClauseIndex

__all__ = ["ClauseIndex", "get_embedder"]
