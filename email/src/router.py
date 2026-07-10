"""Routing table + SLA resolution (LOCKED June 9, 2026).

Maps a classified category (+ confidence + student last name) to an owner,
SLA hours, and whether a reply should be drafted. The A-L / M-Z last-name split
applies to `scheduling` and `cancellation`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import cfg


@dataclass
class RouteDecision:
    category: str            # effective category (may be downgraded to 'unknown')
    owner_key: str | None    # staff key in config.staff, or None (junk)
    owner: dict | None       # staff record {name, hubspot_owner_id, slack_user_id}
    sla_hours: float | None
    should_draft: bool
    auto_archive: bool = False
    fyi: bool = False
    review: bool = False
    priority: str = "normal"
    notes: list[str] = field(default_factory=list)


def last_name_initial(last_name: str | None) -> str | None:
    """First alphabetic character of a last name, uppercased; None if unknown."""
    if not last_name:
        return None
    for ch in last_name.strip():
        if ch.isalpha():
            return ch.upper()
    return None


def scheduler_for_last_name(last_name: str | None) -> tuple[str | None, list[str]]:
    """Return (staff_key, notes) using the A-L / M-Z split."""
    split = cfg()["scheduler_split"]
    initial = last_name_initial(last_name)
    if initial is None:
        # No last name to split on — default to the A-L scheduler and flag.
        return split["a_to_l"], ["last name unknown; defaulted scheduler, needs review"]
    if initial <= "L":
        return split["a_to_l"], []
    return split["m_to_z"], []


def resolve(category: str, confidence: float, last_name: str | None = None) -> RouteDecision:
    c = cfg()
    routing = c["routing"]
    thresholds = c["thresholds"]
    no_draft = set(c["no_draft_categories"])
    min_conf = thresholds["min_confidence"]

    notes: list[str] = []

    # Low confidence → unknown (ticket only, no draft), regardless of category.
    if confidence < min_conf:
        notes.append(f"confidence {confidence:.2f} < {min_conf}; downgraded to unknown")
        category = "unknown"

    # Junk needs HIGHER certainty to auto-archive (LOCKED): below the junk threshold it
    # becomes unknown → Stuck for human review instead of silently disappearing.
    junk_min = thresholds.get("junk_auto_archive", 0.9)
    if category == "junk" and confidence < junk_min:
        notes.append(f"junk at {confidence:.2f} < {junk_min}; held for review instead of archiving")
        category = "unknown"

    rule = routing.get(category)
    if rule is None:
        notes.append(f"unmapped category '{category}'; routed as unknown")
        category = "unknown"
        rule = routing["unknown"]

    # Owner resolution.
    owner_key = rule.get("owner")
    if owner_key in ("scheduler_split", "assigned_scheduler"):
        owner_key, split_notes = scheduler_for_last_name(last_name)
        notes += split_notes

    owner = c["staff"].get(owner_key) if owner_key else None

    # Draft suppression rules.
    should_draft = bool(rule.get("draft")) and category not in no_draft
    if category in ("unknown", "junk"):
        should_draft = False

    return RouteDecision(
        category=category,
        owner_key=owner_key,
        owner=owner,
        sla_hours=rule.get("sla_hours"),
        should_draft=should_draft,
        auto_archive=bool(rule.get("auto_archive")),
        fyi=bool(rule.get("fyi")),
        review=bool(rule.get("review")),
        priority=rule.get("priority", "normal"),
        notes=notes,
    )
