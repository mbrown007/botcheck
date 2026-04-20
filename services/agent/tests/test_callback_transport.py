from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from botcheck_scenarios import ConversationTurn

from src import callback_transport


def _transport() -> callback_transport.CallbackTransport:
    return callback_transport.CallbackTransport(
        botcheck_api_url="http://api.internal",
        harness_secret="secret-123",
        recording_upload_timeout_s=33.0,
        callbacks_total=object(),
        turns_total=object(),
    )


@pytest.mark.asyncio
async def test_post_with_retry_delegates_api_base_and_secret(monkeypatch) -> None:
    mock_post = AsyncMock()
    monkeypatch.setattr(callback_transport.callback_api, "post_with_retry", mock_post)

    transport = _transport()
    await transport.post_with_retry("/runs/run_1/fail", {"reason": "boom"})

    mock_post.assert_awaited_once_with(
        "/runs/run_1/fail",
        {"reason": "boom"},
        botcheck_api_url="http://api.internal",
        harness_secret="secret-123",
    )


@pytest.mark.asyncio
async def test_report_turn_delegates_metrics_and_post_fn(monkeypatch) -> None:
    mock_report = AsyncMock()
    monkeypatch.setattr(callback_transport.callback_api, "report_turn", mock_report)

    transport = _transport()
    turn = ConversationTurn(
        turn_id="t1",
        turn_number=1,
        speaker="harness",
        text="hello",
        audio_start_ms=10,
        audio_end_ms=120,
    )

    await transport.report_turn(
        "run_1",
        turn,
        visit=2,
        branch_condition_matched="billing",
        branch_response_snippet="I need billing support",
    )

    kwargs = mock_report.await_args.kwargs
    assert mock_report.await_count == 1
    assert kwargs["post_with_retry_fn"] == transport.post_with_retry
    assert kwargs["visit"] == 2
    assert kwargs["branch_condition_matched"] == "billing"
    assert kwargs["branch_response_snippet"] == "I need billing support"


@pytest.mark.asyncio
async def test_upload_run_recording_delegates_timeout(monkeypatch, tmp_path: Path) -> None:
    mock_upload = AsyncMock()
    monkeypatch.setattr(callback_transport.callback_api, "upload_run_recording", mock_upload)

    transport = _transport()
    wav_path = tmp_path / "run.wav"
    wav_path.write_bytes(b"RIFF")

    await transport.upload_run_recording(
        "run_2",
        wav_path=wav_path,
        duration_ms=1234,
    )

    mock_upload.assert_awaited_once_with(
        "run_2",
        wav_path=wav_path,
        duration_ms=1234,
        botcheck_api_url="http://api.internal",
        harness_secret="secret-123",
        timeout_s=33.0,
    )


@pytest.mark.asyncio
async def test_fail_run_with_details_delegates_error_code(monkeypatch) -> None:
    mock_fail = AsyncMock()
    monkeypatch.setattr(callback_transport.callback_api, "fail_run_with_details", mock_fail)

    transport = _transport()
    await transport.fail_run_with_details(
        "run_3",
        "runtime unavailable",
        end_reason="service_not_available",
        error_code="ai_caller_unavailable",
    )

    mock_fail.assert_awaited_once()
    kwargs = mock_fail.await_args.kwargs
    assert kwargs["error_code"] == "ai_caller_unavailable"
    assert kwargs["post_with_retry_fn"] == transport.post_with_retry
