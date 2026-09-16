"""Path wiring for the agent: it reuses the email engine's HubSpot client,
audit log, Slack client and pre-send gate, and the messenger's one_to_few
rail. Nothing here is new infrastructure; it is the price of living in
agents/ instead of email/src/.

Import order matters: DRY_RUN is read from the environment when src.config
loads, so __main__ sets DRY_RUN before importing this module.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EMAIL_DIR = ROOT / "email"
MESSENGER_DIR = ROOT / "ops" / "messenger"
ALIAS_FILE = ROOT / "ops" / "hubspot-schema" / "school-aliases.yml"

for p in (str(EMAIL_DIR), str(MESSENGER_DIR), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from src import audit, hubspot_client as hs, presend, slack_client  # noqa: E402
from src.config import DRY_RUN, cfg as email_cfg, google_creds_dict, staff  # noqa: E402
from src.gmail_client import _scrub_outbound as scrub  # noqa: E402
import one_to_few as otf  # noqa: E402

# A dry run must still SEE HubSpot: the plan says create vs update per contact
# and deal, which is a search. The client blanks every POST under DRY_RUN
# unless this flag lets /search through (first live dry run 2026-09-16 called
# Roman's and Danielle's existing contacts "create").
hs.SEARCH_PASSTHROUGH = True

__all__ = ["audit", "hs", "presend", "slack_client", "DRY_RUN", "email_cfg", "google_creds_dict",
           "staff", "scrub", "otf", "agent_cfg", "school_resolver", "ROOT", "EMAIL_DIR"]

_CFG: dict | None = None


def agent_cfg() -> dict:
    global _CFG
    if _CFG is None:
        _CFG = yaml.safe_load((HERE / "config.yml").read_text())
    return _CFG


def _key(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def school_resolver():
    """alias spelling → canonical school, from ops/hubspot-schema/school-aliases.yml
    (the same exact-match rule as scripts/teacher_school_stamp.py: never fuzzy,
    an unlisted spelling is reported by the validator, never guessed)."""
    spec = yaml.safe_load(ALIAS_FILE.read_text())
    aliases: dict[str, str] = {}
    for s in spec.get("schools", []):
        canon = s["canonical"]
        for a in (s.get("aliases") or []) + [canon]:
            aliases[_key(a)] = canon
    return lambda raw: aliases.get(_key(raw))
