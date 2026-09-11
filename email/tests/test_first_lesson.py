"""First-lesson stamp: Teachworks first attended lesson → [Agent] First lesson date."""
import datetime as dt

from src import first_lesson as fl

TODAY = dt.date(2026, 9, 10)


def _cfg():
    return {"first_lesson": {"enabled": True, "every_hours": 6, "window_days": 10,
                             "new_start_days": 60, "season_start": "2026-08-01", "retry_days": 3},
            "deal_sync": {"exclude_pipelines": ["971802"]}}


def _lesson(date, students, status="Attended", lesson_status=""):
    return {"from_date": date, "status": lesson_status,
            "participants": [{"student_name": s, "status": status, "student_id": i}
                             for i, s in enumerate(students, start=100)]}


def test_attended_participants_groups_by_student_and_skips_future_and_absent(monkeypatch):
    monkeypatch.setattr(fl, "_today", lambda: TODAY.isoformat())
    lessons = [_lesson("2026-09-03", ["Ariana Fiore", "Tony Fiore"]),
               _lesson("2026-09-05", ["Ariana Fiore"]),
               _lesson("2026-09-07", ["Ariana Fiore"], status="Cancelled"),
               _lesson("2026-09-12", ["Ariana Fiore"]),                       # future
               {"from_date": "2026-09-04", "status": "Completed",
                "participants": [{"student_name": "Cali  Escandon", "status": ""}]}]   # falls back to lesson status
    out = fl.attended_participants(lessons)
    assert out["ariana fiore"]["dates"] == ["2026-09-03", "2026-09-05"]
    assert out["ariana fiore"]["ids"] == {"100"}
    assert out["tony fiore"]["dates"] == ["2026-09-03"]
    assert out["cali escandon"]["name"] == "Cali  Escandon" and out["cali escandon"]["dates"] == ["2026-09-04"]


def test_earliest_attended_is_the_true_first_lesson(monkeypatch):
    monkeypatch.setattr(fl, "_today", lambda: TODAY.isoformat())
    hist = [{"from_date": "2025-10-02", "status": "Attended"},
            {"from_date": "2025-09-20", "status": "Cancelled"},
            {"from_date": "2025-09-25", "status": "", "participants": [{"status": "Completed"}]},
            {"from_date": "2026-09-30", "status": "Attended"}]
    assert fl.earliest_attended(hist) == "2025-09-25"
    assert fl.earliest_attended([]) == ""


def test_split_name_handles_teachworks_last_comma_first():
    # the 2026-09-10 preview: 0 of 164 students resolved until 'Fiore, Ariana' was read as Ariana Fiore
    assert fl.split_name("Fiore, Ariana") == ("Ariana", "Fiore")
    assert fl.split_name("DaVault, Kailyn Marie") == ("Kailyn Marie", "DaVault")
    assert fl.split_name("Ariana Fiore") == ("Ariana", "Fiore")
    assert fl.split_name("Murray-Fiore, Mateo") == ("Mateo", "Murray-Fiore")
    assert fl.display_name("Fiore, Ariana") == "Ariana Fiore"
    assert fl.split_name("") == ("", "")


def test_last_comma_first_participant_resolves_and_stamps(monkeypatch):
    w = Wire(monkeypatch, lessons=[_lesson("2026-09-05", ["Fiore, Ariana"])],
             history=[{"from_date": "2026-09-01", "status": "Attended"}],
             students=[STUDENT], customers=[CUSTOMER], deals=[DEAL1], contact=CONTACT)
    out = fl.run(force=True)
    assert out["stamped_deals"] == 1 and out["not_in_tw"] == 0
    assert w.saved["online:fiore, ariana"]["name"] == "Ariana Fiore"
    assert out["new_starts"] == ["Ariana Fiore (2026-09-01)"]


def test_choose_deal_picks_the_seasons_earliest_and_skips_excluded_pipelines():
    deals = [{"id": "5", "properties": {"createdate": "2026-09-04T00:00:00Z", "pipeline": "907748", "dealname": "x 5"}},
             {"id": "1", "properties": {"createdate": "2026-08-20T00:00:00Z", "pipeline": "907748", "dealname": "x 1"}},
             {"id": "old", "properties": {"createdate": "2025-09-01T00:00:00Z", "pipeline": "907748", "dealname": "x old"}},
             {"id": "tutor", "properties": {"createdate": "2026-08-01T00:00:00Z", "pipeline": "971802", "dealname": "tutor"}}]
    assert fl.choose_deal(deals, "2026-08-01", {"971802"})["id"] == "1"
    assert fl.choose_deal([deals[2]], "2026-08-01") is None


class Wire:
    def __init__(self, monkeypatch, state=None, lessons=None, history=None, students=None,
                 customers=None, deals=None, contact=None, dry=False):
        self.patches, self.audit, self.saved = [], [], {}
        monkeypatch.setattr(fl, "cfg", _cfg)
        monkeypatch.setattr(fl, "DRY_RUN", dry)
        monkeypatch.setattr(fl, "_today", lambda: TODAY.isoformat())
        monkeypatch.setattr(fl, "now_la", lambda: dt.datetime(2026, 9, 10, 9, 0))
        monkeypatch.setattr(fl, "load_state", lambda: dict(state or {}))
        monkeypatch.setattr(fl, "save_state", lambda s: self.saved.update(s))
        monkeypatch.setattr(fl.tw, "accounts", lambda: {"online": "tok"})

        def tw_get(endpoint, params=None, token=None):
            params = params or {}
            if endpoint == "lessons" and "student_id" in params:
                return list(history or [])
            if endpoint == "lessons":
                return list(lessons or [])
            if endpoint == "students":
                return [s for s in (students or []) if s["first_name"].lower() == params["first_name"].lower()]
            if endpoint == "customers":
                return [c for c in (customers or []) if str(c["id"]) == str(params["id"])]
            return []
        monkeypatch.setattr(fl.tw, "tw_get", tw_get)
        monkeypatch.setattr(fl.hs, "search_deals_by_student", lambda first: list(deals or []))
        monkeypatch.setattr(fl.hs, "find_contact_by_email", lambda e, properties=None: contact)
        monkeypatch.setattr(fl.hs, "_write", lambda m, p, body=None: self.patches.append((m, p, body)) or {})
        monkeypatch.setattr(fl.audit, "append", lambda r: self.audit.append(r))


STUDENT = {"id": 100, "first_name": "Ariana", "last_name": "Fiore", "customer_id": 7}
CUSTOMER = {"id": 7, "email": "SFiore1822@gmail.com"}
DEAL1 = {"id": "64480919678", "properties": {"createdate": "2026-08-28T10:40:00Z", "pipeline": "907748",
                                             "dealname": "Sarah Fiore - Ariana Fiore - iLead 1 - 26/27"}}
DEAL2 = {"id": "999", "properties": {"createdate": "2026-09-09T10:40:00Z", "pipeline": "907748",
                                     "dealname": "Sarah Fiore - Ariana Fiore - iLead 2 - 26/27"}}
CONTACT = {"id": "3167401", "properties": {"email": "sfiore1822@gmail.com"}}


def test_new_student_gets_deal_and_contact_stamped_from_true_history(monkeypatch):
    w = Wire(monkeypatch,
             lessons=[_lesson("2026-09-05", ["Ariana Fiore"])],
             history=[{"from_date": "2026-09-01", "status": "Attended"}, {"from_date": "2026-09-05", "status": "Attended"}],
             students=[STUDENT], customers=[CUSTOMER], deals=[DEAL2, DEAL1], contact=CONTACT)
    out = fl.run(force=True)
    assert out["stamped_deals"] == 1 and out["stamped_contacts"] == 1 and out["new"] == 1
    assert ("PATCH", "/crm/v3/objects/deals/64480919678", {"properties": {"retention_first_lesson_date": "2026-09-01"}}) in w.patches
    assert ("PATCH", "/crm/v3/objects/contacts/3167401", {"properties": {"retention_first_lesson_date": "2026-09-01"}}) in w.patches
    entry = w.saved["online:ariana fiore"]
    assert entry["first"] == "2026-09-01" and entry["deal_id"] == "64480919678" and entry["contact_id"] == "3167401"
    assert entry["email"] == "sfiore1822@gmail.com"
    assert w.audit and w.audit[0]["action_taken"] == "first_lesson_stamped" and w.audit[0]["first_lesson"] == "2026-09-01"
    assert out["new_starts"] == ["Ariana Fiore (2026-09-01)"]


def test_returning_student_is_stamped_but_not_a_new_start(monkeypatch):
    w = Wire(monkeypatch, lessons=[_lesson("2026-09-05", ["Ariana Fiore"])],
             history=[{"from_date": "2025-09-01", "status": "Attended"}],
             students=[STUDENT], customers=[CUSTOMER], deals=[DEAL1], contact=CONTACT)
    out = fl.run(force=True)
    assert out["stamped_deals"] == 1 and out["new_starts"] == [] and not w.audit
    assert w.saved["online:ariana fiore"]["first"] == "2025-09-01"


def test_contact_keeps_the_earliest_sibling_date(monkeypatch):
    contact = {"id": "3167401", "properties": {"email": "sfiore1822@gmail.com", "retention_first_lesson_date": "2026-08-20"}}
    w = Wire(monkeypatch, lessons=[_lesson("2026-09-05", ["Ariana Fiore"])],
             history=[{"from_date": "2026-09-01", "status": "Attended"}],
             students=[STUDENT], customers=[CUSTOMER], deals=[DEAL1], contact=contact)
    out = fl.run(force=True)
    assert out["stamped_contacts"] == 0 and out["stamped_deals"] == 1
    assert not any("/contacts/" in p for _m, p, _b in w.patches)


def test_no_deal_yet_parks_and_retries_later(monkeypatch):
    w = Wire(monkeypatch, lessons=[_lesson("2026-09-05", ["Ariana Fiore"])],
             history=[{"from_date": "2026-09-05", "status": "Attended"}],
             students=[STUDENT], customers=[CUSTOMER], deals=[], contact=CONTACT)
    out = fl.run(force=True)
    assert out["no_deal"] == 1 and out["stamped_contacts"] == 1
    e = w.saved["online:ariana fiore"]
    assert e["no_deal_until"] == "2026-09-13" and "deal_id" not in e
    # next run inside the retry window: skipped without any Teachworks or HubSpot call
    w2 = Wire(monkeypatch, state={"online:ariana fiore": e}, lessons=[_lesson("2026-09-06", ["Ariana Fiore"])],
              students=[STUDENT], customers=[CUSTOMER], deals=[DEAL1], contact=CONTACT)
    fl.run(force=True)
    assert not w2.patches


def test_fully_stamped_student_costs_nothing(monkeypatch):
    done = {"name": "Ariana Fiore", "first": "2026-09-01", "email": "sfiore1822@gmail.com",
            "deal_id": "64480919678", "contact_id": "3167401"}
    w = Wire(monkeypatch, state={"online:ariana fiore": done}, lessons=[_lesson("2026-09-08", ["Ariana Fiore"])],
             students=[STUDENT], customers=[CUSTOMER], deals=[DEAL1], contact=CONTACT)
    out = fl.run(force=True)
    assert out["new"] == 0 and not w.patches and not w.audit


def test_gate_and_dry_run(monkeypatch):
    recent = dt.datetime(2026, 9, 10, 15, 0, tzinfo=dt.timezone.utc).isoformat()
    w = Wire(monkeypatch, state={"_last_run": recent}, lessons=[_lesson("2026-09-05", ["Ariana Fiore"])],
             students=[STUDENT], customers=[CUSTOMER], deals=[DEAL1], contact=CONTACT)
    monkeypatch.setattr(fl, "datetime", _FrozenDatetime)
    assert fl.run() == {"skipped": "recent"}
    w = Wire(monkeypatch, lessons=[_lesson("2026-09-05", ["Ariana Fiore"])],
             history=[{"from_date": "2026-09-01", "status": "Attended"}],
             students=[STUDENT], customers=[CUSTOMER], deals=[DEAL1], contact=CONTACT, dry=True)
    out = fl.run(force=True)
    assert out["stamped_deals"] == 1 and not w.patches            # counted, nothing written
    assert fl.hs.SEARCH_PASSTHROUGH in (None, False)               # restored after the preview


class _FrozenDatetime(dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return dt.datetime(2026, 9, 10, 16, 0, tzinfo=tz)
