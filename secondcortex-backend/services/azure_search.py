from __future__ import annotations

import asyncio
import logging
import importlib
import time
from typing import Any

try:
    AzureKeyCredential = importlib.import_module("azure.core.credentials").AzureKeyCredential
    SearchClient = importlib.import_module("azure.search.documents").SearchClient
    VectorizedQuery = importlib.import_module("azure.search.documents.models").VectorizedQuery
except Exception:
    AzureKeyCredential = None
    SearchClient = None
    VectorizedQuery = None

logger = logging.getLogger("secondcortex.azure_search")


class AzureSearchService:
    """Wrapper around Azure AI Search for vector indexing and retrieval with retry logic."""

    # Configuration for retry behavior
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 1
    RETRY_BACKOFF_MULTIPLIER = 2.0
    HEALTH_CHECK_TIMEOUT_SECONDS = 5

    def __init__(self, endpoint: str, api_key: str, index_name: str = "snapshots"):
        if SearchClient is None or AzureKeyCredential is None:
            raise RuntimeError("azure-search-documents is not installed")
        self.client = SearchClient(
            endpoint=endpoint,
            index_name=index_name,
            credential=AzureKeyCredential(api_key),
        )
        self.endpoint = endpoint
        self.index_name = index_name
        self._health_check_passed = False
        self._last_health_check = 0.0

    async def _check_health(self) -> bool:
        """Check if Azure Search service is reachable and healthy."""
        try:
            # Only check health every 30 seconds to avoid excessive requests
            now = time.time()
            if self._health_check_passed and (now - self._last_health_check) < 30:
                return True

            # Simple health check: run a minimal query against the configured index.
            # SearchClient doesn't expose get_service_statistics; this call validates
            # endpoint, key, and index availability with minimal payload.
            results = self.client.search(search_text="*", top=1)
            next(iter(results), None)
            self._last_health_check = now
            self._health_check_passed = True
            logger.debug("Azure Search health check passed")
            return True
        except Exception as exc:
            self._health_check_passed = False
            logger.warning("Azure Search health check failed: %s", exc)
            return False

    async def _retry_operation(
        self,
        operation_name: str,
        operation_func,
        *args,
        **kwargs
    ) -> Any:
        """Execute an operation with exponential backoff retry logic."""
        last_exception = None
        delay = self.RETRY_DELAY_SECONDS

        for attempt in range(self.MAX_RETRIES):
            try:
                if attempt == 0:
                    # First attempt: do health check
                    is_healthy = await self._check_health()
                    if not is_healthy and attempt == 0:
                        logger.warning("Azure Search unhealthy before %s attempt 1", operation_name)

                result = operation_func(*args, **kwargs)
                
                logger.debug("%s succeeded on attempt %d/%d", operation_name, attempt + 1, self.MAX_RETRIES)
                return result
            except Exception as exc:
                last_exception = exc
                is_last_attempt = attempt == self.MAX_RETRIES - 1

                if is_last_attempt:
                    logger.error(
                        "%s failed after %d attempts. Last error: %s",
                        operation_name,
                        self.MAX_RETRIES,
                        exc,
                    )
                else:
                    logger.warning(
                        "%s attempt %d/%d failed, retrying in %.1f seconds: %s",
                        operation_name,
                        attempt + 1,
                        self.MAX_RETRIES,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    delay *= self.RETRY_BACKOFF_MULTIPLIER

        return None

    def _validate_embedding_dimension(self, embedding: list[float]) -> bool:
        """Validate that embedding has correct dimension (1536 for ada-002/text-embedding-3-large)."""
        if not embedding:
            logger.warning("Empty embedding provided")
            return False
        
        valid_dimensions = [1536, 384]  # ada-002 is 1536, text-embedding-3-small is 384
        if len(embedding) not in valid_dimensions:
            logger.error(
                "Invalid embedding dimension: expected one of %s, got %d",
                valid_dimensions,
                len(embedding),
            )
            return False
        return True

    async def vector_search(
        self,
        query_vector: list[float],
        user_id: str,
        project_id: str | None,
        k: int = 10,
    ) -> list[dict[str, Any]]:
        """Perform vector search with retry logic and health checks."""
        
        # Validate input
        if not self._validate_embedding_dimension(query_vector):
            logger.error("Invalid query embedding dimension, skipping Azure Search")
            return []

        def _search_operation():
            filters: list[str] = [f"user_id eq '{user_id}'"]
            if project_id:
                filters.append(f"project_id eq '{project_id}'")

            if VectorizedQuery is None:
                results = self.client.search(
                    search_text="",
                    filter=" and ".join(filters),
                    top=k,
                )
            else:
                vector_query = VectorizedQuery(
                    vector=query_vector,
                    k_nearest_neighbors=k,
                    fields="embedding"
                )
                results = self.client.search(
                    search_text=None,
                    vector_queries=[vector_query],
                    filter=" and ".join(filters),
                    top=k,
                )

            return [
                {
                    "id": doc.get("id"),
                    "summary": doc.get("summary", ""),
                    "active_file": doc.get("active_file", ""),
                    "project_id": doc.get("project_id"),
                    "timestamp": doc.get("timestamp"),
                    "git_branch": doc.get("git_branch"),
                    "entities": doc.get("entities", ""),
                    "score": float(doc.get("@search.score", 0.0) or 0.0),
                }
                for doc in results
            ]

        result = await self._retry_operation(
            "vector_search",
            _search_operation,
        )
        
        return result if result is not None else []

    async def index_snapshot(self, snapshot: dict[str, Any]) -> bool:
        """Index a snapshot with retry logic and dimension validation."""
        
        # Validate embedding if present
        if "embedding" in snapshot and snapshot["embedding"]:
            if not self._validate_embedding_dimension(snapshot["embedding"]):
                logger.error("Snapshot %s has invalid embedding dimension", snapshot.get("id"))
                return False

        def _index_operation():
            result = self.client.upload_documents([snapshot])
            if not result:
                raise RuntimeError("Upload returned empty result")
            
            success = bool(result[0].succeeded)
            if not success:
                error_msg = result[0].error_message if hasattr(result[0], 'error_message') else "Unknown error"
                raise RuntimeError(f"Document upload failed: {error_msg}")
            
            return success

        result = await self._retry_operation(
            f"index_snapshot[{snapshot.get('id')}]",
            _index_operation,
        )
        
        return bool(result)
