"""JustCall reads — SMS and calls, indexed by the other party's number.

Read-only. The ticket reasoner needs this because a lot of A+ support actually
happens by text: a ticket can look abandoned in HubSpot while the family was
being handled over SMS the whole time (Inna Volodinsky's ticket asked for a
callback about old concerns while she was texting about a physics tutor the day
before).

The API serves only the most recent 3 months and refuses a future
`to_datetime`, so anything older simply cannot be fetched.
"""
from __future__ import annotations

import base64
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

BASE = "https://api.justcall.io/v2.1"
MAX_LOOKBACK_DAYS = 90


def _headers() -> dict:
    k = os.getenv("JUSTCALL_API_KEY", "")
    s = os.getenv("JUSTCALL_API_SECRET", "")
    token = base64.b64encode(f"{k}:{s}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def norm_number(p: str) -> str:
    """Last ten digits — the only form that matches across HubSpot's mixed
    formats (+1 626-437-1321, 6264371321, (626) 437-1321)."""
    d = re.sub(r"\D", "", str(p or ""))
    return d[-10:] if len(d) >= 10 else ""


def _pull(kind: str, since_days: int) -> list[dict]:
    if not os.getenv("JUSTCALL_API_KEY"):
        return []
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=min(since_days, MAX_LOOKBACK_DAYS))
    out, page = [], 0
    while page <= 90:
        try:
            r = requests.get(f"{BASE}/{kind}", headers=_headers(), timeout=40,
                             params={"per_page": 100, "page": page,
                                     "from_datetime": start.strftime("%Y-%m-%d 00:00:00"),
                                     "to_datetime": now.strftime("%Y-%m-%d %H:%M:%S")})
        except requests.RequestException:
            return out
        if r.status_code == 429:
            time.sleep(3)
            continue
        if r.status_code >= 300:
            return out
        j = r.json()
        rows = j.get("data") or []
        out += rows
        if not rows or not j.get("next_page_link"):   # NOT next_page_url
            return out
        page += 1
    return out


def index_by_number(since_days: int = 90) -> dict:
    """{last-10-digits: {"texts": [...], "calls": [...]}} over the window."""
    idx: dict = {}
    for t in _pull("texts", since_days):
        n = norm_number(t.get("contact_number"))
        if not n:
            continue
        idx.setdefault(n, {"texts": [], "calls": []})["texts"].append({
            "at": str(t.get("sms_date") or ""),
            "direction": str(t.get("direction") or "").lower(),
            "text": ((t.get("sms_info") or {}).get("body") or "")[:200]})
    for c in _pull("calls", since_days):
        n = norm_number(c.get("contact_number"))
        if not n:
            continue
        idx.setdefault(n, {"texts": [], "calls": []})["calls"].append({
            "at": str(c.get("call_date") or ""),
            "direction": str(c.get("direction") or "").lower(),
            "seconds": (c.get("call_info") or {}).get("duration"),
            "notes": ((c.get("call_info") or {}).get("notes") or "")[:200]})
    for v in idx.values():
        v["texts"].sort(key=lambda x: x["at"])
        v["calls"].sort(key=lambda x: x["at"])
    return idx
