"""Integration tests for app.routes.sensing — API endpoint tests."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.integration
class TestSensingRoute:
    @pytest.mark.asyncio
    async def test_generate_returns_tracking_id(
        self, async_client, auth_headers, populated_db, mock_sio
    ):
        with patch(
            "core.sensing.pipeline.run_sensing_pipeline",
            new_callable=AsyncMock,
        ):
            response = await async_client.post(
                "/sensing/generate",
                json={"domain": "Generative AI"},
                headers=auth_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert "tracking_id" in data
        assert "message" in data

    @pytest.mark.asyncio
    async def test_generate_requires_auth(self, async_client, patched_db, mock_sio):
        response = await async_client.post(
            "/sensing/generate", json={"domain": "AI"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_generate_with_custom_domain(
        self, async_client, auth_headers, populated_db, mock_sio
    ):
        with patch(
            "core.sensing.pipeline.run_sensing_pipeline",
            new_callable=AsyncMock,
        ):
            response = await async_client.post(
                "/sensing/generate",
                json={
                    "domain": "Quantum Computing",
                    "custom_requirements": "Focus on error correction",
                },
                headers=auth_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert "Quantum Computing" in data["message"]

    @pytest.mark.asyncio
    async def test_status_not_found(
        self, async_client, auth_headers, populated_db, mock_sio
    ):
        response = await async_client.get(
            "/sensing/status/nonexistent-id",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_status_requires_auth(self, async_client, patched_db, mock_sio):
        response = await async_client.get("/sensing/status/some-id")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_history_empty(
        self, async_client, auth_headers, populated_db, mock_sio
    ):
        response = await async_client.get(
            "/sensing/history",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["reports"] == []

    @pytest.mark.asyncio
    async def test_history_requires_auth(self, async_client, patched_db, mock_sio):
        response = await async_client.get("/sensing/history")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_nonexistent(
        self, async_client, auth_headers, populated_db, mock_sio
    ):
        response = await async_client.delete(
            "/sensing/report/nonexistent-id",
            headers=auth_headers,
        )
        # Should succeed even if nothing to delete
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_requires_auth(self, async_client, patched_db, mock_sio):
        response = await async_client.delete("/sensing/report/some-id")
        assert response.status_code == 401
