"""A fake HubSpot for the writer/main tests: option labels, contact upserts,
deal search/create/patch, associations, audit. Records every write."""
from __future__ import annotations

from agents.cohort_intake import writer as W

# the portal's real labels, read live 2026-09-16
OPTIONS = {
    ("contacts", "what_is_your_child_s_current_grade_level_"): [("8", "8"), ("9", "9"), ("10", "10")],
    ("contacts", "subject_need"): [("English Language Arts", "English Language Arts"), ("Math", "Math"),
                                   ("Both", "Both"), ("Other", "Other")],
    ("contacts", "charter_school_teacher"): [("IEM Inc South Sutter/Ocean Grove/Sky Mountain", "IEM Inc SS/OG/SM")],
    ("deals", "online__inperson__charter"): [("ONLINE PRIVATE PAY", "ONLINE PRIVATE PAY"),
                                             ("IN-PERSON PRIVATE PAY", "IN-PERSON PRIVATE PAY"),
                                             ("ONLINE CHARTER", "ONLINE CHARTER"), ("ONLINE OTHER", "ONLINE OTHER")],
    ("deals", "monday_schedule_preference"): [("9AM-12PM", "9AM-12PM"), ("12PM-3PM", "12PM-3PM")],
    ("deals", "wednesday_schedule_preference"): [("9AM-12PM", "9AM-12PM"), ("12PM-3PM", "12PM-3PM")],
}
STAFF = {"scheduler_a_l": {"name": "Janelle", "hubspot_owner_id": "80047202", "slack_user_id": "UJ"},
         "scheduler_m_z": {"name": "Yolanda", "hubspot_owner_id": "86868539", "slack_user_id": "UY"},
         "sales": {"name": "Danielle", "hubspot_owner_id": "227538487", "slack_user_id": "UD"},
         "visionary": {"name": "Roman", "hubspot_owner_id": "38681249", "slack_user_id": "UR"}}


class FakeHS:
    def __init__(self, contacts=None, deals=None, stage="Pre-Lesson", options=None):
        self.contacts = dict(contacts or {})      # email → {"id", "properties"}
        self.deals = list(deals or [])            # existing deals (search results)
        self.stage = stage
        self.options = options if options is not None else OPTIONS
        self.created_contacts, self.patched_contacts = [], []
        self.created_deals, self.patched_deals, self.notes = [], [], []
        self.assoc_cc, self.assoc_cd = [], []
        self._n = 100

    def _get(self, path, params=None):
        if "/crm/v3/properties/" in path:
            obj, prop = path.split("/crm/v3/properties/")[1].split("/")
            return {"options": [{"label": l, "value": v} for l, v in self.options.get((obj, prop), [])]}
        if "/objects/deals/" in path:
            did = path.rsplit("/", 1)[1]
            for d in self.deals + self.created_deals:
                if str(d["id"]) == did:
                    return d
        return {}

    def find_contact_by_email(self, email, properties=None):
        return self.contacts.get(email.lower())

    def create_contact(self, email, firstname=None, lastname=None, phone=None, extra_props=None):
        self._n += 1
        rec = {"id": str(self._n), "properties": {"email": email, "firstname": firstname,
                                                  "lastname": lastname, "phone": phone,
                                                  **(extra_props or {})}}
        self.contacts[email.lower()] = rec
        self.created_contacts.append(rec)
        return rec

    def patch_contact_props(self, cid, props):
        self.patched_contacts.append((cid, props))
        return {}

    def associate_contacts(self, a, b, type_id=15, category="USER_DEFINED"):
        self.assoc_cc.append((a, b))
        return {}

    def associate_contact_to_deal(self, did, cid):
        self.assoc_cd.append((did, cid))
        return {}

    def _search_all(self, path, filters, props):
        sid = next((f["value"] for f in filters if f["propertyName"] == "iem_student_id"), None)
        return [d for d in self.deals if d["properties"].get("iem_student_id") == sid]

    def stage_label(self, pid, sid):
        return self.stage

    def create_deal(self, name, pipeline_id, stage_id, amount=None, contact_id=None, dealtype=None,
                    owner_id=None, closedate_ms=None, extra_props=None):
        self._n += 1
        rec = {"id": str(self._n), "properties": {"dealname": name, "pipeline": pipeline_id,
                                                  "dealstage": stage_id, "amount": amount,
                                                  "hubspot_owner_id": owner_id,
                                                  "closedate": closedate_ms, **(extra_props or {})},
               "contact_id": contact_id}
        self.created_deals.append(rec)
        return rec

    def _write(self, method, path, payload=None):
        if method == "PATCH" and "/objects/deals/" in path:
            self.patched_deals.append((path.rsplit("/", 1)[1], payload["properties"]))
        return {}

    def add_deal_note(self, did, body, attachment_ids=None):
        self.notes.append((did, body))
        return {}


def wire(monkeypatch, fake: FakeHS):
    W._options.cache_clear()
    monkeypatch.setattr(W, "hs", fake)
    monkeypatch.setattr(W, "staff", lambda k: STAFF.get(k, {}))
    recorded = []
    monkeypatch.setattr(W.audit, "append", lambda r: recorded.append(r))
    return recorded


def existing_deal(sid, name, amount="1250", did=None):
    return {"id": did or f"D{sid[-1]}", "properties": {"iem_student_id": sid, "dealname": name,
                                                       "amount": amount, "pipeline": "5119061"}}
