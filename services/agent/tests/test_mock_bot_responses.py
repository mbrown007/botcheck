from __future__ import annotations

from src import mock_bot_responses


def test_parse_response_map_json_returns_empty_for_invalid_json():
    parsed = mock_bot_responses.parse_response_map_json("{not json")
    assert parsed == {}


def test_parse_response_map_json_normalizes_keywords_and_filters_invalid_rows():
    parsed = mock_bot_responses.parse_response_map_json(
        """
        {
          "  Billing  ": "Billing lane",
          "TECHNICAL support": "Tech lane",
          "": "ignored-empty-key",
          "ignored_non_string": 123
        }
        """
    )
    assert parsed == {
        "billing": "Billing lane",
        "technical support": "Tech lane",
    }


def test_resolve_response_map_merges_defaults_with_overrides():
    resolved = mock_bot_responses.resolve_response_map(
        '{"billing":"Override billing","new-key":"new response"}'
    )
    assert resolved["billing"] == "Override billing"
    assert resolved["new-key"] == "new response"
    assert "technical" in resolved  # default preserved


def test_mock_response_keyword_match_is_case_and_whitespace_insensitive():
    response = mock_bot_responses.mock_response(
        "Can you connect me to TECHNICAL   support please?",
        response_map={
            "billing": "billing reply",
            "technical support": "technical reply",
        },
        default_response="fallback",
    )
    assert response == "technical reply"


def test_mock_response_falls_back_to_default():
    response = mock_bot_responses.mock_response(
        "",
        response_map={"billing": "billing reply"},
        default_response="fallback",
    )
    assert response == "fallback"
