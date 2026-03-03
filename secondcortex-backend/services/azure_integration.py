"""
Azure Integration Service — handles connections to:
  1. LLM (GitHub Models or Azure OpenAI) for embeddings
  2. Azure AI Search (vector storage & semantic search)
"""

from __future__ import annotations

import logging
from typing import Any

from config import settings
from services.llm_client import create_llm_client, get_embedding_model

logger = logging.getLogger("secondcortex.azure")


class AzureIntegrationService:
    """Manages LLM embeddings and Azure AI Search operations."""

    def __init__(self) -> None:
        self.openai_client = create_llm_client()

        # Azure AI Search client (lazy init when credentials are available)
        self._search_client = None

    def _get_search_client(self):
        """Lazily initialize the Azure AI Search client."""
        if self._search_client is None:
            try:
                from azure.core.credentials import AzureKeyCredential
                from azure.search.documents import SearchClient

                self._search_client = SearchClient(
                    endpoint=settings.azure_search_endpoint,
                    index_name=settings.azure_search_index_name,
                    credential=AzureKeyCredential(settings.azure_search_api_key),
                )
                logger.info("Azure AI Search client initialized.")
            except Exception as exc:
                logger.warning("Azure AI Search not configured: %s", exc)
        return self._search_client

    # ── Embeddings ──────────────────────────────────────────────

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate a text embedding using the configured LLM provider."""
        try:
            response = self.openai_client.embeddings.create(
                model=get_embedding_model(),
                input=text[:8000],  # Truncate to avoid token limits
            )
            return response.data[0].embedding
        except Exception as exc:
            logger.error("Embedding generation failed: %s", exc)
            return []

    # ── Vector DB Operations ────────────────────────────────────

    async def upsert_snapshot(self, snapshot: Any) -> None:
        """Store a snapshot document (with embedding) in Azure AI Search."""
        client = self._get_search_client()
        if client is None:
            logger.warning("Search client not available — skipping upsert.")
            return

        document = {
            "id": snapshot.id,
            "timestamp": snapshot.timestamp.isoformat() if hasattr(snapshot.timestamp, 'isoformat') else str(snapshot.timestamp),
            "workspace_folder": snapshot.workspace_folder,
            "active_file": snapshot.active_file,
            "language_id": snapshot.language_id,
            "shadow_graph": snapshot.shadow_graph[:5000],
            "git_branch": snapshot.git_branch or "",
            "summary": snapshot.metadata.summary if snapshot.metadata else "",
            "entities": ",".join(snapshot.metadata.entities) if snapshot.metadata else "",
            "embedding": snapshot.embedding or [],
        }

        try:
            client.upload_documents(documents=[document])
            logger.info("Upserted snapshot %s to Azure AI Search.", snapshot.id)
        except Exception as exc:
            logger.error("Upsert to Azure AI Search failed: %s", exc)

    async def semantic_search(self, query: str, top_k: int = 5) -> list[dict]:
        """Perform a vector + semantic search over stored snapshots."""
        client = self._get_search_client()

        # If search is not configured, return empty results
        if client is None:
            logger.warning("Search client not available — returning empty results.")
            return []

        try:
            # Generate embedding for the query
            query_embedding = await self.generate_embedding(query)

            if not query_embedding:
                # Fallback to text search
                results = client.search(
                    search_text=query,
                    top=top_k,
                    select=["id", "timestamp", "active_file", "git_branch", "shadow_graph", "summary"],
                )
            else:
                from azure.search.documents.models import VectorizedQuery

                vector_query = VectorizedQuery(
                    vector=query_embedding,
                    k_nearest_neighbors=top_k,
                    fields="embedding",
                )

                results = client.search(
                    search_text=query,
                    vector_queries=[vector_query],
                    top=top_k,
                    select=["id", "timestamp", "active_file", "git_branch", "shadow_graph", "summary"],
                )

            return [dict(result) for result in results]

        except Exception as exc:
            logger.error("Semantic search failed: %s", exc)
            return []
