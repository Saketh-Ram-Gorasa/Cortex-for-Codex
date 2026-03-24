"""
Vector Database Service — handles connections to:
  1. LLM (GitHub Models or Azure OpenAI) for embeddings
  2. ChromaDB (vector storage & semantic search)

Supports per-user namespaced collections for multi-tenant isolation.
"""

from __future__ import annotations

import logging
import json
import hashlib
import random
import time
from typing import Any

import chromadb

from config import settings
from services.llm_client import task_embedding_create
from services.external_ingest import ExternalMemoryRecord

logger = logging.getLogger("secondcortex.vectordb")


class VectorDBService:
    """Manages LLM embeddings and ChromaDB operations with per-user isolation."""

    def __init__(self) -> None:
        # Initialize ChromaDB client with configurable persistent path
        try:
            db_path = settings.chroma_db_path
            self.chroma_client = chromadb.PersistentClient(path=db_path)
            logger.info("ChromaDB initialized at: %s", db_path)
        except Exception as exc:
            logger.error("ChromaDB initialization failed: %s", exc)
            self.chroma_client = None
        self._query_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._cache_ttl_seconds = 30
        self._cache_max_entries = 512

    def _cache_key(
        self,
        prefix: str,
        user_id: str | None,
        project_id: str | None,
        *parts: Any,
    ) -> str:
        serialized = "::".join(str(part) for part in parts)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return f"{prefix}::{user_id or 'default'}::{project_id or 'all'}::{digest}"

    def _cache_get(self, key: str) -> list[dict[str, Any]] | None:
        hit = self._query_cache.get(key)
        if not hit:
            return None

        expires_at, payload = hit
        if expires_at <= time.time():
            self._query_cache.pop(key, None)
            return None

        return [dict(item) for item in payload]

    def _cache_set(self, key: str, payload: list[dict[str, Any]]) -> None:
        if key in self._query_cache:
            self._query_cache.pop(key, None)
        self._query_cache[key] = (
            time.time() + self._cache_ttl_seconds,
            [dict(item) for item in payload],
        )
        self._prune_query_cache()

    def _prune_query_cache(self) -> None:
        now = time.time()

        expired_keys = [key for key, (expires_at, _payload) in self._query_cache.items() if expires_at <= now]
        for key in expired_keys:
            self._query_cache.pop(key, None)

        while len(self._query_cache) > self._cache_max_entries:
            oldest_key = next(iter(self._query_cache))
            self._query_cache.pop(oldest_key, None)

    def _clear_user_cache(self, user_id: str | None) -> None:
        token = f"::{user_id or 'default'}::"
        stale_keys = [key for key in self._query_cache if token in key]
        for key in stale_keys:
            self._query_cache.pop(key, None)

    def _timestamp_sort_key(self, value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return 0.0
            try:
                return float(raw)
            except ValueError:
                pass
            try:
                from datetime import datetime

                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                return dt.timestamp()
            except Exception:
                return 0.0
        return 0.0

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

    def _infer_collection_dimension(self, collection, default_dim: int = 1536) -> int:
        """Infer vector dimension from existing records, or fall back to a default."""
        try:
            if (collection.count() or 0) <= 0:
                return default_dim

            probe = collection.get(limit=1, include=["embeddings"])
            embeddings = (probe or {}).get("embeddings") or []
            if embeddings and embeddings[0]:
                return len(embeddings[0])
        except Exception:
            pass
        return default_dim

    def _build_fallback_embedding(self, text: str, dimension: int) -> list[float]:
        """
        Deterministic fallback embedding used when external embedding APIs fail.
        Keeps ingestion/query functional instead of dropping all context.
        """
        seed = int.from_bytes(hashlib.sha256((text or "").encode("utf-8")).digest()[:8], "big")
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(max(1, dimension))]

    # ── Embeddings ──────────────────────────────────────────────

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate a text embedding. Routes through the primary OpenAI/GitHub Models client."""
        try:
            response = await task_embedding_create(
                task="embeddings",
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
                "project_id": str(snapshot.project_id or ""),
                "terminal_commands": json.dumps(snapshot.terminal_commands or []),
                "summary": str(snapshot.metadata.summary if snapshot.metadata else ""),
                "entities": ",".join(snapshot.metadata.entities) if snapshot.metadata and snapshot.metadata.entities else "",
                "active_symbol": str((snapshot.function_context or {}).get("activeSymbol") or ""),
                "function_signatures": json.dumps((snapshot.function_context or {}).get("signatures") or []),
            }

            embedding = snapshot.embedding or []
            if not embedding:
                dimension = self._infer_collection_dimension(collection)
                embedding_source = (
                    f"{metadata.get('active_file', '')}\n"
                    f"{metadata.get('summary', '')}\n"
                    f"{metadata.get('shadow_graph', '')}\n"
                    f"{metadata.get('active_symbol', '')}\n"
                    f"{metadata.get('function_signatures', '')}"
                )
                embedding = self._build_fallback_embedding(embedding_source, dimension)
                logger.warning(
                    "Snapshot %s missing external embedding; using deterministic fallback vector (dim=%d).",
                    snapshot.id,
                    len(embedding),
                )

            collection.upsert(
                ids=[str(snapshot.id)],
                embeddings=[embedding],
                metadatas=[metadata],
                documents=[str(snapshot.shadow_graph or "")]
            )
            self._clear_user_cache(user_id)
            logger.info("Upserted snapshot %s to collection for user=%s.", snapshot.id, user_id or "default")
        except Exception as exc:
            logger.error("Upsert to ChromaDB failed: %s", exc)

    async def semantic_search(
        self,
        query: str,
        top_k: int = 5,
        user_id: str | None = None,
        project_id: str | None = None,
    ) -> list[dict]:
        """Perform a vector semantic search over stored snapshots, scoped to the user."""
        collection = self._get_collection(user_id)
        if collection is None:
            logger.warning("Chroma collection not available — returning empty results.")
            return []

        cache_key = self._cache_key("semantic", user_id, project_id, query, top_k)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            # Generate embedding for the query
            query_embedding = await self.generate_embedding(query)

            if not query_embedding:
                logger.warning("No query embedding generated; falling back to recent snapshots.")
                return await self.get_recent_snapshots(limit=top_k, user_id=user_id, project_id=project_id)

            query_kwargs: dict[str, Any] = {
                "query_embeddings": [query_embedding],
                "n_results": top_k,
            }
            if project_id:
                query_kwargs["where"] = {"project_id": str(project_id)}

            results = collection.query(**query_kwargs)

            # ChromaDB returns a dict of lists of lists. We only queried 1 embedding, so index 0
            if results and results.get("metadatas") and results["metadatas"]:
                metadatas_list = results["metadatas"][0]
                if metadatas_list is not None:
                    items = [dict(meta) for meta in metadatas_list]
                    self._cache_set(cache_key, items)
                    return items

            fallback = await self.get_recent_snapshots(limit=top_k, user_id=user_id, project_id=project_id)
            self._cache_set(cache_key, fallback)
            return fallback

        except Exception as exc:
            logger.error("Semantic search failed: %s", exc)
            fallback = await self.get_recent_snapshots(limit=top_k, user_id=user_id, project_id=project_id)
            self._cache_set(cache_key, fallback)
            return fallback

    async def upsert_external_record(self, record: ExternalMemoryRecord, user_id: str | None = None) -> str | None:
        """Store an external memory record (Slack/Notion/Confluence style) with provenance metadata."""
        collection = self._get_collection(user_id)
        if collection is None:
            logger.warning("Chroma collection not available — skipping external upsert.")
            return None

        record_id = record.source_id.replace("/", "_")
        if not record_id:
            record_id = f"external-{int(time.time() * 1000)}"

        content = "\n".join([
            f"{record.title}",
            f"Domain: {record.domain}",
            record.summary,
            record.content,
        ])
        embedding = await self.generate_embedding(content[:8000])
        if not embedding:
            dimension = self._infer_collection_dimension(collection)
            embedding = self._build_fallback_embedding(content, dimension)

        metadata = {
            "id": record_id,
            "timestamp": record.timestamp.isoformat(),
            "workspace_folder": "external",
            "active_file": record.title,
            "language_id": "external",
            "shadow_graph": record.content[:5000],
            "git_branch": "external",
            "project_id": str(record.project_id or ""),
            "terminal_commands": "[]",
            "summary": record.summary,
            "entities": ",".join(record.entities),
            "active_symbol": "",
            "function_signatures": "[]",
            "source_type": record.source_type,
            "source_id": record.source_id,
            "source_uri": record.source_uri,
            "confidence_score": float(record.confidence_score),
            "domain": record.domain,
        }

        try:
            collection.upsert(
                ids=[record_id],
                embeddings=[embedding],
                metadatas=[metadata],
                documents=[record.content],
            )
            self._clear_user_cache(user_id)
            return record_id
        except Exception as exc:
            logger.error("External upsert failed: %s", exc)
            return None

    async def get_recent_snapshots(
            self,
            limit: int = 10,
            user_id: str | None = None,
            project_id: str | None = None,
    ) -> list[dict]:
        """Fetch the most recent snapshots using direct retrieval (not vector search).
        
        This is used by the /api/v1/events endpoint for the live graph.
        Unlike semantic_search, this doesn't require an embedding query.
        """
        collection = self._get_collection(user_id)
        if collection is None:
            logger.warning("Chroma collection not available — returning empty results.")
            return []

        cache_key = self._cache_key("recent", user_id, project_id, limit)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            total = collection.count() or 0
            if total <= 0:
                return []

            fetch_limit = min(total, max(limit * 3, 500))
            get_kwargs: dict[str, Any] = {
                "limit": fetch_limit,
                "include": ["metadatas"],
            }
            if project_id:
                get_kwargs["where"] = {"project_id": str(project_id)}

            results = collection.get(
                **get_kwargs
            )

            if results and results.get("metadatas"):
                metadatas = [dict(meta) for meta in results["metadatas"] if meta]

                sorted_metas = sorted(
                    metadatas,
                    key=lambda m: self._timestamp_sort_key(m.get("timestamp")),
                    reverse=True
                )
                output = sorted_metas[:limit]
                self._cache_set(cache_key, output)
                return output

            return []

        except Exception as exc:
            logger.error("get_recent_snapshots failed: %s", exc)
            return []

    async def get_snapshot_timeline(
        self,
        limit: int = 200,
        user_id: str | None = None,
        project_id: str | None = None,
    ) -> list[dict]:
        """Fetch a chronologically sorted timeline of snapshot metadata (newest first)."""
        collection = self._get_collection(user_id)
        if collection is None:
            logger.warning("Chroma collection not available — returning empty timeline.")
            return []

        cache_key = self._cache_key("timeline", user_id, project_id, limit)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            total = collection.count() or 0
            if total == 0:
                return []
            
            # Fetch only what we need + some buffer for sorting
            fetch_limit = min(total, max(limit * 3, 500))
            get_kwargs: dict[str, Any] = {
                "limit": fetch_limit,
                "include": ["metadatas"],
            }
            if project_id:
                get_kwargs["where"] = {"project_id": str(project_id)}

            results = collection.get(**get_kwargs)
            if not results or not results.get("metadatas"):
                return []

            metadatas = [dict(meta) for meta in results["metadatas"] if meta]

            metadatas.sort(key=lambda meta: self._timestamp_sort_key(meta.get("timestamp")), reverse=True)
            output = metadatas[:limit]
            self._cache_set(cache_key, output)
            return output
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

    async def assign_project_to_user_snapshots(
        self,
        user_id: str,
        project_id: str,
        overwrite_existing: bool = True,
    ) -> int:
        """Backfill project_id metadata for snapshots in one user's collection."""
        collection = self._get_collection(user_id)
        if collection is None:
            return 0

        normalized_project_id = str(project_id or "").strip()
        if not normalized_project_id:
            return 0

        try:
            results = collection.get(include=["metadatas"])
            ids = (results or {}).get("ids") or []
            metadatas = (results or {}).get("metadatas") or []
            if not ids or not metadatas:
                return 0

            updated_count = 0
            for snap_id, meta in zip(ids, metadatas):
                if not snap_id or not meta:
                    continue

                current_project_id = str((meta or {}).get("project_id") or "").strip()
                if current_project_id and not overwrite_existing:
                    continue
                if current_project_id == normalized_project_id:
                    continue

                new_meta = dict(meta)
                new_meta["project_id"] = normalized_project_id
                collection.update(ids=[str(snap_id)], metadatas=[new_meta])
                updated_count += 1

            self._clear_user_cache(user_id)
            return updated_count
        except Exception as exc:
            logger.error("assign_project_to_user_snapshots failed for user=%s: %s", user_id, exc)
            return 0

    # ── Long-Term Memory: Facts ────────────────────────────────

    def _get_facts_collection(self, user_id: str | None = None):
        """Get or create facts collection (separate from snapshots)."""
        if self.chroma_client is None:
            return None

        collection_name = f"facts-{user_id}" if user_id else "secondcortex-facts"
        collection_name = collection_name[:63]  # ChromaDB name limit

        try:
            return self.chroma_client.get_or_create_collection(name=collection_name)
        except Exception as exc:
            logger.error("Failed to get/create facts collection '%s': %s", collection_name, exc)
            return None

    async def upsert_fact(self, fact: Any, user_id: str | None = None) -> None:
        """Store a fact in the facts collection."""
        collection = self._get_facts_collection(user_id)
        if collection is None:
            logger.warning("Facts collection not available for user=%s", user_id or "default")
            return

        try:
            # Generate embedding for the fact
            embedding = await self.generate_embedding(fact.content)
            if not embedding:
                embedding = self._build_fallback_embedding(fact.content, 1536)

            metadata = {
                "id": str(fact.id),
                "kind": fact.kind,
                "salience": fact.salience,
                "confidence": fact.confidence,
                "entities": ",".join(fact.entities),
                "source_snapshot_id": str(fact.source_snapshot_id or ""),
                "created_at": fact.created_at.isoformat(),
                "last_accessed_at": fact.last_accessed_at.isoformat(),
            }

            collection.upsert(
                ids=[str(fact.id)],
                embeddings=[embedding],
                metadatas=[metadata],
                documents=[fact.content]
            )
            logger.info("Upserted fact %s to facts collection for user=%s", fact.id, user_id or "default")
        except Exception as exc:
            logger.error("Failed to upsert fact: %s", exc)

    async def recall_facts(
        self,
        query: str,
        top_k: int = 5,
        user_id: str | None = None,
        min_salience: float = 0.0,
    ) -> list[dict]:
        """Retrieve facts by semantic similarity."""
        collection = self._get_facts_collection(user_id)
        if collection is None:
            logger.warning("Facts collection not available for user=%s", user_id or "default")
            return []

        try:
            query_embedding = await self.generate_embedding(query)
            if not query_embedding:
                logger.warning("No query embedding generated for fact recall")
                return []

            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
            )

            if results and results.get("metadatas") and results["metadatas"]:
                metadatas = results["metadatas"][0]
                facts = []
                for meta in metadatas:
                    if meta and float(meta.get("salience", 0)) >= min_salience:
                        meta_dict = dict(meta)
                        facts.append(meta_dict)
                return facts

            return []
        except Exception as exc:
            logger.error("Fact recall failed: %s", exc)
            return []

    async def get_fact_by_id(self, fact_id: str, user_id: str | None = None) -> dict | None:
        """Fetch a single fact by ID."""
        collection = self._get_facts_collection(user_id)
        if collection is None:
            return None

        try:
            results = collection.get(ids=[fact_id], include=["metadatas", "documents"])
            metadatas = (results or {}).get("metadatas") or []
            documents = (results or {}).get("documents") or []

            if not metadatas:
                return None

            metadata = dict(metadatas[0]) if metadatas[0] else {}
            metadata["document"] = documents[0] if documents else ""
            return metadata
        except Exception as exc:
            logger.error("get_fact_by_id failed for %s: %s", fact_id, exc)
            return None
