"""Scheduling tasks go to the scheduler for the FAMILY's surname.

Paola, 2026-09-22: session-logistics tasks (confirm a session, reschedule or
cancel, a no-show, an address / unit / access correction, tutor-student
scheduling details) must not land on her. A-L Janelle, M-Z Yolanda, and always
the family's surname — not the tutor's, not another contact named in the task.
Her three examples are the first three tests.
"""
from src import case_engine as ce
from src import reroute_scheduling_tasks as rr
from src.config import cfg, staff


def _owner_id(role):
    """Who holds a role right now, from config. Never assert a person's name:
    these tests broke on 2026-09-17 when Mandy left, which is the whole reason
    owners are config values."""
    return str(staff(role)["hubspot_owner_id"])


CARE = _owner_id("charter_sales")


def _role(subject, last_name, current=CARE):
    return ce.owner_for_task(subject, last_name, current)[0]


# ── Paola's three examples ──────────────────────────────────────────────────

def test_moore_family_goes_to_the_m_to_z_scheduler():
    assert _role("[Scheduling] Confirm session details", "Moore") == "scheduler_m_z"


def test_garcia_family_goes_to_the_a_to_l_scheduler():
    assert _role("[Scheduling] Confirm session details", "Garcia") == "scheduler_a_l"


def test_sterling_family_goes_to_the_m_to_z_scheduler():
    assert _role("Reply: cancellation — sterling", "Sterling") == "scheduler_m_z"


# ── what counts as a scheduling task ────────────────────────────────────────

def test_the_label_alone_is_enough():
    assert ce.task_is_scheduling("[Scheduling] anything at all") is True


def test_every_kind_paola_listed_is_scheduling():
    for subject in ("Reschedule Thursday's session",
                    "Cancel the Friday session",
                    "Follow up: no-show on 9/18",
                    "Confirm session address and unit number",
                    "Access instructions / gate code for the building",
                    "Confirm tutor schedule with the family",
                    "Reply: scheduling — hernandez"):
        assert ce.task_is_scheduling(subject) is True, subject


def test_care_work_is_not_scheduling_even_when_it_reads_like_it():
    # "Re-engage:" is the win-back task and "renewal" is the renewals case;
    # both mention a cancellation and both stay Student Success work.
    for subject in ("Re-engage: Moore, Sam (stop)",
                    "Renewal: cancellation of the current package — Moore",
                    "Student Success check-in call — Moore",
                    "Reply: review_received — Moore"):
        assert ce.task_is_scheduling(subject) is False, subject


def test_unrelated_task_is_untouched():
    assert ce.task_is_scheduling("Convert PO to TW invoice — Sam (PO 123, $60)") is False
    assert _role("Convert PO to TW invoice — Sam (PO 123, $60)", "Moore") is None


# ── who the rule may take a task from, and when it refuses ──────────────────

def test_a_task_already_on_a_scheduler_is_left_alone():
    assert _role("[Scheduling] Confirm session", "Moore", _owner_id("scheduler_a_l")) is None


def test_a_task_on_the_billing_seat_is_left_alone():
    # charter_admin holds the PO -> invoice path; that is not misrouted care work.
    assert _role("[Scheduling] Confirm session", "Moore", _owner_id("charter_admin")) is None


def test_no_surname_means_no_move_and_a_reason():
    role, why = ce.owner_for_task("[Scheduling] Confirm session", "", CARE)
    assert role is None and "CHECK" in why


def test_the_l_boundary_is_inclusive_for_a_to_l():
    assert _role("[Scheduling] Confirm session", "Lopez") == "scheduler_a_l"
    assert _role("[Scheduling] Confirm session", "Macias") == "scheduler_m_z"


def test_the_split_is_the_one_in_config_not_a_second_copy():
    split = cfg()["case_engine"]["owner_rules"]["renewals"]["split"]
    assert _role("[Scheduling] Confirm session", "Adams") == split["a_l"]
    assert _role("[Scheduling] Confirm session", "Zhang") == split["m_z"]


# ── the backfill reads the FAMILY contact, never the tutor ──────────────────

def _wire_contacts(monkeypatch, contacts):
    """contacts: list of property dicts, associated to task '1' in order."""
    def fake_get(path, params=None):
        if "/associations/contacts" in path:
            return {"results": [{"toObjectId": str(i)} for i in range(len(contacts))]}
        return {"properties": contacts[int(path.rsplit("/", 1)[1])]}
    monkeypatch.setattr(rr.hs, "_get", fake_get)


def test_surname_comes_from_the_family_contact_not_the_tutor(monkeypatch):
    _wire_contacts(monkeypatch, [
        {"lastname": "Abbott", "a_persona": "Tutors"},      # tutor A-L: the wrong answer
        {"lastname": "Moore", "a_persona": "Family"},
    ])
    assert rr._family_surname("1") == ("Moore", "")
    assert ce.split_role("Moore") == "scheduler_m_z"


def test_two_families_on_one_task_are_reported_not_guessed(monkeypatch):
    _wire_contacts(monkeypatch, [{"lastname": "Moore", "a_persona": "Family"},
                                 {"lastname": "Garcia", "a_persona": "Family"}])
    last, why = rr._family_surname("1")
    assert last is None and "several families" in why


def test_an_untagged_contact_still_counts_as_the_family(monkeypatch):
    # Intake capture often leaves a_persona empty; only a contact tagged as
    # something else (a tutor, a student) is excluded.
    _wire_contacts(monkeypatch, [{"lastname": "Garcia", "a_persona": ""}])
    assert rr._family_surname("1") == ("Garcia", "")


def test_a_task_with_only_a_tutor_on_it_is_refused(monkeypatch):
    _wire_contacts(monkeypatch, [{"lastname": "Abbott", "a_persona": "Tutors"}])
    last, why = rr._family_surname("1")
    assert last is None and "no family contact" in why
