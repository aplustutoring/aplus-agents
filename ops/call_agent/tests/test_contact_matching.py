"""
find_contact_by_phone must not treat CallRail's auto-created caller-ID shell
contacts (name = telco CNAM string, no email) as known contacts — they defeat
the abandoned-IVR spam suppression for unknown numbers (PR #41).

Real examples from the portal are used verbatim.
"""

import call_agent


def _contact(cid, first, last, email=None, source_detail="CallRail"):
    return {
        "id": cid,
        "properties": {
            "firstname": first,
            "lastname": last,
            "email": email,
            "hs_object_source_detail_1": source_detail,
        },
    }


def _search_returning(monkeypatch, results, captured=None):
    """Stub hs_post to return the same result set for every search tier."""
    def fake_hs_post(endpoint, payload):
        assert endpoint == "crm/v3/objects/contacts/search"
        if captured is not None:
            captured.append(payload)
        return {"total": len(results), "results": results}
    monkeypatch.setattr(call_agent, "hs_post", fake_hs_post)


# ─── CNAM name detection ──────────────────────────────────────────────────────

def test_cnam_city_state_names():
    assert call_agent._is_cnam_name("Inglewood Ca")
    assert call_agent._is_cnam_name("Lsan Da 12 Ca")
    assert call_agent._is_cnam_name("Phoenix Az")


def test_cnam_generic_names():
    for name in ["Wireless Caller", "Toll Free", "Toll Free Call",
                 "Unavailable", "Voip Caller", "Anonymous", "Restricted"]:
        assert call_agent._is_cnam_name(name), name


def test_real_names_are_not_cnam():
    assert not call_agent._is_cnam_name("Katie Alexander")
    assert not call_agent._is_cnam_name("Maria Castillo")
    assert not call_agent._is_cnam_name("")


# ─── Junk-contact classification ──────────────────────────────────────────────

def test_callrail_shell_is_junk():
    assert call_agent._is_callrail_junk_contact(_contact("1", "Inglewood", "Ca"))
    assert call_agent._is_callrail_junk_contact(_contact("2", "Wireless", "Caller"))


def test_email_clears_a_callrail_contact():
    # A CallRail-created record that later got a real email is a real family.
    c = _contact("3", "Inglewood", "Ca", email="family@example.com")
    assert not call_agent._is_callrail_junk_contact(c)


def test_non_callrail_source_is_never_junk():
    # Same CNAM-looking name, but not created by CallRail — leave it alone.
    c = _contact("4", "Inglewood", "Ca", source_detail=None)
    assert not call_agent._is_callrail_junk_contact(c)


# ─── find_contact_by_phone end-to-end (hs_post stubbed) ───────────────────────

def test_inglewood_ca_shell_treated_as_unknown(monkeypatch):
    _search_returning(monkeypatch, [_contact("101", "Inglewood", "Ca")])
    assert call_agent.find_contact_by_phone("310-693-5037") is None


def test_lsan_da_12_ca_shell_treated_as_unknown(monkeypatch):
    _search_returning(monkeypatch, [_contact("102", "Lsan Da 12", "Ca")])
    assert call_agent.find_contact_by_phone("323-431-1255") is None


def test_wireless_caller_shell_treated_as_unknown(monkeypatch):
    _search_returning(monkeypatch, [_contact("103", "Wireless", "Caller")])
    assert call_agent.find_contact_by_phone("310-555-0123") is None


def test_real_contact_still_matches(monkeypatch):
    katie = _contact("104", "Katie", "Alexander",
                     email="katie.alexander@example.com", source_detail=None)
    _search_returning(monkeypatch, [katie])
    found = call_agent.find_contact_by_phone("310-693-5037")
    assert found is not None and found["id"] == "104"


def test_shell_does_not_shadow_real_contact(monkeypatch):
    # Junk shell sorts first in the search results; the real contact behind it
    # must still be returned.
    shell = _contact("105", "Inglewood", "Ca")
    katie = _contact("106", "Katie", "Alexander",
                     email="katie.alexander@example.com", source_detail=None)
    _search_returning(monkeypatch, [shell, katie])
    found = call_agent.find_contact_by_phone("310-693-5037")
    assert found is not None and found["id"] == "106"


def test_search_fetches_source_property(monkeypatch):
    # The junk filter needs hs_object_source_detail_1 (and email) on results.
    captured = []
    _search_returning(monkeypatch, [], captured)
    call_agent.find_contact_by_phone("310-693-5037")
    for payload in captured:
        assert "hs_object_source_detail_1" in payload["properties"]
        assert "email" in payload["properties"]
