#!/usr/bin/env python3
"""Credential facts for the fleet — the ONLY way to read a credential claim.

Source of truth: knowledge/credentials.yml (#AP044).

Nothing in this repo should contain a credential claim string as a literal.
Agents resolve claims through this module so that (a) the term window always
travels with the claim, and (b) the `public_ready` gate is enforced in code
rather than by convention.

    from credentials import claim, is_public_ready, resolve

    claim("nssa_program_design_badge", surface="blog_author_bio")
        -> "NSSA Tutoring Program Design Badge, 2026-2029"   (when permitted)
        -> raises CredentialNotPublic                        (when not)

    resolve(text, surface="...")   # substitutes {{credentials.<id>.<field>}}

The gate fails CLOSED. A credential with public_ready false, an unapproved
surface, a prohibited surface, or an expired term raises rather than emitting
a partial or silently-empty claim: a claim that renders as "" in a vendor
packet is worse than a loud failure at build time.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = Path(os.getenv("APLUS_CREDENTIALS_PATH", REPO_ROOT / "knowledge" / "credentials.yml"))

TOKEN_RE = re.compile(r"\{\{\s*credentials\.([a-z0-9_]+)\.([a-z0-9_]+)\s*\}\}")


class CredentialError(Exception):
    """Base class. Callers that must not crash should catch this explicitly."""


class CredentialNotFound(CredentialError):
    pass


class CredentialNotPublic(CredentialError):
    """public_ready is false — usage terms unconfirmed."""


class CredentialSurfaceNotApproved(CredentialError):
    pass


class CredentialExpired(CredentialError):
    pass


_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        with CREDENTIALS_PATH.open() as f:
            _cache = yaml.safe_load(f) or {}
    return _cache


def reload() -> None:
    """Drop the cache. For tests and long-running processes."""
    global _cache
    _cache = None


def get(cred_id: str) -> dict:
    creds = _load().get("credentials") or {}
    if cred_id not in creds:
        raise CredentialNotFound(
            f"{cred_id!r} is not declared in {CREDENTIALS_PATH}. "
            f"Declare it there; never inline a claim string.")
    return creds[cred_id]


def is_public_ready(cred_id: str) -> bool:
    return bool(get(cred_id).get("public_ready"))


def days_until_expiry(cred_id: str, today: _dt.date | None = None) -> int | None:
    raw = get(cred_id).get("expires_on")
    if not raw:
        return None
    expires = raw if isinstance(raw, _dt.date) else _dt.date.fromisoformat(str(raw))
    return (expires - (today or _dt.date.today())).days


def check(cred_id: str, surface: str | None = None, today: _dt.date | None = None) -> dict:
    """Raise unless this credential may be used on this surface right now."""
    c = get(cred_id)
    if not c.get("public_ready"):
        raise CredentialNotPublic(
            f"{cred_id!r} has public_ready: false — usage guidelines are "
            f"unconfirmed, so the claim must not reach any external surface. "
            f"Flip it in {CREDENTIALS_PATH} only after the issuer's terms are read.")
    left = days_until_expiry(cred_id, today)
    if left is not None and left < 0:
        raise CredentialExpired(
            f"{cred_id!r} expired on {c.get('expires_on')}. Stop claiming it.")
    if surface is not None:
        if surface in (c.get("prohibited_surfaces") or []):
            raise CredentialSurfaceNotApproved(
                f"{cred_id!r} is explicitly prohibited on {surface!r}.")
        approved = c.get("approved_surfaces") or []
        if approved and surface not in approved:
            raise CredentialSurfaceNotApproved(
                f"{surface!r} is not in approved_surfaces for {cred_id!r}: {approved}")
    return c


def claim(cred_id: str, surface: str | None = None, today: _dt.date | None = None) -> str:
    """The canonical claim string, or raise. Never paraphrase the result."""
    return check(cred_id, surface, today)["claim_string"]


def resolve(text: str, surface: str | None = None, today: _dt.date | None = None,
            missing: str = "raise") -> str:
    """Substitute {{credentials.<id>.<field>}} tokens in `text`.

    missing="raise"  — gate failures raise (default; correct for build steps)
    missing="strip"  — gate failures remove the whole token, leaving no trace.
                       Only for surfaces where an absent claim is acceptable
                       and a crash is not (e.g. an optional merge field).
    """
    if missing not in ("raise", "strip"):
        raise ValueError("missing must be 'raise' or 'strip'")

    def sub(m: re.Match) -> str:
        cred_id, field = m.group(1), m.group(2)
        try:
            c = check(cred_id, surface, today)
        except CredentialError:
            if missing == "strip":
                return ""
            raise
        if field not in c:
            raise CredentialNotFound(f"{cred_id!r} has no field {field!r}")
        value = c[field]
        if value is None:
            if missing == "strip":
                return ""
            raise CredentialNotFound(
                f"{cred_id}.{field} is null — it has not been filled in yet.")
        return str(value)

    return TOKEN_RE.sub(sub, text)


def has_credential_token(text: str) -> bool:
    return bool(TOKEN_RE.search(text or ""))


if __name__ == "__main__":
    import json
    for cid, c in (_load().get("credentials") or {}).items():
        left = days_until_expiry(cid)
        print(f"{cid}:")
        print(f"  claim        {c.get('claim_string')!r}")
        print(f"  public_ready {c.get('public_ready')}")
        print(f"  expires      {c.get('expires_on')} ({left} days)")
        print(f"  unknowns     {json.dumps([k for k, v in c.items() if v is None])}")
