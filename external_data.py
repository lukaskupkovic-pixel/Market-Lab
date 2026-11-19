"""Supplemental official sources. Display-only until PIT backtesting is audited.

These observations MUST NOT enter training features: current public COT archives
can be revised and their report dates are not their first release timestamps.
"""
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


COT_MARKETS = {
    "GC=F": "GOLD - COMMODITY EXCHANGE INC.",
    "SI=F": "SILVER - COMMODITY EXCHANGE INC.",
    "CL=F": "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE",
}
COT_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
BLS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"


def cot_snapshot(symbol, now=None, opener=urlopen):
    """Mature CFTC COT observation, never a point-in-time historical feature."""
    name = COT_MARKETS.get(symbol)
    if not name:
        return None
    now = now or datetime.now(timezone.utc)
    # Extra 14-day holdback, because Tuesday positions are not Tuesday releases.
    # The holdback is not a replacement for a true vintage/release database.
    safe_date = (now - timedelta(days=14)).date().isoformat()
    where = f"market_and_exchange_names = '{name}' AND report_date_as_yyyy_mm_dd <= '{safe_date}T23:59:59'"
    params = urlencode({"$where": where, "$order": "report_date_as_yyyy_mm_dd DESC", "$limit": 1,
                        "$select": "market_and_exchange_names,report_date_as_yyyy_mm_dd,open_interest_all,m_money_positions_long_all,m_money_positions_short_all"})
    with opener(Request(COT_URL + "?" + params, headers={"User-Agent": "MarketSignalLab/3.0"}), timeout=12) as response:
        rows = json.load(response)
    if not rows:
        return None
    row = rows[0]
    open_interest = int(row["open_interest_all"])
    long, short = int(row["m_money_positions_long_all"]), int(row["m_money_positions_short_all"])
    date = row["report_date_as_yyyy_mm_dd"][:10]
    if open_interest <= 0 or min(long, short) < 0 or date > safe_date:
        raise ValueError("CFTC: nekonzistentní report")
    return {"source": "CFTC COT Disaggregated Futures Only", "market": name,
            "report_date": date, "open_interest": open_interest,
            "managed_money_net": long - short, "net_share_of_oi": round((long - short) / open_interest, 5),
            "release_timestamp_verified": False, "used_in_model": False,
            "note": "14denní konzervativní odstup; report není ověřenou historickou vintage."}


def bls_upcoming(now=None, opener=urlopen):
    """Scheduled US labor/inflation releases for event-risk labeling only."""
    now = now or datetime.now(timezone.utc)
    with opener(Request(BLS_URL, headers={"User-Agent": "Mozilla/5.0"}), timeout=12) as response:
        raw = response.read().decode("utf-8-sig", errors="replace")
    # Unfold continuation lines per RFC 5545.
    raw = re.sub(r"\r?\n[ \t]", "", raw)
    events = []
    for entry in raw.split("BEGIN:VEVENT")[1:]:
        block = entry.split("END:VEVENT", 1)[0]
        title = re.search(r"(?m)^SUMMARY:(.+)$", block)
        start = re.search(r"(?m)^DTSTART(?:;TZID=([^:]+))?:(\d{8}T\d{6}Z?)", block)
        if not title or not start:
            continue
        dt_str = start.group(2)
        date = datetime.strptime(dt_str.rstrip("Z"), "%Y%m%dT%H%M%S")
        zone_name = start.group(1) or "America/New_York"
        # BLS presently publishes US-Eastern; slim Python images may only
        # include the canonical IANA name in their timezone database.
        if zone_name in ("US-Eastern", "Eastern Standard Time"):
            zone_name = "America/New_York"
        try:
            zone = timezone.utc if dt_str.endswith("Z") else ZoneInfo(zone_name)
        except (KeyError, ValueError):
            continue
        date = date.replace(tzinfo=zone).astimezone(timezone.utc)
        if now <= date <= now + timedelta(days=8):
            events.append({"name": title.group(1).strip(), "scheduled_utc": date.isoformat(),
                           "source": "BLS official calendar", "used_in_model": False})
    return sorted(events, key=lambda entry: entry["scheduled_utc"])[:10]
