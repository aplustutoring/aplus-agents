"""The spam gate, and the call it must never drop.

Roman 2026-09-16: "we get a bunch of spam, you gotta be able to filter numbers
some how. i want all of our lines transcribed."

Opening every line to transcription means junk arrives with the real calls.
The gate is built from 30 days of live traffic: of 132 answered inbound calls,
the 18 it drops were all under 20 seconds with a blank caller-ID, the longest
18s. Of the 58 answered calls over three minutes, 52 carried a human-looking
name. Junk has one shape and it is not subtle.
"""
import call_agent as ca


def _cfg(**over):
    cfg = {"spam_gate": {"enabled": True, "min_seconds": 20,
                         "require_unknown_to_hubspot": True},
           "hubspot": {"auto_create_contacts": True,
                       "created_contact_lead_status": "NEW"},
           "justcall": {"line_names": {"18185736293": "Roman's line"}}}
    cfg["spam_gate"].update(over)
    return cfg


def _call(seconds, name="", number="18185551212"):
    return {"id": 1, "contact_number": number, "contact_name": name,
            "justcall_number": "18185736293",
            "call_duration": {"total_duration": seconds}}


# ── what it drops ────────────────────────────────────────────────────────────

def test_drops_a_short_call_from_a_blank_unknown_number():
    spam, why = ca.looks_like_spam(_call(3, ""), _cfg(), contact_known=False)
    assert spam and "3s call" in why


def test_drops_a_short_call_from_a_telco_caller_id_string():
    spam, _ = ca.looks_like_spam(_call(11, "Sherman Oaks Ca"), _cfg(), False)
    assert spam


def test_drops_a_short_call_from_a_generic_caller_id():
    spam, _ = ca.looks_like_spam(_call(9, "Wireless Caller"), _cfg(), False)
    assert spam


# ── what it must NOT drop ────────────────────────────────────────────────────

def test_keeps_the_psat_parent():
    """The case the whole gate must not break. They called Roman's line twice
    on 2026-08-28 (223s and 37s) under JustCall's "New JustCall Contact"
    placeholder, and were still a stranger 18 days later. Both calls clear on
    duration alone."""
    assert not ca.looks_like_spam(
        _call(223, "New JustCall Contact", "18182688000"), _cfg(), False)[0]
    assert not ca.looks_like_spam(
        _call(37, "New JustCall Contact", "18182688000"), _cfg(), False)[0]


def test_keeps_a_short_call_from_a_known_family():
    """A parent ringing to say "running ten minutes late" is short and real."""
    assert not ca.looks_like_spam(_call(6, ""), _cfg(), contact_known=True)[0]


def test_keeps_a_long_call_even_with_no_caller_id():
    assert not ca.looks_like_spam(_call(240, ""), _cfg(), False)[0]


def test_keeps_a_short_call_from_a_human_looking_name():
    assert not ca.looks_like_spam(_call(8, "Annie Wolfstein"), _cfg(), False)[0]


def test_boundary_is_inclusive_at_min_seconds():
    assert ca.looks_like_spam(_call(19, ""), _cfg(), False)[0]
    assert not ca.looks_like_spam(_call(20, ""), _cfg(), False)[0]


def test_gate_off_drops_nothing():
    assert not ca.looks_like_spam(_call(2, ""), _cfg(enabled=False), False)[0]


def test_known_check_can_be_disabled():
    cfg = _cfg(require_unknown_to_hubspot=False)
    assert ca.looks_like_spam(_call(3, ""), cfg, contact_known=True)[0]


# ── contact creation ─────────────────────────────────────────────────────────

def test_creates_a_contact_named_by_number_not_by_caller_id(monkeypatch):
    """Never name a contact from the telco caller-ID. That is exactly how the
    838 CallRail shells got made in July 2026, and a contact called
    "Sherman Oaks Ca" is worse than one called by its number."""
    sent = {}

    def fake_post(endpoint, payload):
        sent.update(payload)
        return {"id": "C42"}

    monkeypatch.setattr(ca, "hs_post", fake_post)
    c = ca.create_contact_from_call(
        _call(223, "Sherman Oaks Ca", "18182688000"), _cfg(), dry_run=False)
    assert c["id"] == "C42"
    props = sent["properties"]
    assert props["phone"] == "+18182688000"
    assert "Sherman" not in props["lastname"]
    assert props["lastname"] == "Caller 818-268-8000"
    assert props["hs_lead_status"] == "NEW"


def test_dry_run_creates_nothing(monkeypatch):
    monkeypatch.setattr(ca, "hs_post",
                        lambda e, p: (_ for _ in ()).throw(AssertionError("wrote in dry run")))
    assert ca.create_contact_from_call(_call(223), _cfg(), dry_run=True) is None


def test_unusable_number_creates_nothing(monkeypatch):
    monkeypatch.setattr(ca, "hs_post",
                        lambda e, p: (_ for _ in ()).throw(AssertionError("wrote for a bad number")))
    assert ca.create_contact_from_call(_call(223, "", "123"), _cfg(), dry_run=False) is None


def test_creation_failure_is_survivable(monkeypatch):
    def boom(endpoint, payload):
        raise RuntimeError("HubSpot 500")

    monkeypatch.setattr(ca, "hs_post", boom)
    assert ca.create_contact_from_call(_call(223), _cfg(), dry_run=False) is None
