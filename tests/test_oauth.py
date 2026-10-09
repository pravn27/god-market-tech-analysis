from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from god_market_api.oauth import (
    KEYRING_SERVICE,
    KEYRING_TOKENS_ACCOUNT,
    KeyringTokenStorage,
    OfficialMCPOAuthCoordinator,
    OAuthStorageError,
    _shared_mcp_session,
    _SharedMCPSession,
)


class MemoryTokenStorage:
    def __init__(self, tokens=None, issued_at=None):
        self.tokens = tokens
        self.issued_at = issued_at
        self.client_info = OAuthClientInformationFull(
            client_id="local-client", redirect_uris=["http://127.0.0.1/callback"]
        )

    async def get_tokens(self):
        return self.tokens

    async def set_tokens(self, tokens):
        self.tokens = tokens
        self.issued_at = datetime.now(timezone.utc)

    async def get_token_issued_at(self):
        return self.issued_at

    async def get_client_info(self):
        return self.client_info

    async def set_client_info(self, client_info):
        self.client_info = client_info


def make_tokens(*, access="access-old", refresh="refresh-old", expires_in=3600):
    return OAuthToken(
        access_token=access,
        refresh_token=refresh,
        expires_in=expires_in,
    )


def test_status_reports_refresh_needed_near_expiry_without_exposing_credentials():
    storage = MemoryTokenStorage(
        make_tokens(), datetime.now(timezone.utc) - timedelta(seconds=3550)
    )
    coordinator = OfficialMCPOAuthCoordinator(storage=storage)

    state = asyncio_run(coordinator.status())

    assert state.status == "refresh_needed"
    assert "access-old" not in repr(state)
    assert "refresh-old" not in repr(state)


def test_status_requires_reauthorization_when_expired_without_refresh_token():
    storage = MemoryTokenStorage(
        make_tokens(refresh=None, expires_in=60), datetime.now(timezone.utc) - timedelta(minutes=2)
    )
    coordinator = OfficialMCPOAuthCoordinator(storage=storage)

    state = asyncio_run(coordinator.status())

    assert state.status == "reconnect_required"
    assert asyncio_run(coordinator.is_authenticated()) is False


def test_legacy_token_without_issuance_timestamp_is_refreshed_before_use():
    storage = MemoryTokenStorage(make_tokens(), issued_at=None)
    coordinator = OfficialMCPOAuthCoordinator(storage=storage)

    state = asyncio_run(coordinator.status())

    assert state.status == "refresh_needed"


def test_keyring_storage_persists_token_issuance_time(monkeypatch):
    keyring_values = {}
    monkeypatch.setattr(
        "god_market_api.oauth.keyring.set_password",
        lambda service, account, value: keyring_values.__setitem__((service, account), value),
    )
    monkeypatch.setattr(
        "god_market_api.oauth.keyring.get_password",
        lambda service, account: keyring_values.get((service, account)),
    )
    storage = KeyringTokenStorage()

    asyncio_run(storage.set_tokens(make_tokens()))
    issued_at = asyncio_run(storage.get_token_issued_at())
    loaded_tokens = asyncio_run(storage.get_tokens())

    assert keyring_values[(KEYRING_SERVICE, KEYRING_TOKENS_ACCOUNT)]
    assert json.loads(keyring_values[(KEYRING_SERVICE, KEYRING_TOKENS_ACCOUNT)])["token_issued_at"]
    assert issued_at is not None
    assert issued_at.tzinfo is not None
    assert loaded_tokens == make_tokens()


def test_refresh_replaces_access_token_and_rotates_refresh_token(monkeypatch):
    storage = MemoryTokenStorage(make_tokens(), datetime.now(timezone.utc) - timedelta(hours=2))
    coordinator = OfficialMCPOAuthCoordinator(storage=storage)
    requests = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "access_token": "access-new",
                "refresh_token": "refresh-new",
                "token_type": "Bearer",
                "expires_in": 1800,
            }

    class FakeHTTPClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, data):
            requests.append((url, data))
            return FakeResponse()

    async def metadata():
        return {"token_endpoint": "https://oauth.example/token"}

    monkeypatch.setattr(coordinator, "_metadata", metadata)
    monkeypatch.setattr("god_market_api.oauth.httpx.AsyncClient", lambda **kwargs: FakeHTTPClient())

    tokens = asyncio_run(coordinator._refresh_tokens())

    assert tokens.access_token == "access-new"
    assert tokens.refresh_token == "refresh-new"
    assert storage.tokens == tokens
    assert storage.issued_at is not None
    assert requests == [
        (
            "https://oauth.example/token",
            {"grant_type": "refresh_token", "refresh_token": "refresh-old", "client_id": "local-client"},
        )
    ]


def test_refresh_preserves_existing_refresh_token_when_server_does_not_rotate(monkeypatch):
    storage = MemoryTokenStorage(make_tokens(), datetime.now(timezone.utc) - timedelta(hours=2))
    coordinator = OfficialMCPOAuthCoordinator(storage=storage)

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "access-new", "token_type": "Bearer", "expires_in": 1800}

    class FakeHTTPClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, data):
            return FakeResponse()

    async def metadata():
        return {"token_endpoint": "https://oauth.example/token"}

    monkeypatch.setattr(coordinator, "_metadata", metadata)
    monkeypatch.setattr("god_market_api.oauth.httpx.AsyncClient", lambda **kwargs: FakeHTTPClient())

    tokens = asyncio_run(coordinator._refresh_tokens())

    assert tokens.access_token == "access-new"
    assert tokens.refresh_token == "refresh-old"


def test_invalid_refresh_grant_requires_manual_reauthorization(monkeypatch):
    storage = MemoryTokenStorage(make_tokens(), datetime.now(timezone.utc) - timedelta(hours=2))
    coordinator = OfficialMCPOAuthCoordinator(storage=storage)

    class FakeHTTPClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, data):
            request = httpx.Request("POST", url)
            response = httpx.Response(400, request=request, json={"error": "invalid_grant"})
            response.raise_for_status()

    async def metadata():
        return {"token_endpoint": "https://oauth.example/token"}

    monkeypatch.setattr(coordinator, "_metadata", metadata)
    monkeypatch.setattr("god_market_api.oauth.httpx.AsyncClient", lambda **kwargs: FakeHTTPClient())

    with pytest.raises(OAuthStorageError, match="authorization expired or was revoked") as error:
        asyncio_run(coordinator._refresh_tokens())

    assert coordinator._state.status == "reconnect_required"
    assert "refresh-old" not in str(error.value)


def test_call_tool_retries_once_after_unauthorized_response(monkeypatch):
    storage = MemoryTokenStorage(make_tokens(), datetime.now(timezone.utc))
    coordinator = OfficialMCPOAuthCoordinator(storage=storage)
    calls = []
    refreshed = make_tokens(access="access-new", refresh="refresh-new", expires_in=1800)

    async def call_once(name, arguments, access_token):
        calls.append(access_token)
        if len(calls) == 1:
            request = httpx.Request("POST", "https://mcp.tradingview.com/mcp")
            response = httpx.Response(401, request=request)
            raise httpx.HTTPStatusError("unauthorized", request=request, response=response)
        return {"result": "ok"}

    async def refresh(expected_access_token=None):
        await storage.set_tokens(refreshed)
        return refreshed

    monkeypatch.setattr(coordinator, "_call_tool_once", call_once)
    monkeypatch.setattr(coordinator, "_refresh_tokens", refresh)

    result = asyncio_run(coordinator.call_tool("get_ohlcv", {"symbol": "NASDAQ:NVDA"}))

    assert result == {"result": "ok"}
    assert calls == ["access-old", "access-new"]


def test_call_tool_uses_shared_session_until_it_fails(monkeypatch):
    coordinator = OfficialMCPOAuthCoordinator(storage=MemoryTokenStorage(make_tokens(), datetime.now(timezone.utc)))
    per_call = []

    class FakeSession:
        def __init__(self):
            self.calls = 0

        async def call_tool(self, name, arguments):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("429 Too Many Requests")
            return {"via": "shared"}

    async def call_once(name, arguments, access_token):
        per_call.append(name)
        return {"via": "per-call"}

    monkeypatch.setattr(coordinator, "_call_tool_once", call_once)
    session = FakeSession()

    async def run():
        _shared_mcp_session.set(_SharedMCPSession(session=session))
        first = await coordinator.call_tool("mcp-tv-get-ohlcv", {})
        with pytest.raises(RuntimeError):
            await coordinator.call_tool("mcp-tv-get-ohlcv", {})
        third = await coordinator.call_tool("mcp-tv-get-ohlcv", {})
        return first, third

    first, third = asyncio_run(run())

    assert first == {"via": "shared"}
    assert third == {"via": "per-call"}
    assert session.calls == 2
    assert per_call == ["mcp-tv-get-ohlcv"]


def test_shared_session_falls_back_to_per_call_sessions_when_it_cannot_open(monkeypatch):
    coordinator = OfficialMCPOAuthCoordinator(storage=MemoryTokenStorage(make_tokens(), datetime.now(timezone.utc)))

    def unavailable_transport(*args, **kwargs):
        raise httpx.ConnectError("offline")

    async def call_once(name, arguments, access_token):
        return {"via": "per-call"}

    monkeypatch.setattr("god_market_api.oauth.streamable_http_client", unavailable_transport)
    monkeypatch.setattr(coordinator, "_call_tool_once", call_once)

    async def run():
        async with coordinator.shared_session():
            return await coordinator.call_tool("mcp-tv-get-ohlcv", {})

    assert asyncio_run(run()) == {"via": "per-call"}


def test_parallel_refreshes_reuse_the_rotated_token(monkeypatch):
    storage = MemoryTokenStorage(make_tokens(), datetime.now(timezone.utc) - timedelta(hours=2))
    coordinator = OfficialMCPOAuthCoordinator(storage=storage)
    request_count = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "access_token": "access-new",
                "refresh_token": "refresh-new",
                "token_type": "Bearer",
                "expires_in": 1800,
            }

    class FakeHTTPClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, data):
            request_count.append(data)
            return FakeResponse()

    async def metadata():
        return {"token_endpoint": "https://oauth.example/token"}

    monkeypatch.setattr(coordinator, "_metadata", metadata)
    monkeypatch.setattr("god_market_api.oauth.httpx.AsyncClient", lambda **kwargs: FakeHTTPClient())

    async def refresh_twice():
        import asyncio

        return await asyncio.gather(
            coordinator._refresh_tokens(expected_access_token="access-old"),
            coordinator._refresh_tokens(expected_access_token="access-old"),
        )

    first, second = asyncio_run(refresh_twice())

    assert first.access_token == second.access_token == "access-new"
    assert len(request_count) == 1


def asyncio_run(awaitable):
    import asyncio

    return asyncio.run(awaitable)
