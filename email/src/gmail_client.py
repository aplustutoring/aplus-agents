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
import re
from email.mime.text import MIMEText
from functools import lru_cache

from .config import DRY_RUN, cfg, google_creds_dict

GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


@lru_cache(maxsize=8)
def _session(address: str | None = None):
    """An authorized session acting AS `address` (default: the charter PO
    mailbox). Domain-wide delegation lets the same service account act as any
    mailbox in the Workspace; po_sources uses that to read admin@ for PO mail
    that schools' ordering systems send to the vendor contact on file."""
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2.service_account import Credentials

    address = address or cfg()["po_inbox"]["address"]
    info = google_creds_dict()
    creds = Credentials.from_service_account_info(info, scopes=SCOPES).with_subject(address)
    return AuthorizedSession(creds)


def _get(path: str, params: dict | None = None, mailbox: str | None = None) -> dict:
    r = _session(mailbox).get(f"{GMAIL}{path}", params=params or {}, timeout=30)
    r.raise_for_status()
    return r.json()


def _post(path: str, payload: dict, mailbox: str | None = None,
          params: dict | None = None) -> dict:
    if DRY_RUN:
        print(f"[DRY_RUN] gmail POST {path}")
        return {"id": "DRYRUN", "dry_run": True}
    r = _session(mailbox).post(f"{GMAIL}{path}", params=params or {}, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def list_messages(query: str, max_results: int = 50, mailbox: str | None = None) -> list[dict]:
    """Message stubs ({id, threadId}) matching a Gmail search query, e.g.
    'in:inbox after:1718000000 -label:agent-processed'."""
    out, token = [], None
    while True:
        params = {"q": query, "maxResults": min(max_results, 100)}
        if token:
            params["pageToken"] = token
        data = _get("/messages", params, mailbox)
        out.extend(data.get("messages", []))
        token = data.get("nextPageToken")
        if not token or len(out) >= max_results:
            break
    return out[:max_results]


def get_thread(thread_id: str) -> list[dict]:
    """Every message in a thread, oldest first, as get_message dicts.

    PO tickets carry no HubSpot email engagements — the inbound mail is embedded
    as a note and any REPLY Kath sends goes out from this Gmail mailbox, so
    HubSpot never sees it. Reading the thread is the only way to know whether we
    answered; without it a handled ticket looks abandoned.
    """
    t = _get(f"/threads/{thread_id}", {"format": "full"})
    out = []
    for m in t.get("messages", []):
        try:
            out.append(_parse_message(m))
        except Exception:  # noqa: BLE001 — one bad part must not lose the thread
            continue
    return sorted(out, key=lambda x: x.get("date_ms") or 0)


def find_thread(subject: str, sender: str = "", newer_than_days: int = 120) -> str:
    """Locate a PO thread from what the ticket recorded about it. Returns a
    thread id, or "" when the search is ambiguous or finds nothing — the caller
    must treat "" as 'unknown', never as 'no reply was sent'."""
    subject = re.sub(r'^(re|fwd):\s*', '', (subject or "").strip(), flags=re.I)
    if not subject:
        return ""
    q = f'subject:"{subject[:120]}" newer_than:{newer_than_days}d'
    if sender and "@" in sender:
        addr = re.search(r'[\w.+-]+@[\w.-]+', sender)
        if addr:
            q += f' from:{addr.group(0)}'
    try:
        stubs = list_messages(q, max_results=10)
    except Exception:  # noqa: BLE001
        return ""
    threads = {s.get("threadId") for s in stubs if s.get("threadId")}
    return threads.pop() if len(threads) == 1 else ""


def _parse_message(m: dict) -> dict:
    """A raw Gmail message resource → the dict shape the agents consume."""
    headers = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}

    def _text(part) -> str:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", "replace")
        return "".join(_text(p) for p in part.get("parts", []) or [])

    body = _text(m.get("payload", {}))
    if not body and m.get("snippet"):
        body = m["snippet"]

    names: list[str] = []

    def _names(part):
        if part.get("filename"):
            names.append(part["filename"])
        for p in part.get("parts", []) or []:
            _names(p)

    _names(m.get("payload", {}))
    # Every address that vouches for the message: ordering systems (OPS) send
    # on behalf of a school, so From is the school and Sender/Reply-To is the
    # platform. po_sources.is_po_shaped needs to see both.
    addr_blob = " ".join(headers.get(h, "") for h in ("from", "sender", "reply-to", "return-path"))
    return {
        "id": m["id"],
        "threadId": m.get("threadId"),
        "sender": headers.get("from", ""),
        "subject": headers.get("subject", ""),
        "message_id_header": headers.get("message-id", ""),
        "date_ms": int(m.get("internalDate", 0)),
        "body": body,
        "has_attachments": bool(names),
        "attachment_names": names,
        "sender_addrs": [a.lower() for a in re.findall(r"[\w.+-]+@[\w.-]+", addr_blob)],
    }


def get_message(msg_id: str, mailbox: str | None = None) -> dict:
    """Full message → {id, threadId, sender, subject, date_ms, body, ...}."""
    return _parse_message(_get(f"/messages/{msg_id}", {"format": "full"}, mailbox))


def get_raw(msg_id: str, mailbox: str | None = None) -> str:
    """The RFC 2822 message, urlsafe-base64: the shape messages.insert takes."""
    return _get(f"/messages/{msg_id}", {"format": "raw"}, mailbox).get("raw") or ""


def insert_raw(raw: str, label_names: list[str] | None = None) -> dict:
    """Copy a raw message into the charter PO mailbox as NEW inbox mail:
    internalDate = now (so the poll's `after:` window sees it), INBOX + UNREAD
    (so it reads as just arrived). Original headers are preserved, so the PO
    extractor still sees the school as the sender. gmail.modify already covers
    messages.insert; no new delegation scope is needed."""
    ids = ["INBOX", "UNREAD"] + [ensure_label(n) for n in (label_names or []) if n]
    return _post("/messages", {"raw": raw, "labelIds": ids},
                 params={"internalDateSource": "receivedTime"})


# Attachment types the PO extractor can read (Claude reads PDFs + images natively).
_READABLE_MIMES = {"application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp"}
_MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024  # per attachment, decoded
_MAX_ATTACHMENTS = 3


def get_attachments(msg_id: str) -> list[dict]:
    """Readable attachments of a message as [{filename, mime, data_b64}] — data_b64 is
    STANDARD base64 (what the Anthropic API expects; Gmail hands back urlsafe).
    Oversized/unreadable attachments are skipped with a note on stdout."""
    m = _get(f"/messages/{msg_id}", {"format": "full"})
    found: list[dict] = []

    def _walk(part):
        for p in part.get("parts", []) or []:
            _walk(p)
        fname = part.get("filename")
        if not fname:
            return
        mime = (part.get("mimeType") or "").lower()
        if mime == "application/octet-stream" and fname.lower().endswith(".pdf"):
            mime = "application/pdf"
        if mime not in _READABLE_MIMES:
            print(f"    📎 skipping unreadable attachment {fname} ({mime})")
            return
        body = part.get("body", {})
        data = body.get("data")
        if not data and body.get("attachmentId"):
            att = _get(f"/messages/{msg_id}/attachments/{body['attachmentId']}")
            data = att.get("data")
        if not data:
            return
        raw = base64.urlsafe_b64decode(data)
        if len(raw) > _MAX_ATTACHMENT_BYTES:
            print(f"    📎 skipping oversized attachment {fname} ({len(raw)} bytes)")
            return
        found.append({"filename": fname, "mime": mime,
                      "data_b64": base64.b64encode(raw).decode()})

    _walk(m.get("payload", {}))
    if len(found) > _MAX_ATTACHMENTS:
        print(f"    📎 {len(found)} attachments; reading first {_MAX_ATTACHMENTS}")
    return found[:_MAX_ATTACHMENTS]


@lru_cache(maxsize=8)
def _labels(mailbox: str | None = None) -> dict:
    return {l["name"]: l["id"] for l in _get("/labels", None, mailbox).get("labels", [])}


def ensure_label(name: str, mailbox: str | None = None) -> str:
    """Label id for `name`, creating it if needed (supports 'Parent/Child' nesting)."""
    if name in _labels(mailbox):
        return _labels(mailbox)[name]
    if DRY_RUN:
        return "DRYRUN_LABEL"
    res = _post("/labels", {"name": name, "labelListVisibility": "labelShow",
                            "messageListVisibility": "show"}, mailbox)
    _labels.cache_clear()
    return res["id"]


def apply_labels(msg_id: str, names: list[str], mailbox: str | None = None) -> None:
    ids = [ensure_label(n, mailbox) for n in names if n]
    if ids:
        _post(f"/messages/{msg_id}/modify", {"addLabelIds": ids}, mailbox)


def _scrub_outbound(text: str) -> str:
    """NEVER an em dash or double hyphen in customer-facing copy (Roman
    2026-08-24, LOCKED). The extractor prompt already says so, but prompts
    drift (a Heartland draft shipped one on 2026-08-19) — this scrub is the
    enforcement, applied to every draft body at the choke point."""
    import re
    t = (text or "").replace(" — ", ", ").replace("—", ", ")
    t = re.sub(r"(?<=\w)\s*--\s*(?=\w)", ", ", t)
    return re.sub(r"\s+,", ",", t)


def create_draft_reply(thread_id: str, to_addr: str, subject: str, body: str,
                       in_reply_to: str = "", bcc: str = "") -> dict:
    """A REAL Gmail draft on the thread — sits in Drafts until a human sends it.
    bcc: the HubSpot log address, so the send lands on the contact timeline."""
    mime = MIMEText(_scrub_outbound(body))
    mime["To"] = to_addr
    mime["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if bcc:
        mime["Bcc"] = bcc
    if in_reply_to:
        mime["In-Reply-To"] = in_reply_to
        mime["References"] = in_reply_to
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    return _post("/drafts", {"message": {"threadId": thread_id, "raw": raw}})


def create_draft(to_addr: str, subject: str, body: str, bcc: str = "") -> dict:
    """A fresh-thread Gmail draft (outreach that should NOT quote a robot
    notification thread — e.g. parent-info requests to a TOR). Returns the
    draft resource; message.threadId is the NEW thread replies will land on."""
    mime = MIMEText(_scrub_outbound(body))
    mime["To"] = to_addr
    mime["Subject"] = subject
    if bcc:
        mime["Bcc"] = bcc
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    return _post("/drafts", {"message": {"raw": raw}})


def get_draft(draft_id: str) -> dict | None:
    """The draft, or None once it's been sent/discarded (404)."""
    try:
        return _get(f"/drafts/{draft_id}")
    except Exception:  # noqa: BLE001 — 404 = no longer a draft
        return None
