"""email/src/po_daily_report.py — the end-of-day PO report."""
from src import po_daily_report as pdr  # noqa: F401


# ── the standing cross-reference (Roman 2026-10-01) ────────────────────────
#
# "we need to always make sure that we can cross reference every deal to have a
# corresponding invoice and purchase order"
#
# Every case here is real, from the 2026-10-01 audit. The first test is the
# mistake I made that day: one global rule flagged all eight IEM Inc. deals as
# missing a PO and reported $11,250 at risk to Roman. They bill the school
# directly and were correct. The real exposure was three missing invoices.

STAGES = {"s_pre": "Pre-Lesson", "s_post": "Post-Lesson",
          "s_stop": "Stopped", "s_reass": "Hours Reassigned"}


def _deal(pipeline, stage="s_post", po="", inv="", name="A Family - A Student",
          amount="1250"):
    return {"properties": {"pipeline": pipeline, "dealstage": stage,
                           "po_number": po, "invoice__": inv,
                           "dealname": name, "amount": amount}}


def test_a_school_billed_pipeline_is_not_missing_a_PO():
    """IEM Inc. bills the school on one charge. Eight deals, no POs, and that
    is CORRECT. Flagging them is how a daily check gets muted."""
    deals = [_deal("5119061", inv="5473%d" % i) for i in range(1, 6)]
    gaps = pdr.billing_gaps(deals, STAGES)
    assert gaps["no_po"] == [], "IEM Inc. must never be flagged for a missing PO"
    assert gaps["no_invoice"] == []


def test_the_three_IEM_deals_that_really_were_unbilled():
    """Delivered, no invoice number on the deal. $3,750, which is the figure
    that mattered."""
    deals = [_deal("5119061", name="Kerri Nordhal - Brooklyn Lebeouf"),
             _deal("5119061", name="Pearl Riddell - Scarlett Riddell"),
             _deal("5119061", name="Katie White - Aster White")]
    gaps = pdr.billing_gaps(deals, STAGES)
    assert len(gaps["no_invoice"]) == 3
    assert gaps["no_po"] == []


def test_a_PO_pipeline_without_a_PO_is_flagged():
    gaps = pdr.billing_gaps([_deal("907748", inv="99")], STAGES)
    assert len(gaps["no_po"]) == 1


def test_a_pre_lesson_deal_owes_no_invoice_yet():
    """Pre-Lesson is early, not late. Two such deals existed on 2026-10-01 and
    neither is a problem."""
    gaps = pdr.billing_gaps([_deal("907748", stage="s_pre", po="123")], STAGES)
    assert gaps["no_invoice"] == [] and gaps["no_po"] == []


def test_stopped_and_reassigned_owe_nothing():
    for st in ("s_stop", "s_reass"):
        gaps = pdr.billing_gaps([_deal("907748", stage=st)], STAGES)
        assert all(not v for v in gaps.values()), st


def test_free_trial_owes_neither():
    gaps = pdr.billing_gaps([_deal("19120821")], STAGES)
    assert all(not v for v in gaps.values())


def test_an_undeclared_pipeline_is_reported_not_assumed():
    """A new school must arrive as a question. Assuming it needs a PO invents
    an alarm; assuming it does not hides one."""
    gaps = pdr.billing_gaps([_deal("999999999", name="New School - Kid")], STAGES)
    assert len(gaps["unknown_pipeline"]) == 1
    assert gaps["no_po"] == [] and gaps["no_invoice"] == []


def test_the_real_2026_10_01_population():
    """399 PO-pipeline deals all had a PO; the only gaps were IEM invoices."""
    deals = ([_deal("907748", po="P%d" % i, inv="I%d" % i) for i in range(399)]
             + [_deal("5119061", inv="5473%d" % i) for i in (1, 2, 3, 9)]
             + [_deal("5119061", name="Katie White - Aster White")])
    gaps = pdr.billing_gaps(deals, STAGES)
    assert gaps["no_po"] == []
    assert len(gaps["no_invoice"]) == 1
    assert gaps["unknown_pipeline"] == []
