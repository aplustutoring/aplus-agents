"""PO mail outside charter@: the shared predicate, the mirror into charter@,
the triage handoff (never junk), and the PO agent closing the handoff.

Background (2026-09-03): Heartwood's OPS account emails POs to admin@; the admin
triage junk-archived 14 PO documents in Aug/Sep 2026 and nobody was told.
"""
import pytest

from src import main, po_inbox as po, po_sources as ps


# ── predicate ────────────────────────────────────────────────────────────────
def test_ops_sender_is_po_shaped_even_with_no_subject_or_attachment():
    why = ps.is_po_shaped(["vendorinfo@heartwoodcharterschool.org", "noreply@ops-online.com"], "", [])
    assert "ops-online.com" in why


def test_purchase_order_subject_is_po_shaped():
    subj = "Heartwood - A+ Tutoring Inc. (APlus Tutoring Inc.), Danielle Brodetsky - Purchase Order #6814193240 - Phoenix"
    assert ps.is_po_shaped(["vendorinfo@heartwoodcharterschool.org"], subj, [])


def test_ops_new_pos_notice_is_po_shaped():
    assert ps.is_po_shaped([], "Heartwood Charter School - new POs - 09/03/2026", [])


def test_po_pdf_attachment_is_po_shaped():
    assert "PO6814193243.pdf" in ps.is_po_shaped(["someone@school.org"], "Fwd:", ["PO6814193243.pdf"])
    assert ps.is_po_shaped([], "form", ["OA2914206871.pdf"])   # OPS order agreements too


@pytest.mark.parametrize("addrs,subj,names", [
    (["receipts@stripe.com"], "Your receipt from A+ Tutoring", []),
    (["parent@gmail.com"], "PO Box change of address", []),
    (["tutor@gmail.com"], "W-9", ["w9_signed.pdf"]),
    (["billing@school.org"], "Invoice 54591 paid", ["remittance.pdf"]),
])
def test_ordinary_mail_is_not_po_shaped(addrs, subj, names):
    assert ps.is_po_shaped(addrs, subj, names) == ""


# ── mirror ───────────────────────────────────────────────────────────────────
@pytest.fixture
def mirror_env(monkeypatch):
    rec = {"inserted": [], "audit": [], "labels": [], "dms": []}
    msgs = {
        "po1": {"id": "po1", "sender": "Heartwood <vendorinfo@heartwoodcharterschool.org>",
                "sender_addrs": ["vendorinfo@heartwoodcharterschool.org", "noreply@ops-online.com"],
                "subject": "Heartwood - Purchase Order #6814193240 - Phoenix",
                "attachment_names": ["PO6814193240.pdf"]},
        "w9": {"id": "w9", "sender": "tutor@gmail.com", "sender_addrs": ["tutor@gmail.com"],
               "subject": "my W-9", "attachment_names": ["w9.pdf"]},
        "old": {"id": "old", "sender": "x", "sender_addrs": ["noreply@ops-online.com"],
                "subject": "Heartwood - new POs - 08/26/2026", "attachment_names": []},
        "trashed": {"id": "trashed", "sender": "x", "sender_addrs": ["noreply@ops-online.com"],
                    "subject": "Heartwood - new POs - 09/01/2026", "attachment_names": [],
                    "label_ids": ["TRASH"]},
        "spammed": {"id": "spammed", "sender": "Heartwood <vendorinfo@heartwoodcharterschool.org>",
                    "sender_addrs": ["vendorinfo@heartwoodcharterschool.org"],
                    "subject": "Heartwood - Purchase Order #6814193241 - Phoenix",
                    "attachment_names": ["PO6814193241.pdf"], "label_ids": ["SPAM"]},
    }
    rec["queries"] = []
    monkeypatch.setattr(ps.gm, "list_messages",
                        lambda q, max_results=50, mailbox=None, include_spam_trash=False:
                        rec["queries"].append((q, include_spam_trash)) or [{"id": k} for k in msgs])
    monkeypatch.setattr(ps.gm, "get_message", lambda i, mailbox=None: msgs[i])
    monkeypatch.setattr(ps.gm, "get_raw", lambda i, mailbox=None: f"RAW-{i}")
    monkeypatch.setattr(ps.gm, "insert_raw",
                        lambda raw, labels=None: rec["inserted"].append(raw) or {"id": f"copy-{raw}"})
    monkeypatch.setattr(ps.gm, "apply_labels",
                        lambda i, names, mailbox=None: rec["labels"].append((mailbox, i, names)))
    monkeypatch.setattr(ps.audit, "append", lambda r: rec["audit"].append(r))
    monkeypatch.setattr(ps.audit, "_iter_records", lambda: [])
    # "old" was mirrored on an earlier run
    monkeypatch.setattr(ps.audit, "processed_message_ids",
                        lambda: {"mirrored:admin@wetutorathome.com:old"})
    monkeypatch.setattr(ps.slack_client, "dm", lambda uid, text: rec["dms"].append(text))
    return rec


def test_mirror_copies_only_po_shaped_mail_and_dedups(mirror_env):
    state = {"last_epoch": 1}
    n = ps.mirror_sources(state)
    assert n == 2
    # not the W-9, not the already-mirrored, not the trashed one; the Spam one IS mirrored
    assert mirror_env["inserted"] == ["RAW-po1", "RAW-spammed"]
    assert mirror_env["queries"][0][1] is True                 # listing reaches into Spam
    a = mirror_env["audit"][0]
    assert a["action_taken"] == "po_mirrored"
    assert a["message_id"] == "mirrored:admin@wetutorathome.com:po1"
    assert a["mirror_msg_id"] == "copy-RAW-po1"
    assert a["attachments"] == ["PO6814193240.pdf"]
    assert "was in Spam" in mirror_env["audit"][1]["why"]
    # source copy labelled in admin@, per-source cursor advanced
    assert mirror_env["labels"][0][0] == "admin@wetutorathome.com"
    assert state["sources"]["admin@wetutorathome.com"] > 0


def test_mirror_skips_po_already_processed_from_charter(mirror_env, monkeypatch):
    # Kath found PO 6814193240 in the OPS portal and forwarded it to charter@
    # before the mirror ran: no second copy, no DUPLICATE alert.
    monkeypatch.setattr(ps.audit, "_iter_records", lambda: [
        {"source": "po_inbox", "action_taken": "po_processed", "po_number": "6814193240"}])
    n = ps.mirror_sources({})
    assert n == 1                                            # only the Spam one (…241) is mirrored
    assert mirror_env["inserted"] == ["RAW-spammed"]
    skipped = [a for a in mirror_env["audit"] if a["action_taken"] == "po_mirror_skipped"]
    assert len(skipped) == 1 and skipped[0]["po_numbers"] == ["6814193240"]


def test_po_numbers_from_subject_and_attachments():
    assert ps.po_numbers("Fwd: Heartwood - Purchase Order #6814193240 - Phoenix", ["PO6814193241.pdf"]) \
        == {"6814193240", "6814193241"}
    assert ps.po_numbers("Heartwood Charter School - new POs - 09/03/2026", []) == set()


def test_mirror_failure_alerts_and_does_not_raise(mirror_env, monkeypatch):
    def boom(q, max_results=50, mailbox=None, include_spam_trash=False):
        raise RuntimeError("unauthorized_client")
    monkeypatch.setattr(ps.gm, "list_messages", boom)
    state = {}
    assert ps.mirror_sources(state) == 0
    assert mirror_env["dms"] and "FAILED" in mirror_env["dms"][0]
    assert "sources" in state and not state["sources"]       # cursor NOT advanced on failure


def test_rescue_moves_po_shaped_spam_to_inbox(monkeypatch):
    rec = {"moved": [], "audit": []}
    msgs = {
        "k1": {"id": "k1", "sender": "OPS <noreply@ops-online.com>", "sender_addrs": ["noreply@ops-online.com"],
               "subject": "Heartwood - Purchase Order #6814193240 - Phoenix Nourn Bernard",
               "attachment_names": ["PO6814193240.pdf"]},
        "seo": {"id": "seo", "sender": "x@spam.io", "sender_addrs": ["x@spam.io"],
                "subject": "rank #1 on Google", "attachment_names": ["deck.pdf"]},
    }
    monkeypatch.setattr(ps.gm, "list_messages",
                        lambda q, max_results=50, mailbox=None, include_spam_trash=False:
                        [{"id": k} for k in msgs])
    monkeypatch.setattr(ps.gm, "get_message", lambda i, mailbox=None: msgs[i])
    monkeypatch.setattr(ps.gm, "move_to_inbox", lambda i, labels=None, mailbox=None: rec["moved"].append(i))
    monkeypatch.setattr(ps.audit, "append", lambda r: rec["audit"].append(r))
    monkeypatch.setattr(ps.audit, "processed_message_ids", lambda: set())
    state = {}
    assert ps.rescue_spam(state) == ["k1"]
    assert rec["moved"] == ["k1"]
    assert rec["audit"][0]["action_taken"] == "po_spam_rescued"
    assert state["spam_cursor"] > 0


def test_run_processes_rescued_ids_even_when_behind_cursor(monkeypatch, tmp_path):
    processed = []
    monkeypatch.setattr(po.po_sources, "mirror_sources", lambda st: 0)
    monkeypatch.setattr(po.po_sources, "rescue_spam", lambda st: ["old-spam-id"])
    monkeypatch.setattr(po.gm, "list_messages", lambda q, **k: [{"id": "fresh"}])
    monkeypatch.setattr(po, "process_po_message", lambda i, force=False: processed.append(i) or {"ok": 1})
    for name in ("_sweep_parent_chases", "_sweep_pending_pos", "_sweep_chase_drafts",
                 "_sweep_chase_self_resolve"):
        monkeypatch.setattr(po, name, lambda: None)
    monkeypatch.setattr(po.draft_feedback, "sweep", lambda: None)
    monkeypatch.setattr(po, "__file__", str(tmp_path / "src" / "po_inbox.py"))
    (tmp_path / "src").mkdir()
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "po_cursor.json").write_text('{"last_epoch": 1700000000}')
    po.run()
    assert processed == ["old-spam-id", "fresh"]


def test_run_mirrors_before_polling_charter(monkeypatch, tmp_path):
    order = []
    monkeypatch.setattr(po.po_sources, "mirror_sources", lambda st: order.append("mirror") or 0)
    monkeypatch.setattr(po.po_sources, "rescue_spam", lambda st: order.append("rescue") or [])
    monkeypatch.setattr(po.gm, "list_messages", lambda q, **k: order.append("poll") or [])
    for name in ("_sweep_parent_chases", "_sweep_pending_pos", "_sweep_chase_drafts",
                 "_sweep_chase_self_resolve"):
        monkeypatch.setattr(po, name, lambda: None)
    monkeypatch.setattr(po.draft_feedback, "sweep", lambda: None)
    cur = tmp_path / "po_cursor.json"
    cur.write_text('{"last_epoch": 1700000000, "sources": {"admin@wetutorathome.com": 1700000000}}')
    monkeypatch.setattr(po, "__file__", str(tmp_path / "src" / "po_inbox.py"))
    (tmp_path / "src").mkdir()
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "po_cursor.json").write_text(cur.read_text())
    po.run()
    assert order == ["mirror", "rescue", "poll"]


# ── triage handoff ───────────────────────────────────────────────────────────
@pytest.fixture
def triage(monkeypatch):
    rec = {"tickets": [], "archived": [], "audit": [], "dms": [], "links": []}
    monkeypatch.setattr(main.audit, "already_processed", lambda mid: False)
    monkeypatch.setattr(main.audit, "append", lambda r: rec["audit"].append(r))
    monkeypatch.setattr(main.audit, "_iter_records", lambda: [])
    monkeypatch.setattr(main.hs, "create_ticket",
                        lambda *a, **k: (rec["tickets"].append((a, k)) or {"id": "T9"}))
    monkeypatch.setattr(main.hs, "link_thread_to_ticket", lambda th, tk: rec["links"].append((th, tk)))
    monkeypatch.setattr(main.hs, "archive_thread", lambda tid: rec["archived"].append(tid))
    monkeypatch.setattr(main.hs, "ticket_url", lambda tid: f"http://t/{tid}")
    monkeypatch.setattr(main.slack_client, "dm", lambda uid, text: rec["dms"].append((uid, text)))

    def never(*a, **k):
        raise AssertionError("PO documents must not reach the classifier / CRM lookups")
    monkeypatch.setattr(main, "classify", never)
    monkeypatch.setattr(main.hs, "find_contact_by_email", never)
    monkeypatch.setattr(main.hs, "create_contact", never)
    return rec


def _ops_po_message():
    return {"id": "m-po", "text": "", "subject":
            "Heartwood - A+ Tutoring Inc. (APlus Tutoring Inc.), Danielle Brodetsky - Purchase Order #6814193240 - Phoenix",
            "senders": [
                {"senderField": "FROM", "deliveryIdentifier": {"type": "HS_EMAIL_ADDRESS",
                                                               "value": "vendorinfo@heartwoodcharterschool.org"}},
                {"senderField": "ORIGINAL_FROM", "deliveryIdentifier": {"type": "HS_EMAIL_ADDRESS",
                                                                        "value": "noreply@ops-online.com"}}],
            "attachments": [{"type": "FILE", "name": "PO6814193240.pdf"}]}


def test_po_document_at_admin_gets_handoff_ticket_not_junk(triage):
    rec = main.process_message("thread-po", _ops_po_message())
    assert rec["action_taken"] == "po_handoff_ticket"
    assert rec["category"] == "po_handoff"
    assert not triage["archived"]
    assert len(triage["tickets"]) == 1
    args, kw = triage["tickets"][0]
    assert args[0].startswith("PO document outside charter inbox:")
    assert args[1] == "513215050"                 # charter_admin (Kath) owns it
    assert args[4] is None                        # no contact created for a noreply sender
    assert kw["priority"] == "HIGH" and kw["category"] == "new_deal_po"
    assert triage["links"] == [("thread-po", "T9")]
    assert triage["dms"] and "outside the charter inbox" in triage["dms"][0][1]
    assert rec["sla_due"] and rec["ticket_id"] == "T9"


def test_already_mirrored_document_is_archived_without_ticket(triage, monkeypatch):
    monkeypatch.setattr(main.audit, "_iter_records", lambda: [
        {"action_taken": "po_mirrored", "subject": "Fwd: " + _ops_po_message()["subject"],
         "attachments": ["PO6814193240.pdf"], "mirror_msg_id": "copy1"}])
    rec = main.process_message("thread-po", _ops_po_message())
    assert rec["action_taken"] == "po_handoff_archived"
    assert triage["archived"] == ["thread-po"]
    assert not triage["tickets"] and rec["mirror_msg_id"] == "copy1"


def test_ops_notice_without_attachment_is_handed_off(triage):
    msg = {"id": "m-n", "text": "One or more purchase orders have recently been processed...",
           "subject": "Heartwood Charter School - new POs - 09/03/2026",
           "senders": [{"deliveryIdentifier": {"type": "HS_EMAIL_ADDRESS", "value": "noreply@ops-online.com"}}],
           "attachments": []}
    rec = main.process_message("thread-n", msg)
    assert rec["action_taken"] == "po_handoff_ticket"


# ── PO agent closes the handoff ──────────────────────────────────────────────
def test_close_handoffs_closes_open_ticket_for_same_document(monkeypatch):
    calls = {"stage": [], "notes": [], "audit": []}
    monkeypatch.setattr(ps.audit, "_iter_records", lambda: [
        {"action_taken": "po_handoff_ticket", "ticket_id": "H1",
         "subject": "Heartwood - Purchase Order #6814193240 - Phoenix", "attachments": ["PO6814193240.pdf"]},
        {"action_taken": "po_handoff_ticket", "ticket_id": "H2",
         "subject": "Heartwood - Purchase Order #6814193241 - Phoenix", "attachments": ["PO6814193241.pdf"]},
        {"action_taken": "po_handoff_ticket", "ticket_id": "H3",
         "subject": "Heartwood - Purchase Order #6814193242 - Phoenix", "attachments": ["PO6814193242.pdf"]},
        {"action_taken": "po_handoff_closed", "ticket_id": "H3"},
    ])
    monkeypatch.setattr(ps.audit, "append", lambda r: calls["audit"].append(r))
    monkeypatch.setattr(ps.hs, "update_ticket_stage", lambda t, s: calls["stage"].append((t, s)))
    monkeypatch.setattr(ps.hs, "add_ticket_note", lambda t, n: calls["notes"].append((t, n)))
    monkeypatch.setattr(ps.hs, "ticket_url", lambda t: f"http://t/{t}")
    # the charter@ copy carries a Fwd: prefix and the same PDF name
    closed = ps.close_handoffs("Fwd: Heartwood - Purchase Order #6814193240 - Phoenix",
                               ["PO6814193240.pdf"], "P77", "💼 deal 123")
    assert closed == ["H1"]
    assert calls["stage"] == [("H1", "4")]           # Done
    assert "http://t/P77" in calls["notes"][0][1]
    assert calls["audit"][0]["action_taken"] == "po_handoff_closed"
