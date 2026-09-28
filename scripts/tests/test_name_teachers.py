"""scripts/name_teachers_from_email.py — naming a teacher from what we hold.

Every case here comes from the 2026-09-25 test run over the live portal. The
refusals matter more than the hits: a wrong name is written into every email
that contact ever receives.

Roman asked for the test before the build, and the test is why three of these
paths exist in the shape they do.
"""
import importlib.util
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE.parent / "email"))
spec = importlib.util.spec_from_file_location(
    "name_teachers", HERE / "name_teachers_from_email.py")
nt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nt)


def _c(*names):
    return Counter(names)


# ── path 1: the address carries both names ─────────────────────────────────

def test_first_dot_last_address_names_itself():
    f, l, how = nt.propose_name("misa.rudge@pacificcoastacademy.org", "", "",
                                Counter(), _c("Misa"))
    assert (f, l) == ("Misa", "Rudge")
    assert "greeting agrees" in how


def test_first_dot_last_works_without_a_greeting():
    """michelle.varju@ had no greeting in anything we sent, and the address is
    still two names. This one nearly got generic_inbox stamped on it by an
    earlier draft of the persona sweep."""
    f, l, _how = nt.propose_name("michelle.varju@theblueridgeacademy.com", "", "",
                                 Counter(), Counter())
    assert (f, l) == ("Michelle", "Varju")


def test_the_greeting_spelling_wins_over_the_address():
    """The address is lowercase and may abbreviate; a human typed the greeting."""
    f, l, _how = nt.propose_name("jenni.pike@pacificcharters.org", "", "",
                                 Counter(), _c("Jenni", "Jenni"))
    assert (f, l) == ("Jenni", "Pike")


# ── path 2: initial + surname, corroborated ────────────────────────────────

def test_greeting_plus_junk_surname_when_the_initial_agrees():
    """"Hi Suzanna" in our own sent mail, "Teacher Polo" on the record,
    spolo@ in the address. Three things agreeing."""
    f, l, how = nt.propose_name("spolo@ileadexploration.org", "Teacher", "Polo",
                                Counter(), _c("Suzanna"))
    assert (f, l) == ("Suzanna", "Polo")
    assert "initial matches" in how


def test_a_greeting_whose_initial_disagrees_is_refused():
    """Daisy Dige would be ddige@, not kdige@. Mirae Kim would be mkim@, not
    iskim@. Both were live in the test run and both are guesses."""
    for addr, junk, greet in (("kdige@ileadexploration.org", "Dige", "Daisy"),
                              ("iskim@ileadexploration.org", "Kim", "Mirae")):
        f, l, why = nt.propose_name(addr, "Teacher", junk, Counter(), _c(greet))
        assert f is None, (addr, f, l)
        assert "does not match the initial" in why


# ── the refusals that make the rest trustworthy ────────────────────────────

def test_a_role_mailbox_is_never_named_after_the_person_who_staffs_it():
    """The first test run produced "Natalie invoicing", "Camille services",
    "Julian accounting" and "Marsha vendors" by gluing a real staffer's first
    name onto a job word. Those people exist; the mailbox is not them."""
    for addr, junk, greet in (
            ("vendorinvoicing@granitemountainschool.com", "Invoicing", "Natalie"),
            ("business.services@cottonwoodk12.org", "Services", "Camille"),
            ("accounting@jcs-inc.org", "Accounting", "Julian"),
            ("vendors@ileadexploration.org", "Vendors", "Marsha"),
            ("studentservices@excelacademy.education", "Services", "Student"),
            ("homeschool@heartwoodcharterschool.org", "School", "Heartwood")):
        f, _l, why = nt.propose_name(addr, "Vendor", junk, Counter(), _c(greet))
        assert f is None, (addr, f)
        assert "role mailbox" in why


def test_a_dotted_role_address_is_still_a_role_address():
    """business.services@ has a dot, so path 1 would otherwise read it as
    "Business Services" and call that a person."""
    f, _l, why = nt.propose_name("vendor.relations@springscs.org", "", "",
                                 Counter(), _c("Suzanne"))
    assert f is None and "role mailbox" in why


def test_an_incoming_signature_is_the_last_resort():
    f, l, how = nt.propose_name("awatters@eliteacademic.com", "", "",
                                Counter({("Allison", "Watters"): 3}), Counter())
    assert (f, l) == ("Allison", "Watters")
    assert "signed their own mail" in how


def test_a_signature_that_does_not_fit_the_address_is_refused():
    """Mike Sarti signs coordinator@brightonhallschool.org. He is real; the
    mailbox is a coordinator inbox, and greeting it "Hi Mike" is wrong.

    "coordinator" is not in the role-shape list, so this is caught one guard
    later, by the signature not fitting the address. Asserting the refusal
    rather than the wording: two independent guards stand behind it and
    pinning either one would make the test brittle for no gain.
    """
    f, l, why = nt.propose_name("coordinator@brightonhallschool.org", "", "",
                                Counter({("Mike", "Sarti"): 2}), Counter())
    assert (f, l) == (None, None), why


def test_nothing_at_all_says_so_plainly():
    f, _l, why = nt.propose_name("kamesse@ieminc.org", "Teacher", "",
                                 Counter(), Counter())
    assert f is None
    assert why == "nothing we hold names them"


# ── the helper the junk surname comes from ─────────────────────────────────

def test_the_junk_word_is_never_taken_as_the_surname():
    assert nt._surname_from_junk("Teacher", "Polo") == "polo"
    assert nt._surname_from_junk("Teacher", "") == ""
    assert nt._surname_from_junk("Vendor", "Invoicing") == ""
