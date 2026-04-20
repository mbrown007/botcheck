"""Persona-related DSL models and enums."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class PersonaMood(str, Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    ANGRY = "angry"
    FRUSTRATED = "frustrated"
    IMPATIENT = "impatient"


class ResponseStyle(str, Enum):
    FORMAL = "formal"
    CASUAL = "casual"
    CURT = "curt"
    VERBOSE = "verbose"


class PersonaConfig(BaseModel):
    """Harness persona profile used to shape caller tone and style."""

    mood: PersonaMood = PersonaMood.NEUTRAL
    response_style: ResponseStyle = ResponseStyle.CASUAL


__all__ = [
    "PersonaMood",
    "ResponseStyle",
    "PersonaConfig",
]
