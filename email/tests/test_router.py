from src.router import last_name_initial, resolve


def test_reschedule_routes_to_scheduler_fast():
    d = resolve("reschedule", 0.9, last_name="Adams")
    assert d.owner_key == "janelle" and d.sla_hours == 1.5 and d.should_draft is True


def test_business_dev_routes_to_danielle():
    d = resolve("business_dev", 0.85)
    assert d.owner_key == "danielle" and d.should_draft is True and d.sla_hours == 8


def test_tutor_issue_routes_to_mandy_no_draft():
    d = resolve("tutor_issue", 0.9)
    assert d.owner_key == "mandy" and d.should_draft is False and d.priority == "high"


def test_scheduling_a_to_l_goes_to_janelle():
    d = resolve("scheduling", 0.9, last_name="Adams")
    assert d.owner_key == "janelle"
    assert d.sla_hours == 1.5
    assert d.should_draft is True


def test_scheduling_m_to_z_goes_to_yolanda():
    d = resolve("scheduling", 0.9, last_name="Zhang")
    assert d.owner_key == "yolanda"


def test_cancellation_uses_same_split():
    assert resolve("cancellation", 0.9, last_name="Brown").owner_key == "janelle"
    assert resolve("cancellation", 0.9, last_name="Nguyen").owner_key == "yolanda"


def test_l_boundary_is_inclusive_for_a_to_l():
    assert last_name_initial("Lopez") == "L"
    assert resolve("scheduling", 0.9, last_name="Lopez").owner_key == "janelle"
    assert resolve("scheduling", 0.9, last_name="Martin").owner_key == "yolanda"


def test_complaint_routes_to_mandy_no_draft():
    d = resolve("complaint", 0.95)
    assert d.owner_key == "mandy"
    assert d.sla_hours == 1.5
    assert d.should_draft is False  # complaints never get a draft


def test_payment_dispute_no_draft():
    assert resolve("payment_dispute", 0.99).should_draft is False


def test_low_confidence_downgrades_to_unknown():
    d = resolve("school_partner", 0.5)
    assert d.category == "unknown"
    assert d.should_draft is False
    assert d.owner_key == "mandy"   # Mandy owns the Stuck/unknown queue
    assert d.sla_hours == 4


def test_junk_auto_archives():
    d = resolve("junk", 0.95)
    assert d.auto_archive is True
    assert d.should_draft is False
    assert d.owner_key is None


def test_junk_below_090_held_for_review_not_archived():
    # LOCKED: junk under the 0.9 threshold must NOT silently disappear —
    # it becomes unknown → Stuck → Mandy. (The Mitchell Feldman misfire.)
    d = resolve("junk", 0.82)
    assert d.auto_archive is False
    assert d.category == "unknown"
    assert d.owner_key == "mandy"
    assert any("held for review" in n for n in d.notes)


def test_school_partner_high_priority_4h():
    d = resolve("school_partner", 0.9)
    assert d.owner_key == "danielle"
    assert d.sla_hours == 1.5
    assert d.priority == "high"
    assert d.should_draft is True


def test_charter_newsletter_is_fyi_no_draft():
    d = resolve("charter_newsletter", 0.9)
    assert d.owner_key == "danielle"
    assert d.fyi is True
    assert d.should_draft is False


def test_scheduling_missing_last_name_defaults_and_flags():
    d = resolve("scheduling", 0.9, last_name=None)
    assert d.owner_key == "janelle"
    assert any("needs review" in n for n in d.notes)
