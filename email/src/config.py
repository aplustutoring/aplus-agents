"""Central config + secrets loader.

Local dev reads a gitignored .env (via python-dotenv). In GitHub Actions the same
names are injected by the workflow `env:` block, so os.environ already has them.
config.yaml holds the non-secret routing/owner/board config.
"""
import json
import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv(override=False)  # CI env wins; .env fills gaps for local dev

ROOT = Path(__file__).resolve().parent.parent

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# ── Secrets (env) ────────────────────────────────────────────────
HUBSPOT_PRIVATE_APP_TOKEN = os.getenv("HUBSPOT_PRIVATE_APP_TOKEN", "")
# Two Teachworks accounts. Online token accepts either name (CI secret uses
# TEACHWORKS_TOKEN; local .env uses the clearer TEACHWORKS_TOKEN_ONLINE).
TEACHWORKS_TOKEN = os.getenv("TEACHWORKS_TOKEN", "") or os.getenv("TEACHWORKS_TOKEN_ONLINE", "")
TEACHWORKS_TOKEN_INPERSON = os.getenv("TEACHWORKS_TOKEN_INPERSON", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
MONDAY_TOKEN = os.getenv("MONDAY_TOKEN", "")
GOOGLE_SHEETS_CREDS = os.getenv("GOOGLE_SHEETS_CREDS", "")


# Accountability-chart resolution (Roman, 2026-08-14): config.yaml names ROLES
# in these keys; at load time each role resolves to its staff key via the
# roles: block, so every consumer keeps working with resolved people.
_ROLE_KEYS = {"owner", "recipient", "assign_to", "cc_owner_dms_to", "fallback",
              "level2", "level3", "a_to_l", "m_to_z", "charter_sales",
              "compliance_owner"}
_ROLE_LIST_KEYS = {"missing_info_dms", "monitor"}


def _resolve_roles(node, roles: dict) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _ROLE_KEYS and isinstance(v, str) and v in roles:
                node[k] = roles[v]
            elif k in _ROLE_LIST_KEYS and isinstance(v, list):
                node[k] = [roles.get(x, x) for x in v]
            else:
                _resolve_roles(v, roles)
    elif isinstance(node, list):
        for v in node:
            _resolve_roles(v, roles)


@lru_cache(maxsize=1)
def cfg() -> dict:
    """Parsed config.yaml (cached), with role seats resolved to staff keys."""
    with open(ROOT / "config.yaml") as f:
        c = yaml.safe_load(f)
    _resolve_roles(c, c.get("roles") or {})
    return c


def staff(key: str) -> dict:
    """Resolve a ROLE title (accountability-chart seat: charter_admin,
    scheduler_a_l, visionary, …) OR a legacy staff key to the staff record.
    Functional config names ROLES, never people (Roman, 2026-08-14) — the
    roles: block maps seat → person; the staff: block is the only place
    names live. Team change = edit roles:, nothing else."""
    c = cfg()
    st = c.get("staff") or {}
    if key in st:
        return st[key] or {}
    return st.get((c.get("roles") or {}).get(key, ""), {}) or {}


def google_creds_dict():
    """Return the Google service-account creds as a dict.

    Accepts either a path to a JSON file (local dev) or the raw JSON string
    (CI secret). Returns None if unset.
    """
    raw = GOOGLE_SHEETS_CREDS.strip()
    if not raw:
        return None
    if raw.startswith("{"):
        return json.loads(raw)
    p = Path(raw)
    if p.exists():
        return json.loads(p.read_text())
    raise ValueError("GOOGLE_SHEETS_CREDS is neither valid JSON nor an existing file path")


def require(*names: str) -> None:
    """Raise if any required secret is missing (skip the check in DRY_RUN)."""
    if DRY_RUN:
        return
    missing = [n for n in names if not os.getenv(n)]
    if missing:
        raise RuntimeError(f"Missing required secrets: {', '.join(missing)}")
