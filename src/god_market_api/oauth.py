"""Application-owned OAuth support for the official TradingView MCP."""

import asyncio
import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
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
    authorization_url: Optional[str] = None
    status: str = "starting"
    error: Optional[str] = None
    completed_at: Optional[datetime] = None
    tools: Optional[list] = None
    oauth_state: Optional[str] = None
    code_verifier: Optional[str] = None


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
        async with httpx.AsyncClient(headers={"Authorization": f"Bearer {tokens.access_token}"}) as client:
            async with streamable_http_client(OFFICIAL_MCP_URL, http_client=client) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self._state.tools = [tool.name for tool in tools.tools]

    async def status(self) -> AuthorizationState:
        if await self.is_authenticated() and self._state.status == "starting":
            self._state.status = "authenticated"
        return self._state

    async def is_authenticated(self) -> bool:
        return bool(await self._storage.get_tokens())

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a read-only official-MCP tool with application-owned credentials."""
        tokens = await self._storage.get_tokens()
        if not tokens:
            raise OAuthStorageError("Official MCP authorization is required before requesting market data.")
        async with httpx.AsyncClient(headers={"Authorization": f"Bearer {tokens.access_token}"}) as client:
            async with streamable_http_client(OFFICIAL_MCP_URL, http_client=client) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    return await session.call_tool(name, arguments)
