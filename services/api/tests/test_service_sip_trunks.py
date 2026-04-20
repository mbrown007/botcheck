from __future__ import annotations

from types import SimpleNamespace

import pytest

from botcheck_api.packs import service_sip_trunks as mod


class _FakeSipService:
    def __init__(self, response):
        self._response = response
        self.calls: list[object] = []

    async def list_outbound_trunk(self, request):
        self.calls.append(request)
        return self._response


class _FakeLiveKitAPI:
    last_instance: "_FakeLiveKitAPI | None" = None

    def __init__(self, *args, **kwargs):
        self.sip = _FakeSipService(
            SimpleNamespace(
                items=[
                    SimpleNamespace(
                        trunk_id="trunk-1",
                        name="Carrier One",
                        address="carrier.example.com",
                        transport="SIP_TRANSPORT_TLS",
                        numbers=["+15550001111"],
                        metadata={"region": "eu-west-1"},
                    )
                ]
            )
        )
        _FakeLiveKitAPI.last_instance = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


@pytest.mark.asyncio
async def test_discover_livekit_sip_trunks_uses_top_level_request_class(monkeypatch):
    class _TopLevelRequest:
        pass

    monkeypatch.setattr(
        mod,
        "lk_api",
        SimpleNamespace(
            LiveKitAPI=_FakeLiveKitAPI,
            ListSIPOutboundTrunkRequest=_TopLevelRequest,
        ),
    )

    rows = await mod.discover_livekit_sip_trunks(livekit_api_cls=_FakeLiveKitAPI)

    assert [row.trunk_id for row in rows] == ["trunk-1"]
    assert isinstance(_FakeLiveKitAPI.last_instance.sip.calls[0], _TopLevelRequest)


@pytest.mark.asyncio
async def test_discover_livekit_sip_trunks_falls_back_to_legacy_sip_namespace(monkeypatch):
    class _LegacyRequest:
        pass

    monkeypatch.setattr(
        mod,
        "lk_api",
        SimpleNamespace(
            LiveKitAPI=_FakeLiveKitAPI,
            sip=SimpleNamespace(ListSIPOutboundTrunkRequest=_LegacyRequest),
        ),
    )

    rows = await mod.discover_livekit_sip_trunks(livekit_api_cls=_FakeLiveKitAPI)

    assert [row.trunk_id for row in rows] == ["trunk-1"]
    assert isinstance(_FakeLiveKitAPI.last_instance.sip.calls[0], _LegacyRequest)
