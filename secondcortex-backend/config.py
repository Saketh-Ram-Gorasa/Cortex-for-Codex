"""
SecondCortex Backend — Application settings loaded from environment variables.

Supports two modes:
  1. GitHub Models (default) — uses a GitHub PAT token with models.inference.ai.azure.com
  2. Azure OpenAI (legacy)  — uses Azure OpenAI endpoint + key
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── LLM Provider (github_models | azure_openai) ──────────
    llm_provider: str = "github_models"

    # ── GitHub Models ────────────────────────────────────────
    github_token: str = ""
    github_models_endpoint: str = "https://models.inference.ai.azure.com"
    github_models_chat_model: str = "gpt-4o"
    github_models_embedding_model: str = "text-embedding-3-small"

    # ── Azure OpenAI (legacy fallback) ───────────────────────
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = "gpt-4o"
    azure_openai_api_version: str = "2024-02-01"
    azure_openai_embedding_deployment: str = "text-embedding-ada-002"

    # ── ChromaDB Storage ─────────────────────────────────────
    # On Azure App Service, set to /home/chroma_db for persistence.
    # Locally, defaults to ./chroma_db.
    chroma_db_path: str = "./chroma_db"

    # ── API Authentication ───────────────────────────────────
    # Comma-separated list of "user_id:api_key" pairs.
    # Example: "suhaan:sk-abc123,teammate:sk-def456"
    api_keys: str = ""

    # ── Server ───────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def get_api_key_map(self) -> dict[str, str]:
        """Parse 'user_id:api_key' pairs into a lookup dict {api_key: user_id}."""
        key_map: dict[str, str] = {}
        if not self.api_keys:
            return key_map
        for entry in self.api_keys.split(","):
            entry = entry.strip()
            if ":" in entry:
                user_id, api_key = entry.split(":", 1)
                key_map[api_key.strip()] = user_id.strip()
        return key_map


settings = Settings()
