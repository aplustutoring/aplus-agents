"""Family replies on low-balance cases (Roman 2026-10-01): the scheduler owns
the case, the family email's reply-to is admin@, triage hands a reply from a
family with an open case to that case, and the sweep's reply check reads
HubSpot instead of a Gmail inbox the schedulers do not have."""
from src import low_balance as lb

CFG = {"low_balance": {"enabled": True, "owner": "charter_sales",
                       "family_email": {"reply_passthrough_categories": ["complaint", "cancellation"]}}}

CASES = {
    "low-balance:26-27:ana-ruiz:charter": {"student": "Ana Ruiz", "first_name": "Maria",
                                           "parent_email": "maria@example.com", "owner": "scheduler_m_z",
                                           "ticket_id": "T1", "opened_at": "2026-09-28T16:00:00+00:00"},
    "low-balance:26-27:leo-ruiz:charter": {"student": "Leo Ruiz", "first_name": "Maria",
                                           "parent_email": "Maria@Example.com", "owner": "scheduler_m_z",
                                           "ticket_id": "T2", "opened_at": "2026-09-28T16:00:00+00:00",
                                           "replied": True},
    "low-balance:26-27:sam-diaz:charter": {"student": "Sam Diaz", "parent_email": "d@example.com",
                                           "owner": "scheduler_a_l", "ticket_id": "T3",
                                           "opened_at": "2026-09-28T16:00:00+00:00"},
}


def _wire(monkeypatch, cases=CASES):
    calls = {"audit": [], "moves": [], "notes": [], "links": [], "dms": [], "comments": []}
    monkeypatch.setattr(lb, "cfg", lambda: CFG)
    monkeypatch.setattr(lb, "open_cases", lambda: dict(cases))
    monkeypatch.setattr(lb.audit, "append", lambda r: calls["audit"].append(r))
    monkeypatch.setattr(lb.ce, "move", lambda t, n, s, note=None, props=None: calls["moves"].append((t, s)))
    monkeypatch.setattr(lb.ce, "dm_role", lambda role, text: calls["dms"].append((role, text)))
    monkeypatch.setattr(lb.hs, "add_ticket_note", lambda t, n: calls["notes"].append((t, n)))
    monkeypatch.setattr(lb.hs, "link_thread_to_ticket", lambda th, t: calls["links"].append((th, t)))
    monkeypatch.setattr(lb.hs, "post_comment", lambda th, t: calls["comments"].append((th, t)))
    monkeypatch.setattr(lb.hs, "ticket_url", lambda t: f"https://hs/{t}")
    return calls


BODY = "Thanks, I asked the teacher today.\n\nOn Mon, Sep 28, A+ Tutoring wrote:\n> hours are low"


def test_reply_joins_every_sibling_case_and_dms_the_owning_scheduler(monkeypatch):
    c = _wire(monkeypatch)
    rec = lb.handle_family_reply("th1", {"id": "m1", "subject": "Re: hours"}, "MARIA@example.com",
                                 BODY, "new_po", "Draft text", True)
    assert rec["action_taken"] == "low_balance_reply_routed" and rec["message_id"] == "m1"
    assert set(rec["case_keys"]) == {"low-balance:26-27:ana-ruiz:charter", "low-balance:26-27:leo-ruiz:charter"}
    assert sorted(c["moves"]) == [("T1", "needs_scheduler"), ("T2", "needs_scheduler")]
    assert sorted(c["links"]) == [("th1", "T1"), ("th1", "T2")]
    # one DM, to the scheduler who owns the case, never Paola, with the family's own words
    assert len(c["dms"]) == 1 and c["dms"][0][0] == "scheduler_m_z"
    assert "Ana Ruiz, Leo Ruiz" in c["dms"][0][1] and "I asked the teacher today." in c["dms"][0][1]
    assert "hours are low" not in c["dms"][0][1]
    # the replied record (which holds the teacher email) is written once per case
    replied = [r for r in c["audit"] if r.get("action_taken") == "low_balance_family_replied"]
    assert [r["message_id"] for r in replied] == ["low-balance:26-27:ana-ruiz:charter:replied"]
    assert c["comments"] == [("th1", "[A+ draft reply — review & send]\n\nDraft text")]


def test_escalations_and_strangers_take_the_ordinary_path(monkeypatch):
    c = _wire(monkeypatch)
    assert lb.handle_family_reply("th1", {"id": "m1"}, "maria@example.com", BODY, "complaint") is None
    assert lb.handle_family_reply("th1", {"id": "m2"}, "nobody@example.com", BODY, "new_po") is None
    assert lb.handle_family_reply("th1", {"id": "m3"}, "", BODY, "new_po") is None
    assert not any(c.values())


def test_disabled_agent_never_intercepts(monkeypatch):
    c = _wire(monkeypatch)
    monkeypatch.setattr(lb, "cfg", lambda: {"low_balance": {"enabled": False}})
    assert lb.handle_family_reply("th1", {"id": "m1"}, "maria@example.com", BODY, "new_po") is None
    assert not any(c.values())


def test_parent_replied_reads_hubspot_as_stored_and_lowercased(monkeypatch):
    seen = []

    def fake_write(method, path, body):
        seen.append((method, path, body))
        return {"total": 1, "results": [{"id": "e1"}]}
    monkeypatch.setattr(lb.hs, "_write", fake_write)
    case = {"parent_email": "Maria@Example.com", "opened_at": "2026-09-28T16:00:00+00:00"}
    assert lb._parent_replied(case, {}, {}) is True
    method, path, body = seen[0]
    assert path == "/crm/v3/objects/emails/search"
    addrs = [next(f["value"] for f in g["filters"] if f["propertyName"] == "hs_email_from_email")
             for g in body["filterGroups"]]
    assert addrs == ["Maria@Example.com", "maria@example.com"]
    assert all({"propertyName": "hs_email_direction", "operator": "EQ", "value": "INCOMING_EMAIL"} in g["filters"]
               for g in body["filterGroups"])


def test_parent_replied_no_hit_or_failure_is_no_reply(monkeypatch):
    monkeypatch.setattr(lb.hs, "_write", lambda m, p, b: {"total": 0, "results": []})
    case = {"parent_email": "a@b.com", "opened_at": "2026-09-28T16:00:00+00:00"}
    assert lb._parent_replied(case, {}, {}) is False

    def boom(m, p, b):
        raise RuntimeError("429")
    monkeypatch.setattr(lb.hs, "_write", boom)
    assert lb._parent_replied(case, {}, {}) is False
    assert lb._parent_replied({"parent_email": "a@b.com"}, {}, {}) is False


def test_reply_quote_keeps_only_the_familys_words():
    assert lb._reply_quote(BODY) == "Thanks, I asked the teacher today."
    assert lb._reply_quote("ok\n> quoted") == "ok"
