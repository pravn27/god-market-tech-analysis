# PS_Global_Indices coverage dry-run — 2026-10-06

**Mode:** Read-only proposal. No TradingView change was made.

## Evidence used

- Read-only `PS_Global_Indices` snapshot recorded on 2026-10-06 in [source readiness](global-market-source-readiness.md).
- Moneycontrol’s [Global Market](https://www.moneycontrol.com/markets/global-indices/) page, whose Global Indices view defines US, European, and Asian regional blocks. Its index rows were client-side loading at the time of this dry-run, so it could not supply a reliable current row-by-row membership comparison.
- The project’s global-sentiment coverage checklist.

## Live read-only verification

TradingView Desktop was launched with its local debug connection and the existing bridge attached successfully:

- active chart: `TVC:DJI`, Daily;
- watchlist read: 16 symbols, matching the recorded USA and India ADR snapshot;
- no Europe or Asia-Pacific instrument was returned by the current watchlist read;
- each proposed symbol below was returned by TradingView symbol search. No exchange prefix is guessed.

## Current coverage

| Area | Status | Evidence |
| --- | --- | --- |
| US risk appetite | Covered | S&P 500, Nasdaq 100, Nasdaq Composite, Dow Jones Industrial Average |
| US breadth / small caps | Partial | NYSE Composite exists; Russell 2000 is absent |
| Europe | Missing | Existing `EUROPE` section has no instrument rows |
| Asia-Pacific / China cues | Missing | Existing `ASIA PACIFIC` section has no instrument rows |
| India overnight cues | Partial | USDINR and four India ADRs exist; GIFT Nifty is absent |
| Volatility | Covered | VIX exists |
| Dollar / FX | Covered | DXY and USDINR exist |
| Rates / bonds | Missing (optional macro proxy) | No yield instrument recorded |
| Commodities | Missing (optional macro proxy) | No crude, gold, or copper instrument recorded |

## Proposed PS_Global_Indices changes

### Keep

- **USA:** `TVC:SPX`, `NASDAQ:NDX`, `NASDAQ:IXIC`, `TVC:DJI`, `TVC:NYA`, `TVC:VIX`, `TVC:DXY`, and `VANTAGE:USDINR` remain useful first-pass global-sentiment evidence.
- **INDIA ADRS:** `NYSE:HDB`, `NYSE:IBN`, `NYSE:INFY`, and `NYSE:WIT` remain useful next-day India cues if the user intends to retain ADR context.
- Existing specialist/duplicate-context instruments (`DJCFD:DJT`, `CBOE:MAGS`, `BLACKBULL:DJ30.F`, `BLACKBULL:US30`) are retained pending an explicit decision about their distinct purpose and chart reliability.

### Add candidates — exact symbols validated; requires user confirmation

| Section | Index / cue | Why | Status |
| --- | --- | --- | --- |
| USA | Russell 2000 | `CBOEFTSE:RUT` | Small-cap risk appetite / US breadth |
| EUROPE | EURO STOXX 50 | `FXCM:EUSTX50` | Eurozone broad-market cue |
| EUROPE | DAX | `XETR:DAX` | Germany benchmark |
| EUROPE | FTSE 100 | `FTSE:UKX` | UK benchmark |
| EUROPE | CAC 40 | `TVC:CAC40` | France benchmark |
| ASIA PACIFIC | GIFT Nifty futures | `NSEIX:NIFTY` | India overnight cue |
| ASIA PACIFIC | Nikkei 225 cash | `IG:NIKKEI` | Japan / overnight Asia cue |
| ASIA PACIFIC | Hang Seng | `HSI:HSI` | Hong Kong / China risk cue |
| ASIA PACIFIC | CSI 300 | `SSE:000300` | Mainland China cue |
| ASIA PACIFIC | KOSPI | `KRX:KOSPI` | Korea cue |
| ASIA PACIFIC | Taiwan Weighted | `TWSE:IX0001` | Taiwan semiconductor / Asia cue |
| ASIA PACIFIC | S&P/ASX 200 | `SP:XJO` | Australia / regional risk cue |
| ASIA PACIFIC | Straits Times | `FTSEST:STI` | ASEAN cue |

### Delete candidates

None. A list of existing specialist or overlapping US instruments is not sufficient evidence to delete a user-chosen item.

### Reorder

None proposed. The section order and all current row orders remain unchanged until a live Desktop re-read and explicit confirmation.

### Needs review

- **India ADRS** is useful for India-market context but lies outside strict Global Indices membership.
- **Rates and commodities** should remain outside this index-focused watchlist unless the user explicitly wants a broader macro-sentiment monitor.
- **SSE Composite vs CSI 300** needs one selected China representation to keep the list compact.
- USA contains cash, future, CFD, and thematic/transport signals that may overlap; their retention should be based on the user’s preferred chart/data quality, not automated deletion.

## Outcome

`PS_Global_Indices` is enough for a first-pass US and India-context scan, but has important Europe, Asia-Pacific, China, GIFT Nifty, and US-small-cap coverage gaps. No changes were applied.

The proposal is now ready for the user's exact confirmation. It contains no deletes and no reorder.
