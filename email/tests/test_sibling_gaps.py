"""Sibling-gap tripwire — detection, settle window, dedupe, routing."""
import datetime as dt

from src import sibling_gaps as sg

NOW = dt.datetime(2026, 9, 10, tzinfo=dt.timezone.utc)


def _d(name, created="2026-09-01T12:00:00Z"):
    return {"properties": {"dealname": name, "createdate": created}}


PRIOR = [_d("Sarah Fiore - Eliana - iLead 2 (May) 25/26"),
         _d("Sarah Fiore - Tony - iLead 3 (June) 25/26"),
         _d("Ana Solo - Kid - iLead 1 (May) 25/26")]


def test_detects_the_eliana_pattern():
    current = [_d("Sarah Fiore - Tony Fiore - iLead 1 - 26/27")]
    gaps = sg.find_gaps(PRIOR, current, settle_days=5, now_utc=NOW)
    assert gaps == [{"family": "sarah fiore", "missing": ["eliana"],
                     "renewed": ["tony"]}]


def test_whole_family_unrenewed_is_not_a_gap():
    # Ana Solo hasn't renewed at all — that's the chase list, not a red flag
    current = [_d("Sarah Fiore - Tony Fiore - iLead 1 - 26/27"),
               _d("Sarah Fiore - Eliana Fiore - iLead 1 - 26/27")]
    gaps = sg.find_gaps(PRIOR, current, settle_days=5, now_utc=NOW)
    assert gaps == []


def test_settle_window_holds_fire():
    # family's newest PO is 2 days old; siblings' OAs arrive spread out
    current = [_d("Sarah Fiore - Tony Fiore - iLead 1 - 26/27",
                  created="2026-09-08T12:00:00Z")]
    assert sg.find_gaps(PRIOR, current, settle_days=5, now_utc=NOW) == []
    assert sg.find_gaps(PRIOR, current, settle_days=1, now_utc=NOW) != []


def test_needs_parent_deals_never_count():
    current = [_d("NEEDS PARENT - Tony Fiore - iLead 1 - 26/27")]
    assert sg.find_gaps(PRIOR, current, settle_days=5, now_utc=NOW) == []


def test_run_dms_charter_sales_once(monkeypatch):
    cfgv = {"sibling_gap": {"enabled": True, "hour_pt": 10, "settle_days": 5,
                            "season_start": "2026-08-15",
                            "prior_window_start": "2026-02-01",
                            "prior_window_end": "2026-07-15",
                            "notify": "charter_sales"},
            "staff": {"paola": {"name": "Paola", "slack_user_id": "UPAO"}}}
    monkeypatch.setattr(sg, "cfg", lambda: cfgv)
    monkeypatch.setattr(sg, "staff", lambda k: cfgv["staff"]["paola"])
    monkeypatch.setattr(sg, "now_la",
                        lambda: dt.datetime(2026, 9, 10, 10, 5,
                                            tzinfo=dt.timezone.utc))
    calls = {"n": 0}
    def fake_deals(start, end=None):
        calls["n"] += 1
        return PRIOR if end else [_d("Sarah Fiore - Tony Fiore - iLead 1 - 26/27")]
    monkeypatch.setattr(sg, "_po_deals", fake_deals)
    dms, recs = [], []
    seen = set()
    monkeypatch.setattr(sg.slack_client, "dm",
                        lambda u, t: dms.append((u, t)) or {"ok": True})
    monkeypatch.setattr(sg.audit, "already_processed", lambda k: k in seen)
    monkeypatch.setattr(sg.audit, "append",
                        lambda r: (recs.append(r), seen.add(r["message_id"])))
    sg.run()
    assert len(dms) == 1 and dms[0][0] == "UPAO"
    assert "Eliana" in dms[0][1] and "Sarah Fiore" in dms[0][1]
    assert recs and recs[0]["action_taken"] == "sibling_gap_flagged"
    sg.run()                      # second day: audited, no re-DM
    assert len(dms) == 1


def test_wrong_hour_is_a_noop(monkeypatch):
    monkeypatch.setattr(sg, "cfg", lambda: {"sibling_gap": {"enabled": True,
                                                            "hour_pt": 10}})
    monkeypatch.setattr(sg, "now_la",
                        lambda: dt.datetime(2026, 9, 10, 14, 0,
                                            tzinfo=dt.timezone.utc))
    called = []
    monkeypatch.setattr(sg, "_po_deals", lambda *a, **k: called.append(1) or [])
    sg.run()
    assert called == []
