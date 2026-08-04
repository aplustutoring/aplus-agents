#!/usr/bin/env python3
"""
A+ Tutoring — Automation Audit v1 (Fleet Manager, first mission)

READ-ONLY census of every HubSpot workflow/flow: inventory, uselessness
signals, and the DOORBELL / PLUMBING / DECIDER / GUARDRAIL classification
(#AP016). Produces an HTML report, drafted Decision Log entries, and a JSON
run summary. NOTHING is modified, disabled, or deleted — this script only
issues GET requests (plus HubSpot's documented read-only token-introspection
POST, which is required for the write-scope guardrail).

Usage:
  HUBSPOT_AUDIT_TOKEN=pat-... python3 audit_hubspot_workflows.py
  python3 audit_hubspot_workflows.py --selftest      # offline fixture run
  python3 audit_hubspot_workflows.py --out-dir /tmp/audit

Guardrails (fleet doctrine):
  * Refuses to run if the token carries ANY write scope (#AP008 dry-run spirit).
  * Enumeration properties are reported by LABEL, never internal value (#AP014).
  * Evidence, not verdicts — every flag carries the raw datum it came from.
  * Anything the API does not expose is reported as "unknown", never guessed.

Endpoints (verified against developers.hubspot.com, 2026-07):
  POST /oauth/v2/private-apps/get/access-token-info   token scopes (guardrail)
  GET  /automation/v4/flows                            flow list (cursor paging)
  GET  /automation/v4/flows/{flowId}                   full flow detail
  GET  /automation/v3/workflows                        classic workflows fallback
  GET  /automation/v3/workflows/{id}?stats=true        enrollment totals (contact flows)
  GET  /crm/v3/properties/{objectType}                 property schema (labels)
  GET  /crm/v3/pipelines/{objectType}                  pipeline/stage existence
  GET  /crm/v3/lists/{listId}                          list existence
  GET  /marketing/v3/emails/{emailId}                  email/template existence
"""

import argparse
import html as html_mod
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None  # allowed for --selftest, refused for a live run

try:
    import yaml
except ImportError:
    yaml = None

BASE = "https://api.hubapi.com"
AUDIT_DIR = Path(__file__).resolve().parent
REPO_ROOT = AUDIT_DIR.parents[2]
REGISTRY_PATH = REPO_ROOT / "registry.yml"

NOW = datetime.now(timezone.utc)
TODAY = NOW.strftime("%Y-%m-%d")

# Documented CRM object type ids.
OBJECT_TYPE_LABELS = {
    "0-1": "contacts",
    "0-2": "companies",
    "0-3": "deals",
    "0-5": "tickets",
    "0-7": "products",
    "0-8": "line_items",
    "0-11": "conversations",
    "0-27": "tasks",
    "0-49": "communications",
}

# Signal keywords — these are transparent heuristics; every classification in
# the report shows the signals it was derived from so a human can re-bucket.
GUARDRAIL_NAME_KEYWORDS = (
    "dedup", "de-dup", "duplicate guard", "suppress", "suppression",
    "re-ping", "reping", "timer", "cooldown", "cool-down", "guard",
    "do not", "don't", "throttle", "rate limit",
)
# Branching that is mechanical, not judgment (#AP016 names the grade
# incrementer explicitly) — branches + one of these names = still PLUMBING.
PLUMBING_NAME_KEYWORDS = (
    "grade increment", "increment", "copy ", "timestamp", "date stamp",
    "datestamp", "sync ",
)
WEBHOOK_FIELD_KEYWORDS = ("webhook", "webhookurl", "url_to_notify")
NOTIFY_FIELD_KEYWORDS = (
    "notification", "send_internal", "internal_email", "in_app",
    "slack", "notify",
)
PROPERTY_SET_KEYWORDS = (
    "set_property", "set_contact_property", "set_deal_property",
    "copy_property", "copy_prop", "date_stamp", "datestamp",
    "increment", "clear_property",
)

# Absorption routing: keyword → fleet agent. First match wins, top to bottom.
ABSORPTION_MAP = [
    ("Tutor Onboarding", ("tutor",)),
    ("Low-Balance/PO", ("low balance", "low-balance", "balance", "purchase order",
                        " po ", "po -", "po:", "invoice", "payment", "renewal",
                        "hours remaining")),
    ("Revival", ("revival", "revive", "re-engage", "reengage", "winback",
                 "win-back", "win back", "dormant", "cold lead", "lapsed")),
    ("Onboarding", ("onboard", "welcome", "new student", "new family",
                    "intake", "kickoff", "kick-off", "first lesson")),
    ("Conversation", ("call", "sms", "text message", "conversation", "chat",
                      "voicemail", "missed call")),
    ("Email Engine v2", ("email", "nurture", "newsletter", "drip", "follow-up",
                         "follow up", "sequence", "digest")),
]

DAYS_180 = timedelta(days=180)
DAYS_365 = timedelta(days=365)
DAYS_730 = timedelta(days=730)

DECISION_LOG_DOC_ID = "1rulyEYlUldSEPvlZtoM6KcKBa2tJ8ZlZ-HMDybbMYCI"


def log(msg):
    print(f"[audit] {msg}", flush=True)


def die(msg, code=2):
    print(f"[audit] FATAL: {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


# ───────────────────────────── HubSpot client ─────────────────────────────

class HubSpotClient:
    """GET-only client. The single POST it makes is HubSpot's documented
    read-only token-introspection endpoint (needed for the scope guardrail)."""

    TOKEN_INFO_PATH = "/oauth/v2/private-apps/get/access-token-info"

    def __init__(self, token):
        self.token = token
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.calls = 0

    def _request(self, method, path, **kwargs):
        if method != "GET" and path != self.TOKEN_INFO_PATH:
            raise RuntimeError(f"write-shaped request blocked: {method} {path}")
        url = BASE + path
        for attempt in range(5):
            self.calls += 1
            resp = self.session.request(method, url, timeout=30, **kwargs)
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", 2 ** attempt))
                time.sleep(min(wait, 30))
                continue
            if resp.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            return resp
        return resp

    def get(self, path, params=None):
        return self._request("GET", path, params=params)

    def get_json(self, path, params=None):
        resp = self.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def token_info(self):
        resp = self._request("POST", self.TOKEN_INFO_PATH,
                             json={"tokenKey": self.token})
        resp.raise_for_status()
        return resp.json()


def verify_token_readonly(client, accept_write_scoped=False):
    """Refuse to run unless we can PROVE the token has no write scope.

    With --accept-write-scoped-token the refusal becomes a loud warning:
    the client still hard-blocks every non-GET request, so the run stays
    read-only structurally — but the doctrine-preferred setup is a dedicated
    read-only app, and the override is recorded in the run summary."""
    try:
        info = client.token_info()
    except Exception as exc:
        die(f"could not verify token scopes ({exc}). Refusing to run: the "
            "read-only guardrail requires provable scopes.")
    scopes = info.get("scopes") or []
    write_scopes = [s for s in scopes if "write" in s.lower()]
    if write_scopes and not accept_write_scoped:
        die("token carries WRITE scopes — refusing to run. This audit is "
            f"read-only by doctrine. Offending scopes: {write_scopes}. "
            "Either create a read-only private app for HUBSPOT_AUDIT_TOKEN, "
            "or re-run with --accept-write-scoped-token to proceed anyway "
            "(the HTTP client still blocks every non-GET request).")
    if write_scopes:
        log(f"WARNING: token carries WRITE scopes {write_scopes} — accepted "
            "via --accept-write-scoped-token. The client enforces GET-only, "
            "but doctrine prefers a dedicated read-only app.")
    if not scopes:
        die("token introspection returned zero scopes — refusing to run.")
    log(f"token verified ({len(scopes)} scopes, hub "
        f"{info.get('hubId')}): {sorted(scopes)}")
    return sorted(scopes), sorted(write_scopes)


# ───────────────────────────── data collection ─────────────────────────────

def fetch_flows(client):
    """v4 flows (primary) merged with v3 classic workflows.

    The two APIs use DIFFERENT id namespaces for the SAME workflows (classic
    workflows migrated to the flows platform keep a v3 id and gain a v4 id).
    Naive union double-counts them — verified live 2026-07-27: 155 of 172 v3
    workflows matched a v4 flow by name. So: a v3 workflow whose name matches
    exactly one v4 flow is folded INTO that v4 record (contributing its
    enrollment stats); only genuinely v3-only workflows become records."""
    flows = {}
    after = None
    while True:
        params = {"limit": 100}
        if after:
            params["after"] = after
        page = client.get_json("/automation/v4/flows", params=params)
        for summary in page.get("results", []):
            flows[str(summary["id"])] = {"summary": summary, "source": "v4"}
        after = (page.get("paging") or {}).get("next", {}).get("after")
        if not after:
            break
    log(f"v4 flow list: {len(flows)} flows")

    for fid, entry in flows.items():
        detail = client.get_json(f"/automation/v4/flows/{fid}")
        entry["detail"] = detail

    def norm(name):
        return (name or "").strip().lower()

    by_name = defaultdict(list)
    for fid, entry in flows.items():
        by_name[norm(entry["detail"].get("name"))].append(fid)

    try:
        v3 = client.get_json("/automation/v3/workflows")
        v3_workflows = v3.get("workflows", v3 if isinstance(v3, list) else [])
        merged = standalone = 0
        for wf in v3_workflows:
            twins = by_name.get(norm(wf.get("name")), [])
            if len(twins) == 1:
                flows[twins[0]]["v3_stats"] = wf
                merged += 1
            else:
                wid = f"v3-{wf.get('id')}"
                note = (f"name matches {len(twins)} v4 flows — kept separate"
                        if twins else None)
                flows[wid] = {"summary": wf, "detail": wf, "source": "v3",
                              "v3_stats": wf, "merge_note": note}
                standalone += 1
        log(f"v3 classic list: {len(v3_workflows)} workflows — {merged} merged "
            f"into their v4 twin by name, {standalone} kept standalone")
    except Exception as exc:
        log(f"v3 workflow list unavailable ({exc}) — continuing with v4 only")

    return flows


def fetch_activity(entry):
    """Enrollment stats. The public API exposes per-workflow TOTALS for
    classic contact workflows — as `contactCounts` on the v3 LIST response
    (verified live; the per-workflow detail endpoint does NOT return counts).
    It exposes NO windowed (90d/180d/365d) counts — those stay 'unknown',
    never guessed."""
    activity = {
        "status": "unknown",
        "total_enrolled": None,
        "currently_active": None,
        "enrollments_90d": "unknown",
        "enrollments_365d": "unknown",
        "source": None,
        "raw_counts": {},
    }
    wf = entry.get("v3_stats")
    if not wf:
        return activity
    cc = wf.get("contactCounts")
    if not isinstance(cc, dict):
        return activity
    activity["raw_counts"] = {"contactCounts": cc}
    activity["source"] = (f"GET /automation/v3/workflows list item "
                          f"(classic id {wf.get('id')})")
    if isinstance(cc.get("enrolled"), int):
        activity["total_enrolled"] = cc["enrolled"]
        activity["status"] = "known_totals_only"
    if isinstance(cc.get("active"), int):
        activity["currently_active"] = cc["active"]
        activity["status"] = "known_totals_only"
    return activity


# ─────────────────────────── reference extraction ──────────────────────────

REF_PROPERTY_KEYS = {"property", "propertyname", "propertynames",
                     "targetproperty", "sourceproperty"}
REF_LIST_KEYS = {"listid", "listids", "suppressionlistids"}
REF_PIPELINE_KEYS = {"pipelineid", "pipeline"}
REF_STAGE_KEYS = {"stageid", "dealstage", "hspipelinestage", "stage"}
REF_EMAIL_KEYS = {"emailcontentid", "contentid", "templateid",
                  "marketingemailid", "emailid"}
# Values that LOOK like property names but are HubSpot-internal event-filter
# meta keys (re-enrollment trigger filters carry property=hs_name/hs_value
# meaning "the changed property's name/value") — verified live 2026-07-27.
PROPERTY_VALUE_DENYLIST = {"hs_name", "hs_value"}
# Fields of the LEGACY unified engagements object (branch filters like "has
# engagement of type CALL") — real fields, but they predate /crm/v3/properties
# and cannot be verified there. Verified live 2026-07-27.
LEGACY_ENGAGEMENT_FIELDS = {"hs_engagement_type"}


def _walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, f"{path}.{k}" if path else k)
            yield (path, k, v)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")


def collect_references(detail):
    """Walk the raw flow JSON and pull out every property / list / pipeline /
    stage / email reference we can recognize by documented key names."""
    refs = []
    seen = set()

    def add(kind, identifier, where):
        key = (kind, str(identifier))
        if key in seen or identifier in (None, "", []):
            return
        seen.add(key)
        refs.append({"kind": kind, "id": str(identifier), "where": where,
                     "status": "unchecked", "label": None, "detail": None})

    for path, key, val in _walk(detail):
        lk = key.lower().replace("_", "")   # matches property_name AND propertyName
        if lk in REF_PROPERTY_KEYS:
            # Properties inside event-filter, (re-enrollment) trigger-filter,
            # and goal filter-line branches are EVENT fields (form-submission,
            # email-open, property-changed, …), not CRM schema properties —
            # they cannot be verified against /crm/v3/properties. Same for
            # legacy engagements-object fields in branch filters.
            lp = path.lower()
            is_event_path = any(seg in lp for seg in
                                ("eventfilter", "triggersfilter",
                                 "filterlines", "goalfilter"))
            for v in (val if isinstance(val, list) else [val]):
                if (isinstance(v, str) and re.fullmatch(r"[a-z0-9_.\-]+", v)
                        and v not in PROPERTY_VALUE_DENYLIST):
                    kind = ("event_property"
                            if is_event_path or v in LEGACY_ENGAGEMENT_FIELDS
                            else "property")
                    add(kind, v, path)
        elif lk in REF_LIST_KEYS:
            for v in (val if isinstance(val, list) else [val]):
                if isinstance(v, (int, str)) and str(v).isdigit():
                    add("list", v, path)
        elif lk in REF_PIPELINE_KEYS and isinstance(val, (str, int)):
            add("pipeline", val, path)
        elif lk in REF_STAGE_KEYS and isinstance(val, (str, int)):
            add("stage", val, path)
        elif lk in REF_EMAIL_KEYS and isinstance(val, (int, str)) and str(val).isdigit():
            add("email", val, path)
    return refs


class SchemaCache:
    """Lazy caches for CRM schemas so we resolve labels once (#AP014)."""

    def __init__(self, client):
        self.client = client
        self.properties = {}   # objectType -> {name: {label, options{value:label}}}
        self.pipelines = {}    # objectType -> {pipelineId: {label, stages{id:label}}}
        self.list_status = {}  # listId -> (status, label)
        self.email_status = {}

    def props_for(self, object_type):
        if object_type not in self.properties:
            try:
                data = self.client.get_json(f"/crm/v3/properties/{object_type}")
                self.properties[object_type] = {
                    p["name"]: {
                        "label": p.get("label") or p["name"],
                        "options": {o.get("value"): o.get("label")
                                    for o in (p.get("options") or [])},
                    }
                    for p in data.get("results", [])
                }
            except Exception as exc:
                log(f"schema fetch failed for {object_type}: {exc}")
                self.properties[object_type] = None
        return self.properties[object_type]

    def pipelines_for(self, object_type):
        if object_type not in self.pipelines:
            try:
                data = self.client.get_json(f"/crm/v3/pipelines/{object_type}")
                self.pipelines[object_type] = {
                    p["id"]: {
                        "label": p.get("label"),
                        "stages": {s["id"]: s.get("label")
                                   for s in p.get("stages", [])},
                    }
                    for p in data.get("results", [])
                }
            except Exception:
                self.pipelines[object_type] = None
        return self.pipelines[object_type]

    def check_list(self, list_id):
        if list_id not in self.list_status:
            resp = self.client.get(f"/crm/v3/lists/{list_id}")
            if resp.status_code == 200:
                name = (resp.json().get("list") or resp.json()).get("name")
                self.list_status[list_id] = ("ok", name)
            elif resp.status_code == 404:
                self.list_status[list_id] = ("broken", None)
            else:
                self.list_status[list_id] = ("unverifiable",
                                             f"HTTP {resp.status_code}")
        return self.list_status[list_id]

    def check_email(self, email_id):
        if email_id not in self.email_status:
            resp = self.client.get(f"/marketing/v3/emails/{email_id}")
            if resp.status_code == 200:
                self.email_status[email_id] = ("ok", resp.json().get("name"))
            elif resp.status_code == 404:
                self.email_status[email_id] = ("broken", None)
            else:
                self.email_status[email_id] = ("unverifiable",
                                               f"HTTP {resp.status_code}")
        return self.email_status[email_id]


# Where a property may legitimately live: the flow's own object, the other
# standard CRM objects (cross-object actions via associations), and the
# engagement objects (workflows set/read call/meeting/task fields).
PROPERTY_SCHEMA_CANDIDATES = ["0-1", "0-2", "0-3", "0-5",
                              "calls", "meetings", "tasks", "notes", "emails"]


def verify_references(schema, record):
    obj_type = record["object_type_id"] or "0-1"

    for ref in record["references"]:
        if ref["kind"] == "event_property":
            ref["status"] = "unverifiable"
            ref["detail"] = ("event-filter field — not verifiable against "
                            "CRM property schemas")
        elif ref["kind"] == "property":
            hit = None
            found_on = None
            for candidate in [obj_type] + PROPERTY_SCHEMA_CANDIDATES:
                table = schema.props_for(candidate)
                if table and ref["id"] in table:
                    hit, found_on = table[ref["id"]], candidate
                    break
            if hit:
                ref["status"] = "ok"
                ref["label"] = hit["label"]
                if found_on != obj_type:
                    ref["detail"] = f"found on {found_on} (cross-object)"
            elif schema.props_for(obj_type) is None:
                ref["status"] = "unverifiable"
                ref["detail"] = "property schema unavailable (scope?)"
            else:
                ref["status"] = "broken"
                ref["detail"] = (f"property not found on {obj_type} or any "
                                "standard/engagement schema")
        elif ref["kind"] == "list":
            status, label = schema.check_list(ref["id"])
            ref["status"], ref["label"] = status, label
            if status == "broken":
                ref["detail"] = "list id returns 404"
        elif ref["kind"] in ("pipeline", "stage"):
            found = None
            for ot in ("deals", "tickets"):
                pl = schema.pipelines_for(ot)
                if not pl:
                    continue
                if ref["kind"] == "pipeline" and ref["id"] in pl:
                    found = pl[ref["id"]]["label"]
                if ref["kind"] == "stage":
                    for p in pl.values():
                        if ref["id"] in p["stages"]:
                            found = p["stages"][ref["id"]]
            if found:
                ref["status"], ref["label"] = "ok", found
            else:
                ref["status"] = "broken"
                ref["detail"] = f"{ref['kind']} id not found in deal/ticket pipelines"
        elif ref["kind"] == "email":
            status, label = schema.check_email(ref["id"])
            ref["status"], ref["label"] = status, label
            if status == "broken":
                ref["detail"] = "email/template id returns 404"


# ──────────────────────── classification + scoring ─────────────────────────

def summarize_actions(detail):
    """Reduce the raw action list to transparent signals."""
    actions = detail.get("actions") or []
    signals = []
    branch_count = 0
    for a in actions:
        atype = str(a.get("type", ""))
        atid = str(a.get("actionTypeId", ""))
        blob = json.dumps(a).lower()
        kinds = set()
        if atype in ("LIST_BRANCH", "STATIC_BRANCH") or "branch" in atype.lower():
            kinds.add("branch")
            branch_count += 1
        if any(k in blob for k in WEBHOOK_FIELD_KEYWORDS):
            kinds.add("webhook")
        if any(k in blob for k in NOTIFY_FIELD_KEYWORDS):
            kinds.add("notify")
        if any(k in blob for k in PROPERTY_SET_KEYWORDS) or \
                ("propertyname" in blob and "value" in blob):
            kinds.add("property_set")
        if "delay" in atype.lower() or "delay" in blob[:200]:
            kinds.add("delay")
        if not kinds:
            kinds.add("other")
        signals.append({"type": atype or "?", "actionTypeId": atid,
                        "kinds": sorted(kinds)})
    return signals, branch_count


def classify(record):
    """#AP016 buckets. Signals are recorded so a human can re-bucket."""
    name = (record["name"] or "").lower()
    sigs = record["action_signals"]
    kinds = set(k for s in sigs for k in s["kinds"])
    branches = record["branch_count"]
    guardrailish = any(k in name for k in GUARDRAIL_NAME_KEYWORDS)

    plumbingish = any(k in name for k in PLUMBING_NAME_KEYWORDS)
    if branches > 0:
        if guardrailish:
            bucket, why = "GUARDRAIL", (f"{branches} branch action(s); "
                                        "name matches guardrail keywords")
        elif plumbingish:
            bucket, why = "PLUMBING", (f"{branches} branch action(s) but name "
                                       "matches mechanical keywords (#AP016 "
                                       "grade-incrementer rule) — verify by hand")
        else:
            bucket, why = "DECIDER", (f"{branches} branch action(s) — "
                                      "branching on business meaning")
    elif guardrailish:
        bucket, why = "GUARDRAIL", "name matches guardrail keywords, no branches"
    elif kinds and kinds <= {"webhook", "notify", "delay"}:
        bucket, why = "DOORBELL", "actions are webhook/notification only"
    elif kinds <= {"property_set", "delay", "other"} and "property_set" in kinds:
        bucket, why = "PLUMBING", "mechanical property writes, no branching"
    else:
        bucket = "PLUMBING"
        why = (f"no branches; action kinds {sorted(kinds) or ['none']} — "
               "default PLUMBING, verify by hand")
    record["bucket"] = bucket
    record["bucket_why"] = why


def absorption_target(record):
    name = (record["name"] or "").lower()
    for agent, keywords in ABSORPTION_MAP:
        if any(k in name for k in keywords):
            return agent
    return "NEW"


def parse_ts(val):
    if not val:
        return None
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val / 1000, tz=timezone.utc)
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except ValueError:
        return None


def apply_flags(record):
    """Uselessness signals — each with the datum it came from."""
    flags = []
    enabled = record["enabled"]
    created = parse_ts(record["created_at"])
    updated = parse_ts(record["updated_at"])
    act = record["activity"]
    total = act.get("total_enrolled")

    if enabled and total == 0 and created and (NOW - created) > DAYS_180:
        flags.append(("ZOMBIE",
                      f"enabled; 0 total enrollments ever (source: {act['source']}); "
                      f"created {created.date()} (> 180 days ago) — so 0 in the "
                      "last 180 days by implication"))
    if not enabled and updated and (NOW - updated) > DAYS_365:
        flags.append(("DORMANT",
                      f"disabled; last edited {updated.date()} (> 365 days ago). "
                      "NOTE: API exposes no disabled-at date; updatedAt is the proxy"))
    broken = [r for r in record["references"] if r["status"] == "broken"]
    if broken:
        parts = "; ".join(f"{r['kind']} `{r['id']}` ({r['detail']})" for r in broken)
        flags.append(("BROKEN", f"{len(broken)} dead reference(s): {parts}"))
    if updated and (NOW - updated) > DAYS_730:
        live_refs = [r for r in record["references"] if r["status"] == "ok"]
        if live_refs:
            sample = ", ".join(
                f"{r['label'] or r['id']}" for r in live_refs[:3])
            flags.append(("FROZEN",
                          f"last edited {updated.date()} (> 2 years) yet still "
                          f"touches live schema: {sample}"))
    if total == 0:
        flags.append(("MYSTERY", "zero enrollments ever "
                      f"(source: {act['source']})"))
    elif act["status"] == "unknown" and not enabled:
        flags.append(("MYSTERY", "activity unknown (API exposes no stats for "
                      "this workflow type) AND workflow is disabled"))
    record["flags"] = [{"flag": f, "evidence": e} for f, e in flags]


def find_duplicates(records):
    """≥80% identical trigger+action chain, same object type."""
    def chain(rec):
        parts = [rec["object_type_id"] or "?"]
        for s in rec["action_signals"]:
            parts.append(f"{s['type']}:{s['actionTypeId']}")
        ec = rec["raw"].get("enrollmentCriteria") or {}
        for _, key, val in _walk(ec):
            if key.lower() in REF_PROPERTY_KEYS and isinstance(val, str):
                parts.append(f"trig:{val}")
        return "|".join(parts)

    chains = {r["id"]: chain(r) for r in records}
    by_type = defaultdict(list)
    for r in records:
        # A near-empty chain (no parsed actions/triggers) matches everything
        # trivially — that is absence of data, not evidence of duplication.
        if chains[r["id"]].count("|") >= 2:
            by_type[r["object_type_id"]].append(r)
    best = {}   # record id -> (ratio, twin)
    for group in by_type.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                ratio = SequenceMatcher(None, chains[a["id"]],
                                        chains[b["id"]]).ratio()
                if ratio >= 0.80:
                    for rec, twin in ((a, b), (b, a)):
                        if ratio > best.get(rec["id"], (0, None))[0]:
                            best[rec["id"]] = (ratio, twin)
    for group in by_type.values():
        for rec in group:
            hit = best.get(rec["id"])
            if hit:
                ratio, twin = hit
                rec["flags"].append({
                    "flag": "DUPLICATE",
                    "evidence": (f"{ratio:.0%} identical trigger+action "
                                 f"chain to “{twin['name']}” (id {twin['id']}) "
                                 "— closest twin shown; see appendix for chain")})


def rank_deciders(records):
    """Rank = enrollments-90d × branches. The API does not expose 90-day
    windows, so when unknown we fall back to all-time enrollments × branches
    and say so — never silently."""
    deciders = [r for r in records if r["bucket"] == "DECIDER"]
    for r in deciders:
        e90 = r["activity"].get("enrollments_90d")
        total = r["activity"].get("total_enrolled")
        if isinstance(e90, int):
            r["rank_score"] = e90 * max(r["branch_count"], 1)
            r["rank_basis"] = f"enrollments_90d ({e90}) × branches ({r['branch_count']})"
        elif isinstance(total, int):
            r["rank_score"] = total * max(r["branch_count"], 1)
            r["rank_basis"] = (f"ALL-TIME enrollments ({total}) × branches "
                              f"({r['branch_count']}) — 90d window not exposed by API")
        else:
            r["rank_score"] = r["branch_count"]
            r["rank_basis"] = (f"branches only ({r['branch_count']}) — "
                              "no enrollment stats exposed for this type")
        r["absorb_into"] = absorption_target(r)
    deciders.sort(key=lambda r: r["rank_score"], reverse=True)
    return deciders


# ───────────────────────────── registry diff ──────────────────────────────

def registry_diff(records):
    diff = {"registry_found": REGISTRY_PATH.exists(),
            "hubspot_not_in_registry": [], "notes": []}
    if not REGISTRY_PATH.exists():
        diff["notes"].append("registry.yml not found at repo root")
        return diff
    raw = REGISTRY_PATH.read_text(encoding="utf-8")
    raw_lower = raw.lower()
    for r in records:
        name = (r["name"] or "").strip()
        if name and name.lower() in raw_lower:
            continue
        if r["id"] in raw:
            continue
        diff["hubspot_not_in_registry"].append(
            {"id": r["id"], "name": name, "enabled": r["enabled"]})
    diff["notes"].append(
        "registry.yml tracks fleet agents, not HubSpot-native workflows — it has "
        "no hubspot_workflows section today, so absence is expected. The fix is "
        "to add surviving keep-list workflows to the registry after the kill pass.")
    if yaml:
        try:
            reg = yaml.safe_load(raw)
            hubspot_agents = [
                a["id"] for a in reg.get("agents", [])
                if "hubspot" in json.dumps(a).lower()]
            diff["registry_agents_touching_hubspot"] = hubspot_agents
        except Exception as exc:
            diff["notes"].append(f"registry.yml parse failed: {exc}")
    return diff


# ───────────────────────────── record building ─────────────────────────────

def build_record(fid, entry):
    detail = entry["detail"]
    summary = entry["summary"]
    name = detail.get("name") or summary.get("name") or f"(unnamed {fid})"
    enabled = detail.get("isEnabled", detail.get("enabled"))
    obj = detail.get("objectTypeId") or summary.get("objectTypeId")
    record = {
        "id": str(fid),
        "name": name,
        "source_api": entry["source"],
        "flow_type": detail.get("flowType") or detail.get("type") or "?",
        "object_type_id": obj,
        "object_type": OBJECT_TYPE_LABELS.get(obj, obj or "?"),
        "enabled": bool(enabled),
        "created_at": detail.get("createdAt") or detail.get("insertedAt"),
        "updated_at": detail.get("updatedAt"),
        "creator": detail.get("createdBy") or detail.get("originalAuthorUserId"),
        "raw": detail,
    }
    record["action_signals"], record["branch_count"] = summarize_actions(detail)
    record["references"] = collect_references(detail)
    record["re_enrollment"] = ((detail.get("enrollmentCriteria") or {})
                               .get("shouldReEnroll"))
    return record


# ─────────────────────────────── HTML report ───────────────────────────────

CSS = """
:root {
  --paper:#f6f3ea; --ink:#17150f; --ink-soft:#5a5648;
  --live:#1e7a4a; --pending:#b9821c; --gap:#b23a2e;
  --card:#fffdf7; --line:#d8d2c0;
}
* { box-sizing:border-box; }
body {
  margin:0; color:var(--ink);
  font-family:'Archivo',system-ui,sans-serif;
  background:var(--paper);
  background-image:
    linear-gradient(rgba(23,21,15,.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(23,21,15,.045) 1px, transparent 1px);
  background-size:24px 24px;
  padding:16px; line-height:1.45;
}
.wrap { max-width:1100px; margin:0 auto; }
h1 { font-size:clamp(1.4rem,4vw,2.2rem); margin:.2em 0 0; letter-spacing:-.02em; }
h2 { font-size:clamp(1.05rem,3vw,1.4rem); margin:2.2em 0 .4em;
     border-bottom:3px solid var(--ink); padding-bottom:.2em; }
.sub, .mono { font-family:'IBM Plex Mono',ui-monospace,monospace; }
.sub { color:var(--ink-soft); font-size:.8rem; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
         gap:10px; margin:18px 0; }
.card { background:var(--card); border:1.5px solid var(--ink);
        box-shadow:3px 3px 0 var(--ink); padding:10px 12px; }
.card .num { font-family:'IBM Plex Mono',monospace; font-size:1.9rem;
             font-weight:700; display:block; }
.card .lbl { font-size:.72rem; text-transform:uppercase; letter-spacing:.08em;
             color:var(--ink-soft); }
.num.live { color:var(--live); } .num.pending { color:var(--pending); }
.num.gap { color:var(--gap); }
.tblwrap { overflow-x:auto; background:var(--card); border:1.5px solid var(--ink);
           box-shadow:3px 3px 0 var(--ink); }
table { border-collapse:collapse; width:100%; font-size:.82rem; }
th { text-align:left; font-family:'IBM Plex Mono',monospace; font-size:.68rem;
     text-transform:uppercase; letter-spacing:.06em; background:var(--ink);
     color:var(--paper); padding:7px 9px; position:sticky; top:0; }
td { padding:7px 9px; border-bottom:1px solid var(--line); vertical-align:top; }
tr:last-child td { border-bottom:none; }
.flag { display:inline-block; font-family:'IBM Plex Mono',monospace;
        font-size:.66rem; font-weight:700; padding:1px 6px; margin:1px 2px 1px 0;
        border:1.5px solid; border-radius:3px; }
.flag.gapc { color:var(--gap); border-color:var(--gap); }
.flag.pendingc { color:var(--pending); border-color:var(--pending); }
.flag.livec { color:var(--live); border-color:var(--live); }
.flag.inkc { color:var(--ink); border-color:var(--ink); }
.ev { font-family:'IBM Plex Mono',monospace; font-size:.72rem;
      color:var(--ink-soft); display:block; margin-top:2px; }
.banner { background:var(--card); border:2px solid var(--gap);
          box-shadow:3px 3px 0 var(--gap); color:var(--gap); font-weight:700;
          padding:10px 14px; margin:14px 0; font-family:'IBM Plex Mono',monospace;
          font-size:.8rem; }
input[type=checkbox] { width:18px; height:18px; accent-color:var(--gap); }
.count { font-family:'IBM Plex Mono',monospace; font-weight:700; }
details summary { cursor:pointer; font-weight:600; margin:8px 0; }
@media (max-width:640px){ body{padding:8px;} td,th{padding:5px 6px;} }
"""


def esc(s):
    return html_mod.escape(str(s if s is not None else "—"))


def flag_class(flag):
    return {"ZOMBIE": "gapc", "BROKEN": "gapc", "DUPLICATE": "pendingc",
            "DORMANT": "pendingc", "FROZEN": "pendingc",
            "MYSTERY": "inkc"}.get(flag, "inkc")


def build_html(records, deciders, reg_diff, meta):
    flagged = [r for r in records if r["flags"]]
    flagged.sort(key=lambda r: len(r["flags"]), reverse=True)
    keep = [r for r in records
            if not r["flags"] and r["bucket"] in ("DOORBELL", "PLUMBING", "GUARDRAIL")]
    enabled_n = sum(1 for r in records if r["enabled"])

    out = []
    a = out.append
    a("<meta charset='utf-8'><meta name='viewport' "
      "content='width=device-width,initial-scale=1'>")
    a(f"<title>Automation Audit — {TODAY}</title>")
    a("<link rel='preconnect' href='https://fonts.googleapis.com'>")
    a("<link href='https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;"
      "700&family=IBM+Plex+Mono:wght@400;700&display=swap' rel='stylesheet'>")
    a(f"<style>{CSS}</style><div class='wrap'>")
    a(f"<div class='sub'>A+ TUTORING · FLEET HEALTH · READ-ONLY CENSUS · {TODAY}</div>")
    a("<h1>Automation Audit v1 — HubSpot workflows</h1>")
    a("<div class='banner'>⚠ NOTHING IS DELETED BY THIS SCRIPT. Checkboxes are "
      "an approval worksheet for Roman; every kill is executed by a human.</div>")
    if meta.get("write_scopes_accepted"):
        a("<div class='banner'>⚠ RUN USED A WRITE-SCOPED TOKEN (override "
          "accepted). The client blocked all non-GET requests, but doctrine "
          "prefers a dedicated read-only app. Scopes: "
          f"{esc(', '.join(meta['write_scopes_accepted']))}</div>")

    a("<div class='cards'>")
    for num, lbl, cls in [
            (len(records), "total workflows", ""),
            (enabled_n, "enabled", "live"),
            (len(flagged), "flagged (evidence of uselessness)", "gap"),
            (len(deciders), "deciders → absorption", "pending"),
            (sum(1 for r in records for f in r["flags"] if f["flag"] == "BROKEN"),
             "broken references", "gap")]:
        a(f"<div class='card'><span class='num {cls}'>{num}</span>"
          f"<span class='lbl'>{esc(lbl)}</span></div>")
    a("</div>")

    # Kill list
    a("<h2>Kill list — flagged workflows, worst first</h2>")
    a("<p class='sub'>Approved for kill: <span class='count' id='killcount'>0"
      f"</span> / {len(flagged)}</p>")
    a("<div class='tblwrap'><table><tr><th>✓</th><th>workflow</th>"
      "<th>state</th><th>flags + evidence</th></tr>")
    for r in flagged:
        flags_html = "".join(
            f"<span class='flag {flag_class(f['flag'])}'>{esc(f['flag'])}</span>"
            f"<span class='ev'>{esc(f['evidence'])}</span>"
            for f in r["flags"])
        state = "ENABLED" if r["enabled"] else "disabled"
        a(f"<tr><td><input type='checkbox' onchange='tally()'></td>"
          f"<td><b>{esc(r['name'])}</b><span class='ev'>id {esc(r['id'])} · "
          f"{esc(r['object_type'])} · bucket {esc(r['bucket'])}</span></td>"
          f"<td class='mono'>{state}</td><td>{flags_html}</td></tr>")
    if not flagged:
        a("<tr><td colspan='4'>No workflows flagged.</td></tr>")
    a("</table></div>")

    # Absorption backlog
    a("<h2>Absorption backlog — deciders, ranked</h2>")
    a("<p class='sub'>Frozen judgment calls an agent should be making (#AP016). "
      "Rank basis is stated per row — the API exposes no 90-day enrollment "
      "window, so all-time counts are used where noted.</p>")
    a("<div class='tblwrap'><table><tr><th>#</th><th>workflow</th>"
      "<th>judgment being faked</th><th>absorb into</th><th>rank basis</th></tr>")
    for i, r in enumerate(deciders, 1):
        a(f"<tr><td class='mono'>{i}</td><td><b>{esc(r['name'])}</b>"
          f"<span class='ev'>id {esc(r['id'])} · {esc(r['object_type'])} · "
          f"{'ENABLED' if r['enabled'] else 'disabled'}</span></td>"
          f"<td>{esc(r['bucket_why'])}</td>"
          f"<td class='mono'>{esc(r['absorb_into'])}</td>"
          f"<td class='ev'>{esc(r['rank_basis'])}</td></tr>")
    if not deciders:
        a("<tr><td colspan='5'>No deciders found.</td></tr>")
    a("</table></div>")

    # Keep list
    a("<h2>Keep list — doorbells, plumbing, guardrails (unflagged)</h2>")
    a("<div class='tblwrap'><table><tr><th>workflow</th><th>bucket</th>"
      "<th>why</th></tr>")
    for r in sorted(keep, key=lambda x: (x["bucket"], x["name"] or "")):
        a(f"<tr><td><b>{esc(r['name'])}</b><span class='ev'>id {esc(r['id'])}"
          f"</span></td><td class='mono'>{esc(r['bucket'])}</td>"
          f"<td class='ev'>{esc(r['bucket_why'])}</td></tr>")
    if not keep:
        a("<tr><td colspan='3'>Nothing unflagged in keep buckets.</td></tr>")
    a("</table></div>")

    # Registry diff
    a("<h2>Registry diff</h2>")
    missing = reg_diff.get("hubspot_not_in_registry", [])
    a(f"<p>HubSpot workflows with no mention in <span class='mono'>registry.yml"
      f"</span>: <b>{len(missing)}</b> of {len(records)}.</p>")
    for note in reg_diff.get("notes", []):
        a(f"<p class='sub'>{esc(note)}</p>")
    if missing:
        a("<details><summary>Show all</summary><div class='tblwrap'><table>"
          "<tr><th>id</th><th>name</th><th>enabled</th></tr>")
        for m in missing:
            a(f"<tr><td class='mono'>{esc(m['id'])}</td><td>{esc(m['name'])}</td>"
              f"<td class='mono'>{'yes' if m['enabled'] else 'no'}</td></tr>")
        a("</table></div></details>")

    # Appendix
    a("<h2>Appendix — full raw inventory</h2>")
    a("<details><summary>Show all workflows</summary><div class='tblwrap'><table>")
    a("<tr><th>id</th><th>name</th><th>src</th><th>object</th><th>enabled</th>"
      "<th>bucket</th><th>branches</th><th>enrolled (all-time)</th>"
      "<th>created</th><th>updated</th><th>refs ok/broken/unv</th></tr>")
    for r in sorted(records, key=lambda x: (x["name"] or "").lower()):
        refs = r["references"]
        ok = sum(1 for x in refs if x["status"] == "ok")
        br = sum(1 for x in refs if x["status"] == "broken")
        uv = sum(1 for x in refs if x["status"] == "unverifiable")
        tot = r["activity"].get("total_enrolled")
        tot = tot if tot is not None else "unknown"
        cr, up = parse_ts(r["created_at"]), parse_ts(r["updated_at"])
        a(f"<tr><td class='mono'>{esc(r['id'])}</td><td>{esc(r['name'])}</td>"
          f"<td class='mono'>{esc(r['source_api'])}</td><td>{esc(r['object_type'])}</td>"
          f"<td class='mono'>{'yes' if r['enabled'] else 'no'}</td>"
          f"<td class='mono'>{esc(r['bucket'])}</td>"
          f"<td class='mono'>{r['branch_count']}</td><td class='mono'>{esc(tot)}</td>"
          f"<td class='mono'>{cr.date() if cr else '—'}</td>"
          f"<td class='mono'>{up.date() if up else '—'}</td>"
          f"<td class='mono'>{ok}/{br}/{uv}</td></tr>")
    a("</table></div></details>")

    a(f"<p class='sub'>Run: {meta['run_id']} · {meta['api_calls']} API calls · "
      f"token scopes verified read-only · generated {NOW.isoformat(timespec='seconds')}"
      "</p></div>")
    a("<script>function tally(){document.getElementById('killcount').textContent="
      "document.querySelectorAll('input[type=checkbox]:checked').length}</script>")
    return "\n".join(out)


# ───────────────────────────── decision log ────────────────────────────────

def build_decision_log(records, deciders, flagged_count):
    top = ", ".join(f"“{r['name']}” → {r['absorb_into']}" for r in deciders[:5])
    entries = f"""\
DRAFT — NOT SENT. Roman approves, then append via the existing Zapier Google
Docs pipe. Append gotcha: the document param key is `file`; pass the Decision
Log ID explicitly ({DECISION_LOG_DOC_ID}); treat any
resolvedParams status of `guessed` on the file field as a FAILED write.

======
{TODAY} | #AP015
DECISION: HubSpot is the single system of record for operational work. Monday
  is limited to the L10 scorecard + NPS boards only. Migrations: low-balance/PO
  tracking moves to HubSpot tickets; teacher evaluations move to tickets on the
  tutor contact + deal. The tutor pipeline is confirmed as a trigger rail, with
  an Onboarding Agent exclusion.
WHY: Two half-authoritative systems means every agent needs two write paths and
  every human checks two places. HubSpot already owns families + comms
  (registry.yml doctrine); consolidating kills the split-brain.
OWNER: Roman
STATUS: DRAFT — pending approval
TAG: fleet / systems-of-record

======
{TODAY} | #AP016
DECISION: Workflows sense, agents decide. Every HubSpot workflow is classified
  DOORBELL (trigger→notify, keep) / PLUMBING (mechanical, keep) / DECIDER
  (business judgment frozen into if-branches → absorbed by a fleet agent) /
  GUARDRAIL (deliberately deterministic safety logic — stays dumb forever).
WHY: 8 years of workflows accumulated judgment calls that belong in agents.
  Deterministic safety logic must NOT be absorbed — guardrails that "get smart"
  stop being guardrails.
OWNER: Roman
STATUS: DRAFT — pending approval
TAG: fleet / doctrine

======
{TODAY} | #AP017
DECISION: Automation Audit v1 findings accepted as the working inventory:
  {len(records)} HubSpot workflows total, {sum(1 for r in records if r['enabled'])}
  enabled, {flagged_count} flagged with uselessness evidence (kill-list
  candidates), {len(deciders)} deciders queued for absorption.
  Top absorptions: {top or 'none found'}.
WHY: First full census in 8 years; kill list + absorption backlog are now
  evidence-backed instead of folklore. Humans approve all kills.
OWNER: Roman
STATUS: DRAFT — pending approval (fill/adjust after Roman's checkbox pass)
TAG: fleet / audit / hubspot
"""
    return entries


# ─────────────────────────────── selftest ──────────────────────────────────

def selftest_records():
    """Synthetic fixtures that exercise every flag + bucket offline."""
    mk = lambda **kw: {**{"actions": [], "enrollmentCriteria": {}}, **kw}
    old = (NOW - timedelta(days=900)).isoformat()
    mid = (NOW - timedelta(days=400)).isoformat()
    fixtures = {
        "101": {"source": "v4", "summary": {}, "detail": mk(
            name="Lead source router — email template by segment",
            isEnabled=True, objectTypeId="0-1", createdAt=old, updatedAt=mid,
            actions=[{"type": "LIST_BRANCH", "actionTypeId": "x",
                      "fields": {"property": "lead_source"}},
                     {"type": "SINGLE_CONNECTION", "actionTypeId": "y",
                      "fields": {"emailContentId": "999999"}}])},
        "102": {"source": "v4", "summary": {}, "detail": mk(
            name="Slack doorbell — new deal webhook", isEnabled=True,
            objectTypeId="0-3", createdAt=old, updatedAt=old,
            actions=[{"type": "SINGLE_CONNECTION", "actionTypeId": "wh",
                      "fields": {"webhookUrl": "https://hooks.example"}}])},
        "103": {"source": "v3", "summary": {}, "detail": mk(
            name="Copy grade to student record", isEnabled=False,
            objectTypeId="0-1", createdAt=old, updatedAt=old,
            actions=[{"type": "SINGLE_CONNECTION", "actionTypeId": "sp",
                      "fields": {"set_property": True,
                                 "propertyName": "student_grade", "value": "x"}}])},
        "104": {"source": "v4", "summary": {}, "detail": mk(
            name="Dedup guard — suppress re-ping 7d", isEnabled=True,
            objectTypeId="0-1", createdAt=mid, updatedAt=mid,
            actions=[{"type": "STATIC_BRANCH", "actionTypeId": "b",
                      "fields": {"property": "last_ping_date"}}])},
        "105": {"source": "v4", "summary": {}, "detail": mk(
            name="Lead source router — email template by segment (copy)",
            isEnabled=True, objectTypeId="0-1", createdAt=old, updatedAt=old,
            actions=[{"type": "LIST_BRANCH", "actionTypeId": "x",
                      "fields": {"property": "lead_source"}},
                     {"type": "SINGLE_CONNECTION", "actionTypeId": "y",
                      "fields": {"emailContentId": "999999"}}])},
    }
    records = [build_record(fid, e) for fid, e in fixtures.items()]
    for i, r in enumerate(records):
        r["activity"] = {"status": "known_totals_only" if i != 2 else "unknown",
                         "total_enrolled": [412, 0, None, 88, 12][i],
                         "currently_active": 0,
                         "enrollments_90d": "unknown",
                         "enrollments_365d": "unknown",
                         "source": "fixture", "raw_counts": {}}
        for ref in r["references"]:
            ref["status"] = "broken" if ref["kind"] == "email" else "ok"
            ref["label"] = "Lead Source" if ref["id"] == "lead_source" else ref["id"]
            if ref["status"] == "broken":
                ref["detail"] = "email/template id returns 404 (fixture)"
    return records


# ────────────────────────────────── main ───────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1].strip())
    ap.add_argument("--out-dir", default=None,
                    help="override output root (default: this folder)")
    ap.add_argument("--selftest", action="store_true",
                    help="run the full pipeline offline on bundled fixtures")
    ap.add_argument("--accept-write-scoped-token", action="store_true",
                    help="proceed with a write-scoped token (loud warning; "
                         "the client still blocks every non-GET request)")
    args = ap.parse_args()

    out_root = Path(args.out_dir) if args.out_dir else AUDIT_DIR
    reports_dir = out_root / "reports"
    runs_dir = out_root / "runs"
    reports_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    run_id = f"automation-audit-{TODAY}"
    errors = []

    write_scopes_accepted = []
    if args.selftest:
        log("SELFTEST — offline fixtures, no network")
        records = selftest_records()
        scopes, api_calls = ["(selftest)"], 0
        run_id += "-selftest"
    else:
        if requests is None:
            die("the 'requests' package is required for a live run "
                "(pip install -r requirements.txt)")
        token = os.environ.get("HUBSPOT_AUDIT_TOKEN")
        if not token:
            die("HUBSPOT_AUDIT_TOKEN is not set")
        client = HubSpotClient(token)
        scopes, write_scopes_accepted = verify_token_readonly(
            client, accept_write_scoped=args.accept_write_scoped_token)

        flows = fetch_flows(client)
        log(f"fetching detail + activity for {len(flows)} workflows…")
        schema = SchemaCache(client)
        records = []
        for fid, entry in flows.items():
            try:
                rec = build_record(fid, entry)
                rec["activity"] = fetch_activity(entry)
                verify_references(schema, rec)
                records.append(rec)
            except Exception as exc:
                errors.append(f"workflow {fid}: {exc}")
                log(f"ERROR on workflow {fid}: {exc}")
        api_calls = client.calls

    for rec in records:
        classify(rec)
        apply_flags(rec)
    find_duplicates(records)
    deciders = rank_deciders(records)
    reg_diff = registry_diff(records)

    flagged = [r for r in records if r["flags"]]
    meta = {"run_id": run_id, "api_calls": api_calls,
            "write_scopes_accepted": write_scopes_accepted}

    html_path = reports_dir / f"{run_id}.html"
    html_path.write_text(build_html(records, deciders, reg_diff, meta),
                         encoding="utf-8")
    log(f"HTML report → {html_path}")

    draft_name = ("decision-log-draft-selftest.txt" if args.selftest
                  else "decision-log-draft.txt")
    draft_path = reports_dir / draft_name
    draft_path.write_text(build_decision_log(records, deciders, len(flagged)),
                          encoding="utf-8")
    log(f"decision log draft → {draft_path}")

    summary = {
        "run_id": run_id,
        "generated_at": NOW.isoformat(timespec="seconds"),
        "mode": "selftest" if args.selftest else "live",
        "token_scopes": scopes,
        "write_scopes_accepted": write_scopes_accepted,
        "api_calls": api_calls,
        "totals": {
            "workflows": len(records),
            "enabled": sum(1 for r in records if r["enabled"]),
            "activity_known": sum(1 for r in records
                                  if r["activity"].get("status") != "unknown"),
            "flagged": len(flagged),
            "deciders": len(deciders),
            "flag_counts": {
                flag: sum(1 for r in records for f in r["flags"]
                          if f["flag"] == flag)
                for flag in ("ZOMBIE", "DORMANT", "BROKEN", "DUPLICATE",
                             "FROZEN", "MYSTERY")},
            "buckets": {
                b: sum(1 for r in records if r["bucket"] == b)
                for b in ("DOORBELL", "PLUMBING", "DECIDER", "GUARDRAIL")},
        },
        "registry_diff": {
            "hubspot_not_in_registry": len(reg_diff.get("hubspot_not_in_registry", []))},
        "errors": errors,
        "outputs": {"html": str(html_path), "decision_log_draft": str(draft_path)},
    }
    run_path = runs_dir / f"{run_id}.json"
    run_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log(f"run summary → {run_path}")

    log(f"done: {len(records)} workflows, {len(flagged)} flagged, "
        f"{len(deciders)} deciders, {len(errors)} errors")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
