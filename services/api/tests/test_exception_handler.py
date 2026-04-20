"""Tests for centralized RFC 7807 error handling."""

from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient

from botcheck_api.config import settings
from botcheck_api.exceptions import ApiProblem
from botcheck_api.main import api_problem_handler, http_exception_as_problem, app

from factories import make_run_create_payload, make_sip_scenario_yaml, make_scenario_upload_payload


PROBLEM_CONTENT_TYPE = "application/problem+json"


def _mini_app():
    """Isolated FastAPI app with only the exception handlers under test."""
    from botcheck_api.exceptions import ApiProblem
    from fastapi import FastAPI, HTTPException

    mini = FastAPI()
    mini.add_exception_handler(ApiProblem, api_problem_handler)
    mini.add_exception_handler(HTTPException, http_exception_as_problem)

    @mini.get("/_raise_problem")
    async def _trigger_problem():
        raise ApiProblem(
            status=429,
            error_code="test_code",
            detail="test detail",
            title="Test Title",
            headers={"X-Test": "yes"},
        )

    @mini.get("/_raise_http")
    async def _trigger_http():
        raise HTTPException(status_code=404, detail="not here")

    return mini


class TestApiProblemHandler:

    async def test_api_problem_returns_rfc7807(self):
        """ApiProblem raised in a route returns RFC 7807 shape with error_code."""
        mini = _mini_app()
        async with AsyncClient(
            transport=ASGITransport(app=mini), base_url="http://test"
        ) as ac:
            resp = await ac.get("/_raise_problem")
        assert resp.status_code == 429
        assert PROBLEM_CONTENT_TYPE in resp.headers.get("content-type", "")
        assert resp.headers.get("x-test") == "yes"
        body = resp.json()
        assert body["status"] == 429
        assert body["detail"] == "test detail"
        assert body["error_code"] == "test_code"
        assert body["title"] == "Test Title"
        assert body["type"] == "about:blank"

    async def test_http_exception_wrapped_as_problem(self):
        """HTTPException is wrapped into RFC 7807 shape without error_code."""
        mini = _mini_app()
        async with AsyncClient(
            transport=ASGITransport(app=mini), base_url="http://test"
        ) as ac:
            resp = await ac.get("/_raise_http")
        assert resp.status_code == 404
        assert PROBLEM_CONTENT_TYPE in resp.headers.get("content-type", "")
        body = resp.json()
        assert body["status"] == 404
        assert isinstance(body["detail"], str)
        assert body["title"] == "Not Found"
        assert "error_code" not in body

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_sip_capacity_error_code(
        self,
        mock_lk_class,
        client,
        user_auth_headers,
        monkeypatch,
    ):
        """SIP capacity exhausted returns error_code sip_capacity_exhausted."""
        # Upload a SIP scenario first
        sip_yaml = make_sip_scenario_yaml()
        upload_resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(sip_yaml),
            headers=user_auth_headers,
        )
        assert upload_resp.status_code == 201
        scenario_id = upload_resp.json()["id"]

        monkeypatch.setattr(settings, "enable_outbound_sip", True)
        monkeypatch.setattr(settings, "sip_secret_provider", "env")
        monkeypatch.setattr(settings, "sip_trunk_id", "trunk-test")
        monkeypatch.setattr(settings, "sip_auth_username", "sip-user")
        monkeypatch.setattr(settings, "sip_auth_password", "sip-pass")
        monkeypatch.setattr(settings, "sip_destination_allowlist", ["test.example.com"])
        monkeypatch.setattr(
            "botcheck_api.runs.service_lifecycle.try_acquire_sip_slot",
            AsyncMock(return_value=False),
        )

        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(scenario_id),
            headers=user_auth_headers,
        )
        assert resp.status_code == 429
        body = resp.json()
        assert body["error_code"] == "sip_capacity_exhausted"
        assert PROBLEM_CONTENT_TYPE in resp.headers.get("content-type", "")
