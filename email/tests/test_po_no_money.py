"""Roman 2026-09-23: the deal description reaches the tutor channel, so it
never carries the PO value or our hourly rate."""
from src import po_inbox


def test_real_ilead_summaries_lose_the_price_and_keep_the_facts():
    s = ("OPS/iLEAD Vendor Agreement Form (Order Agreement) for Aaron Amaya, Grade 4, at iCC1 for iLEAD "
         "Hybrid Exploration. PO #3114264191 covers 4 hours of Level Up A+ Tutoring for September 2026 "
         "at $75/hour, totaling $300. Marked 'THIS IS NOT A PO'. EF/TOR is Mary Nieves. Parent is Elizabeth Amaya.")
    out = po_inbox.no_money(s)
    assert "$" not in out and "75" not in out and "300" not in out and "/hour" not in out
    assert "PO #3114264191 covers 4 hours of Level Up A+ Tutoring for September 2026." in out
    assert "EF/TOR is Mary Nieves. Parent is Elizabeth Amaya." in out and "Grade 4" in out
    s2 = ("PO #3114263336 authorizes 4 hours of Level Up A+ Tutoring for October 2026 at $75/hour, "
          "totaling $300. Teacher of Record is Christie Beadle.")
    assert po_inbox.no_money(s2) == ("PO #3114263336 authorizes 4 hours of Level Up A+ Tutoring for October 2026. "
                                     "Teacher of Record is Christie Beadle.")


def test_every_money_shape_is_removed():
    cases = {
        "8 sessions at $60 per 45-minute session, total of $480, for Mia.": "8 sessions, for Mia.",
        "Value 150.00 but payout 140.00 on PO 12.": "but on PO 12.",
        "Hourly rate of $75 (Total Cost: $600.00) for 8 hours.": "for 8 hours.",
        "10 hours @ 75/hr for October.": "10 hours for October.",
        "Amount $1,200.50 covers 16 hours.": "covers 16 hours.",
        "PO 4471 for 6 hours of tutoring.": "PO 4471 for 6 hours of tutoring.",      # no money: untouched
        "": "",
    }
    for src, want in cases.items():
        assert po_inbox.no_money(src) == want, src


def test_hours_and_po_numbers_survive():
    out = po_inbox.no_money("PO #635417 covers 1.5 hours for Ellie in November 2026 at $75/hour, totaling $112.50.")
    assert out == "PO #635417 covers 1.5 hours for Ellie in November 2026."
