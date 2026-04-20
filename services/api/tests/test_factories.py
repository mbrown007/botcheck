"""Tests for shared API test factories."""

from __future__ import annotations

import yaml

from botcheck_api.config import settings

from factories import (
    make_conversation_turn,
    make_run_patch_payload,
    make_run_retention_sweep_payload,
    make_scenario_cache_sync_payload,
    make_scenario_generate_payload,
    make_login_payload,
    make_run_complete_payload,
    make_scenario_dict,
    make_scenario_yaml,
)


class TestScenarioFactories:
    def test_make_scenario_yaml_emits_expected_defaults(self):
        loaded = yaml.safe_load(make_scenario_yaml())
        assert loaded["id"] == "test-jailbreak"
        assert loaded["bot"]["protocol"] == "mock"
        assert len(loaded["turns"]) == 2

    def test_make_scenario_dict_deep_merges_overrides(self):
        payload = make_scenario_dict(
            overrides={"bot": {"protocol": "sip"}, "config": {"max_total_turns": 12}}
        )
        assert payload["bot"]["protocol"] == "sip"
        assert payload["bot"]["endpoint"] == "sip:bot@test.example.com"
        assert payload["config"]["max_total_turns"] == 12


class TestRunFactories:
    def test_make_run_complete_payload_copies_conversation(self):
        conversation = [make_conversation_turn(turn_id="t1", text="hello")]
        payload = make_run_complete_payload(conversation=conversation)
        conversation[0]["text"] = "mutated"
        assert payload["conversation"][0]["text"] == "hello"

    def test_make_run_patch_payload_accepts_arbitrary_fields(self):
        payload = make_run_patch_payload(gate_result="passed", summary="ok")
        assert payload == {"gate_result": "passed", "summary": "ok"}

    def test_make_run_retention_sweep_payload_handles_optional_fields(self):
        payload = make_run_retention_sweep_payload(limit=100, dry_run=True)
        assert payload == {"limit": 100, "dry_run": True}


class TestScenarioOperationFactories:
    def test_make_scenario_generate_payload_defaults(self):
        payload = make_scenario_generate_payload()
        assert payload["target_system_prompt"]
        assert payload["user_objective"] == "Test"
        assert payload["count"] == 1

    def test_make_scenario_cache_sync_payload_uses_tenant_default(self):
        payload = make_scenario_cache_sync_payload("v1", cache_status="partial")
        assert payload["tenant_id"] == settings.tenant_id
        assert payload["scenario_version_hash"] == "v1"
        assert payload["cache_status"] == "partial"


class TestAuthFactories:
    def test_make_login_payload_uses_seed_defaults(self):
        payload = make_login_payload()
        assert payload["email"] == settings.local_auth_email
        assert payload["password"] == settings.local_auth_password
        assert payload["tenant_id"] == settings.tenant_id
