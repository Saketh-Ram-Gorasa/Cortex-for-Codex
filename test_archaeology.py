import requests
from datetime import datetime

test_payload = {
    "filePath": "test.py",
    "symbolName": "test_func",
    "signature": "def test_func():",
    "commitHash": "abc123",
    "commitMessage": "test commit",
    "author": "Test User",
    "timestamp": datetime.now().isoformat()
}

headers = {
    "Authorization": "Bearer test-token-invalid"
}

try:
    r = requests.post(
        'http://localhost:8000/api/v1/decision-archaeology',
        json=test_payload,
        headers=headers,
        timeout=5
    )
    print(f"Status: {r.status_code}")
    print(f"Response headers: {r.headers.get('content-type', 'unknown')}")
    print(f"Response body (first 500 chars):\n{r.text[:500]}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
