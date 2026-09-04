"""Sibling-gap tripwire — a family renews SOME kids and one is left out.

Roman, 2026-09-04, after three live cases surfaced in one manual query
(Eliana Fiore, Zahavi Villa, Abigail Miller — every one a family that
renewed siblings but had one child with no 26/27 PO): "in the event that we
ever get purchase orders for siblings, but not for all of them, how do we
raise a red flag and let Paola know?"

The pattern is the strongest miss signal there is: a family renewing ANY
kid clearly means to continue, so an active sibling with no new PO is far
more likely a school/TOR oversight than churn. Runs daily (self-gated, from
deal_sync like the invoice sweep): students active at the END of last
season (a PO deal created inside prior_window) are compared per family
against this season's PO deals (created after season_start). A missing
sibling flags ONLY once the family's newest PO is settle_days old —
siblings' OAs arrive spread out (Fiore: 16 minutes; Bernard: 2 days), and
flagging on day one would cry wolf.

Flag = one DM to the charter_sales seat (families/specific students belong
to that seat per Roman's routing rule), audited once per family+kid per
season — never a daily drumbeat.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import audit, hubspot_client as hs, slack_client
from .business_hours import now_la
from .config import cfg, staff


def _po_deals(start_ms: int, end_ms: int | None = None) -> list[dict]:
    filters = [{"propertyName": "po_number", "operator": "HAS_PROPERTY"}]
    if end_ms:
        filters.append({"propertyName": "createdate", "operator": "BETWEEN",
                        "value": str(start_ms), "highValue": str(end_ms)})
    else:
        filters.append({"propertyName": "createdate", "operator": "GTE",
                        "value": str(start_ms)})
    out, after = [], None
    while True:
        body = {"filterGroups": [{"filters": filters}],
                "properties": ["dealname", "createdate"], "limit": 100}
        if after:
            body["after"] = after
        res = hs._write("POST", "/crm/v3/objects/deals/search", body)
        out += res.get("results", [])
        after = ((res.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            break
    return out


def _parse(dealname: str):
    """'Parent - Student ...' → (parent lowercased, student first name)."""
    parts = [p.strip() for p in (dealname or "").split(" - ")]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None, None
    student = parts[1].split()[0]
    if not student or parts[0].upper().startswith("NEEDS PARENT"):
        return None, None
    return parts[0].lower(), student.lower()


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp()) * 1000


def find_gaps(prior: list[dict], current: list[dict], settle_days: int,
              now_utc: datetime) -> list[dict]:
    """Pure detection: families in `current` whose `prior`-active siblings are
    absent, where the family's newest current PO is at least settle_days old."""
    prior_fams: dict = {}
    for r in prior:
        p, s = _parse((r.get("properties") or {}).get("dealname"))
        if p and s:
            prior_fams.setdefault(p, set()).add(s)
    cur_fams: dict = {}
    for r in current:
        p, s = _parse((r.get("properties") or {}).get("dealname"))
        if not (p and s):
            continue
        fam = cur_fams.setdefault(p, {"kids": set(), "newest": ""})
        fam["kids"].add(s)
        fam["newest"] = max(fam["newest"],
                            (r.get("properties") or {}).get("createdate") or "")
    gaps = []
    for famkey, fam in cur_fams.items():
        left_out = prior_fams.get(famkey, set()) - fam["kids"]
        if not left_out:
            continue
        try:
            newest = datetime.fromisoformat(fam["newest"].replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if (now_utc - newest).days < settle_days:
            continue   # siblings' OAs arrive spread out — give the school time
        gaps.append({"family": famkey, "missing": sorted(left_out),
                     "renewed": sorted(fam["kids"])})
    return gaps


def run() -> None:
    sg = cfg().get("sibling_gap") or {}
    if not sg.get("enabled"):
        return
    now = now_la()
    if not (now.hour == int(sg.get("hour_pt", 10)) and now.minute < 15):
        return   # once a day, like the invoice sweep
    season = sg.get("season_start", "2026-08-15")
    prior_a = sg.get("prior_window_start", "2026-02-01")
    prior_b = sg.get("prior_window_end", "2026-07-15")
    settle = int(sg.get("settle_days", 5))
    try:
        prior = _po_deals(_ms(prior_a), _ms(prior_b))
        current = _po_deals(_ms(season))
    except Exception as e:  # noqa: BLE001 — a read hiccup waits for tomorrow
        print(f"sibling_gap: fetch failed ({e}); retrying tomorrow")
        return
    gaps = find_gaps(prior, current, settle, now.astimezone(timezone.utc))
    target = staff(sg.get("notify", "charter_sales"))
    flagged = 0
    for g in gaps:
        new_kids = [k for k in g["missing"]
                    if not audit.already_processed(
                        f"sibling-gap:{season}:{g['family']}:{k}")]
        if not new_kids:
            continue
        msg = (f"🚩 Sibling gap: the {g['family'].title()} family renewed "
               f"{', '.join(k.title() for k in g['renewed'])} but "
               f"{', '.join(k.title() for k in new_kids)} "
               f"{'has' if len(new_kids) == 1 else 'have'} no new PO, and it has "
               f"been {settle}+ days since the family's last one arrived. They "
               f"were active last season. Please check with the family or their "
               f"TOR whether {'this kid is' if len(new_kids) == 1 else 'these kids are'} "
               f"continuing. If yes, the school still needs to issue the order "
               f"agreement. If no, tell Roman so we close it.")
        if target.get("slack_user_id"):
            try:
                slack_client.dm(target["slack_user_id"], msg)
            except Exception as e:  # noqa: BLE001
                print(f"sibling_gap: DM failed ({e}); will retry tomorrow")
                continue   # don't audit — tomorrow retries
        for k in new_kids:
            audit.append({"message_id": f"sibling-gap:{season}:{g['family']}:{k}",
                          "source": "sibling_gap", "action_taken": "sibling_gap_flagged",
                          "family": g["family"], "student": k,
                          "renewed_siblings": g["renewed"]})
        flagged += 1
    print(f"sibling_gap: {len(gaps)} gap famil{'y' if len(gaps) == 1 else 'ies'}, "
          f"{flagged} newly flagged")
