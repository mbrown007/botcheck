from botcheck_api.runs.service import normalize_branch_snippet


def test_normalize_branch_snippet_returns_none_for_empty_or_non_string():
    assert normalize_branch_snippet(None) is None
    assert normalize_branch_snippet(123) is None
    assert normalize_branch_snippet("   ") is None


def test_normalize_branch_snippet_truncates_to_120_chars():
    snippet = "x" * 200
    out = normalize_branch_snippet(snippet)
    assert isinstance(out, str)
    assert len(out) == 120
    assert out == "x" * 120


def test_normalize_branch_snippet_applies_redaction_before_persist():
    out = normalize_branch_snippet("Call me at four one five five five five one two one two")
    assert out == "Call me at [PHONE]"
