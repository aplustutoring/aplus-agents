import datetime as dt

from src import daily_summary as ds
from src.business_hours import LA


def test_gather_today_counts_only_today(monkeypatch):
    monkeypatch.setattr(ds, "now_la", lambda: dt.datetime(2026, 6, 10, 18, 0, tzinfo=LA))
    recs = [
        {"timestamp": "2026-06-10T20:00:00+00:00", "action_taken": "ticket_created",
         "category": "scheduling", "owner": "janelle", "draft_posted": True,
         "deal_moved": {"moves": [{"deal_id": "d1"}, {"deal_id": "d2"}]}},        # 1pm PT today
        {"timestamp": "2026-06-10T23:00:00+00:00", "action_taken": "junk_archived"},  # today
        {"timestamp": "2026-06-09T20:00:00+00:00", "action_taken": "ticket_created",
         "category": "complaint", "owner": "mandy"},                            # yesterday
    ]
    monkeypatch.setattr(ds.audit, "_iter_records", lambda: iter(recs))
    m = ds.gather_today()
    assert m["total"] == 1 and m["drafts"] == 1 and m["junk"] == 1
    assert m["by_category"] == {"scheduling": 1, "junk": 1}
    assert m["by_owner"] == {"janelle": 1}
    assert m["deals_moved"] == 2
    assert len(m["deal_moves"]) == 2


def test_summary_lists_each_deal_move():
    m = {"date": "2026-06-11", "total": 1, "drafts": 0, "junk": 0, "escalations": 0,
         "deals_moved": 1, "by_category": {}, "by_owner": {},
         "deal_moves": [{"deal_name": "Michelle Schnider - Layla", "from": "Pre-Lesson", "to": "Stopped"}]}
    text = ds.format_summary(m)
    assert "Michelle Schnider - Layla: Pre-Lesson → Stopped" in text
    assert "undo if any look wrong" in text


def test_closed_counts_by_closed_date_any_creation(monkeypatch):
    # A ticket created days ago but closed on the previous BUSINESS day (Fri, since
    # today is Mon) must count in that day's closed — regardless of creation date.
    today = dt.datetime(2026, 6, 15, 18, 0, tzinfo=LA)   # Monday
    fri_iso = "2026-06-12T20:00:00Z"   # = 1pm PT Friday June 12
    monkeypatch.setattr(ds, "now_la", lambda: today)
    monkeypatch.setattr(ds.audit, "_iter_records", lambda: iter([]))   # no audit creates
    monkeypatch.setattr(ds, "cfg", lambda: {"hubspot": {"ticket_stages": {"closed": "4"}}})
    from src import hubspot_client as hs
    monkeypatch.setattr(hs, "_write", lambda m, p, b=None: {
        "results": [{"id": "T9", "properties": {"closed_date": fri_iso}}], "paging": {}})
    s = ds.ticket_eod_stats()
    from src.business_hours import prev_business_day
    assert s["closed"][prev_business_day(today.date())] == 1   # Friday
    assert s["closed"][today.date()] == 0


def test_gate_skips_when_not_6pm(monkeypatch):
    monkeypatch.setattr(ds, "DRY_RUN", False)        # force off
    monkeypatch.delenv("FORCE_RUN", raising=False)
    monkeypatch.setattr(ds, "now_la", lambda: dt.datetime(2026, 6, 10, 14, 0, tzinfo=LA))
    sent = []
    monkeypatch.setattr(ds.slack_client, "dm", lambda u, t: sent.append(t))
    ds.run()
    assert sent == []  # not 6 PM → nothing sent


def test_ticket_eod_format(monkeypatch):
    import datetime as dt2
    from src.business_hours import LA as LA2
    # Pin to a Monday so prev business day = Friday and Sat/Sun count as "new".
    monday = dt2.datetime(2026, 6, 15, 18, 0, tzinfo=LA2)
    monkeypatch.setattr(ds, "now_la", lambda: monday)
    today = monday.date()
    friday = dt2.date(2026, 6, 12)
    saturday = dt2.date(2026, 6, 13)
    s = {"created": {today: 3, friday: 5}, "closed": {today: 2, friday: 4},
         "open": [{"ticket": "1", "category": "scheduling", "owner": "yolanda",
                   "stage": "Needs Approval", "created": saturday.isoformat()},   # weekend → new
                  {"ticket": "2", "category": "unknown", "owner": "mandy",
                   "stage": "Stuck", "created": friday.isoformat()}]}             # Fri → carried
    text = ds.format_ticket_eod(s)
    assert "created 3 · closed 2" in text and "Fri: created 5 · closed 4" in text
    assert "New since Fri (incl. weekend) (1)" in text and "scheduling → yolanda" in text
    assert "Carried over" in text and "unknown → mandy [Stuck]" in text
