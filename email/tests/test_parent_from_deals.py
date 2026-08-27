"""Parent resolution from the DEAL student-name properties (Roman 2026-08-26).

Fixtures are the nine real families behind the 19 deals flagged NEEDS PARENT
since 2026-08-01, with the shapes that actually broke the old lookups:

  Di Nardo / Rose   family surname differs from the student's
  Doyal             parent tagged BOTH Teacher of Record and Family
  Doyal / Holloway  a mis-stamped deal drags a second family into the match
  Czaja             three siblings on one parent, all new students
"""
from src import hubspot_client as hs, po_inbox


def _deal(did, name, first, last):
    return {"id": did, "properties": {
        "dealname": name,
        hs.STUDENT_FIRST_PROP: first,
        hs.STUDENT_LAST_PROP: last}}


def _contact(cid, first, last, email, persona="Family"):
    return {"id": cid, "properties": {
        "firstname": first, "lastname": last, "email": email, "a_persona": persona}}


def _wire(monkeypatch, deals, contacts_by_deal):
    monkeypatch.setattr(hs, "search_deals_by_student", lambda f, l=None: deals)
    monkeypatch.setattr(hs, "get_deal_contacts",
                        lambda did: contacts_by_deal.get(did, []))


# ── the two cases the parent-surname search could never handle ──────────────
def test_resolves_when_family_surname_differs(monkeypatch):
    """Giada Di Nardo's parent is Leeanne Gonzales — `lastname EQ 'Di Nardo'`
    returns zero contacts, so the old path flagged NEEDS PARENT."""
    d = _deal("1", "Leeanne Gonzales - Giada Di Nardo - iLead 1", "Giada", "Di Nardo")
    _wire(monkeypatch, [d], {"1": [_contact("c1", "Leeanne", "Gonzales", "lg@gmail.com")]})
    got = po_inbox._parent_from_student_deals(
        {"student_first": "Giada", "student_last": "Di Nardo"})
    assert got and got[0]["id"] == "c1"


def test_does_not_pick_the_wrong_same_surname_contact(monkeypatch):
    """Matthew Rose's parent is Megan Miller. The surname search matched Dina
    Rose (a 2022 contact) and named five deals after her."""
    d = _deal("1", "Megan Miller - Matthew Rose - iLead 1", "Matthew", "Rose")
    _wire(monkeypatch, [d], {"1": [_contact("c9", "Megan", "Miller", "mm@yahoo.com")]})
    got = po_inbox._parent_from_student_deals(
        {"student_first": "Matthew", "student_last": "Rose"})
    assert got[0]["properties"]["lastname"] == "Miller"


# ── the persona trap ────────────────────────────────────────────────────────
def test_parent_who_is_also_the_teacher_of_record_still_counts(monkeypatch):
    """Kath's homeschool families: a_persona reads 'Teacher of Record/EF/ES;Family'.
    Excluding every TOR-tagged contact drops the actual parent."""
    d = _deal("1", "Kristy Doyal - Cooper - Heartland 1", "Cooper", "Doyal")
    _wire(monkeypatch, [d], {"1": [
        _contact("c1", "Kristy", "Doyal", "kd@gmail.com",
                 "Teacher of Record/EF/ES;Family")]})
    got = po_inbox._parent_from_student_deals(
        {"student_first": "Cooper", "student_last": "Doyal"})
    assert got and got[0]["id"] == "c1"


def test_school_side_teacher_of_record_is_still_excluded(monkeypatch):
    d = _deal("1", "x - Kruz Vouniozos - iLead 1", "Kruz", "Vouniozos")
    _wire(monkeypatch, [d], {"1": [
        _contact("t1", "Christie", "Beadle", "christie@ileadexploration.org",
                 "Teacher of Record/EF/ES"),
        _contact("c1", "August", "Vouniozos", "av@gmail.com")]})
    got = po_inbox._parent_from_student_deals(
        {"student_first": "Kruz", "student_last": "Vouniozos"})
    assert got[0]["id"] == "c1"


def test_tor_named_on_the_po_is_excluded_even_if_tagged_family(monkeypatch):
    d = _deal("1", "x - Finn Goodings - iLead 1", "Finn", "Goodings")
    _wire(monkeypatch, [d], {"1": [
        _contact("t1", "Christie", "Beadle", "christie@ilead.org", "Family"),
        _contact("c1", "Robbie", "Goodings", "rg@gmail.com")]})
    got = po_inbox._parent_from_student_deals(
        {"student_first": "Finn", "student_last": "Goodings",
         "tor_email": "christie@ilead.org"})
    assert got[0]["id"] == "c1"


# ── the guards ──────────────────────────────────────────────────────────────
def test_frequency_breaks_a_contaminated_match(monkeypatch):
    """Deal 57397570424 is Payton Curtis's but carries student_last_name 'Doyal'.
    Kristy appears on seven Cooper deals, Anita on one — Kristy wins."""
    deals = [_deal(str(i), f"Kristy Doyal - Cooper - Heartland {i}", "Cooper", "Doyal")
             for i in range(1, 8)]
    deals.append(_deal("99", "Anita Curtis - Payton - Heartland 4", "Cooper", "Doyal"))
    by_deal = {str(i): [_contact("kd", "Kristy", "Doyal", "kd@gmail.com")]
               for i in range(1, 8)}
    by_deal["99"] = [_contact("ac", "Anita", "Curtis", "ac@gmail.com")]
    _wire(monkeypatch, deals, by_deal)
    got = po_inbox._parent_from_student_deals(
        {"student_first": "Cooper", "student_last": "Doyal"})
    assert got[0]["id"] == "kd"


def test_a_tie_refuses_to_guess(monkeypatch):
    """Rayven Holloway ties 7-7 with another family. Naming the deal after the
    wrong parent also addresses that family's scheduling SMS to the wrong people,
    so a tie must fall through to NEEDS PARENT."""
    deals = [_deal(str(i), f"deal {i}", "Rayven", "Holloway") for i in range(1, 3)]
    _wire(monkeypatch, deals, {
        "1": [_contact("a", "Jamie", "Holloway", "jh@gmail.com")],
        "2": [_contact("b", "Kristy", "Doyal", "kd@gmail.com")]})
    assert po_inbox._parent_from_student_deals(
        {"student_first": "Rayven", "student_last": "Holloway"}) is None


def test_first_name_alone_is_never_used_for_PARENT_resolution(monkeypatch):
    """`search_deals_by_student` deliberately allows a first-name-only lookup —
    deal SEQUENCE NUMBERING needs it for older deals that never got the
    last-name stamp. Parent resolution must not: 'Cooper' alone spans three
    unrelated families, so a wrong match would name the deal, and address the
    family's scheduling SMS, after the wrong parent."""
    called = []
    monkeypatch.setattr(hs, "search_deals_by_student",
                        lambda f, l=None: called.append((f, l)) or [])
    assert po_inbox._parent_from_student_deals({"student_first": "Cooper"}) is None
    assert po_inbox._parent_from_student_deals(
        {"student_first": "Cooper", "student_last": ""}) is None
    assert called == [], "no lookup may run without BOTH names"


def test_no_matching_deals_falls_through(monkeypatch):
    _wire(monkeypatch, [], {})
    assert po_inbox._parent_from_student_deals(
        {"student_first": "Nobody", "student_last": "Here"}) is None


def test_lookup_failure_is_not_fatal(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("429")

    monkeypatch.setattr(hs, "search_deals_by_student", boom)
    assert po_inbox._parent_from_student_deals(
        {"student_first": "Giada", "student_last": "Di Nardo"}) is None


# ── the search itself ───────────────────────────────────────────────────────
def test_search_filters_on_both_name_properties(monkeypatch):
    """Narrowing happens server-side, so both properties must reach HubSpot."""
    seen = {}
    monkeypatch.setattr(hs, "_write",
                        lambda m, p, body=None: seen.update(body or {}) or {"results": []})
    hs.search_deals_by_student("Cooper", "Doyal")
    props = [f["propertyName"] for f in seen["filterGroups"][0]["filters"]]
    assert props == [hs.STUDENT_FIRST_PROP, hs.STUDENT_LAST_PROP]


def test_is_family_contact_rules():
    fam = {"email": "a@b.com", "a_persona": "Family"}
    both = {"email": "a@b.com", "a_persona": "Teacher of Record/EF/ES;Family"}
    tor = {"email": "t@school.org", "a_persona": "Teacher of Record/EF/ES"}
    assert hs.is_family_contact(fam)
    assert hs.is_family_contact(both)
    assert not hs.is_family_contact(tor)
    assert not hs.is_family_contact({"email": ""})
    assert not hs.is_family_contact(fam, tor_email="A@B.com")
