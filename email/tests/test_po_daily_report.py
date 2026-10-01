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


# ── the group is the billing unit where the invoice covers one ─────────────
#
# Roman 2026-10-01, on the three Ocean Grove deals: "they are on angies charge",
# then of grouping: "i like that option".
#
# The evidence is the invoice numbers themselves. Eight deals created 2026-09-16
# split C1-G1 -> 54731/54732/54733, C1-G3 -> 54739/54740, C1-G2 -> nothing, with
# 54734-54738 unused and sitting exactly between the two runs. Asking each of
# G2's three deals for its own number asks for something the billing does not
# produce.


def _iem(group, inv="", name="A Parent - A Student", stage="s_post"):
    return {"properties": {"pipeline": "5119061", "dealstage": stage,
                           "po_number": "", "invoice__": inv,
                           "hsa_group": group, "dealname": name,
                           "amount": "1250"}}


def test_one_invoice_in_a_group_covers_the_whole_group():
    """C1-G1: three deals, one number between them. All three are satisfied."""
    deals = [_iem("C1-G1", "54731", "Guadalupe Lucero - Melanie Espinoza"),
             _iem("C1-G1", "", "Mindy Young - Kloie Young"),
             _iem("C1-G1", "", "Ariana Avendano - Daniel Avendano")]
    gaps = pdr.billing_gaps(deals, STAGES)
    assert gaps["no_invoice"] == []
    assert gaps["no_invoice_groups"] == []


def test_a_group_with_no_invoice_anywhere_is_reported_once():
    """C1-G2, the real case. One line, not three."""
    deals = [_iem("C1-G2", "", "Kerri Nordhal - Brooklyn Lebeouf"),
             _iem("C1-G2", "", "Pearl Riddell - Scarlett Riddell"),
             _iem("C1-G2", "", "Katie White - Aster White")]
    gaps = pdr.billing_gaps(deals, STAGES)
    assert gaps["no_invoice"] == [], "must not also report them per deal"
    assert len(gaps["no_invoice_groups"]) == 1
    g = gaps["no_invoice_groups"][0]
    assert g["group"] == "C1-G2" and len(g["deals"]) == 3


def test_groups_are_judged_separately():
    """G1 and G3 are covered, G2 is not. Only G2 is reported."""
    deals = [_iem("C1-G1", "54731"), _iem("C1-G1", ""),
             _iem("C1-G2", ""), _iem("C1-G2", ""),
             _iem("C1-G3", "54739"), _iem("C1-G3", "")]
    gaps = pdr.billing_gaps(deals, STAGES)
    assert [g["group"] for g in gaps["no_invoice_groups"]] == ["C1-G2"]


def test_a_pre_lesson_deal_never_drags_its_group_in():
    deals = [_iem("C1-G4", "", stage="s_pre"), _iem("C1-G4", "", stage="s_pre")]
    gaps = pdr.billing_gaps(deals, STAGES)
    assert gaps["no_invoice_groups"] == [] and gaps["no_invoice"] == []


def test_a_deal_with_no_group_value_falls_back_to_per_deal():
    """A blank hsa_group cannot be grouped, so it is judged on its own rather
    than silently passing."""
    gaps = pdr.billing_gaps([_iem("", "", "Someone - Somebody")], STAGES)
    assert len(gaps["no_invoice"]) == 1
    assert gaps["no_invoice_groups"] == []


def test_a_pipeline_with_no_group_field_is_unaffected():
    """Traditional Vendor Funds invoices per student; grouping must not leak
    into it even if a deal happens to carry an hsa_group value."""
    d = {"properties": {"pipeline": "907748", "dealstage": "s_post",
                        "po_number": "P1", "invoice__": "",
                        "hsa_group": "C1-G2", "dealname": "X - Y",
                        "amount": "750"}}
    gaps = pdr.billing_gaps([d], STAGES)
    assert len(gaps["no_invoice"]) == 1
    assert gaps["no_invoice_groups"] == []


def test_the_count_does_not_double_report_a_group():
    """The headline number counts the DEALS inside an unbilled group, once."""
    deals = [_iem("C1-G2", "") for _ in range(3)]
    gaps = pdr.billing_gaps(deals, STAGES)
    n = (len(gaps["no_po"]) + len(gaps["no_invoice"])
         + len(gaps["unknown_pipeline"])
         + sum(len(g["deals"]) for g in gaps["no_invoice_groups"]))
    assert n == 3
