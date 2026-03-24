from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Load environment variables from .env file
env_file = BACKEND_ROOT / ".env"
if env_file.exists():
    load_dotenv(env_file)

# Prevent local .env from affecting unit tests unexpectedly.
os.environ.setdefault("PYTEST_RUNNING", "1")


@pytest.fixture(autouse=True)
def clear_llm_client_caches():
    import services.llm_client as llm_client

    llm_client._client_cache.clear()
    with llm_client._metrics_lock:
        llm_client._metrics.clear()
    yield
    llm_client._client_cache.clear()
