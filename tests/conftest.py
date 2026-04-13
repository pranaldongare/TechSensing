"""
Root conftest.py — shared fixtures for TechSensing tests.
"""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# Env setup BEFORE any app imports
os.environ.update(
    {
        "SECRET_KEY": "test-secret-key-for-jwt",
        "MODE": "test",
        "API_KEY_1": "test-key-1",
        "API_KEY_2": "test-key-2",
        "API_KEY_3": "test-key-3",
        "API_KEY_4": "test-key-4",
        "API_KEY_5": "test-key-5",
        "API_KEY_6": "test-key-6",
        "OPENAI_API": "test-openai-key",
        "QUERY_URL": "http://localhost:11434",
        "VISION_URL": "http://localhost:11435",
        "MAIN_MODEL": "test-model",
    }
)


# ---------------------------------------------------------------------------
# JWT / Auth helpers
# ---------------------------------------------------------------------------
@pytest.fixture()
def jwt_secret():
    return "test-secret-key-for-jwt"


@pytest.fixture()
def sample_user_payload():
    """Standard JWT payload for a test user."""
    return {
        "userId": "user_test_123",
        "name": "Test User",
        "email": "test@example.com",
        "is_active": True,
    }


@pytest.fixture()
def auth_token(sample_user_payload, jwt_secret):
    """Generates a valid JWT token for test requests."""
    import jwt as pyjwt
    from datetime import timedelta

    payload = {
        **sample_user_payload,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return pyjwt.encode(payload, jwt_secret, algorithm="HS256")


@pytest.fixture()
def auth_headers(auth_token):
    """Returns headers dict with Bearer token."""
    return {"Authorization": f"Bearer {auth_token}"}


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------
@pytest.fixture()
def mock_sio():
    """Mock Socket.IO server to prevent real socket operations."""
    mock = AsyncMock()
    mock.emit = AsyncMock()
    with patch("app.socket_handler.sio", mock):
        yield mock


@pytest.fixture()
async def async_client(mock_sio):
    """
    Async HTTP client for FastAPI integration tests.
    """
    from app.main import fastapi_app

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# LLM mock
# ---------------------------------------------------------------------------
@pytest.fixture()
def mock_invoke_llm():
    """Patches invoke_llm globally and returns the mock for assertion."""
    with patch("core.llm.client.invoke_llm", new_callable=AsyncMock) as mock:
        yield mock
