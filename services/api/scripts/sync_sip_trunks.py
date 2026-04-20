#!/usr/bin/env python3
"""Sync SIP trunk inventory from LiveKit into the BotCheck API database."""

from __future__ import annotations

from botcheck_api.admin import main


if __name__ == "__main__":
    raise SystemExit(main())
