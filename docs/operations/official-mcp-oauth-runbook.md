# Official TradingView MCP OAuth runbook

## Security model

The local API service authenticates directly to the official TradingView MCP using OAuth 2.1. It owns the authorization-code flow with PKCE and dynamic client registration; the MCP Python SDK is used only for the MCP transport after authorization.

## Local application authorization

The service uses TradingView OAuth 2.1. On the first explicit authorization request, it dynamically registers a local public OAuth client at TradingView's advertised registration endpoint. The resulting client identifier and, after approval, OAuth tokens are stored only in the operating-system keychain. The service does not read or reuse Codex's OAuth credentials.

- Redirect URI: `http://127.0.0.1:8000/api/v1/oauth/official/callback`
- Credential storage: the current user's operating-system keyring
- Stored values: access/refresh tokens and dynamically registered client information
- Not used: Codex OAuth credential store, source-controlled configuration files, API keys, or TradingView passwords

## User-approved authorization flow

1. Start the local API service on the configured localhost port.
   Use `uv run uvicorn god_market_api.app:app --reload --no-access-log` during OAuth so the callback's authorization code is not written to a terminal access log.
2. Call `POST /api/v1/oauth/official/start`.
3. Review the generated TradingView authorization URL.
4. Obtain explicit user approval immediately before opening that URL.
5. The user signs in and authorizes TradingView access in their browser.
6. TradingView redirects to the localhost callback.
7. The service validates the OAuth state, stores its own credentials in the OS keyring, and performs a read-only tool inventory.

## Failure handling

- If the callback state is missing or mismatched, the service rejects the exchange.
- If the keyring is unavailable, no credentials are written; report the failure to the user.
- If authorization fails or is cancelled, retain no fabricated ready state; show the official source as unavailable.
- If a stored credential receives an official-MCP `401`, treat it as expired or revoked: keep the source unavailable, request fresh user approval, and repeat the local authorization flow. Never print or attempt to repair tokens manually.
- Do not expose authorization codes, tokens, client secrets, or full authorization URLs in logs.
- If TradingView temporarily rate-limits the technical-rating tool, return current OHLCV with an explicit partial-data warning; do not invent technical values.
