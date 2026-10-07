# Official TradingView MCP OAuth runbook

## Security model

The local API service authenticates directly to the official TradingView MCP using OAuth 2.1. It owns the authorization-code flow with PKCE and dynamic client registration; the MCP Python SDK is used only for the MCP transport after authorization.

## Local application authorization

The service uses TradingView OAuth 2.1. On the first explicit authorization request, it dynamically registers a local public OAuth client at TradingView's advertised registration endpoint. The resulting client identifier and, after approval, OAuth tokens are stored only in the operating-system keychain. The service does not read or reuse Codex's OAuth credentials.

- Redirect URI: `http://127.0.0.1:8000/api/v1/oauth/official/callback`
- Credential storage: the current user's operating-system keyring
- Stored values: access/refresh tokens, token issuance time, and dynamically registered client information
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

## Token renewal and connection status

- TradingView's published OAuth metadata advertises both `authorization_code` and `refresh_token` grants. The service uses the advertised token endpoint and the public client identifier; it does not assume a fixed token lifetime.
- The access-token `expires_in` value is treated as a duration from token issuance. Its issuance timestamp is stored alongside the token in the OS keyring so expiration can still be calculated after restarting the local service.
- When a token is within 60 seconds of expiry, or an older stored token has no issuance timestamp, the service refreshes it before the next MCP tool call. Concurrent calls share one refresh; if TradingView rotates the refresh token, the new pair replaces the previous pair in the keyring.
- If an MCP request receives HTTP 401, the service attempts one refresh and retries that read-only tool call once. It does not retry indefinitely.
- The OAuth status endpoint reports `authenticated`, `refresh_needed`, or `reconnect_required` based on locally stored token metadata. It never returns token values. `refresh_needed` means renewal will be attempted automatically before the next tool call; `reconnect_required` means no usable refresh credential is available or TradingView rejected it as expired/revoked.
- No background keepalive or scheduled refresh is run while the app is idle. A session is renewed on the next tool call, not simply because the backend remains running. TradingView's public MCP/OAuth documentation does not promise a refresh-token lifetime, so manual reauthorization may still be required if TradingView expires or revokes the grant.
- If a refresh fails because of a temporary network/server error, retain the credential and report a retryable source failure. Do not erase tokens or ask for a new login unless TradingView explicitly rejects the refresh grant.

## Failure handling

- If the callback state is missing or mismatched, the service rejects the exchange.
- If the keyring is unavailable, no credentials are written; report the failure to the user.
- If authorization fails or is cancelled, retain no fabricated ready state; show the official source as unavailable.
- If a stored credential receives an official-MCP `401`, attempt one refresh as described above. If TradingView rejects the refresh grant, keep the source unavailable and request fresh user approval. Never print or attempt to repair tokens manually.
- Do not expose authorization codes, tokens, client secrets, or full authorization URLs in logs.
- If TradingView temporarily rate-limits the technical-rating tool, return current OHLCV with an explicit partial-data warning; do not invent technical values.
