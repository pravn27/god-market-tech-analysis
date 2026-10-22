"""Assigns each daily bar to the trading day it belongs to.

Desktop stamps an evening-open session at the evening it opens, which is the previous UTC date: the
22 Oct session of BLACKBULL:US30 is stored as 21 Oct 22:00Z. Keying bars by UTC date would move weekly
and monthly boundaries by a day. Instead the bar's time is converted to the symbol's exchange time zone.
An evening-open instrument (EVENING_OPEN) trades on the next local day when the local hour is 12:00 or
later. Every other instrument trades on its local date. The rule is per instrument, not per hour: a
morning session that runs in the afternoon (for example NSE's Diwali Muhurat session) must keep its day.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Dict
from zoneinfo import ZoneInfo

CUTOFF_HOUR = 12

# Instruments whose daily session opens in the evening of the previous calendar day.
EVENING_OPEN = frozenset(
    {
        "BLACKBULL:DJ30.F",
        "BLACKBULL:US30",
        "TVC:DXY",
        "TVC:US10Y",
        "VANTAGE:USDINR",
    }
)

SESSION_ZONES: Dict[str, str] = {
    # New York: US indices, US stocks, CME/CBOE futures and CFDs, USD/INR forex (day starts 17:00 ET).
    "BLACKBULL:DJ30.F": "America/New_York",
    "BLACKBULL:US30": "America/New_York",
    "TVC:SPX": "America/New_York",
    "TVC:DJI": "America/New_York",
    "TVC:NYA": "America/New_York",
    "TVC:VIX": "America/New_York",
    "TVC:DXY": "America/New_York",
    "TVC:US10Y": "America/New_York",
    "NASDAQ:NDX": "America/New_York",
    "NASDAQ:IXIC": "America/New_York",
    "CBOE:MAGS": "America/New_York",
    "CBOEFTSE:RUT": "America/New_York",
    "DJCFD:DJT": "America/New_York",
    "VANTAGE:USDINR": "America/New_York",
    "NYSE:HDB": "America/New_York",
    "NYSE:IBN": "America/New_York",
    "NYSE:INFY": "America/New_York",
    "NYSE:WIT": "America/New_York",
    "NYSE:RDY": "America/New_York",
    # Europe.
    "TVC:SX5E": "Europe/Berlin",
    "XETR:DAX": "Europe/Berlin",
    "TVC:CAC40": "Europe/Paris",
    "FTSE:UKX": "Europe/London",
    # Asia-Pacific.
    "NSEIX:NIFTY1!": "Asia/Kolkata",
    "TVC:NI225": "Asia/Tokyo",
    "TVC:HSI": "Asia/Hong_Kong",
    "SSE:000300": "Asia/Shanghai",
    "SSE:000001": "Asia/Shanghai",
    "KRX:KOSPI": "Asia/Seoul",
    "TWSE:TAIEX": "Asia/Taipei",
    "ASX:XJO": "Australia/Sydney",
    "TVC:STI": "Asia/Singapore",
    "IDX:COMPOSITE": "Asia/Jakarta",
    "SET:SET": "Asia/Bangkok",
}


class UnknownSessionZone(ValueError):
    """The symbol has no exchange time zone, so its bars cannot be assigned to a trading day."""


def trading_day(symbol: str, bar_time: datetime) -> datetime:
    """UTC midnight of the trading day that a bar stamped ``bar_time`` belongs to."""
    key = symbol.upper()
    zone_name = SESSION_ZONES.get(key)
    if zone_name is None:
        raise UnknownSessionZone(f"No exchange time zone is set for {symbol}, so its bars cannot be dated.")
    local = bar_time.astimezone(ZoneInfo(zone_name))
    evening = key in EVENING_OPEN and local.hour >= CUTOFF_HOUR
    day = local.date() + timedelta(days=1) if evening else local.date()
    return datetime.combine(day, time(0), tzinfo=timezone.utc)
