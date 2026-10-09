"""Application-owned OAuth support for the official TradingView MCP."""

import asyncio
import base64
import hashlib
import json
import logging
import secrets
from contextlib import AsyncExitStack, asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Optional
from urllib.parse import urlencode

import httpx
import keyring
from fastapi import HTTPException
from mcp import ClientSession
from mcp.client.auth.oauth2 import TokenStorage
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


OFFICIAL_MCP_URL = "https://mcp.tradingview.com/mcp"
OFFICIAL_OAUTH_METADATA_URL = "https://www.tradingview.com/.well-known/oauth-authorization-server"
KEYRING_SERVICE = "god-market-tech-analysis"
KEYRING_TOKENS_ACCOUNT = "tradingview-official.tokens"
KEYRING_CLIENT_ACCOUNT = "tradingview-official.client-info"
TOKEN_REFRESH_LEEWAY_SECONDS = 60
# Official MCP tool calls routinely take 3-5 s, so httpx's 5 s default read timeout is too short.
OFFICIAL_MCP_HTTP_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
OFFICIAL_MCP_READ_TIMEOUT = timedelta(seconds=30)

logger = logging.getLogger(__name__)


class OAuthStorageError(RuntimeError):
    """Raised when the operating-system credential store cannot be used."""


class KeyringTokenStorage(TokenStorage):
    """Persist OAuth tokens and dynamically registered client information locally."""

    @staticmethod
    def _load(account: str, model_type):
        try:
            value = keyring.get_password(KEYRING_SERVICE, account)
        except keyring.errors.KeyringError as error:
            raise OAuthStorageError("Unable to read the local operating-system keyring.") from error
        return model_type.model_validate_json(value) if value else None

    @staticmethod
    def _store(account: str, value) -> None:
        try:
            keyring.set_password(KEYRING_SERVICE, account, value.model_dump_json())
        except keyring.errors.KeyringError as error:
            raise OAuthStorageError("Unable to write to the local operating-system keyring.") from error

    async def get_tokens(self) -> Optional[OAuthToken]:
        return self._load(KEYRING_TOKENS_ACCOUNT, OAuthToken)

    async def set_tokens(self, tokens: OAuthToken) -> None:
        try:
            keyring.set_password(
                KEYRING_SERVICE,
                KEYRING_TOKENS_ACCOUNT,
                json.dumps(
                    {
                        **tokens.model_dump(),
                        "token_issued_at": datetime.now(timezone.utc).isoformat(),
                    }
                ),
            )
        except keyring.errors.KeyringError as error:
            raise OAuthStorageError("Unable to save OAuth credentials to the local operating-system keyring.") from error

    async def get_token_issued_at(self) -> Optional[datetime]:
        try:
            value = keyring.get_password(KEYRING_SERVICE, KEYRING_TOKENS_ACCOUNT)
        except keyring.errors.KeyringError as error:
            raise OAuthStorageError("Unable to read local OAuth token expiry metadata.") from error
        if not value:
            return None
        try:
            timestamp_value = json.loads(value).get("token_issued_at")
            timestamp = datetime.fromisoformat(timestamp_value) if timestamp_value else None
        except (TypeError, ValueError, AttributeError):
            return None
        if timestamp is None:
            return None
        return timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)

    async def get_client_info(self) -> Optional[OAuthClientInformationFull]:
        return self._load(KEYRING_CLIENT_ACCOUNT, OAuthClientInformationFull)

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._store(KEYRING_CLIENT_ACCOUNT, client_info)


@dataclass
class AuthorizationState:
    authorization_url: Optional[str] = None
    status: str = "starting"
    error: Optional[str] = None
    completed_at: Optional[datetime] = None
    tools: Optional[list] = None
    oauth_state: Optional[str] = None
    code_verifier: Optional[str] = None


@dataclass
class _SharedMCPSession:
    session: ClientSession
    healthy: bool = True


_shared_mcp_session: ContextVar[Optional[_SharedMCPSession]] = ContextVar("shared_mcp_session", default=None)


class OfficialMCPOAuthCoordinator:
    """Runs an explicit, local OAuth 2.1 authorization-code flow with PKCE."""

    def __init__(
        self,
        redirect_uri: str = "http://127.0.0.1:8000/api/v1/oauth/official/callback",
        storage: Optional[TokenStorage] = None,
    ) -> None:
        self._redirect_uri = redirect_uri
        self._storage = storage or KeyringTokenStorage()
        self._state = AuthorizationState()
        self._lock = asyncio.Lock()
        self._token_lock = asyncio.Lock()

    async def _metadata(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(OFFICIAL_OAUTH_METADATA_URL)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise OAuthStorageError("Unable to read TradingView OAuth metadata.") from error

    async def _ensure_client_registration(self, metadata: dict[str, Any]) -> OAuthClientInformationFull:
        client_info = await self._storage.get_client_info()
        if client_info:
            return client_info
        registration_endpoint = metadata.get("registration_endpoint")
        if not registration_endpoint:
            raise OAuthStorageError("TradingView did not provide an OAuth registration endpoint.")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    registration_endpoint,
                    json={
                        "client_name": "God Market Local MCP API",
                        "redirect_uris": [self._redirect_uri],
                        "grant_types": ["authorization_code", "refresh_token"],
                        "response_types": ["code"],
                        "token_endpoint_auth_method": "none",
                        "scope": "mcp:read mcp:tools",
                    },
                )
                response.raise_for_status()
                client_info = OAuthClientInformationFull.model_validate(response.json())
                client_info.issuer = metadata.get("issuer")
                await self._storage.set_client_info(client_info)
                return client_info
        except (httpx.HTTPError, ValueError) as error:
            raise OAuthStorageError("Unable to register the local OAuth client with TradingView.") from error

    @staticmethod
    def _pkce_challenge(verifier: str) -> str:
        digest = hashlib.sha256(verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    async def start(self) -> AuthorizationState:
        """Prepare, but never open, a user-approved TradingView authorization URL."""
        async with self._lock:
            if self._state.status == "awaiting_user" and self._state.authorization_url:
                return self._state
            try:
                metadata = await self._metadata()
                client_info = await self._ensure_client_registration(metadata)
                if not client_info.client_id or not metadata.get("authorization_endpoint"):
                    raise OAuthStorageError("TradingView OAuth metadata is incomplete.")
                verifier = secrets.token_urlsafe(64)
                oauth_state = secrets.token_urlsafe(32)
                parameters = {
                    "response_type": "code",
                    "client_id": client_info.client_id,
                    "redirect_uri": self._redirect_uri,
                    "scope": "mcp:read mcp:tools",
                    "state": oauth_state,
                    "code_challenge": self._pkce_challenge(verifier),
                    "code_challenge_method": "S256",
                    "resource": OFFICIAL_MCP_URL,
                }
                self._state = AuthorizationState(
                    authorization_url=f"{metadata['authorization_endpoint']}?{urlencode(parameters)}",
                    status="awaiting_user",
                    oauth_state=oauth_state,
                    code_verifier=verifier,
                )
            except OAuthStorageError as error:
                self._state = AuthorizationState(status="failed", error=str(error))
            return self._state

    async def _exchange_token_and_inventory(self, code: str) -> None:
        try:
            metadata = await self._metadata()
            client_info = await self._storage.get_client_info()
            if not client_info or not client_info.client_id or not self._state.code_verifier:
                raise OAuthStorageError("The local OAuth authorization state is incomplete.")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    metadata["token_endpoint"],
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "client_id": client_info.client_id,
                        "redirect_uri": self._redirect_uri,
                        "code_verifier": self._state.code_verifier,
                    },
                )
                response.raise_for_status()
                await self._storage.set_tokens(OAuthToken.model_validate(response.json()))
            self._state.code_verifier = None
            await self._inventory_tools()
            self._state.status = "connected"
            self._state.completed_at = datetime.now(timezone.utc)
        except Exception as error:
            self._state.status = "failed"
            self._state.error = str(error)

    async def complete_callback(self, code: str, state: Optional[str]) -> AuthorizationState:
        if self._state.status != "awaiting_user" or not self._state.oauth_state:
            raise HTTPException(status_code=409, detail="No OAuth authorization is awaiting a callback.")
        if not secrets.compare_digest(state or "", self._state.oauth_state):
            raise HTTPException(status_code=400, detail="The OAuth callback state did not match the local request.")
        self._state.status = "exchanging_token"
        asyncio.create_task(self._exchange_token_and_inventory(code))
        return self._state

    async def _inventory_tools(self) -> None:
        tokens = await self._storage.get_tokens()
        if not tokens:
            raise OAuthStorageError("TradingView OAuth token was not saved.")
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {tokens.access_token}"}, timeout=OFFICIAL_MCP_HTTP_TIMEOUT
        ) as client:
            async with streamable_http_client(OFFICIAL_MCP_URL, http_client=client) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self._state.tools = [tool.name for tool in tools.tools]

    async def status(self) -> AuthorizationState:
        tokens = await self._storage.get_tokens()
        if tokens:
            self._state.status = await self._token_status(tokens)
        return self._state

    async def _token_status(self, tokens: OAuthToken) -> str:
        if tokens.expires_in is None:
            return "authenticated"
        if not await self._tokens_need_refresh(tokens):
            return "authenticated"
        return "refresh_needed" if tokens.refresh_token else "reconnect_required"

    async def _token_expiry(self, tokens: OAuthToken) -> Optional[datetime]:
        if tokens.expires_in is None:
            return None
        get_issued_at = getattr(self._storage, "get_token_issued_at", None)
        if get_issued_at is None:
            return None
        issued_at = await get_issued_at()
        if issued_at is None:
            return None
        return issued_at + timedelta(seconds=tokens.expires_in)

    async def _tokens_need_refresh(self, tokens: OAuthToken) -> bool:
        if tokens.expires_in is None:
            return False
        expires_at = await self._token_expiry(tokens)
        if expires_at is None:
            # Older stored credentials have no issuance timestamp. Refresh before
            # use when possible rather than treating expires_in as a fresh TTL.
            return bool(tokens.refresh_token)
        return datetime.now(timezone.utc) >= expires_at - timedelta(seconds=TOKEN_REFRESH_LEEWAY_SECONDS)

    async def is_authenticated(self) -> bool:
        tokens = await self._storage.get_tokens()
        if not tokens:
            return False
        return await self._token_status(tokens) != "reconnect_required"

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a read-only official-MCP tool with application-owned credentials."""
        tokens = await self._storage.get_tokens()
        if not tokens:
            self._state.status = "reconnect_required"
            raise OAuthStorageError("Official MCP authorization is required before requesting market data.")

        shared = _shared_mcp_session.get()
        if shared is not None and shared.healthy:
            try:
                return await shared.session.call_tool(name, arguments)
            except Exception:
                # Stop routing through a failed shared session; retries open their own sessions.
                shared.healthy = False
                raise

        if await self._tokens_need_refresh(tokens):
            tokens = await self._refresh_tokens(expected_access_token=tokens.access_token)

        try:
            return await self._call_tool_once(name, arguments, tokens.access_token)
        except httpx.HTTPStatusError as error:
            if error.response.status_code != 401:
                raise
            tokens = await self._refresh_tokens(expected_access_token=tokens.access_token)
            return await self._call_tool_once(name, arguments, tokens.access_token)

    @asynccontextmanager
    async def shared_session(self) -> AsyncIterator[bool]:
        """Route call_tool through one MCP session for the duration of a batch.

        Opening a session per call costs several HTTP requests each and trips
        TradingView's 429 rate limit for a full watchlist refresh. Yields whether
        the shared session opened; if not, calls fall back to per-call sessions.
        """
        current = _shared_mcp_session.get()
        if current is not None:
            yield current.healthy
            return
        stack = AsyncExitStack()
        shared: Optional[_SharedMCPSession] = None
        try:
            tokens = await self._storage.get_tokens()
            if tokens:
                if await self._tokens_need_refresh(tokens):
                    tokens = await self._refresh_tokens(expected_access_token=tokens.access_token)
                client = await stack.enter_async_context(
                    httpx.AsyncClient(
                        headers={"Authorization": f"Bearer {tokens.access_token}"}, timeout=OFFICIAL_MCP_HTTP_TIMEOUT
                    )
                )
                read_stream, write_stream, _ = await stack.enter_async_context(
                    streamable_http_client(OFFICIAL_MCP_URL, http_client=client)
                )
                session = await stack.enter_async_context(
                    ClientSession(read_stream, write_stream, read_timeout_seconds=OFFICIAL_MCP_READ_TIMEOUT)
                )
                await session.initialize()
                shared = _SharedMCPSession(session=session)
                if not self._state.tools:
                    self._state.tools = [tool.name for tool in (await session.list_tools()).tools]
        except Exception:
            logger.warning("Shared official MCP session could not be opened; using per-call sessions.")
            await self._close_quietly(stack)
            stack = AsyncExitStack()
            shared = None

        token = _shared_mcp_session.set(shared)
        try:
            yield shared is not None
        finally:
            _shared_mcp_session.reset(token)
            await self._close_quietly(stack)

    @staticmethod
    async def _close_quietly(stack: AsyncExitStack) -> None:
        try:
            await stack.aclose()
        except BaseException as error:  # noqa: BLE001 - teardown of a dead session must not fail the batch
            if isinstance(error, asyncio.CancelledError):
                raise
            logger.debug("Ignoring error while closing the shared official MCP session.", exc_info=True)

    async def _call_tool_once(self, name: str, arguments: dict[str, Any], access_token: str) -> Any:
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {access_token}"}, timeout=OFFICIAL_MCP_HTTP_TIMEOUT
        ) as client:
            async with streamable_http_client(OFFICIAL_MCP_URL, http_client=client) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    return await session.call_tool(name, arguments)

    async def _refresh_tokens(self, expected_access_token: Optional[str] = None) -> OAuthToken:
        """Refresh an expiring token once, serializing concurrent callers."""
        async with self._token_lock:
            tokens = await self._storage.get_tokens()
            if not tokens:
                self._state.status = "reconnect_required"
                raise OAuthStorageError("Official MCP authorization is required before requesting market data.")
            if expected_access_token and tokens.access_token != expected_access_token:
                return tokens
            if not tokens.refresh_token:
                self._state.status = "reconnect_required"
                raise OAuthStorageError("Official MCP authorization expired; reconnect TradingView.")

            try:
                metadata = await self._metadata()
                client_info = await self._storage.get_client_info()
                token_endpoint = metadata.get("token_endpoint")
                if not token_endpoint or not client_info or not client_info.client_id:
                    raise OAuthStorageError("TradingView OAuth refresh configuration is incomplete.")
                async with httpx.AsyncClient(timeout=15) as client:
                    response = await client.post(
                        token_endpoint,
                        data={
                            "grant_type": "refresh_token",
                            "refresh_token": tokens.refresh_token,
                            "client_id": client_info.client_id,
                        },
                    )
                    response.raise_for_status()
                    refreshed_tokens = OAuthToken.model_validate(response.json())
            except httpx.HTTPStatusError as error:
                if error.response.status_code == 400:
                    try:
                        oauth_error = error.response.json().get("error")
                    except (ValueError, AttributeError):
                        oauth_error = None
                    if oauth_error == "invalid_grant":
                        self._state.status = "reconnect_required"
                        raise OAuthStorageError("TradingView authorization expired or was revoked; reconnect required.") from error
                self._state.status = "refresh_needed"
                raise OAuthStorageError("Unable to refresh the TradingView connection; retry later.") from error
            except OAuthStorageError:
                self._state.status = "refresh_needed"
                raise
            except (httpx.HTTPError, ValueError) as error:
                self._state.status = "refresh_needed"
                raise OAuthStorageError("Unable to refresh the TradingView connection; retry later.") from error

            if refreshed_tokens.refresh_token is None:
                refreshed_tokens.refresh_token = tokens.refresh_token
            if refreshed_tokens.scope is None:
                refreshed_tokens.scope = tokens.scope
            await self._storage.set_tokens(refreshed_tokens)
            self._state.status = "authenticated"
            self._state.error = None
            return refreshed_tokens
