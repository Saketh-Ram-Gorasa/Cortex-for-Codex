"""
Vector Database Service — handles connections to:
  1. LLM (GitHub Models or Azure OpenAI) for embeddings
  2. ChromaDB (vector storage & semantic search)

Supports per-user namespaced collections for multi-tenant isolation.
"""

from __future__ import annotations

import logging
import json
from typing import Any

import chromadb

from config import settings
from services.llm_client import create_llm_client, get_embedding_model
from services.rate_limiter import rate_limited_call

logger = logging.getLogger("secondcortex.vectordb")


class VectorDBService:
    """Manages LLM embeddings and ChromaDB operations with per-user isolation."""

    def __init__(self) -> None:
        self.openai_client = create_llm_client()

        # Initialize ChromaDB client with configurable persistent path
        try:
            db_path = settings.chroma_db_path
            self.chroma_client = chromadb.PersistentClient(path=db_path)
            logger.info("ChromaDB initialized at: %s", db_path)
        except Exception as exc:
            logger.error("ChromaDB initialization failed: %s", exc)
            self.chroma_client = None

    # ── Per-User Collection ────────────────────────────────────

    def _get_collection(self, user_id: str | None = None):
        """Get or create a ChromaDB collection namespaced to the user."""
        if self.chroma_client is None:
            return None

        collection_name = f"snapshots-{user_id}" if user_id else "secondcortex-snapshots"
        # ChromaDB collection names must be 3-63 chars, alphanumeric + hyphens
        collection_name = collection_name[:63]

        try:
            return self.chroma_client.get_or_create_collection(name=collection_name)
        except Exception as exc:
            logger.error("Failed to get/create collection '%s': %s", collection_name, exc)
            return None

    # ── Embeddings ──────────────────────────────────────────────

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate a text embedding. Routes through the primary OpenAI/GitHub Models client."""
        try:
            response = await rate_limited_call(
                self.openai_client.embeddings.create,
                model=get_embedding_model(),
                input=text[:8000],
            )
            return response.data[0].embedding
        except Exception as exc:
            logger.error("Embedding generation failed: %s", exc)
            return []

    # ── Vector DB Operations ────────────────────────────────────

    async def upsert_snapshot(self, snapshot: Any, user_id: str | None = None) -> None:
        """Store a snapshot document (with embedding) in ChromaDB, scoped to the user."""
        collection = self._get_collection(user_id)
        if collection is None:
            logger.warning("Chroma collection not available — skipping upsert.")
            return

        try:
            # ChromaDB metadatas support str, int, bool, float
            metadata = {
                "id": str(snapshot.id),
                "timestamp": snapshot.timestamp.isoformat() if hasattr(snapshot.timestamp, 'isoformat') else str(snapshot.timestamp),
                "workspace_folder": str(snapshot.workspace_folder or ""),
                "active_file": str(snapshot.active_file or ""),
                "language_id": str(snapshot.language_id or ""),
                "shadow_graph": str((snapshot.shadow_graph or "")[:5000]),
                "git_branch": str(snapshot.git_branch or ""),
                "terminal_commands": json.dumps(snapshot.terminal_commands or []),
                "summary": str(snapshot.metadata.summary if snapshot.metadata else ""),
                "entities": ",".join(snapshot.metadata.entities) if snapshot.metadata and snapshot.metadata.entities else "",
            }

            collection.add(
                ids=[str(snapshot.id)],
                embeddings=[snapshot.embedding or []],
                metadatas=[metadata],
                documents=[str(snapshot.shadow_graph or "")]
            )
            logger.info("Upserted snapshot %s to collection for user=%s.", snapshot.id, user_id or "default")
        except Exception as exc:
            logger.error("Upsert to ChromaDB failed: %s", exc)

    async def semantic_search(self, query: str, top_k: int = 5, user_id: str | None = None) -> list[dict]:
        """Perform a vector semantic search over stored snapshots, scoped to the user."""
        collection = self._get_collection(user_id)
        if collection is None:
            logger.warning("Chroma collection not available — returning empty results.")
            return []

        try:
            # Generate embedding for the query
            query_embedding = await self.generate_embedding(query)

            if not query_embedding:
                logger.warning("No query embedding generated.")
                return []

            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k
            )

            # ChromaDB returns a dict of lists of lists. We only queried 1 embedding, so index 0
            if results and results.get("metadatas") and results["metadatas"]:
                metadatas_list = results["metadatas"][0]
                if metadatas_list is not None:
                    return [dict(meta) for meta in metadatas_list]

            return []

        except Exception as exc:
            logger.error("Semantic search failed: %s", exc)
            return []

    async def get_recent_snapshots(self, limit: int = 10, user_id: str | None = None) -> list[dict]:
        """Fetch the most recent snapshots using direct retrieval (not vector search).
        
        This is used by the /api/v1/events endpoint for the live graph.
        Unlike semantic_search, this doesn't require an embedding query.
        """
        collection = self._get_collection(user_id)
        if collection is None:
            logger.warning("Chroma collection not available — returning empty results.")
            return []

        try:
            # Fetch everything, sort by timestamp, return newest N.
            # ChromaDB offset does NOT guarantee insertion order.
            total = collection.count() or 0
            results = collection.get(
                limit=total if total > 0 else 1,
                include=["metadatas", "documents"]
            )

            if results and results.get("metadatas"):
                sorted_metas = sorted(
                    results["metadatas"],
                    key=lambda m: m.get("timestamp", ""),
                    reverse=True
                )
                return [dict(meta) for meta in sorted_metas[:limit]]

            return []

        except Exception as exc:
            logger.error("get_recent_snapshots failed: %s", exc)
            return []

    async def get_snapshot_timeline(self, limit: int = 200, user_id: str | None = None) -> list[dict]:
        """Fetch a chronologically sorted timeline of snapshot metadata (newest first)."""
        collection = self._get_collection(user_id)
        if collection is None:
            logger.warning("Chroma collection not available — returning empty timeline.")
            return []

        try:
            total = collection.count() or 0
            if total == 0:
                return []
            
            # Fetch only what we need + some buffer for sorting
            fetch_limit = min(total, max(limit * 3, 500))
            results = collection.get(
                limit=fetch_limit,
                include=["metadatas"]
            )
            if not results or not results.get("metadatas"):
                return []

            metadatas = [dict(meta) for meta in results["metadatas"] if meta]
            # Sort by timestamp (newest first) with proper numeric comparison
            def get_sort_key(m: dict) -> float:
                ts = m.get("timestamp", "")
                if isinstance(ts, (int, float)):
                    return float(ts)
                # Try parsing ISO string to float unix timestamp
                if isinstance(ts, str):
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        return dt.timestamp()
                    except Exception:
                        return 0.0
                return 0.0
            
            metadatas.sort(key=get_sort_key, reverse=True)
            return metadatas[:limit]
        except Exception as exc:
            logger.error("get_snapshot_timeline failed: %s", exc)
            return []

    async def get_snapshot_by_id(self, snapshot_id: str, user_id: str | None = None) -> dict | None:
        """Fetch one snapshot by ID from Chroma metadata/documents."""
        collection = self._get_collection(user_id)
        if collection is None:
            logger.warning("Chroma collection not available — snapshot lookup skipped.")
            return None

        try:
            results = collection.get(ids=[snapshot_id], include=["metadatas", "documents"])
            metadatas = (results or {}).get("metadatas") or []
            documents = (results or {}).get("documents") or []

            if not metadatas:
                return None

            metadata = dict(metadatas[0]) if metadatas[0] else {}
            metadata["document"] = documents[0] if documents else ""
            return metadata
        except Exception as exc:
            logger.error("get_snapshot_by_id failed for %s: %s", snapshot_id, exc)
            return None
