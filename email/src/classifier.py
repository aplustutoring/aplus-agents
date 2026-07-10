"""Claude (Sonnet) email classifier — structured JSON only.

Sends ONLY the email body + the structured enrichment summary + rules.md to Claude
(FERPA: never full student records/attachments). Returns validated JSON:
  {category, risk, confidence, routing_target, sla_tier, draft_reply, reason}
Retries once on malformed output.
"""
import json
import re

from .config import ANTHROPIC_API_KEY, ROOT, cfg

REQUIRED_KEYS = {
    "category", "risk", "confidence", "routing_target",
    "sla_tier", "draft_reply", "reason",
}

VALID_CATEGORIES = {
    "reschedule", "scheduling", "cancellation", "tutor_issue",
    "school_partner", "business_dev", "complaint", "payment_dispute",
    "tor_inquiry", "new_po", "tutor_document", "recruitment",
    "charter_newsletter", "junk", "unknown",
}


class ClassificationError(Exception):
    pass


def parse_classification(text: str) -> dict:
    """Extract + validate the JSON object from a model response.

    Tolerates ```json fences and surrounding prose by grabbing the outermost
    brace pair. Raises ClassificationError on malformed/incomplete output.
    """
    if not text or not text.strip():
        raise ClassificationError("empty response")

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()

    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ClassificationError(f"no JSON object found in: {text[:200]!r}")

    try:
        obj = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as e:
        raise ClassificationError(f"invalid JSON: {e}")

    missing = REQUIRED_KEYS - obj.keys()
    if missing:
        raise ClassificationError(f"missing keys: {sorted(missing)}")

    obj["category"] = str(obj["category"]).strip().lower()
    if obj["category"] not in VALID_CATEGORIES:
        obj["category"] = "unknown"

    try:
        obj["confidence"] = float(obj["confidence"])
    except (TypeError, ValueError):
        raise ClassificationError(f"confidence not numeric: {obj['confidence']!r}")
    obj["confidence"] = max(0.0, min(1.0, obj["confidence"]))

    obj["risk"] = str(obj.get("risk", "")).strip().lower() or "medium"
    obj.setdefault("cancellation_reason", "")  # optional; populated for cancellations
    obj.setdefault("cancellation_type", "")    # optional; stop|pause for cancellations
    obj.setdefault("parent_last_name", "")     # optional; family surname from content
    obj.setdefault("student_first_name", "")   # optional; student first name (disambiguation)
    obj.setdefault("internal_recipient", "")   # optional; teammate an internal email addresses
    obj.setdefault("schedule_preference", "")  # optional; stated days/times for sessions
    obj.setdefault("student_grade", "")        # optional; student's grade level if stated/derivable
    return obj


def _rules_md() -> str:
    return (ROOT / "rules.md").read_text()


SYSTEM = (
    "You are the triage classifier for A+ Tutoring's company inbox. "
    "Classify the email using the rules provided. "
    "Respond with a SINGLE JSON object and nothing else — no prose, no code fences. "
    "Keys: category, risk, confidence, routing_target, sla_tier, draft_reply, reason, "
    "cancellation_reason, cancellation_type, parent_last_name, student_first_name, internal_recipient. "
    "confidence is a number 0-1. risk is high|medium|low. "
    "For cancellation emails (including Teachworks notifications), set cancellation_reason "
    "to the stated reason; otherwise an empty string. "
    "cancellation_type (only for category=cancellation) = one of: 'one_time' (skip/cancel a "
    "single session, family stays), 'pause' (temporary — postpone, summer break, resume "
    "later), or 'stop' (permanently ending/quitting). Be conservative: unsure between stop "
    "and pause → 'pause'; unsure if it's even ongoing → 'one_time'. Empty if not a cancellation. "
    "Use category 'reschedule' (NOT cancellation) when they want to MOVE a session to another "
    "time, and 'tutor_issue' when they're unhappy with the tutor or want a different one. "
    "parent_last_name = the LAST NAME of the parent/family the email is about, read from "
    "the email content (e.g. a Teachworks notice that says 'Layla Schnider has cancelled' "
    "→ 'Schnider'; a signature or 'the Martinez family' → 'Martinez'). It is the family/"
    "parent surname, never the tutor or staff. Empty string if none is stated. "
    "student_first_name = the FIRST name of the STUDENT named in the email ('Layla "
    "Schnider has cancelled' → 'Layla'), used to disambiguate same-surname families. Empty if none. "
    "internal_recipient = if the email is from an A+ staff member to another A+ teammate, "
    "the FIRST NAME the email is addressed to (e.g. 'Hi Kath,' → 'Kath'); else empty. "
    "schedule_preference = any stated days/times for sessions ('Thursdays after 4pm PT'); "
    "empty if not stated. student_grade = the student's grade level if stated or clearly "
    "derivable ('below 2nd grade level on her report card' → '2'); empty otherwise. "
    "For scheduling/reschedule emails missing a schedule preference, the draft_reply "
    "should ASK for preferred days/times. "
    "draft_reply is the proposed reply text (warm, first person plural 'we', no em dashes, "
    "signed 'A+ Tutoring Team'), or an empty string if no reply should be drafted."
)


def build_user_prompt(body: str, enrichment_summary: str) -> str:
    return (
        f"{_rules_md()}\n\n"
        "=== EMAIL BODY ===\n"
        f"{body}\n\n"
        "=== ENRICHMENT SUMMARY (structured, no raw student records) ===\n"
        f"{enrichment_summary}\n\n"
        "Return the JSON object now."
    )


def classify(body: str, enrichment_summary: str, client=None) -> dict:
    """Call Claude Sonnet and return validated classification JSON (retry once)."""
    from anthropic import Anthropic  # imported lazily so tests need no SDK

    client = client or Anthropic(api_key=ANTHROPIC_API_KEY)
    c = cfg()["classifier"]
    user = build_user_prompt(body, enrichment_summary)

    last_err = None
    for attempt in range(2):
        msg = client.messages.create(
            model=c["model"],
            max_tokens=c["max_tokens"],
            system=SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        try:
            return parse_classification(text)
        except ClassificationError as e:
            last_err = e
            user += (
                "\n\nYour previous response was not valid. "
                "Return ONLY the JSON object with all required keys."
            )
    raise ClassificationError(f"classifier failed after retry: {last_err}")
