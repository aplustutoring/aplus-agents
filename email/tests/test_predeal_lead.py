"""The pre-deal-lead override, and the Teachworks notice it used to swallow.

Sam Sterling's 9/20 cancellation notice routed to charter sales instead of
Yolanda (Paola, 2026-09-21): the override asked the NO-REPLY sender whether it
was an active family, and a no-reply address never is.
"""
from src.main import _predeal_lead
from src.router import is_notification_sender, resolve

LEAD = {"properties": {"lifecyclestage": "lead"}, "associated_deals": 0}
NO_TW = {"teachworks_match": False}


def test_teachworks_notice_keeps_the_scheduler():
    # Sterling is M-Z → the M-Z scheduler, and the notice does not hand it away.
    d = resolve("cancellation", 0.95, last_name="Sterling")
    assert d.owner_key == "yolanda"
    assert _predeal_lead(d, LEAD, NO_TW, notification=True) is False


def test_real_pre_deal_lead_still_goes_to_charter_sales():
    # The Deanna Smith case (Roman 2026-07-20) — a family writing in with no
    # deal and no Teachworks account still belongs to charter sales.
    d = resolve("scheduling", 0.9, last_name="Smith")
    assert _predeal_lead(d, LEAD, NO_TW, notification=False) is True


def test_active_family_is_not_a_pre_deal_lead():
    d = resolve("cancellation", 0.95, last_name="Adams")
    assert _predeal_lead(d, {"properties": {"lifecyclestage": "customer"},
                             "associated_deals": 2}, NO_TW, notification=False) is False


def test_non_scheduler_routing_is_untouched():
    d = resolve("new_po", 0.9)
    assert _predeal_lead(d, LEAD, NO_TW, notification=False) is False


def test_notification_sender_matches_teachworks_only():
    assert is_notification_sender("notifications@teachworks.com") is True
    assert is_notification_sender("NoReply@Teachworks.com") is True
    assert is_notification_sender("mom@gmail.com") is False
    assert is_notification_sender("") is False
    assert is_notification_sender(None) is False
    # a look-alike domain is not ours
    assert is_notification_sender("spam@notteachworks.com") is False
