from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Awaitable, Callable, Literal

from botcheck_scenarios import CircuitTransition

from .metrics import (
    PROVIDER_CIRCUIT_REJECTIONS_TOTAL,
    PROVIDER_CIRCUIT_TRANSITIONS_TOTAL,
    set_provider_circuit_state,
)

ProviderCircuitStateCallback = (
    Callable[
        ...,
        Awaitable[None],
    ]
    | None
)


class AgentTtsCircuitBridge:
    def __init__(
        self,
        *,
        provider: str = "openai",
        logger_obj,
        provider_circuit_state_callback: ProviderCircuitStateCallback = None,
    ) -> None:
        self._provider = provider.strip().lower() or "openai"
        self._logger = logger_obj
        self._provider_circuit_state_callback = provider_circuit_state_callback

    @staticmethod
    def _known_provider_state(value: str) -> Literal["open", "half_open", "closed"] | None:
        normalized = value.strip().lower()
        if normalized == "open":
            return "open"
        if normalized == "half_open":
            return "half_open"
        if normalized == "closed":
            return "closed"
        return None

    def _publish_provider_circuit_state(
        self,
        *,
        state: Literal["open", "half_open", "closed"],
    ) -> None:
        if self._provider_circuit_state_callback is None:
            return
        publish_task = asyncio.create_task(
            self._provider_circuit_state_callback(
                source="agent",
                provider=self._provider,
                service="tts",
                component="agent_live_tts",
                state=state,
                observed_at=datetime.now(UTC),
            )
        )

        def _on_publish_done(task: asyncio.Task[None]) -> None:
            try:
                task.result()
            except Exception:
                self._logger.warning(
                    "provider_circuit_snapshot_publish_failed source=agent provider=%s service=tts component=agent_live_tts",
                    self._provider,
                    exc_info=True,
                )

        publish_task.add_done_callback(_on_publish_done)

    def init_gauge(self) -> None:
        # Ensure the gauge is present even before the first breaker transition.
        set_provider_circuit_state(
            source="agent",
            provider=self._provider,
            service="tts",
            component="agent_live_tts",
            state="unknown",
        )

    def on_transition(self, transition: CircuitTransition) -> None:
        PROVIDER_CIRCUIT_TRANSITIONS_TOTAL.labels(
            provider=self._provider,
            service="tts",
            component="agent_live_tts",
            from_state=transition.from_state.value,
            to_state=transition.to_state.value,
        ).inc()
        self._logger.warning(
            "provider_circuit_transition provider=%s service=tts component=agent_live_tts from=%s to=%s reason=%s",
            self._provider,
            transition.from_state.value,
            transition.to_state.value,
            transition.reason,
        )
        state = self._known_provider_state(transition.to_state.value)
        if state is not None:
            set_provider_circuit_state(
                source="agent",
                provider=self._provider,
                service="tts",
                component="agent_live_tts",
                state=state,
            )
            self._publish_provider_circuit_state(state=state)

    def on_reject(self, state_obj) -> None:
        PROVIDER_CIRCUIT_REJECTIONS_TOTAL.labels(
            provider=self._provider,
            service="tts",
            component="agent_live_tts",
        ).inc()
        self._logger.warning(
            "provider_circuit_rejected provider=%s service=tts component=agent_live_tts",
            self._provider,
        )
        state = self._known_provider_state(str(getattr(state_obj, "value", state_obj)))
        if state is not None:
            set_provider_circuit_state(
                source="agent",
                provider=self._provider,
                service="tts",
                component="agent_live_tts",
                state=state,
            )
            self._publish_provider_circuit_state(state=state)


class AgentAiCallerCircuitBridge:
    def __init__(
        self,
        *,
        logger_obj,
        provider_circuit_state_callback: ProviderCircuitStateCallback = None,
    ) -> None:
        self._logger = logger_obj
        self._provider_circuit_state_callback = provider_circuit_state_callback

    @staticmethod
    def _known_provider_state(value: str) -> Literal["open", "half_open", "closed"] | None:
        normalized = value.strip().lower()
        if normalized == "open":
            return "open"
        if normalized == "half_open":
            return "half_open"
        if normalized == "closed":
            return "closed"
        return None

    def _publish_provider_circuit_state(
        self,
        *,
        state: Literal["open", "half_open", "closed"],
    ) -> None:
        if self._provider_circuit_state_callback is None:
            return
        publish_task = asyncio.create_task(
            self._provider_circuit_state_callback(
                source="agent",
                provider="openai",
                service="llm",
                component="agent_ai_caller",
                state=state,
                observed_at=datetime.now(UTC),
            )
        )

        def _on_publish_done(task: asyncio.Task[None]) -> None:
            try:
                task.result()
            except Exception:
                self._logger.warning(
                    "provider_circuit_snapshot_publish_failed source=agent provider=openai service=llm component=agent_ai_caller",
                    exc_info=True,
                )

        publish_task.add_done_callback(_on_publish_done)

    def init_gauge(self) -> None:
        set_provider_circuit_state(
            source="agent",
            provider="openai",
            service="llm",
            component="agent_ai_caller",
            state="unknown",
        )

    def on_transition(self, transition: CircuitTransition) -> None:
        PROVIDER_CIRCUIT_TRANSITIONS_TOTAL.labels(
            provider="openai",
            service="llm",
            component="agent_ai_caller",
            from_state=transition.from_state.value,
            to_state=transition.to_state.value,
        ).inc()
        self._logger.warning(
            "provider_circuit_transition provider=openai service=llm component=agent_ai_caller from=%s to=%s reason=%s",
            transition.from_state.value,
            transition.to_state.value,
            transition.reason,
        )
        state = self._known_provider_state(transition.to_state.value)
        if state is not None:
            set_provider_circuit_state(
                source="agent",
                provider="openai",
                service="llm",
                component="agent_ai_caller",
                state=state,
            )
            self._publish_provider_circuit_state(state=state)

    def on_reject(self, state_obj) -> None:
        PROVIDER_CIRCUIT_REJECTIONS_TOTAL.labels(
            provider="openai",
            service="llm",
            component="agent_ai_caller",
        ).inc()
        self._logger.warning(
            "provider_circuit_rejected provider=openai service=llm component=agent_ai_caller",
        )
        state = self._known_provider_state(str(getattr(state_obj, "value", state_obj)))
        if state is not None:
            set_provider_circuit_state(
                source="agent",
                provider="openai",
                service="llm",
                component="agent_ai_caller",
                state=state,
            )
            self._publish_provider_circuit_state(state=state)


class AgentSttCircuitBridge:
    def __init__(
        self,
        *,
        provider: str = "deepgram",
        logger_obj,
        provider_circuit_state_callback: ProviderCircuitStateCallback = None,
    ) -> None:
        self._provider = provider.strip().lower() or "deepgram"
        self._logger = logger_obj
        self._provider_circuit_state_callback = provider_circuit_state_callback
        self._state: str = "unknown"

    def _publish_provider_circuit_state(
        self,
        *,
        state: Literal["open", "half_open", "closed"],
    ) -> None:
        if self._provider_circuit_state_callback is None:
            return
        publish_task = asyncio.create_task(
            self._provider_circuit_state_callback(
                source="agent",
                provider=self._provider,
                service="stt",
                component="agent_live_stt",
                state=state,
                observed_at=datetime.now(UTC),
            )
        )

        def _on_publish_done(task: asyncio.Task[None]) -> None:
            try:
                task.result()
            except Exception:
                self._logger.warning(
                    "provider_circuit_snapshot_publish_failed source=agent provider=%s service=stt component=agent_live_stt",
                    self._provider,
                    exc_info=True,
                )

        publish_task.add_done_callback(_on_publish_done)

    def init_gauge(self) -> None:
        set_provider_circuit_state(
            source="agent",
            provider=self._provider,
            service="stt",
            component="agent_live_stt",
            state="unknown",
        )

    def _transition_to(
        self,
        state: Literal["open", "closed"],
        *,
        reason: str,
    ) -> None:
        previous_state = self._state
        if previous_state != state:
            PROVIDER_CIRCUIT_TRANSITIONS_TOTAL.labels(
                provider=self._provider,
                service="stt",
                component="agent_live_stt",
                from_state=previous_state,
                to_state=state,
            ).inc()
            self._logger.warning(
                "provider_circuit_transition provider=%s service=stt component=agent_live_stt from=%s to=%s reason=%s",
                self._provider,
                previous_state,
                state,
                reason,
            )
            self._state = state

        set_provider_circuit_state(
            source="agent",
            provider=self._provider,
            service="stt",
            component="agent_live_stt",
            state=state,
        )
        self._publish_provider_circuit_state(state=state)

    def mark_closed(self, *, reason: str = "available") -> None:
        self._transition_to("closed", reason=reason)

    def mark_open(self, *, reason: str) -> None:
        self._transition_to("open", reason=reason)


async def publish_harness_audio_track(
    *,
    room,
    rtc_module,
    recorder=None,
):
    """Create and publish the harness local audio track, return its source.

    If a recorder is provided and recording is enabled, wraps the source in a
    RecordingAudioSource proxy so every harness frame is also captured for the
    dual-channel recording.
    """
    from .audio import RecordingAudioSource

    audio_source = rtc_module.AudioSource(sample_rate=24000, num_channels=1)
    audio_track = rtc_module.LocalAudioTrack.create_audio_track("harness", audio_source)
    await room.local_participant.publish_track(
        audio_track,
        rtc_module.TrackPublishOptions(source=rtc_module.TrackSource.SOURCE_MICROPHONE),
    )
    if recorder is not None and recorder.enabled:
        return RecordingAudioSource(audio_source, recorder)
    return audio_source


async def remove_participant_from_room(
    *,
    room_name: str,
    participant_identity: str,
    livekit_api_cls,
    room_participant_identity_cls,
    livekit_url: str,
    livekit_api_key: str,
    livekit_api_secret: str,
) -> None:
    async with livekit_api_cls(
        url=livekit_url,
        api_key=livekit_api_key,
        api_secret=livekit_api_secret,
    ) as lkapi:
        await lkapi.room.remove_participant(
            room_participant_identity_cls(
                room=room_name,
                identity=participant_identity,
            )
        )
