"""Application-owned OAuth support for the official TradingView MCP.

The local service owns its OAuth flow and stores credentials in the operating
system keyring. It intentionally never reads the Codex application's tokens.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

import httpx
import keyring
from fastapi import HTTPException
from mcp import ClientSession
from mcp.client.auth.oauth2 import OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken


OFFICIAL_MCP_URL = "https://mcp.tradingview.com/mcp"
KEYRING_SERVICE = "god-market-tech-analysis"
KEYRING_TOKENS_ACCOUNT = "tradingview-official.tokens"
KEYRING_CLIENT_ACCOUNT = "tradingview-official.client-info"


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
        self._store(KEYRING_TOKENS_ACCOUNT, tokens)

    async def get_client_info(self) -> Optional[OAuthClientInformationFull]:
        return self._load(KEYRING_CLIENT_ACCOUNT, OAuthClientInformationFull)

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._store(KEYRING_CLIENT_ACCOUNT, client_info)


@dataclass
class AuthorizationState:
    """One pending local authorization interaction."""

    authorization_url: Optional[str] = None
    callback: Optional[asyncio.Future] = None
    status: str = "starting"
    error: Optional[str] = None
    completed_at: Optional[datetime] = None
    tools: Optional[list] = None


class OfficialMCPOAuthCoordinator:
    """Runs OAuth only when a local user explicitly starts authorization."""

    def __init__(
        self,
        redirect_uri: str = "http://127.0.0.1:8000/api/v1/oauth/official/callback",
        storage: Optional[TokenStorage] = None,
    ) -> None:
        self._redirect_uri = redirect_uri
        self._storage = storage or KeyringTokenStorage()
        self._state = AuthorizationState()
        self._lock = asyncio.Lock()

    def _provider(self) -> OAuthClientProvider:
        metadata = OAuthClientMetadata(
            client_name="God Market Local MCP API",
            redirect_uris=[self._redirect_uri],
            scope="mcp:read mcp:tools",
        )
        return OAuthClientProvider(
            server_url=OFFICIAL_MCP_URL,
            client_metadata=metadata,
            storage=self._storage,
            redirect_handler=self._capture_authorization_url,
            callback_handler=self._wait_for_callback,
        )

    async def _capture_authorization_url(self, authorization_url: str) -> None:
        self._state.authorization_url = authorization_url
        self._state.status = "awaiting_user"

    async def _wait_for_callback(self) -> tuple[str, Optional[str]]:
        loop = asyncio.get_running_loop()
        self._state.callback = loop.create_future()
        return await self._state.callback

    async def start(self) -> AuthorizationState:
        """Start a user-approved authorization flow without opening a browser."""
        async with self._lock:
            if self._state.status in {"starting", "awaiting_user"} and self._state.authorization_url:
                return self._state
            self._state = AuthorizationState()
            asyncio.create_task(self._discover_and_connect())

        for _ in range(100):
            if self._state.authorization_url or self._state.error:
                break
            await asyncio.sleep(0.05)
        return self._state

    async def _discover_and_connect(self) -> None:
        try:
            provider = self._provider()
            async with httpx.AsyncClient(auth=provider) as client:
                async with streamable_http_client(OFFICIAL_MCP_URL, http_client=client) as (
                    read_stream,
                    write_stream,
                    _,
                ):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        self._state.tools = [tool.name for tool in tools.tools]
                        self._state.status = "connected"
                        self._state.completed_at = datetime.now(timezone.utc)
        except Exception as error:  # Report a safe local status; no token details are exposed.
            self._state.status = "failed"
            self._state.error = str(error)

    async def complete_callback(self, code: str, state: Optional[str]) -> AuthorizationState:
        callback = self._state.callback
        if self._state.status != "awaiting_user" or callback is None:
            raise HTTPException(status_code=409, detail="No OAuth authorization is awaiting a callback.")
        if callback.done():
            raise HTTPException(status_code=409, detail="The OAuth callback was already completed.")
        callback.set_result((code, state))
        self._state.status = "exchanging_token"
        return self._state

    async def status(self) -> AuthorizationState:
        tokens = await self._storage.get_tokens()
        if tokens and self._state.status == "starting":
            self._state.status = "authenticated"
        return self._state
