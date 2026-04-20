from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from .metrics import SIP_CALL_OUTCOMES_TOTAL, TELEPHONY_MINUTES_TOTAL


async def finalize_run_media(
    *,
    run_id: str,
    room,
    bot_participant,
    is_sip: bool,
    call_started_monotonic: float,
    bot_listener,
    recorder,
    settings_obj,
    livekit_api_cls,
    room_participant_identity_cls,
    remove_participant_from_room_fn: Callable[..., Awaitable[None]],
    upload_run_recording_fn: Callable[..., Awaitable[None]],
    logger_obj: Any,
    participant_removal_enabled: bool = True,
) -> None:
    await bot_listener.stop()

    call_duration_s = time.monotonic() - call_started_monotonic
    telephony_provider = "livekit-sip" if is_sip else "internal"
    TELEPHONY_MINUTES_TOTAL.labels(
        provider=telephony_provider,
        direction="outbound",
    ).inc(call_duration_s / 60.0)
    if is_sip:
        SIP_CALL_OUTCOMES_TOTAL.labels(outcome="completed").inc()

    logger_obj.info("Run %s: recorder stats %s", run_id, recorder.stats)

    # Hang up the SIP call by removing the bot participant.
    if participant_removal_enabled:
        try:
            await remove_participant_from_room_fn(
                room_name=room.name,
                participant_identity=bot_participant.identity,
                livekit_api_cls=livekit_api_cls,
                room_participant_identity_cls=room_participant_identity_cls,
                livekit_url=settings_obj.livekit_url,
                livekit_api_key=settings_obj.livekit_api_key,
                livekit_api_secret=settings_obj.livekit_api_secret,
            )
            logger_obj.info("Run %s: SIP call ended (participant removed)", run_id)
        except Exception:
            logger_obj.warning("Run %s: could not remove bot participant to end call", run_id)
    else:
        logger_obj.info("Run %s: skipping bot participant removal for remote transport", run_id)

    if settings_obj.recording_upload_enabled:
        wav_path: Path | None = await recorder.write_wav(run_id)
        if wav_path is not None:
            try:
                await upload_run_recording_fn(
                    run_id,
                    wav_path=wav_path,
                    duration_ms=recorder.duration_ms,
                )
                logger_obj.info(
                    "Run %s: call recording uploaded (%s, %dms)",
                    run_id,
                    wav_path.name,
                    recorder.duration_ms,
                )
            except Exception:
                logger_obj.warning("Run %s: call recording upload failed", run_id, exc_info=True)
            finally:
                try:
                    wav_path.unlink(missing_ok=True)
                except Exception:
                    logger_obj.debug(
                        "Failed to clean temp recording file %s",
                        wav_path,
                        exc_info=True,
                    )
        else:
            logger_obj.info("Run %s: recording not uploaded (no wav artifact created)", run_id)
    else:
        logger_obj.info("Run %s: recording upload disabled by config", run_id)
