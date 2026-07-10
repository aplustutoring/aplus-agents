"""Gmail client for the charter-PO inbox.

Uses the existing Google service account with DOMAIN-WIDE DELEGATION to act as the
PO mailbox (read + label + create drafts — it can never send or delete). Raw REST via
google-auth's AuthorizedSession, so no new dependencies.

Setup (one-time, Workspace admin): grant the service account's client_id the scope
https://www.googleapis.com/auth/gmail.modify in Admin console → Security →
API controls → Domain-wide delegation. See SETUP.md §7.
"""
from __future__ import annotations

import base64
from email.mime.text import MIMEText
from functools import lru_cache

from .config import DRY_RUN, cfg, google_creds_dict

GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


@lru_cache(maxsize=1)
def _session():
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2.service_account import Credentials

    address = cfg()["po_inbox"]["address"]
    info = google_creds_dict()
    creds = Credentials.from_service_account_info(info, scopes=SCOPES).with_subject(address)
    return AuthorizedSession(creds)


def _get(path: str, params: dict | None = None) -> dict:
    r = _session().get(f"{GMAIL}{path}", params=params or {}, timeout=30)
    r.raise_for_status()
    return r.json()


def _post(path: str, payload: dict) -> dict:
    if DRY_RUN:
        print(f"[DRY_RUN] gmail POST {path}")
        return {"id": "DRYRUN", "dry_run": True}
    r = _session().post(f"{GMAIL}{path}", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def list_messages(query: str, max_results: int = 50) -> list[dict]:
    """Message stubs ({id, threadId}) matching a Gmail search query, e.g.
    'in:inbox after:1718000000 -label:agent-processed'."""
    out, token = [], None
    while True:
        params = {"q": query, "maxResults": min(max_results, 100)}
        if token:
            params["pageToken"] = token
        data = _get("/messages", params)
        out.extend(data.get("messages", []))
        token = data.get("nextPageToken")
        if not token or len(out) >= max_results:
            break
    return out[:max_results]


def get_message(msg_id: str) -> dict:
    """Full message → {id, threadId, sender, subject, date_ms, body}."""
    m = _get(f"/messages/{msg_id}", {"format": "full"})
    headers = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}

    def _text(part) -> str:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", "replace")
        return "".join(_text(p) for p in part.get("parts", []) or [])

    body = _text(m.get("payload", {}))
    if not body and m.get("snippet"):
        body = m["snippet"]
    return {
        "id": m["id"],
        "threadId": m.get("threadId"),
        "sender": headers.get("from", ""),
        "subject": headers.get("subject", ""),
        "message_id_header": headers.get("message-id", ""),
        "date_ms": int(m.get("internalDate", 0)),
        "body": body,
        "has_attachments": any(
            p.get("filename") for p in (m.get("payload", {}).get("parts") or [])
        ),
    }


@lru_cache(maxsize=1)
def _labels() -> dict:
    return {l["name"]: l["id"] for l in _get("/labels").get("labels", [])}


def ensure_label(name: str) -> str:
    """Label id for `name`, creating it if needed (supports 'Parent/Child' nesting)."""
    if name in _labels():
        return _labels()[name]
    if DRY_RUN:
        return "DRYRUN_LABEL"
    res = _post("/labels", {"name": name, "labelListVisibility": "labelShow",
                            "messageListVisibility": "show"})
    _labels.cache_clear()
    return res["id"]


def apply_labels(msg_id: str, names: list[str]) -> None:
    ids = [ensure_label(n) for n in names if n]
    if ids:
        _post(f"/messages/{msg_id}/modify", {"addLabelIds": ids})


def create_draft_reply(thread_id: str, to_addr: str, subject: str, body: str,
                       in_reply_to: str = "") -> dict:
    """A REAL Gmail draft on the thread — sits in Drafts until a human sends it."""
    mime = MIMEText(body)
    mime["To"] = to_addr
    mime["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if in_reply_to:
        mime["In-Reply-To"] = in_reply_to
        mime["References"] = in_reply_to
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    return _post("/drafts", {"message": {"threadId": thread_id, "raw": raw}})
