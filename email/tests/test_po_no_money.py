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
        # cadence, not price (Ebalina Barrientos, 2026-09-23 dry run): kept whole
        "Math tutoring at 1/2 hour per week, covering October at $37.50/session.": "Math tutoring at 1/2 hour per week, covering October.",
        "Reading at 1 hour per week for 8 weeks.": "Reading at 1 hour per week for 8 weeks.",
        "Two POs: #1 for September ($150) and #2 for October ($300), total $450.": "Two POs: #1 for September and #2 for October.",
        "two sessions per week ($150/week), for September 2026.": "two sessions per week, for September 2026.",
        # the money word left standing (2026-09-23 dry run)
        "Mondays and Wednesdays 10/5. Total: $300.00. No tutor named.": "Mondays and Wednesdays 10/5. No tutor named.",
        "5 sessions for September 2026 at $300 total. TOR is Ana.": "5 sessions for September 2026. TOR is Ana.",
        "once a week in September 2026. Total PO value is $300. Tutor is Roman.": "once a week in September 2026. Tutor is Roman.",
        "Authorizes 4 sessions of online Math Tutoring = $300 total. Service dates 9/9.": "Authorizes 4 sessions of online Math Tutoring. Service dates 9/9.",
        "for September 2026 at $300.00 total ($60/session). Tutor named is Roman.": "for September 2026. Tutor named is Roman.",
        "ELA and math support for September 2026. Total authorized: $300. Tutor assigned: Roman.": "ELA and math support for September 2026. Tutor assigned: Roman.",
        "support for September 2026. PO value is $300.00. Tutor assigned is Roman.": "support for September 2026. Tutor assigned is Roman.",
        "Gianna Davis (4 hours) and Londyn Brixey (4 hours). Total certificate value $600.00.": "Gianna Davis (4 hours) and Londyn Brixey (4 hours).",
        "two sessions per week, for September 2026. PO total $300.": "two sessions per week, for September 2026.",
        "virtual math tutoring for Yanisel (Grade 12) for November at $525. Service period is Sept.": "virtual math tutoring for Yanisel (Grade 12) for November. Service period is Sept.",
        "Three POs: 3114234164 (Sept, $225.00), 3114234165 (Oct, $337.50). Total cost $862.50. TOR is Courtney.": "Three POs: 3114234164 (Sept), 3114234165 (Oct). TOR is Courtney.",
        "PO 6614257316 for October 2026 (same service). Total combined $600. Document is stamped.": "PO 6614257316 for October 2026 (same service). Document is stamped.",
        "PO 6614252513 for September 2026 ($150, one 45-minute session per week starting 9/2).":
            "PO 6614252513 for September 2026 (one 45-minute session per week starting 9/2).",
        "": "",
    }
    for src, want in cases.items():
        assert po_inbox.no_money(src) == want, src


def test_hours_and_po_numbers_survive():
    out = po_inbox.no_money("PO #635417 covers 1.5 hours for Ellie in November 2026 at $75/hour, totaling $112.50.")
    assert out == "PO #635417 covers 1.5 hours for Ellie in November 2026."
