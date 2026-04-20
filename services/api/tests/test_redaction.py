"""Tests for transcript redaction helpers."""

from botcheck_api.redaction import normalize_spoken_numbers, redact_text_pipeline


def test_normalize_spoken_numbers_compacts_digits():
    text = "call me at four one five five five five one two three four"
    assert normalize_spoken_numbers(text) == "call me at 4155551234"


def test_redact_text_pipeline_replaces_structured_pii():
    text = "ssn 123-45-6789 card 4111-1111-1111-1111 phone 415-555-1234"
    redacted = redact_text_pipeline(text)
    assert "[SSN]" in redacted
    assert "[CARD]" in redacted
    assert "[PHONE]" in redacted


def test_redact_text_pipeline_spoken_number_then_phone_redaction():
    text = "my number is four one five five five five one two three four"
    assert redact_text_pipeline(text) == "my number is [PHONE]"
