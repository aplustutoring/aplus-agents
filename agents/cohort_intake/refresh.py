"""Read the rails back into the sheet (spec §3: the Intake row is the
compliance record) and close the one silent path in the SMS rail (spec §5.6
item d): a cohort deal whose text was skipped or failed gets a DM to its
deal owner, once.

Sources, all in email/state/audit_log.jsonl:
  deal:{id}        deal_sync    → tw_customer_id            → "Teachworks ID"
  sms-sent:{id}    sms          → timestamp, welcome_email_to → "Text Sent", "Welcome Sent"
  sms-skip:{id}, sms-error:{id}:n, presend:{id}:block → owner DM (hsa-sms-skip-dm:{id})
"""
from __future__ import annotations

from . import state as ST
from ._bootstrap import audit, email_cfg, hs, slack_client
from .writer import deal_url


def _records_for(deal_ids: set[str]) -> dict[str, dict]:
    """deal_id → {tw_customer_id, text_sent, welcome_to, skipped: [reasons], dm_sent}."""
    out = {d: {"tw_customer_id": "", "text_sent": "", "welcome_to": "", "skipped": [], "dm_sent": False}
           for d in deal_ids}
    for r in audit._iter_records():
        did = str(r.get("deal_id") or "")
        mid = str(r.get("message_id") or "")
        if did not in out:
            if mid.startswith("deal:") and mid[5:] in out:
                did = mid[5:]
            else:
                continue
        slot = out[did]
        act = r.get("action_taken") or ""
        if mid == f"deal:{did}" and r.get("tw_customer_id"):
            slot["tw_customer_id"] = str(r["tw_customer_id"])
        elif act == "sms_sent":
            slot["text_sent"] = (r.get("timestamp") or "")[:16].replace("T", " ")
            if r.get("welcome_email_to"):
                slot["welcome_to"] = r["welcome_email_to"]
        elif act in ("sms_skipped_unverified", "sms_error", "sms_held"):
            slot["skipped"].append(f"{act}: {r.get('reason') or r.get('error') or r.get('verdict') or ''}")
        elif mid == f"hsa-sms-skip-dm:{did}":
            slot["dm_sent"] = True
    for did, slot in out.items():
        if ST.already_processed(f"hsa-sms-skip-dm:{did}"):
            slot["dm_sent"] = True
    return out


def _owner_slack(deal_id: str) -> tuple[str, str]:
    got = hs._get(f"/crm/v3/objects/deals/{deal_id}", {"properties": "hubspot_owner_id,dealname"})
    p = (got or {}).get("properties") or {}
    oid = str(p.get("hubspot_owner_id") or "")
    for rec in (email_cfg().get("staff") or {}).values():
        if str(rec.get("hubspot_owner_id") or "") == oid:
            return rec.get("slack_user_id") or "", p.get("dealname") or deal_id
    return "", p.get("dealname") or deal_id


def refresh(sheet, headers: list[str], row_deals: dict[int, str], dry_run: bool) -> dict[str, dict]:
    """row_number → deal id. Writes the four rail columns and DMs owners of
    skipped texts. Returns what it found (for the Log line)."""
    recs = _records_for(set(row_deals.values()))
    for row_number, did in row_deals.items():
        rec = recs.get(did) or {}
        vals = {}
        if rec.get("tw_customer_id"):
            vals["Teachworks ID"] = rec["tw_customer_id"]
        if rec.get("text_sent"):
            vals["Text Sent"] = rec["text_sent"]
        if rec.get("welcome_to"):
            vals["Welcome Sent"] = rec["welcome_to"]
        if vals:
            sheet.write_outputs(headers, row_number, vals)
        if rec.get("skipped") and not rec.get("text_sent") and not rec.get("dm_sent"):
            uid, name = _owner_slack(did)
            text = (f"⚠️ HSA cohort family text did not go out for *{name}*: "
                    f"{'; '.join(rec['skipped'][-2:])}. Text the family yourself or fix the "
                    f"contact and the sweep retries. {deal_url(did)}")
            if dry_run:
                print(f"[DRY_RUN] would DM {uid or '(no slack id)'}: {text}")
            else:
                if uid:
                    slack_client.dm(uid, text)
                ST.append({"message_id": f"hsa-sms-skip-dm:{did}", "source": "cohort_intake",
                              "action_taken": "cohort_sms_skip_dm", "deal_id": did,
                              "notified": uid, "reasons": rec["skipped"][-2:]})
    return recs
