"""Weekly digest (Mon 8 AM PT).

Volume by category + owner, median time-to-handled, SLA breach count, still-open
count → Slack #email-agent, a row appended to the dashboard Google Sheet, and two
measurables on the Monday L10 Scorecard (board 18402267902):
  - Email SLA Breaches            (goal 0)
  - Email Median Response Time (hrs) (goal < 8)
"""
from __future__ import annotations

import statistics
from collections import Counter
from datetime import date, datetime

from . import audit, hubspot_client as hs, monday_client as mon, slack_client
from .config import DRY_RUN, cfg, google_creds_dict

RESOLVED_STAGES = None  # filled lazily from config


def _in_window(ts: str | None, start: date, end: date) -> bool:
    if not ts:
        return False
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
    except ValueError:
        return False
    return start <= d <= end


def gather_metrics(start: date, end: date) -> dict:
    stages = cfg()["hubspot"]["ticket_stages"]
    resolved = {stages.get("handled"), stages.get("closed")}

    by_category: Counter = Counter()
    by_owner: Counter = Counter()
    cancel_kpi: Counter = Counter()   # reschedule (save) + cancellation by type
    breach_tickets: set[str] = set()
    ticket_ids: list[str] = []

    for r in audit._iter_records():
        if not _in_window(r.get("timestamp"), start, end):
            continue
        action = r.get("action_taken")
        if action == "ticket_created":
            cat = r.get("category", "unknown")
            by_category[cat] += 1
            if cat == "reschedule":
                cancel_kpi["reschedule (saved)"] += 1
            elif cat == "cancellation":
                cancel_kpi[r.get("cancellation_type") or "one_time"] += 1
            if r.get("owner"):
                by_owner[r["owner"]] += 1
            if r.get("ticket_id"):
                ticket_ids.append(r["ticket_id"])
        elif action == "junk_archived":
            by_category["junk"] += 1
        elif action == "escalation" and r.get("ticket_id"):
            breach_tickets.add(r["ticket_id"])

    # Response time + open count (best-effort HubSpot reads).
    response_hrs: list[float] = []
    open_count = 0
    for tid in ticket_ids:
        try:
            t = hs.get_ticket_timing(tid)
        except Exception:  # noqa: BLE001
            continue
        if t.get("stage") in resolved and t.get("created") and t.get("modified"):
            try:
                c = datetime.fromisoformat(t["created"].replace("Z", "+00:00"))
                m = datetime.fromisoformat(t["modified"].replace("Z", "+00:00"))
                response_hrs.append((m - c).total_seconds() / 3600.0)
            except ValueError:
                pass
        else:
            open_count += 1

    median_hrs = round(statistics.median(response_hrs), 1) if response_hrs else 0.0

    return {
        "week": f"{start.isoformat()} – {end.isoformat()}",
        "total": sum(by_category.values()),
        "by_category": dict(by_category),
        "by_owner": dict(by_owner),
        "sla_breaches": len(breach_tickets),
        "median_response_hrs": median_hrs,
        "open_count": open_count,
        "cancel_kpi": dict(cancel_kpi),
    }


def _format_slack(m: dict) -> str:
    cats = "\n".join(f"  • {k}: {v}" for k, v in sorted(m["by_category"].items())) or "  • none"
    owners = "\n".join(f"  • {k}: {v}" for k, v in sorted(m["by_owner"].items())) or "  • none"
    kpi = m.get("cancel_kpi", {})
    kpi_line = "  ·  ".join(f"{k}: {v}" for k, v in sorted(kpi.items())) or "none"
    return (
        f"*📬 Email Agent — Weekly Digest* ({m['week']})\n"
        f"*Total triaged:* {m['total']}\n"
        f"*SLA breaches:* {m['sla_breaches']}  |  *Median response:* {m['median_response_hrs']}h  "
        f"|  *Still open:* {m['open_count']}\n"
        f"*📉 Cancellation KPI:* {kpi_line}\n"
        f"*By category:*\n{cats}\n*By owner:*\n{owners}"
    )


def _write_sheet(m: dict) -> None:
    creds = google_creds_dict()
    sheet_id = cfg()["google_sheets"]["dashboard_sheet_id"]
    if DRY_RUN or not creds or sheet_id.startswith("REPLACE"):
        print(f"[DRY_RUN/skip] sheet row: {m['week']}")
        return
    import gspread
    from google.oauth2.service_account import Credentials

    scoped = Credentials.from_service_account_info(
        creds, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    gc = gspread.authorize(scoped)
    ws = gc.open_by_key(sheet_id).worksheet(cfg()["google_sheets"]["dashboard_tab"])
    ws.append_row([
        m["week"], m["total"], m["sla_breaches"], m["median_response_hrs"], m["open_count"],
        ", ".join(f"{k}:{v}" for k, v in sorted(m["by_category"].items())),
    ])


def _write_monday(m: dict, start: date, end: date) -> None:
    mc = cfg()["monday"]
    board = mc["scorecard_board_id"]
    items = mc["measurables"]
    if DRY_RUN or str(items["sla_breaches_item_id"]).startswith("REPLACE"):
        print(f"[DRY_RUN/skip] monday scorecard: breaches={m['sla_breaches']} median={m['median_response_hrs']}")
        return
    col = mon.get_or_create_scorecard_week_col(board, start, end)
    mon.update_item(board, items["sla_breaches_item_id"], {col: m["sla_breaches"]})
    mon.update_item(board, items["median_response_hrs_item_id"], {col: m["median_response_hrs"]})


def run() -> None:
    start, end = mon.get_last_week_range()
    m = gather_metrics(start, end)
    print(_format_slack(m))
    slack_client.post_message(cfg()["slack"]["digest_channel"], _format_slack(m))
    _write_sheet(m)
    _write_monday(m, start, end)
    print("=== digest complete ===")


if __name__ == "__main__":
    run()
