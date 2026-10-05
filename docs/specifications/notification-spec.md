# Specification: monitoring and notifications

## Purpose

Notify the user about meaningful setup-state changes without repeated noise.

## Events eligible for notification

- A setup first reaches `Near ready`.
- A setup first reaches `Confirmed`.
- A `Near ready` or `Confirmed` setup becomes `Invalidated`.
- TradingView/MCP connection changes to unavailable or recovers.

## Rules

- A notification is tied to a state transition, not each refresh.
- Store a delivery attempt locally with timestamp and result.
- Do not send Gmail until the user explicitly enables and configures it.
- Failure to send an email must not change the setup evaluation.
- All messages state that the result is decision support, not an order or financial advice.

## Acceptance criteria

1. One transition produces one in-dashboard event.
2. Repeated identical evaluations do not create duplicate alerts.
3. The dashboard displays notification delivery status.
4. A user can inspect why the event was produced.
