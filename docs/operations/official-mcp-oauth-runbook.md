# Official TradingView MCP OAuth runbook

## Security model

The local API service authenticates directly to the official TradingView MCP using OAuth 2.1. It uses the MCP Python SDK's authorization-code flow with PKCE and dynamic client registration when supported by the authorization server.

- Redirect URI: `http://127.0.0.1:8000/api/v1/oauth/official/callback`
- Credential storage: the current user's operating-system keyring
- Stored values: access/refresh tokens and dynamically registered client information
- Not used: Codex OAuth credential store, source-controlled configuration files, API keys, or TradingView passwords

## User-approved authorization flow

1. Start the local API service on the configured localhost port.
2. Call `POST /api/v1/oauth/official/start`.
3. Review the generated TradingView authorization URL.
4. Obtain explicit user approval immediately before opening that URL.
5. The user signs in and authorizes TradingView access in their browser.
6. TradingView redirects to the localhost callback.
7. The service validates the OAuth state, stores its own credentials in the OS keyring, and performs a read-only tool inventory.

## Failure handling

- If the callback state is missing or mismatched, the SDK rejects the exchange.
- If the keyring is unavailable, no credentials are written; report the failure to the user.
- If authorization fails or is cancelled, retain no fabricated ready state; show the official source as unavailable.
- Do not expose authorization codes, tokens, client secrets, or full authorization URLs in logs.
