"""
SecondCortex backend settings loaded from environment variables.

Primary migration target:
  - Azure OpenAI v1 endpoint with managed identity -> key fallback.

Backward compatibility:
  - Legacy LLM_PROVIDER and AZURE_OPENAI_ENDPOINT style variables are still accepted.
"""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Provider routing (task-aware, with legacy fallback support)
    llm_provider_default: str = Field(
        "azure_openai",
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

    # GitHub Models (kept for rollback and plug-and-play migration)
    github_token: str = Field("", validation_alias="GITHUB_TOKEN")
    github_models_endpoint: str = "https://models.inference.ai.azure.com"
    github_models_chat_model: str = "gpt-4o"
    github_models_embedding_model: str = "text-embedding-3-small"

    # Groq (kept for rollback and fast-provider overrides)
    groq_api_key: str = Field("", validation_alias="GROQ_API_KEY")
    groq_model: str = "llama-3.1-8b-instant"
    groq_endpoint: str = "https://api.groq.com/openai/v1"

    # Azure OpenAI v1 settings
    azure_openai_base_url: str = Field(
        "",
        validation_alias=AliasChoices("AZURE_OPENAI_BASE_URL", "AZURE_OPENAI_ENDPOINT"),
    )
    azure_openai_auth_mode: str = Field(
        "managed_identity_then_key",
        validation_alias="AZURE_OPENAI_AUTH_MODE",
    )
    azure_openai_client_id: str = Field("", validation_alias="AZURE_OPENAI_CLIENT_ID")
    azure_openai_api_key: str = Field("", validation_alias="AZURE_OPENAI_API_KEY")
    azure_openai_token_scope: str = Field(
        "https://ai.azure.com/.default",
        validation_alias="AZURE_OPENAI_TOKEN_SCOPE",
    )

    # Legacy fields retained for compatibility with existing deployments/scripts.
    azure_openai_api_version: str = "2024-02-01"
    azure_openai_deployment: str = Field(
        "gpt-4o",
        validation_alias=AliasChoices("AZURE_OPENAI_DEPLOYMENT_DEFAULT", "AZURE_OPENAI_DEPLOYMENT"),
    )
    azure_openai_embedding_deployment: str = Field(
        "text-embedding-ada-002",
        validation_alias="AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
    )

    # Azure OpenAI per-capability deployment routing
    azure_openai_deployment_retriever: str = Field("", validation_alias="AZURE_OPENAI_DEPLOYMENT_RETRIEVER")
    azure_openai_deployment_planner: str = Field("", validation_alias="AZURE_OPENAI_DEPLOYMENT_PLANNER")
    azure_openai_deployment_executor: str = Field("", validation_alias="AZURE_OPENAI_DEPLOYMENT_EXECUTOR")
    azure_openai_deployment_simulator: str = Field("", validation_alias="AZURE_OPENAI_DEPLOYMENT_SIMULATOR")
    azure_openai_deployment_archaeology: str = Field("", validation_alias="AZURE_OPENAI_DEPLOYMENT_ARCHAEOLOGY")
    azure_openai_deployment_embeddings: str = Field(
        "",
        validation_alias="AZURE_OPENAI_DEPLOYMENT_EMBEDDINGS",
    )

    # Rate limiting controls (provider-aware)
    llm_rate_limit_default_per_minute: int = Field(60, validation_alias="LLM_RATE_LIMIT_DEFAULT_PER_MINUTE")
    llm_rate_limit_groq_per_minute: int = Field(12, validation_alias="LLM_RATE_LIMIT_GROQ_PER_MINUTE")
    llm_rate_limit_azure_openai_per_minute: int = Field(120, validation_alias="LLM_RATE_LIMIT_AZURE_OPENAI_PER_MINUTE")
    llm_rate_limit_github_models_per_minute: int = Field(60, validation_alias="LLM_RATE_LIMIT_GITHUB_MODELS_PER_MINUTE")
    llm_rate_limit_max_retries: int = Field(2, validation_alias="LLM_RATE_LIMIT_MAX_RETRIES")

    # ChromaDB storage
    # Azure App Service persistent path: /home/chroma_db
    # Local default: ./chroma_db
    chroma_db_path: str = "./chroma_db"

    # JWT auth
    jwt_secret: str = Field("", validation_alias="JWT_SECRET")
    pm_guest_enabled: bool = Field(True, validation_alias="PM_GUEST_ENABLED")
    pm_guest_team_id: str = Field("", validation_alias="PM_GUEST_TEAM_ID")
    pm_guest_display_name: str = Field("PM Guest", validation_alias="PM_GUEST_DISPLAY_NAME")
    pm_guest_email: str = Field("pm-guest@secondcortex.local", validation_alias="PM_GUEST_EMAIL")
    pm_guest_token_expiry_seconds: int = Field(8 * 3600, validation_alias="PM_GUEST_TOKEN_EXPIRY_SECONDS")
    project_scoped_ingestion_enabled: bool = Field(False, validation_alias="PROJECT_SCOPED_INGESTION_ENABLED")

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
