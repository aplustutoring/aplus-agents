"""HubSpot client — Conversations (poll/comment/archive) + CRM (contacts/tickets).

Documented REST endpoints via requests (Bearer private-app token). The private app
MUST hold: conversations.read, conversations.write, tickets,
crm.objects.contacts.read, crm.objects.contacts.write.

The proposed reply is posted as an internal COMMENT (HubSpot has no draft status).
The ONLY MESSAGE the agent ever sends is the tutor-document receipt — guarded in main.
"""
from __future__ import annotations

import requests

from .config import DRY_RUN, HUBSPOT_PRIVATE_APP_TOKEN, cfg

HS_BASE = "https://api.hubapi.com"


class HubSpotScopeError(RuntimeError):
    pass


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {HUBSPOT_PRIVATE_APP_TOKEN}",
        "Content-Type": "application/json",
    }


def _get(path: str, params: dict | None = None) -> dict:
    r = requests.get(f"{HS_BASE}{path}", headers=_headers(), params=params or {}, timeout=30)
    r.raise_for_status()
    return r.json()


def _write(method: str, path: str, payload: dict | None = None):
    """POST/PATCH/PUT/DELETE — short-circuited in DRY_RUN."""
    if DRY_RUN:
        print(f"[DRY_RUN] hubspot {method} {path} {payload if payload else ''}")
        return {"id": "DRYRUN", "dry_run": True}
    r = requests.request(method, f"{HS_BASE}{path}", headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json() if r.text else {}


def ticket_url(ticket_id: str) -> str:
    portal = cfg()["hubspot"]["portal_id"]
    return f"https://app.hubspot.com/contacts/{portal}/ticket/{ticket_id}"


# ── Scope probe (used by smoke test) ─────────────────────────────
def check_scopes() -> dict:
    """Verify the token can reach Conversations + Tickets + Contacts. Read-only."""
    results = {}
    for label, path in (
        ("conversations", "/conversations/v3/conversations/threads"),
        ("tickets", "/crm/v3/objects/tickets"),
        ("contacts", "/crm/v3/objects/contacts"),
    ):
        try:
            _get(path, {"limit": 1})
            results[label] = "ok"
        except requests.HTTPError as e:
            results[label] = f"FAIL ({e.response.status_code})"
    return results


# ── Conversations ────────────────────────────────────────────────
def list_threads(latest_after: str | None = None, after: str | None = None,
                 limit: int = 100) -> dict:
    """List conversation threads.

    With `latest_after` (an ISO timestamp): returns threads whose latest message is
    after it, sorted ascending by latest activity — the incremental-poll path. The
    HubSpot API only accepts `sort=latestMessageTimestamp` alongside that filter.
    Without it: newest threads first via `sort=-id` (used for discovery).
    `after` is the pagination token from `paging.next.after`.
    """
    params: dict = {"limit": limit}
    if latest_after:
        params["latestMessageTimestampAfter"] = latest_after
        params["sort"] = "latestMessageTimestamp"
    else:
        params["sort"] = "-id"
    if after:
        params["after"] = after
    return _get("/conversations/v3/conversations/threads", params)


def get_messages(thread_id: str) -> list[dict]:
    data = _get(f"/conversations/v3/conversations/threads/{thread_id}/messages")
    return data.get("results", [])


def latest_inbound(thread_id: str) -> dict | None:
    """The most recent INCOMING message on a thread (a real inbound email)."""
    inbound = [
        m for m in get_messages(thread_id)
        if m.get("type") == "MESSAGE" and m.get("direction") == "INCOMING"
    ]
    if not inbound:
        return None
    inbound.sort(key=lambda m: m.get("createdAt", ""))
    return inbound[-1]


def sender_email(message: dict) -> str | None:
    for sender in message.get("senders", []):
        for field in ("deliveryIdentifier", "actorId"):
            val = sender.get(field)
            if isinstance(val, dict) and val.get("value") and "@" in str(val.get("value")):
                return val["value"].lower()
        dv = sender.get("deliveryIdentifier", {})
        if isinstance(dv, dict) and "@" in str(dv.get("value", "")):
            return dv["value"].lower()
    return None


def post_comment(thread_id: str, text: str) -> dict:
    """Post an internal COMMENT (team-only, never sent to the customer)."""
    return _write("POST", f"/conversations/v3/conversations/threads/{thread_id}/messages", {
        "type": "COMMENT",
        "text": text,
    })


def send_message(thread_id: str, text: str, *, channel_id, channel_account_id,
                 sender_actor_id: str, recipients: list) -> dict:
    """Send a real outbound MESSAGE. ONLY the doc-receipt path may call this.
    Requires a valid agent senderActorId (A-{userId}) and reply-to recipients."""
    return _write("POST", f"/conversations/v3/conversations/threads/{thread_id}/messages", {
        "type": "MESSAGE",
        "text": text,
        "channelId": str(channel_id),
        "channelAccountId": str(channel_account_id),
        "senderActorId": sender_actor_id,
        "recipients": recipients,
    })


def link_thread_to_ticket(thread_id: str, ticket_id: str) -> dict:
    """Associate the email conversation thread to the ticket (v4, typeId 31) so the
    full email shows on the ticket and the ticket shows on the conversation."""
    return _write(
        "PUT",
        f"/crm/v4/objects/conversations/{thread_id}/associations/tickets/{ticket_id}",
        [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 31}],
    )


def archive_thread(thread_id: str) -> dict:
    """Soft-archive (recoverable) — used for junk. Never hard-deletes."""
    return _write("DELETE", f"/conversations/v3/conversations/threads/{thread_id}")


# ── Contacts ─────────────────────────────────────────────────────
def find_contact_by_email(email: str) -> dict | None:
    body = {
        "filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}],
        "properties": ["email", "firstname", "lastname", "lifecyclestage", "hubspot_owner_id"],
        "limit": 1,
    }
    res = _write("POST", "/crm/v3/objects/contacts/search", body)
    results = res.get("results", []) if isinstance(res, dict) else []
    return results[0] if results else None


def find_contacts_by_lastname(lastname: str) -> list[dict]:
    if not lastname:
        return []
    body = {
        "filterGroups": [{"filters": [{"propertyName": "lastname", "operator": "EQ", "value": lastname}]}],
        "properties": ["email", "firstname", "lastname"],
        "limit": 5,
    }
    res = _write("POST", "/crm/v3/objects/contacts/search", body)
    return res.get("results", []) if isinstance(res, dict) else []


import functools


@functools.lru_cache(maxsize=1)
def _deal_pipelines() -> dict:
    """{pipeline_id: {stage_id: stage_label}} for all deal pipelines (cached)."""
    d = _get("/crm/v3/pipelines/deals")
    return {p["id"]: {s["id"]: (s.get("label") or "") for s in p.get("stages", [])}
            for p in d.get("results", [])}


def stage_label(pipeline_id: str, stage_id: str) -> str:
    return _deal_pipelines().get(pipeline_id, {}).get(stage_id, "")


def find_stop_stage(pipeline_id: str, patterns: list[str]):
    """The (stage_id, label) in a pipeline whose label matches a stop pattern, else (None, None)."""
    for sid, label in _deal_pipelines().get(pipeline_id, {}).items():
        low = label.lower()
        if any(pat in low for pat in patterns):
            return sid, label
    return None, None


def get_contact_deals(contact_id: str) -> list[dict]:
    """Associated deals as {id, name, pipeline, stage}."""
    try:
        assoc = _get(f"/crm/v3/objects/contacts/{contact_id}/associations/deals")
    except requests.HTTPError:
        return []
    ids = [r.get("toObjectId") or r.get("id") for r in assoc.get("results", [])]
    out = []
    for did in ids[:30]:
        try:
            d = _get(f"/crm/v3/objects/deals/{did}", {"properties": "dealname,pipeline,dealstage"})
        except requests.HTTPError:
            continue
        p = d.get("properties") or {}
        out.append({"id": did, "name": p.get("dealname") or "",
                    "pipeline": p.get("pipeline"), "stage": p.get("dealstage")})
    return out


def move_deal_stage(deal_id: str, stage_id: str) -> dict:
    return _write("PATCH", f"/crm/v3/objects/deals/{deal_id}", {"properties": {"dealstage": stage_id}})


def search_deals_by_name(token: str, pipeline_id: str | None = None,
                         stage_id: str | None = None) -> list[dict]:
    """Deals whose name contains `token`, optionally narrowed to pipeline/stage."""
    filters = [{"propertyName": "dealname", "operator": "CONTAINS_TOKEN", "value": token}]
    if pipeline_id:
        filters.append({"propertyName": "pipeline", "operator": "EQ", "value": pipeline_id})
    if stage_id:
        filters.append({"propertyName": "dealstage", "operator": "EQ", "value": stage_id})
    body = {"filterGroups": [{"filters": filters}],
            "properties": ["dealname", "pipeline", "dealstage", "amount"], "limit": 10}
    res = _write("POST", "/crm/v3/objects/deals/search", body)
    return res.get("results", []) if isinstance(res, dict) else []


def find_deals_by_po_number(po_number: str) -> list[dict]:
    """Deals whose po_number PROPERTY matches exactly — the canonical PO lookup
    (5k+ deals carry this field; far more reliable than deal-name matching)."""
    if not po_number:
        return []
    body = {"filterGroups": [{"filters": [
        {"propertyName": "po_number", "operator": "EQ", "value": po_number.strip()}]}],
        "properties": ["dealname", "po_number", "pipeline", "dealstage"], "limit": 10}
    res = _write("POST", "/crm/v3/objects/deals/search", body)
    return res.get("results", []) if isinstance(res, dict) else []


def create_deal(name: str, pipeline_id: str, stage_id: str, amount: str | None = None,
                contact_id: str | None = None, dealtype: str | None = None,
                owner_id: str | None = None, closedate_ms: int | None = None,
                extra_props: dict | None = None) -> dict:
    props = {"dealname": name, "pipeline": pipeline_id, "dealstage": stage_id}
    for k, v in (extra_props or {}).items():
        if v not in (None, ""):
            props[k] = v
    if amount:
        props["amount"] = str(amount)
    if dealtype:
        props["dealtype"] = dealtype  # newbusiness | existingbusiness
    if owner_id and owner_id != "REPLACE":
        props["hubspot_owner_id"] = owner_id
    if closedate_ms:
        props["closedate"] = closedate_ms
    payload: dict = {"properties": props}
    if contact_id:
        payload["associations"] = [{
            "to": {"id": contact_id},
            "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3}],
        }]
    try:
        return _write("POST", "/crm/v3/objects/deals", payload)
    except requests.HTTPError:
        payload.pop("associations", None)
        return _write("POST", "/crm/v3/objects/deals", payload)


def enroll_contact_in_workflow(workflow_id: str, email: str) -> dict:
    """Enroll a contact (by email) into a HubSpot workflow (legacy automation v2).
    The workflow must allow manual/API enrollment."""
    return _write("POST", f"/automation/v2/workflows/{workflow_id}/enrollments/contacts/{email}")


def contact_deal_names(contact_id: str) -> list[str]:
    """Names of the deals associated to a contact. Deal names reliably contain the
    student first name (e.g. 'Michelle Schnider - Layla')."""
    try:
        assoc = _get(f"/crm/v3/objects/contacts/{contact_id}/associations/deals")
    except requests.HTTPError:
        return []
    ids = [r.get("toObjectId") or r.get("id") for r in assoc.get("results", [])]
    names = []
    for did in ids[:25]:
        try:
            d = _get(f"/crm/v3/objects/deals/{did}", {"properties": "dealname"})
            n = (d.get("properties") or {}).get("dealname")
            if n:
                names.append(n)
        except requests.HTTPError:
            continue
    return names


def find_family_contact(student_first: str, lastname: str) -> list[dict]:
    """Find the PARENT family contact to link a Teachworks-notice ticket to.

    Contacts are the parents; the notice names the student. So we search parents by last
    name, and on a same-surname collision use the student first name as a best-effort
    tiebreaker against the (messy, multi-sibling) student-name properties. Returns a single
    contact when resolved; the caller links only on a unique result (else manual).
    """
    if not lastname:
        return []
    sprops = cfg().get("teachworks", {}).get("student_name_properties", [])
    body = {
        "filterGroups": [{"filters": [{"propertyName": "lastname", "operator": "EQ", "value": lastname}]}],
        "properties": ["email", "firstname", "lastname"] + sprops,
        "limit": 10,
    }
    res = _write("POST", "/crm/v3/objects/contacts/search", body)
    parents = res.get("results", []) if isinstance(res, dict) else []
    if len(parents) <= 1:
        return parents
    sf = (student_first or "").strip().lower()
    if sf:
        def has_student(c: dict) -> bool:
            props = c.get("properties") or {}
            if any(sf in str(props.get(p, "") or "").lower() for p in sprops):
                return True
            # Deal names are the reliable source — "Parent - Student".
            return any(sf in n.lower() for n in contact_deal_names(c["id"]))
        matched = [c for c in parents if has_student(c)]
        if len(matched) == 1:
            return matched
    return parents  # ambiguous → caller leaves it for manual linking


def create_contact(email: str, firstname: str | None = None, lastname: str | None = None) -> dict:
    props = {"email": email}
    if firstname:
        props["firstname"] = firstname
    if lastname:
        props["lastname"] = lastname
    return _write("POST", "/crm/v3/objects/contacts", {"properties": props})


def contact_enrichment(contact_id: str) -> dict:
    """Best-effort CRM summary: properties + associated deal count. Partial on error."""
    summary: dict = {}
    try:
        props = ["email", "firstname", "lastname", "lifecyclestage", "hubspot_owner_id",
                 "hs_lead_status", "notes_last_updated"]
        c = _get(f"/crm/v3/objects/contacts/{contact_id}", {"properties": ",".join(props)})
        summary["properties"] = c.get("properties", {})
    except requests.HTTPError:
        summary["properties"] = {}
    try:
        assoc = _get(f"/crm/v3/objects/contacts/{contact_id}/associations/deals")
        summary["associated_deals"] = len(assoc.get("results", []))
    except requests.HTTPError:
        summary["associated_deals"] = 0
    return summary


# ── Tickets ──────────────────────────────────────────────────────
def create_ticket(subject: str, owner_id: str | None, stage_id: str,
                   description: str, contact_id: str | None,
                   priority: str | None = None, category: str | None = None,
                   source: str | None = None) -> dict:
    hs = cfg()["hubspot"]
    props = {
        "subject": subject,
        "hs_pipeline": hs["ticket_pipeline_id"],
        "hs_pipeline_stage": stage_id,
        "content": description,
    }
    if owner_id and owner_id != "REPLACE":
        props["hubspot_owner_id"] = owner_id
    if priority:
        props["hs_ticket_priority"] = priority
    if category:
        props["hs_ticket_category"] = category
    if source:
        props["source_type"] = source

    payload: dict = {"properties": props}
    if contact_id:
        # 16 = default ticket→contact association type id
        payload["associations"] = [{
            "to": {"id": contact_id},
            "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 16}],
        }]
    try:
        return _write("POST", "/crm/v3/objects/tickets", payload)
    except requests.HTTPError as e:
        body = e.response.text if e.response is not None else ""
        if e.response is not None and e.response.status_code == 400 and "INVALID_OWNER_ID" in body:
            # Bad owner id must never drop an email — create unassigned (owner still gets the Slack DM).
            print(f"    ⚠️  invalid owner_id {owner_id}; creating ticket UNASSIGNED")
            props.pop("hubspot_owner_id", None)
            return _write("POST", "/crm/v3/objects/tickets", payload)
        raise


def create_task(subject: str, body: str, owner_id: str | None, due_ms: int,
                priority: str = "MEDIUM", contact_id: str | None = None) -> dict:
    """Create a HubSpot Task (owner to-do with a due date + reminders)."""
    if priority == "URGENT":
        priority = "HIGH"  # tasks support LOW/MEDIUM/HIGH only
    props = {
        "hs_task_subject": subject,
        "hs_task_body": body,
        "hs_task_status": "NOT_STARTED",
        "hs_task_type": "TODO",
        "hs_timestamp": due_ms,
    }
    if priority in ("LOW", "MEDIUM", "HIGH"):
        props["hs_task_priority"] = priority
    if owner_id and owner_id != "REPLACE":
        props["hubspot_owner_id"] = owner_id
    payload: dict = {"properties": props}
    if contact_id:
        payload["associations"] = [{
            "to": {"id": contact_id},
            "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 204}],
        }]
    try:
        return _write("POST", "/crm/v3/objects/tasks", payload)
    except requests.HTTPError:
        payload.pop("associations", None)  # association is best-effort
        return _write("POST", "/crm/v3/objects/tasks", payload)


def get_ticket(ticket_id: str) -> dict:
    return _get(f"/crm/v3/objects/tickets/{ticket_id}",
                {"properties": "subject,hs_pipeline_stage,hubspot_owner_id"})


def get_ticket_timing(ticket_id: str) -> dict:
    """Return {created, modified, stage} for digest response-time math."""
    t = _get(f"/crm/v3/objects/tickets/{ticket_id}",
             {"properties": "createdate,hs_lastmodifieddate,hs_pipeline_stage"})
    p = t.get("properties", {})
    return {
        "created": p.get("createdate"),
        "modified": p.get("hs_lastmodifieddate"),
        "stage": p.get("hs_pipeline_stage"),
    }


def update_ticket_stage(ticket_id: str, stage_id: str) -> dict:
    """Move a ticket to another stage (agent-managed, since there's no Service Hub workflow)."""
    return _write("PATCH", f"/crm/v3/objects/tickets/{ticket_id}",
                  {"properties": {"hs_pipeline_stage": stage_id}})


def thread_has_outbound_reply(thread_id: str, exclude_message_id: str | None = None,
                              after_ts: str | None = None) -> bool:
    """True if a human outbound MESSAGE exists on the thread AFTER `after_ts`
    (ISO; normally the ticket-creation time — replies that predate the ticket must
    not mark it handled). Excludes the agent's own doc-receipt."""
    for m in get_messages(thread_id):
        if m.get("type") == "MESSAGE" and m.get("direction") == "OUTGOING":
            if exclude_message_id and m.get("id") == exclude_message_id:
                continue
            if after_ts and (m.get("createdAt") or "") <= after_ts:
                continue
            return True
    return False


# ── Setup helpers (used by smoke_test / id discovery) ────────────
def list_inboxes() -> list[dict]:
    return _get("/conversations/v3/conversations/inboxes").get("results", [])


def list_ticket_pipelines() -> list[dict]:
    return _get("/crm/v3/pipelines/tickets").get("results", [])


def add_ticket_note(ticket_id: str, body: str) -> dict:
    """Attach a note engagement to a ticket (mirrors the audit entry)."""
    payload = {
        "properties": {"hs_note_body": body, "hs_timestamp": _now_ms()},
        "associations": [{
            "to": {"id": ticket_id},
            "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 228}],
        }],
    }
    return _write("POST", "/crm/v3/objects/notes", payload)


def _now_ms() -> int:
    from datetime import datetime, timezone
    return int(datetime.now(timezone.utc).timestamp() * 1000)
