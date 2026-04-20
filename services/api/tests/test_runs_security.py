"""Tests for cross-tenant and idempotency run protections."""

from unittest.mock import patch

from botcheck_api.main import app

from factories import make_run_create_payload, make_run_turn_payload
from runs_test_helpers import _create_run, _livekit_mock, _other_tenant_headers

class TestCrossTenantIsolation:
    """A user from tenant B must not be able to read or mutate tenant A's runs."""

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_get_run_from_other_tenant_returns_404(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

        resp = await client.get(f"/runs/{run_id}", headers=_other_tenant_headers())
        # 403 from require_tenant_match OR 404 from get_run_for_tenant; either is acceptable.
        assert resp.status_code in (403, 404)

    async def test_create_run_with_mismatched_tenant_is_rejected(
        self,
        client,
        uploaded_scenario,
    ):
        resp = await client.post(
            "/runs/",
            json=make_run_create_payload(uploaded_scenario["id"]),
            headers=_other_tenant_headers(),
        )
        assert resp.status_code == 403

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_list_runs_does_not_leak_other_tenant_runs(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
    ):
        """Runs created by the default tenant must not appear in another tenant's listing."""
        mock_lk_class.return_value = _livekit_mock()
        await _create_run(client, uploaded_scenario["id"], user_auth_headers)

        resp = await client.get("/runs/", headers=_other_tenant_headers())
        # Either rejected by require_tenant_match (403) or returns an empty list.
        if resp.status_code == 200:
            assert resp.json() == []
        else:
            assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Duplicate-turn idempotency  (item 12)
# ---------------------------------------------------------------------------


class TestDuplicateTurnIdempotency:
    """Posting the same turn twice must not create a duplicate in the conversation."""

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_duplicate_turn_is_deduplicated(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

        turn_payload = make_run_turn_payload(
            turn_id="t1",
            turn_number=1,
            speaker="harness",
            text="Hello.",
            audio_start_ms=0,
            audio_end_ms=500,
        )
        # Post the same turn twice
        r1 = await client.post(f"/runs/{run_id}/turns", json=turn_payload, headers=harness_auth_headers)
        r2 = await client.post(f"/runs/{run_id}/turns", json=turn_payload, headers=harness_auth_headers)
        assert r1.status_code == 200
        assert r2.status_code == 200

        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        conversation = run_resp.json()["conversation"]
        # Exactly one turn with turn_id=t1
        matching = [t for t in conversation if t["turn_id"] == "t1"]
        assert len(matching) == 1

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_different_turn_numbers_are_not_deduplicated(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        """Turns with same turn_id but different turn_number should both be stored."""
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

        await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(
                turn_id="t1",
                turn_number=1,
                speaker="harness",
                text="Hello.",
                audio_start_ms=0,
                audio_end_ms=500,
            ),
            headers=harness_auth_headers,
        )
        await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(
                turn_id="t1",
                turn_number=2,
                speaker="harness",
                text="Hello again.",
                audio_start_ms=600,
                audio_end_ms=1200,
            ),
            headers=harness_auth_headers,
        )

        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        conversation = run_resp.json()["conversation"]
        assert len(conversation) == 2

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_duplicate_turn_does_not_duplicate_turn_executed_event(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

        payload = make_run_turn_payload(
            turn_id="t1",
            turn_number=1,
            speaker="harness",
            text="Hello.",
            audio_start_ms=0,
            audio_end_ms=500,
            visit=1,
        )
        first = await client.post(
            f"/runs/{run_id}/turns",
            json=payload,
            headers=harness_auth_headers,
        )
        second = await client.post(
            f"/runs/{run_id}/turns",
            json=payload,
            headers=harness_auth_headers,
        )
        assert first.status_code == 200
        assert second.status_code == 200

        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        events = run_resp.json()["events"]
        executed = [
            e
            for e in events
            if e["type"] == "turn_executed" and e.get("detail", {}).get("turn_id") == "t1"
        ]
        assert len(executed) == 1
        detail = executed[0]["detail"]
        assert detail["visit"] == 1
        assert detail["turn_number"] == 1

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_branch_decision_event_is_redacted_and_turn_payload_stays_clean(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

        resp = await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(
                turn_id="t1",
                turn_number=1,
                speaker="harness",
                text="Please route me to billing",
                audio_start_ms=0,
                audio_end_ms=600,
                visit=1,
                branch_condition_matched="billing",
                branch_response_snippet="Call me at four one five five five five one two one two",
            ),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 200

        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        data = run_resp.json()

        branch_events = [
            e
            for e in data["events"]
            if e["type"] == "branch_decision" and e.get("detail", {}).get("turn_id") == "t1"
        ]
        assert len(branch_events) == 1
        branch_detail = branch_events[0]["detail"]
        assert branch_detail["condition_matched"] == "billing"
        assert branch_detail["bot_response_snippet_redacted"] == "Call me at [PHONE]"

        stored_turn = data["conversation"][0]
        assert "visit" not in stored_turn
        assert "branch_condition_matched" not in stored_turn
        assert "branch_response_snippet" not in stored_turn

    @patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
    async def test_branch_decision_event_truncates_then_redacts_snippet(
        self,
        mock_lk_class,
        client,
        uploaded_scenario,
        user_auth_headers,
        harness_auth_headers,
    ):
        mock_lk_class.return_value = _livekit_mock()
        run_id = await _create_run(client, uploaded_scenario["id"], user_auth_headers)

        long_tail = " extra-context" * 30
        raw_snippet = f"Call me at 415-555-1212.{long_tail}"
        assert len(raw_snippet) > 120

        resp = await client.post(
            f"/runs/{run_id}/turns",
            json=make_run_turn_payload(
                turn_id="t1",
                turn_number=1,
                speaker="harness",
                text="Please route me to billing",
                audio_start_ms=0,
                audio_end_ms=600,
                visit=1,
                branch_condition_matched="billing",
                branch_response_snippet=raw_snippet,
            ),
            headers=harness_auth_headers,
        )
        assert resp.status_code == 200

        run_resp = await client.get(f"/runs/{run_id}", headers=user_auth_headers)
        assert run_resp.status_code == 200
        data = run_resp.json()

        branch_event = next(
            e
            for e in data["events"]
            if e["type"] == "branch_decision" and e.get("detail", {}).get("turn_id") == "t1"
        )
        snippet = branch_event["detail"]["bot_response_snippet_redacted"]
        assert isinstance(snippet, str)
        assert len(snippet) <= 120
        assert "[PHONE]" in snippet
        assert "415-555-1212" not in snippet
