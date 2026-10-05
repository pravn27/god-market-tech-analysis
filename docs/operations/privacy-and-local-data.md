# Privacy and local data

## Local-first policy

The application stores its configuration, rule versions, evaluation history, notification records, and manual decisions locally unless a future approved feature explicitly changes this.

## Secrets

- Never store TradingView passwords in the application or repository.
- Keep Gmail credentials/tokens outside source control in an approved local secret mechanism.
- Add secret/configuration files to `.gitignore` before adding notification capabilities.
- Do not place screenshots containing account information in public issue discussions.

## Data retention decisions

Before implementation, decide how long to keep evaluation history, logs, alert records, and manual decisions. Record the choice in the feature specification.
