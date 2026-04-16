"""
SecondCortex backend settings loaded from environment variables.

Current architecture:
  - OpenAI API (API-key billing) is the primary provider for chat + embeddings.
  - Azure AI services are intentionally not used for inference.
"""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Provider routing (task-aware)
    llm_provider_default: str = Field(
        "openai",
        validation_alias=AliasChoices("LLM_PROVIDER_DEFAULT", "LLM_PROVIDER"),
    )
    llm_provider_retriever: str = Field("", validation_alias="LLM_PROVIDER_RETRIEVER")
    llm_provider_planner: str = Field("", validation_alias="LLM_PROVIDER_PLANNER")
    llm_provider_executor: str = Field("", validation_alias="LLM_PROVIDER_EXECUTOR")
    llm_provider_simulator: str = Field("", validation_alias="LLM_PROVIDER_SIMULATOR")
    llm_provider_archaeology: str = Field("", validation_alias="LLM_PROVIDER_ARCHAEOLOGY")
    llm_provider_embeddings: str = Field("", validation_alias="LLM_PROVIDER_EMBEDDINGS")

    llm_fallback_provider_retriever: str = Field("", validation_alias="LLM_FALLBACK_PROVIDER_RETRIEVER")
    llm_fallback_provider_planner: str = Field("", validation_alias="LLM_FALLBACK_PROVIDER_PLANNER")
    llm_fallback_provider_executor: str = Field("", validation_alias="LLM_FALLBACK_PROVIDER_EXECUTOR")
    llm_fallback_provider_simulator: str = Field("", validation_alias="LLM_FALLBACK_PROVIDER_SIMULATOR")
    llm_fallback_provider_archaeology: str = Field("", validation_alias="LLM_FALLBACK_PROVIDER_ARCHAEOLOGY")
    llm_fallback_provider_embeddings: str = Field("", validation_alias="LLM_FALLBACK_PROVIDER_EMBEDDINGS")

    # OpenAI API (primary)
    openai_api_key: str = Field("", validation_alias=AliasChoices("OPENAI_API_KEY", "OPENAI_TOKEN"))
    openai_api_base_url: str = Field(
        "",
        validation_alias=AliasChoices("OPENAI_API_BASE_URL", "OPENAI_BASE_URL", "OPENAI_BASE"),
    )
    openai_chat_model: str = Field(
        "gpt-4o",
        validation_alias=AliasChoices("OPENAI_CHAT_MODEL", "OPENAI_MODEL", "OPENAI_CHAT"),
    )
    openai_embedding_model: str = Field(
        "text-embedding-3-small",
        validation_alias=AliasChoices("OPENAI_EMBEDDING_MODEL", "OPENAI_EMBEDDING"),
    )

    # GitHub Models (kept for rollback and plug-and-play migration)
    github_token: str = Field("", validation_alias="GITHUB_TOKEN")
    github_models_endpoint: str = "https://models.inference.ai.azure.com"
    github_models_chat_model: str = "gpt-4o"
    github_models_embedding_model: str = "text-embedding-3-small"

    # Groq (kept for rollback and fast-provider overrides)
    groq_api_key: str = Field("", validation_alias="GROQ_API_KEY")
    groq_model: str = "llama-3.1-8b-instant"
    groq_endpoint: str = "https://api.groq.com/openai/v1"

    # Rate limiting controls (provider-aware)
    llm_rate_limit_default_per_minute: int = Field(60, validation_alias="LLM_RATE_LIMIT_DEFAULT_PER_MINUTE")
    llm_rate_limit_groq_per_minute: int = Field(12, validation_alias="LLM_RATE_LIMIT_GROQ_PER_MINUTE")
    llm_rate_limit_openai_per_minute: int = Field(120, validation_alias="LLM_RATE_LIMIT_OPENAI_PER_MINUTE")
    llm_rate_limit_github_models_per_minute: int = Field(60, validation_alias="LLM_RATE_LIMIT_GITHUB_MODELS_PER_MINUTE")
    llm_rate_limit_max_retries: int = Field(2, validation_alias="LLM_RATE_LIMIT_MAX_RETRIES")

    # ChromaDB storage (primary local store for snapshots + facts)
    # Azure App Service persistent path: /home/chroma_db
    # Local default: ./chroma_db
    chroma_db_path: str = "./chroma_db"

    # CosmosDB settings (legacy; local ChromaDB is the active snapshot store).
    cosmosdb_endpoint: str = Field("", validation_alias="COSMOSDB_ENDPOINT")
    cosmosdb_key: str = Field("", validation_alias="COSMOSDB_KEY")
    cosmosdb_database_name: str = Field("secondcortex", validation_alias="COSMOSDB_DATABASE_NAME")
    cosmosdb_container_name: str = Field("snapshots", validation_alias="COSMOSDB_CONTAINER_NAME")

    # Azure AI Search settings retained for compatibility; ChromaDB is primary.
    azure_search_endpoint: str = Field("", validation_alias="AZURE_SEARCH_ENDPOINT")
    azure_search_api_key: str = Field("", validation_alias="AZURE_SEARCH_API_KEY")
    azure_search_index_name: str = Field("snapshots", validation_alias="AZURE_SEARCH_INDEX_NAME")

    # JWT auth
    jwt_secret: str = Field("", validation_alias="JWT_SECRET")
    pm_guest_enabled: bool = Field(True, validation_alias="PM_GUEST_ENABLED")
    pm_guest_team_id: str = Field("", validation_alias="PM_GUEST_TEAM_ID")
    pm_guest_display_name: str = Field("PM Guest", validation_alias="PM_GUEST_DISPLAY_NAME")
    pm_guest_email: str = Field("pm-guest@secondcortex.local", validation_alias="PM_GUEST_EMAIL")
    pm_guest_token_expiry_seconds: int = Field(8 * 3600, validation_alias="PM_GUEST_TOKEN_EXPIRY_SECONDS")
    project_scoped_ingestion_enabled: bool = Field(False, validation_alias="PROJECT_SCOPED_INGESTION_ENABLED")

    # Human interaction harness (command gating + confirmation semantics)
    human_interaction_mode: str = Field("prompt", validation_alias="HUMAN_INTERACTION_MODE")
    human_interaction_max_actions: int = Field(8, validation_alias="HUMAN_INTERACTION_MAX_ACTIONS")
    human_interaction_deny_patterns: str = Field(
        "rm -rf,git reset --hard,del /f,format c:,shutdown,reboot,mkfs,dd if=",
        validation_alias="HUMAN_INTERACTION_DENY_PATTERNS",
    )

    # MCP hardening and rollout controls
    mcp_dns_rebinding_protection_enabled: bool = Field(
        True,
        validation_alias="MCP_DNS_REBINDING_PROTECTION_ENABLED",
    )
    mcp_allowed_hosts: str = Field("", validation_alias="MCP_ALLOWED_HOSTS")
    mcp_allowed_origins: str = Field("", validation_alias="MCP_ALLOWED_ORIGINS")
    mcp_legacy_tool_api_key_enabled: bool = Field(True, validation_alias="MCP_LEGACY_TOOL_API_KEY_ENABLED")
    mcp_max_top_k: int = Field(20, validation_alias="MCP_MAX_TOP_K")
    mcp_default_top_k: int = Field(5, validation_alias="MCP_DEFAULT_TOP_K")
    mcp_max_query_chars: int = Field(1000, validation_alias="MCP_MAX_QUERY_CHARS")
    mcp_rate_limit_per_minute: int = Field(60, validation_alias="MCP_RATE_LIMIT_PER_MINUTE")
    mcp_key_ttl_days: int = Field(90, validation_alias="MCP_KEY_TTL_DAYS")
    mcp_task_summary_cache_enabled: bool = Field(True, validation_alias="MCP_TASK_SUMMARY_CACHE_ENABLED")
    mcp_task_summary_ttl_seconds: int = Field(900, validation_alias="MCP_TASK_SUMMARY_TTL_SECONDS")
    mcp_task_summary_default_max_tokens: int = Field(
        1000,
        validation_alias="MCP_TASK_SUMMARY_DEFAULT_MAX_TOKENS",
    )
    mcp_external_ingestion_enabled: bool = Field(True, validation_alias="MCP_EXTERNAL_INGESTION_ENABLED")
    mcp_external_slack_enabled: bool = Field(False, validation_alias="MCP_EXTERNAL_SLACK_ENABLED")
    mcp_external_document_enabled: bool = Field(False, validation_alias="MCP_EXTERNAL_DOCUMENT_ENABLED")
    mcp_external_max_messages: int = Field(50, validation_alias="MCP_EXTERNAL_MAX_MESSAGES")
    mcp_search_memory_cache_enabled: bool = Field(True, validation_alias="MCP_SEARCH_MEMORY_CACHE_ENABLED")
    mcp_search_memory_ttl_seconds: int = Field(300, validation_alias="MCP_SEARCH_MEMORY_TTL_SECONDS")
    mcp_search_memory_batch_max_queries: int = Field(8, validation_alias="MCP_SEARCH_MEMORY_BATCH_MAX_QUERIES")
    mcp_response_soft_char_limit: int = Field(24000, validation_alias="MCP_RESPONSE_SOFT_CHAR_LIMIT")

    # Azure AI Document Intelligence (external document ingestion)
    azure_document_intelligence_endpoint: str = Field(
        "",
        validation_alias="AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
    )
    azure_document_intelligence_key: str = Field("", validation_alias="AZURE_DOCUMENT_INTELLIGENCE_KEY")
    azure_document_intelligence_model_id: str = Field(
        "prebuilt-read",
        validation_alias="AZURE_DOCUMENT_INTELLIGENCE_MODEL_ID",
    )

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
