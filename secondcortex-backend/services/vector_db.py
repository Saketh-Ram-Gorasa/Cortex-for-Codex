"""Vector Database Service using local ChromaDB as primary storage."""

from __future__ import annotations

import logging
import json
import hashlib
import random
import time
import uuid
from typing import Any

import chromadb

try:
    import psycopg2
    from psycopg2 import Binary
    from psycopg2.extras import Json
except Exception:
    psycopg2 = None

    def Binary(value):
        return value

    def Json(value):
        return value

from config import settings
from services.llm_client import task_embedding_create
from services.external_ingest import ExternalMemoryRecord

logger = logging.getLogger("secondcortex.vectordb")


class VectorDBService:
    """Manages LLM embeddings and ChromaDB operations with per-user isolation."""

    def __init__(self) -> None:
        # Initialize ChromaDB as local primary store during this migration
        try:
            db_path = settings.chroma_db_path
            self.chroma_client = chromadb.PersistentClient(path=db_path)
            logger.info("ChromaDB initialized at: %s (primary local store)", db_path)
        except Exception as exc:
            logger.error("ChromaDB initialization failed: %s", exc)
            self.chroma_client = None
        
        self._query_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._cache_ttl_seconds = 30
        self._cache_max_entries = 512
        self._collection_aliases: dict[str, str] = {}
        self._failover_last_switch_at: dict[str, float] = {}
        self._failover_cooldown_seconds = 300


    def _to_uuid(self, value: Any) -> uuid.UUID | None:
        try:
            return uuid.UUID(str(value))
        except Exception:
            return None

    async def _store_snapshot_cosmosdb(self, snapshot: Any, user_id: str | None, metadata: dict[str, Any], embedding: list[float]) -> bool:
        """Store snapshot in CosmosDB as PRIMARY persistent storage."""
        if self.cosmosdb_client is None:
            return False

        try:
            # Create CosmosDB document
            doc = {
                "id": str(snapshot.id),
                "user_id": str(user_id or ""),
                "project_id": str(snapshot.project_id or ""),
                "active_file": str(snapshot.active_file or ""),
                "language_id": str(snapshot.language_id or ""),
                "git_branch": str(snapshot.git_branch or ""),
                "timestamp": snapshot.timestamp.isoformat() if hasattr(snapshot.timestamp, "isoformat") else str(snapshot.timestamp),
                "shadow_graph": str((snapshot.shadow_graph or "")[:5000]),
                "capture_level": str(getattr(snapshot, "capture_level", "medium") or "medium"),
                "capture_meta": getattr(snapshot, "capture_meta", {}) or {},
                "summary": str(metadata.get("summary") or ""),
                "entities": metadata.get("entities", ""),
                "embedding": embedding,
                "sync_status": "SYNCED",
                "_partition": str(user_id or "default"),
            }
            
            # Upsert into CosmosDB
            self.cosmosdb_client.upsert_item(doc)
            logger.info("Snapshot %s successfully stored in CosmosDB (PRIMARY)", snapshot.id)
            return True
        except Exception as exc:
            logger.error("CosmosDB snapshot upsert failed for snapshot=%s: %s", getattr(snapshot, "id", "unknown"), exc)
            return False


    def _collection_user_key(self, user_id: str | None) -> str:
        return user_id or "__default__"

    def _base_collection_name(self, user_id: str | None = None) -> str:
        return f"snapshots-{user_id}" if user_id else "secondcortex-snapshots"

    def _safe_collection_name(self, name: str) -> str:
        return str(name or "secondcortex-snapshots")[:63]

    def _is_compactor_metadata_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        return "backfill request to compactor" in text or "metadata segment" in text

    def _activate_collection_failover(self, user_id: str | None, reason: Exception) -> None:
        """
        Activate failover collection and migrate data from old collection if possible.
        This prevents data loss when Chroma compactor fails.
        """
        user_key = self._collection_user_key(user_id)
        base_name = self._base_collection_name(user_id)
        now = time.time()
        existing_alias = self._collection_aliases.get(user_key) or ""
        last_switch_at = self._failover_last_switch_at.get(user_key, 0.0)

        if "recovery" in existing_alias.lower() and (now - last_switch_at) < self._failover_cooldown_seconds:
            logger.warning(
                "Chroma compactor failure repeated for user=%s, reusing existing failover collection '%s' "
                "(cooldown %ds). error=%s",
                user_id or "default",
                existing_alias,
                self._failover_cooldown_seconds,
                reason,
            )
            self._clear_user_cache(user_id)
            return

        failover_name = self._safe_collection_name(f"{base_name}-recovery-{int(now)}")
        
        # Try to migrate data from old collection to failover collection
        try:
            old_collection_name = self._collection_aliases.get(user_key) or base_name
            old_collection_name = self._safe_collection_name(old_collection_name)
            
            # Don't attempt migration if we're already in a recovery collection
            if "recovery" not in old_collection_name.lower():
                old_coll = self.chroma_client.get_or_create_collection(name=old_collection_name)
                failover_coll = self.chroma_client.get_or_create_collection(name=failover_name)
                
                # Get all data from old collection
                try:
                    old_count = old_coll.count() or 0
                    if old_count > 0:
                        results = old_coll.get(limit=100000, include=["embeddings", "metadatas", "documents"])
                        ids = results.get("ids") or []
                        embeddings = results.get("embeddings") or []
                        metadatas = results.get("metadatas") or []
                        documents = results.get("documents") or []
                        
                        if ids:
                            # Migrate to failover collection
                            failover_coll.upsert(
                                ids=ids,
                                embeddings=embeddings if embeddings else None,
                                metadatas=metadatas,
                                documents=documents
                            )
                            logger.info(
                                "Migrated %d snapshot records from '%s' to failover collection '%s'",
                                len(ids),
                                old_collection_name,
                                failover_name,
                            )
                except Exception as migration_exc:
                    logger.warning(
                        "Failed to migrate data from old collection during failover: %s. "
                        "Failover collection will be empty but future writes will succeed.",
                        migration_exc,
                    )
        except Exception as failover_exc:
            logger.warning("Error during failover setup: %s", failover_exc)
        
        # Update alias to point to new collection
        self._collection_aliases[user_key] = failover_name
        self._failover_last_switch_at[user_key] = now
        self._clear_user_cache(user_id)
        logger.error(
            "Detected Chroma metadata compactor failure for user=%s. Switching to failover collection '%s'. error=%s",
            user_id or "default",
            failover_name,
            reason,
        )

    def _with_compactor_recovery(self, user_id: str | None, exc: Exception) -> bool:
        if not self._is_compactor_metadata_error(exc):
            return False
        self._activate_collection_failover(user_id, exc)
        return True

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

        user_key = self._collection_user_key(user_id)
        collection_name = self._collection_aliases.get(user_key) or self._base_collection_name(user_id)
        collection_name = self._safe_collection_name(collection_name)

        try:
            return self.chroma_client.get_or_create_collection(name=collection_name)
        except Exception as exc:
            logger.error("Failed to get/create collection '%s': %s", collection_name, exc)
            return None

    async def _try_recovery_collections(
        self,
        user_id: str,
        limit: int = 200,
        project_id: str | None = None,
    ) -> list[dict]:
        """Scan for recovery collections and try to fetch data from them."""
        if not self.chroma_client:
            return []
        
        try:
            base_name = self._base_collection_name(user_id)
            recovery_prefix = f"{base_name}-recovery-"
            
            # List all collections and find recovery collections for this user
            all_collections = self.chroma_client.list_collections()
            recovery_collections = [
                c for c in all_collections 
                if recovery_prefix in c.name
            ]
            
            if not recovery_collections:
                logger.debug("No recovery collections found for user=%s", user_id)
                return []
            
            # Sort by creation time (embedded in name) - try newest first
            recovery_collections.sort(key=lambda c: c.name, reverse=True)
            
            logger.info("Found %d recovery collections for user=%s, attempting recovery...", 
                       len(recovery_collections), user_id)
            
            # Try each recovery collection
            for recovery_coll in recovery_collections:
                try:
                    count = recovery_coll.count() or 0
                    if count == 0:
                        continue
                    
                    fetch_limit = min(count, max(limit * 3, 500))
                    get_kwargs = {
                        "limit": fetch_limit,
                        "include": ["metadatas"],
                    }
                    if project_id:
                        get_kwargs["where"] = {"project_id": str(project_id)}
                    
                    results = recovery_coll.get(**get_kwargs)
                    if not results or not results.get("metadatas"):
                        continue
                    
                    metadatas = [dict(meta) for meta in results["metadatas"] if meta]
                    metadatas.sort(key=lambda meta: self._timestamp_sort_key(meta.get("timestamp")), reverse=True)
                    output = metadatas[:limit]
                    
                    logger.info(
                        "Successfully recovered %d snapshots from recovery collection '%s' for user=%s",
                        len(output),
                        recovery_coll.name,
                        user_id,
                    )
                    
                    # Update alias to use this recovery collection for future queries
                    user_key = self._collection_user_key(user_id)
                    self._collection_aliases[user_key] = recovery_coll.name
                    
                    return output
                except Exception as recovery_exc:
                    logger.debug(
                        "Recovery collection '%s' query failed: %s", 
                        recovery_coll.name, 
                        recovery_exc
                    )
                    continue
            
            logger.warning("All recovery collections for user=%s were empty or inaccessible", user_id)
            return []
        except Exception as exc:
            logger.debug("Recovery collection scan failed: %s", exc)
            return []

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
        """Store snapshot in local ChromaDB with OpenAI-backed embedding generation."""
        collection = self._get_collection(user_id)
        if collection is None:
            logger.warning("Chroma collection not available. Snapshot persistence skipped.")
            return

        metadata = {
            "id": str(snapshot.id),
            "timestamp": snapshot.timestamp.isoformat() if hasattr(snapshot.timestamp, "isoformat") else str(snapshot.timestamp),
            "workspace_folder": str(snapshot.workspace_folder or ""),
            "active_file": str(snapshot.active_file or ""),
            "language_id": str(snapshot.language_id or ""),
            "shadow_graph": str((snapshot.shadow_graph or "")[:5000]),
            "git_branch": str(snapshot.git_branch or ""),
            "project_id": str(snapshot.project_id or ""),
            "terminal_commands": json.dumps(snapshot.terminal_commands or []),
            "capture_level": str(getattr(snapshot, "capture_level", "medium") or "medium"),
            "capture_meta": json.dumps(getattr(snapshot, "capture_meta", {}) or {}),
            "summary": str(snapshot.metadata.summary if snapshot.metadata else ""),
            "entities": ",".join(snapshot.metadata.entities) if snapshot.metadata and snapshot.metadata.entities else "",
            "active_symbol": str((snapshot.function_context or {}).get("activeSymbol") or ""),
            "function_signatures": json.dumps((snapshot.function_context or {}).get("signatures") or []),
        }

        embedding = list(snapshot.embedding or [])
        embedding_source = (
            f"{metadata.get('active_file', '')}\n"
            f"{metadata.get('summary', '')}\n"
            f"{metadata.get('shadow_graph', '')}\n"
            f"{metadata.get('active_symbol', '')}\n"
            f"{metadata.get('function_signatures', '')}"
        )
        if not embedding:
            embedding = await self.generate_embedding(embedding_source)
            if not embedding:
                dimension = self._infer_collection_dimension(collection)
                embedding = self._build_fallback_embedding(embedding_source, dimension)
                logger.warning(
                    "Snapshot %s missing usable embedding; using deterministic fallback vector (dim=%d).",
                    snapshot.id,
                    len(embedding),
                )
        elif len(embedding) not in (384, 1536, 3072):
            logger.warning(
                "Snapshot %s provided embedding dimension=%d. Regenerating with OpenAI fallback.",
                snapshot.id,
                len(embedding),
            )
            regenerated = await self.generate_embedding(embedding_source)
            if regenerated:
                embedding = regenerated

        try:
            collection.upsert(
                ids=[str(snapshot.id)],
                embeddings=[embedding],
                metadatas=[metadata],
                documents=[str(snapshot.shadow_graph or "")],
            )
            logger.info("Upserted snapshot %s to collection for user=%s.", snapshot.id, user_id or "default")
        except Exception as exc:
            if self._with_compactor_recovery(user_id, exc):
                collection = self._get_collection(user_id)
                if collection is not None:
                    try:
                        collection.upsert(
                            ids=[str(snapshot.id)],
                            embeddings=[embedding],
                            metadatas=[metadata],
                            documents=[str(snapshot.shadow_graph or "")],
                        )
                        logger.info(
                            "Upserted snapshot %s to failover collection for user=%s.",
                            snapshot.id,
                            user_id or "default",
                        )
                    except Exception as retry_exc:
                        logger.error("Retry upsert to failover collection failed: %s", retry_exc)
            else:
                logger.error("Upsert to ChromaDB failed: %s", exc)

        self._clear_user_cache(user_id)

    async def semantic_search(
        self,
        query: str,
        top_k: int = 5,
        user_id: str | None = None,
        project_id: str | None = None,
    ) -> list[dict]:
        """Perform a semantic search over local ChromaDB snapshots."""
        cache_key = self._cache_key("semantic", user_id, project_id, query, top_k)
        cached = self._cache_get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for semantic_search: user=%s, query=%s", user_id, query[:50])
            return cached

        try:
            # Generate embedding for the query
            query_embedding = await self.generate_embedding(query)

            if not query_embedding:
                logger.warning("No query embedding generated; falling back to recent snapshots.")
                fallback = await self.get_recent_snapshots(limit=top_k, user_id=user_id, project_id=project_id)
                self._cache_set(cache_key, fallback)
                return fallback

            # Strategy 1: ChromaDB vector search
            collection = self._get_collection(user_id)
            if collection is None:
                logger.warning("Chroma collection not available for user=%s — returning recent snapshots fallback.", user_id)
                fallback = await self.get_recent_snapshots(limit=top_k, user_id=user_id, project_id=project_id)
                self._cache_set(cache_key, fallback)
                return fallback

            query_kwargs: dict[str, Any] = {
                "query_embeddings": [query_embedding],
                "n_results": top_k,
            }
            if project_id:
                query_kwargs["where"] = {"project_id": str(project_id)}

            logger.debug("Querying ChromaDB for user=%s with %d results requested", user_id, top_k)
            results = collection.query(**query_kwargs)

            # ChromaDB returns a dict of lists of lists. We only queried 1 embedding, so index 0
            if results and results.get("metadatas") and results["metadatas"]:
                metadatas_list = results["metadatas"][0]
                if metadatas_list is not None:
                    items = [dict(meta) for meta in metadatas_list]
                    logger.info("ChromaDB returned %d results for user=%s", len(items), user_id)
                    self._cache_set(cache_key, items)
                    return items

            # Strategy 2: Fall back to recent snapshots
            logger.debug("ChromaDB returned no results, falling back to recent snapshots for user=%s", user_id)
            fallback = await self.get_recent_snapshots(limit=top_k, user_id=user_id, project_id=project_id)
            self._cache_set(cache_key, fallback)
            return fallback

        except Exception as exc:
            if self._with_compactor_recovery(user_id, exc):
                logger.info("Activated ChromaDB compactor recovery for user=%s", user_id)
                return await self.get_recent_snapshots(limit=top_k, user_id=user_id, project_id=project_id)
            logger.error("Semantic search failed for user=%s: %s", user_id, exc)
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
            if self._with_compactor_recovery(user_id, exc):
                collection = self._get_collection(user_id)
                if collection is not None:
                    try:
                        collection.upsert(
                            ids=[record_id],
                            embeddings=[embedding],
                            metadatas=[metadata],
                            documents=[record.content],
                        )
                        self._clear_user_cache(user_id)
                        return record_id
                    except Exception as retry_exc:
                        logger.error("Retry external upsert to failover collection failed: %s", retry_exc)
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
            if self._with_compactor_recovery(user_id, exc):
                return []
            logger.error("get_recent_snapshots failed: %s", exc)
            return []

    def get_snapshot_metadatas(
        self,
        user_id: str | None = None,
        *,
        limit: int = 2500,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch raw snapshot metadata with compactor-aware failover recovery."""
        collection = self._get_collection(user_id)
        if collection is None:
            logger.warning("Chroma collection not available — returning empty metadata list.")
            return []

        attempted_recovery = False
        while True:
            try:
                total = collection.count() or 0
                if total <= 0:
                    return []

                fetch_limit = min(max(1, int(limit)), total)
                get_kwargs: dict[str, Any] = {
                    "limit": fetch_limit,
                    "include": ["metadatas"],
                }
                if project_id:
                    get_kwargs["where"] = {"project_id": str(project_id)}

                result = collection.get(**get_kwargs)
                metadatas = (result or {}).get("metadatas") or []
                return [dict(meta) for meta in metadatas if meta]
            except Exception as exc:
                if not attempted_recovery and self._with_compactor_recovery(user_id, exc):
                    collection = self._get_collection(user_id)
                    if collection is None:
                        return []
                    attempted_recovery = True
                    continue
                logger.error("get_snapshot_metadatas failed for user=%s: %s", user_id or "default", exc)
                return []

    async def get_snapshot_timeline(
        self,
        limit: int = 200,
        user_id: str | None = None,
        project_id: str | None = None,
    ) -> list[dict]:
        """Fetch a chronologically sorted timeline of snapshot metadata (newest first)."""
        cache_key = self._cache_key("timeline", user_id, project_id, limit)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        # Chroma timeline retrieval
        collection = self._get_collection(user_id)
        if collection is None:
            logger.warning("Chroma collection not available — returning empty timeline.")
            return []

        attempted_recovery = False
        while True:
            try:
                total = collection.count() or 0
                if total == 0:
                    # If current collection is empty, try recovery collections
                    if not attempted_recovery and user_id:
                        results = await self._try_recovery_collections(user_id, limit, project_id)
                        if results:
                            self._cache_set(cache_key, results)
                            return results
                        attempted_recovery = True
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
                    if not attempted_recovery and user_id:
                        # Try recovery collections
                        recovery_results = await self._try_recovery_collections(user_id, limit, project_id)
                        if recovery_results:
                            self._cache_set(cache_key, recovery_results)
                            return recovery_results
                        attempted_recovery = True
                    return []

                metadatas = [dict(meta) for meta in results["metadatas"] if meta]

                metadatas.sort(key=lambda meta: self._timestamp_sort_key(meta.get("timestamp")), reverse=True)
                output = metadatas[:limit]
                self._cache_set(cache_key, output)
                return output
            except Exception as exc:
                if not attempted_recovery and self._with_compactor_recovery(user_id, exc):
                    # Recovery activated, retry with new collection
                    collection = self._get_collection(user_id)
                    if collection is None:
                        return []
                    attempted_recovery = True
                    continue

                # If primary recovery didn't help, try recovery collections
                if user_id and not attempted_recovery:
                    try:
                        results = await self._try_recovery_collections(user_id, limit, project_id)
                        if results:
                            self._cache_set(cache_key, results)
                            return results
                    except Exception as recovery_exc:
                        logger.debug("Recovery collection scan failed: %s", recovery_exc)

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
            if self._with_compactor_recovery(user_id, exc):
                return None
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
            if self._with_compactor_recovery(user_id, exc):
                return 0
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

