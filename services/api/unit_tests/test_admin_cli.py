from __future__ import annotations

import argparse
import asyncio

import pytest

from botcheck_api import admin_cli


@pytest.mark.asyncio
async def test_main_async_closes_db_on_same_event_loop(monkeypatch: pytest.MonkeyPatch):
    loops: dict[str, int] = {}

    async def fake_run(args: argparse.Namespace) -> int:
        loops["run"] = id(asyncio.get_running_loop())
        return 7

    async def fake_close_db() -> None:
        loops["close"] = id(asyncio.get_running_loop())

    monkeypatch.setattr(admin_cli, "_run", fake_run)
    monkeypatch.setattr(admin_cli.database, "close_db", fake_close_db)

    result = await admin_cli._main_async(argparse.Namespace(command="sync-sip-trunks"))

    assert result == 7
    assert loops["run"] == loops["close"]


@pytest.mark.asyncio
async def test_main_async_closes_db_when_run_raises(monkeypatch: pytest.MonkeyPatch):
    loops: dict[str, int] = {}

    async def fake_run(args: argparse.Namespace) -> int:
        loops["run"] = id(asyncio.get_running_loop())
        raise RuntimeError("boom")

    async def fake_close_db() -> None:
        loops["close"] = id(asyncio.get_running_loop())

    monkeypatch.setattr(admin_cli, "_run", fake_run)
    monkeypatch.setattr(admin_cli.database, "close_db", fake_close_db)

    with pytest.raises(RuntimeError, match="boom"):
        await admin_cli._main_async(argparse.Namespace(command="rejudge-run"))

    assert loops["run"] == loops["close"]
