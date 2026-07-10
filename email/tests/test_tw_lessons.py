"""upcoming_lessons_for_family — dual-account leftover-lesson check."""
from src import teachworks_client as tw


def _fake_data(account_token):
    # two accounts: online (tok1) has Tali w/ a future lesson; in_person (tok2) has Layla
    data = {
        "tok1": {
            "customers": [{"id": 10}],
            "students": [{"id": 100, "first_name": "Tali", "last_name": "Schnider"}],
            "lessons": {100: [{"id": 1, "from_date": "2026-06-20", "from_time": "15:00",
                               "status": "Scheduled", "employee_name": "James, Kelly"}]},
        },
        "tok2": {
            "customers": [{"id": 20}],
            "students": [{"id": 200, "first_name": "Layla", "last_name": "Schnider"}],
            "lessons": {200: [
                {"id": 2, "from_date": "2026-06-18", "from_time": "16:45",
                 "status": "Scheduled", "employee_name": "KC, Shiwani"},
                {"id": 3, "from_date": "2026-06-25", "from_time": "16:45",
                 "status": "Cancelled", "employee_name": "KC, Shiwani"},   # excluded
            ]},
        },
    }
    return data[account_token]


def _mock(monkeypatch):
    monkeypatch.setattr(tw, "accounts", lambda: {"online": "tok1", "in_person": "tok2"})
    def fake_get(endpoint, params=None, token=None):
        d = _fake_data(token)
        if endpoint == "customers":
            return d["customers"]
        if endpoint == "students":
            return d["students"]
        if endpoint == "lessons":
            return d["lessons"].get(params["student_id"], [])
        return []
    monkeypatch.setattr(tw, "tw_get", fake_get)


def test_narrows_to_named_student(monkeypatch):
    _mock(monkeypatch)
    left = tw.upcoming_lessons_for_family("mom@x.com", "Layla")
    # Layla matched in in_person only; Tali's online lesson excluded by the narrow;
    # the already-cancelled 6/25 lesson excluded too.
    assert len(left) == 1
    assert left[0]["account"] == "in_person" and left[0]["date"] == "2026-06-18"


def test_no_name_reports_all_siblings(monkeypatch):
    _mock(monkeypatch)
    left = tw.upcoming_lessons_for_family("mom@x.com")
    assert {l["student"] for l in left} == {"Tali Schnider", "Layla Schnider"}
    assert len(left) == 2   # cancelled one still excluded
