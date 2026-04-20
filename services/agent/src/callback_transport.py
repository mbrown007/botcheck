from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from botcheck_scenarios import ConversationTurn

from . import callbacks as callback_api


class CallbackTransport:
    def __init__(
        self,
        *,
        botcheck_api_url: str,
        harness_secret: str,
        recording_upload_timeout_s: float,
        callbacks_total,
        turns_total,
    ) -> None:
        self._botcheck_api_url = botcheck_api_url
        self._harness_secret = harness_secret
        self._recording_upload_timeout_s = recording_upload_timeout_s
        self._callbacks_total = callbacks_total
        self._turns_total = turns_total

    def api_headers(self) -> dict[str, str]:
        return callback_api.api_headers(harness_secret=self._harness_secret)

    @staticmethod
    def is_retryable(exc: BaseException) -> bool:
        return callback_api.is_retryable(exc)

    async def post_with_retry(self, path: str, payload: dict) -> None:
        await callback_api.post_with_retry(
            path,
            payload,
            botcheck_api_url=self._botcheck_api_url,
            harness_secret=self._harness_secret,
        )

    async def fetch_scenario(self, scenario_id: str):
        return await callback_api.fetch_scenario(
            scenario_id,
            botcheck_api_url=self._botcheck_api_url,
            harness_secret=self._harness_secret,
        )

    async def fetch_run_transport_context(self, run_id: str):
        return await callback_api.fetch_run_transport_context(
            run_id,
            botcheck_api_url=self._botcheck_api_url,
            harness_secret=self._harness_secret,
        )

    async def fetch_provider_runtime_context(
        self,
        *,
        tenant_id: str,
        runtime_scope: str,
        tts_voice: str | None,
        stt_provider: str | None,
        stt_model: str | None,
    ):
        return await callback_api.fetch_provider_runtime_context(
            tenant_id=tenant_id,
            runtime_scope=runtime_scope,
            tts_voice=tts_voice,
            stt_provider=stt_provider,
            stt_model=stt_model,
            botcheck_api_url=self._botcheck_api_url,
            harness_secret=self._harness_secret,
        )

    async def report_turn(
        self,
        run_id: str,
        turn: ConversationTurn,
        *,
        visit: int | None = None,
        branch_condition_matched: str | None = None,
        branch_response_snippet: str | None = None,
    ) -> None:
        await callback_api.report_turn(
            run_id,
            turn,
            visit=visit,
            branch_condition_matched=branch_condition_matched,
            branch_response_snippet=branch_response_snippet,
            post_with_retry_fn=self.post_with_retry,
            callbacks_total=self._callbacks_total,
            turns_total=self._turns_total,
        )

    async def post_playground_event(
        self,
        run_id: str,
        *,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        await callback_api.post_playground_event(
            run_id,
            event_type=event_type,
            payload=payload,
            post_with_retry_fn=self.post_with_retry,
            callbacks_total=self._callbacks_total,
        )

    async def complete_run(
        self,
        run_id: str,
        conversation: list[ConversationTurn],
        *,
        end_reason: str,
        end_source: str = "harness",
    ) -> None:
        await callback_api.complete_run(
            run_id,
            conversation,
            end_reason=end_reason,
            end_source=end_source,
            post_with_retry_fn=self.post_with_retry,
            callbacks_total=self._callbacks_total,
        )

    async def fail_run_with_details(
        self,
        run_id: str,
        reason: str,
        *,
        end_reason: str = "service_not_available",
        error_code: str | None = None,
        loop_guard: dict[str, object] | None = None,
    ) -> None:
        await callback_api.fail_run_with_details(
            run_id,
            reason,
            end_reason=end_reason,
            error_code=error_code,
            loop_guard=loop_guard,
            post_with_retry_fn=self.post_with_retry,
            callbacks_total=self._callbacks_total,
        )

    async def post_run_heartbeat(
        self,
        run_id: str,
        *,
        seq: int,
        sent_at: datetime,
        turn_number: int | None = None,
        listener_state: str | None = None,
    ) -> None:
        await callback_api.post_run_heartbeat(
            run_id,
            seq=seq,
            sent_at=sent_at,
            turn_number=turn_number,
            listener_state=listener_state,
            post_with_retry_fn=self.post_with_retry,
            callbacks_total=self._callbacks_total,
        )

    async def post_provider_circuit_state(
        self,
        *,
        source: Literal["agent", "judge", "api"],
        provider: str,
        service: str,
        component: str,
        state: Literal["open", "half_open", "closed"],
        observed_at: datetime | None = None,
    ) -> None:
        await callback_api.post_provider_circuit_state(
            source=source,
            provider=provider,
            service=service,
            component=component,
            state=state,
            observed_at=observed_at,
            post_with_retry_fn=self.post_with_retry,
            callbacks_total=self._callbacks_total,
        )

    async def upload_run_recording(
        self,
        run_id: str,
        *,
        wav_path: Path,
        duration_ms: int,
    ) -> None:
        await callback_api.upload_run_recording(
            run_id,
            wav_path=wav_path,
            duration_ms=duration_ms,
            botcheck_api_url=self._botcheck_api_url,
            harness_secret=self._harness_secret,
            timeout_s=self._recording_upload_timeout_s,
        )
