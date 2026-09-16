"""cohort_intake — turn Ready rows on the A+ HSA intake sheet into HubSpot
contacts + deals, the ES group email, and a scheduler handoff, in one run.

    python -m agents.cohort_intake                      # dry run: plan only
    python -m agents.cohort_intake --only-row TEST-001  # one student id
    python -m agents.cohort_intake --execute            # write, after the stop window
    python -m agents.cohort_intake --refresh            # sheet columns from the rails only

Dry run is the default; --execute is the only way anything is written.
Ground all reasoning and output in A+ CARE core values: ops/values/care-values.md.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cohort_intake")
    ap.add_argument("--execute", action="store_true", help="write (default is a dry run)")
    ap.add_argument("--only-row", default="", help="process only this Student ID")
    ap.add_argument("--group-label", default="",
                    help="process only this group, e.g. C1-G4 (cohort 1, group 4)")
    ap.add_argument("--sheet-id", default="", help="override HSA_INTAKE_SHEET_ID")
    ap.add_argument("--wait-minutes", type=float, default=None,
                    help="stop window before writing (config default 15; 0 = none)")
    ap.add_argument("--refresh", action="store_true",
                    help="only read the rails back into the sheet (Teachworks ID, Text/Welcome Sent)")
    ap.add_argument("--by", default=os.getenv("GITHUB_ACTOR", "local"), help="who ran it (Log)")
    args = ap.parse_args(argv)

    # DRY_RUN must be settled before the email package loads.
    os.environ["DRY_RUN"] = "false" if args.execute else "true"
    from . import cohort as C, messages as M, refresh as RF, rows as R, stop_window, writer as W
    from . import sheet as S
    from ._bootstrap import agent_cfg, audit, otf, school_resolver, slack_client, staff

    dry = not args.execute
    mode = "execute" if args.execute else "dry-run"
    if args.only_row:
        mode += f" only-row {args.only_row}"
    sid = S.sheet_id(args.sheet_id or None)
    sheet = S.Sheet(sid, dry_run=dry)
    headers, body = sheet.read_intake()
    idx = R.header_map(headers)
    resolve = school_resolver()
    today = date.today()

    # ── parse Ready rows; every hard-stop is reported, none is guessed ──
    parsed: list[R.Row] = []
    refused: list[str] = []
    for row_number, cells in body:
        if not R.is_ready(cells, idx):
            continue
        try:
            row = R.parse_row(row_number, cells, idx, resolve)
        except R.RowError as e:
            refused.append(str(e))
            continue
        if args.only_row and row.student_id != args.only_row:
            continue
        parsed.append(row)
    if args.only_row and not parsed:
        print(f"no Ready row with Student ID {args.only_row!r}" +
              (f"; refused: {refused}" if refused else ""))
        return 1
    try:
        groups = R.assemble_groups(parsed)
    except R.RowError as e:
        refused.append(str(e))
        groups = []
    if args.group_label:
        groups = [g for g in groups if f"C{g.cohort.number}-G{g.number}" == args.group_label]

    row_deals: dict[int, str] = {r.sheet_row: (r.outputs.get("HubSpot Deal ID") or "")
                                 for r in parsed if r.outputs.get("HubSpot Deal ID")}

    if args.refresh:
        headers = sheet.ensure_output_columns(headers)
        recs = RF.refresh(sheet, headers, row_deals, dry)
        sheet.append_log(f"refresh ({mode})", len(row_deals),
                         f"rail columns for {len(row_deals)} deal(s); "
                         f"{sum(1 for v in recs.values() if v.get('text_sent'))} texted", "", args.by)
        return 0

    if not groups:
        msg = "nothing to do: no Ready rows" + (f"; refused: {refused}" if refused else "")
        print(msg)
        sheet.append_log(mode, 0, "nothing", "; ".join(refused), args.by)
        return 1 if refused else 0

    # ── plan ──
    plans = {g.label: W.plan_group(g, today) for g in groups}
    summary = M.plan_summary(groups, plans, refused, mode)
    print(summary)
    for seat in agent_cfg()["slack"]["summary_to"]:
        uid = (staff(seat) or {}).get("slack_user_id")
        if uid:
            slack_client.dm(uid, summary)
    if dry:
        sheet.append_log(mode, sum(len(g.rows) for g in groups), "plan only (see DM)",
                         "; ".join(refused), args.by)
        print("DRY RUN: nothing written. Re-run with --execute.")
        return 0

    # ── stop window ──
    minutes = agent_cfg()["slack"]["wait_minutes"] if args.wait_minutes is None else args.wait_minutes
    proceed, why = stop_window.hold(summary, minutes)
    if not proceed:
        print(f"not executing: {why}")
        sheet.append_log(mode, sum(len(g.rows) for g in groups), f"NOT executed: {why}",
                         "; ".join(refused), args.by)
        return 2

    # ── execute ──
    headers = sheet.ensure_output_columns(headers)
    did_lines: list[str] = []
    for g in groups:
        outcomes = W.execute_group(g, plans[g.label], today, dry_run=False)
        urls = {o.student_id: W.deal_url(o.deal_id) for o in outcomes}
        for r, o in zip(g.rows, outcomes):
            sheet.write_outputs(headers, r.sheet_row, {
                "HubSpot Deal ID": o.deal_id, "Cohort": str(g.cohort.number),
                "Sessions": str(o.sessions), "Last Updated": S.now_stamp()})
            row_deals[r.sheet_row] = o.deal_id
            did_lines.append(f"{r.student_id} deal {o.deal_id} "
                             f"{'created' if o.deal_created else 'updated'} ${o.amount}"
                             + (f" (skipped props: {', '.join(o.skipped_props)})" if o.skipped_props else ""))
        # ES group email (one per ES per group) through the one_to_few rail
        dates = plans[g.label]["dates"]
        for es in g.es_emails:
            tor_id = next((o.tor_id for r, o in zip(g.rows, outcomes) if r.es_email == es), "")
            subject, bodytext = M.es_email(g, es, dates)
            contacts = otf.fetch_contacts([tor_id]) if tor_id and tor_id != "DRYRUN" else []
            if not contacts:
                did_lines.append(f"ES email to {es}: no contact id, NOT sent")
                continue
            ec = agent_cfg()["es_email"]
            rws = otf.build_rows(contacts, purpose=ec["purpose"], from_line=ec["from_line"],
                                 bodies={tor_id: bodytext}, subjects={tor_id: subject},
                                 channel="email")
            counts = otf.send_rows(rws, purpose=ec["purpose"], from_line=ec["from_line"],
                                   approved_by=args.by, channel="email", delay=0)
            status = "sent" if counts["sent"] else f"NOT sent ({rws[0]['verdict']}: {'; '.join(rws[0]['reasons'])[:120]})"
            did_lines.append(f"ES email to {es} ({g.label}): {status}")
            for r in g.rows:
                if r.es_email == es and counts["sent"]:
                    sheet.write_outputs(headers, r.sheet_row, {"ES Email Sent": S.now_stamp()})
        # scheduler handoff
        owner = W.group_owner(g.number)
        handoff = M.scheduler_handoff(g, dates, urls, owner.get("name", "scheduler"))
        if owner.get("slack_user_id"):
            slack_client.dm(owner["slack_user_id"], handoff)
        did_lines.append(f"handoff DM → {owner.get('name', '?')} for {g.label}")
        audit.append({"message_id": f"cohort-run:{g.label}:{today.isoformat()}", "source": "cohort_intake",
                      "action_taken": "cohort_group_processed", "group": f"C{g.cohort.number}-G{g.number}",
                      "deals": [o.deal_id for o in outcomes], "es": g.es_emails,
                      "owner": owner.get("name")})

    # ── rails back into the sheet (best effort; the next run repeats it) ──
    try:
        RF.refresh(sheet, headers, row_deals, dry_run=False)
    except Exception as e:  # noqa: BLE001
        did_lines.append(f"refresh skipped: {e}")

    done = "\n".join(did_lines)
    final = (f"✅ *cohort_intake done* ({mode}): {len(groups)} group(s).\n{done}\n"
             f"Texts + welcome emails follow on the SMS sweep (≤15 min). "
             f"Refused: {'; '.join(refused) or 'none'}")
    print(final)
    for seat in agent_cfg()["slack"]["summary_to"]:
        uid = (staff(seat) or {}).get("slack_user_id")
        if uid:
            slack_client.dm(uid, final)
    sheet.append_log(mode, sum(len(g.rows) for g in groups), done, "; ".join(refused), args.by)
    return 0


if __name__ == "__main__":
    sys.exit(main())
