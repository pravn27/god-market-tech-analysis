# Specification: multi-timeframe analysis

This document defines the **analysis presentation and evidence**. The data-fetching, caching, freshness, and partial-response behaviour is defined separately in [multi-timeframe-orchestration.md](multi-timeframe-orchestration.md).

## Purpose

Summarise chart context from larger to smaller timeframes without hiding the evidence behind the conclusion.

## Layers

| Layer | Timeframes | Decision question |
| --- | --- | --- |
| Super TIDE | Monthly, Weekly | What is the strategic market bias? |
| TIDE | Daily, 4H | What is the swing direction and location? |
| WAVE | 4H, 1H | Is a valid setup forming? |
| Ripple / Super Ripple | 1H, 15m | Is entry timing confirmed? |

## Required outputs per timeframe

- Trend structure: bullish, bearish, sideways, or unavailable.
- Location: support, resistance, mid-range, or unavailable.
- Momentum state: strong, improving, weakening, neutral, or unavailable.
- Rule evidence: relevant price action, indicators, patterns, and volume observations.
- Timestamp and freshness status.

## Acceptance criteria

1. A user can see all configured layers for one symbol on one screen.
2. Every layer shows a timestamp and freshness state.
3. Selecting a layer exposes its detailed evidence.
4. If any required timeframe is unavailable, the overall result is visibly qualified as incomplete.
5. No output is presented as a trade instruction.
