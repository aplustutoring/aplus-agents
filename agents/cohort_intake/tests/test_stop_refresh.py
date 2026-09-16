"""Stop window (fails closed) and the refresh pass (rails back into the sheet,
owner DM once on a skipped text)."""
from agents.cohort_intake import refresh as RF, stop_window as SW


# ─── stop window ─────────────────────────────────────────────────────────────

def test_said_stop_matches_plain_words_only():
    assert SW.said_stop([{"text": "stop", "user": "U1"}]) == "U1"
    assert SW.said_stop([{"text": "STOP please", "user": "U2"}]) == "U2"
    assert SW.said_stop([{"text": "looks good, go", "user": "U3"}]) is None
    assert SW.said_stop([{"text": "unstoppable", "user": "U4"}]) is None


def test_hold_zero_minutes_posts_and_proceeds(monkeypatch):
    posts = []
    monkeypatch.setattr(SW, "DRY_RUN", False)
    monkeypatch.setattr(SW.slack_client, "post_message", lambda ch, t: posts.append(t) or {"ok": True, "ts": "1"})
    monkeypatch.setattr(SW, "_mentions", lambda: "<@UR> <@UD>")
    assert SW.hold("plan", 0) == (True, "no wait requested")
    assert "Executing now" in posts[0] and "<@UR>" in posts[0]


def test_hold_stops_when_someone_replies_stop(monkeypatch):
    posts = []
    monkeypatch.setattr(SW, "DRY_RUN", False)
    monkeypatch.setattr(SW.slack_client, "post_message",
                        lambda ch, t: posts.append(t) or {"ok": True, "ts": "1", "channel": "C"})
    monkeypatch.setattr(SW, "_mentions", lambda: "")
    monkeypatch.setattr(SW, "_replies", lambda ch, ts: [{"text": "stop", "user": "UD"}])
    monkeypatch.setattr(SW.time, "sleep", lambda s: None)
    ok, why = SW.hold("plan", 1, poll_seconds=1)
    assert ok is False and why == "stopped by UD"
    assert any("Stopped by <@UD>" in p for p in posts)


def test_hold_fails_closed_when_replies_cannot_be_read(monkeypatch):
    monkeypatch.setattr(SW, "DRY_RUN", False)
    monkeypatch.setattr(SW.slack_client, "post_message", lambda ch, t: {"ok": True, "ts": "1", "channel": "C"})
    monkeypatch.setattr(SW, "_mentions", lambda: "")
    monkeypatch.setattr(SW, "_replies", lambda ch, ts: None)
    monkeypatch.setattr(SW.time, "sleep", lambda s: None)
    ok, why = SW.hold("plan", 1, poll_seconds=1)
    assert ok is False and "not proceeding blind" in why


def test_hold_proceeds_after_a_quiet_window(monkeypatch):
    posts = []
    monkeypatch.setattr(SW, "DRY_RUN", False)
    monkeypatch.setattr(SW.slack_client, "post_message",
                        lambda ch, t: posts.append(t) or {"ok": True, "ts": "1", "channel": "C"})
    monkeypatch.setattr(SW, "_mentions", lambda: "")
    monkeypatch.setattr(SW, "_replies", lambda ch, ts: [{"text": "looks right", "user": "UR"}])
    clock = {"t": 0.0}
    monkeypatch.setattr(SW.time, "time", lambda: clock["t"])
    monkeypatch.setattr(SW.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    ok, why = SW.hold("plan", 0.05, poll_seconds=1)
    assert ok is True and why == "window elapsed"
    assert any("No stop in the window" in p for p in posts)


# ─── refresh ─────────────────────────────────────────────────────────────────

class FakeSheet:
    def __init__(self):
        self.writes = []

    def write_outputs(self, headers, row, values):
        self.writes.append((row, values))


def _wire(monkeypatch, records):
    dms, appended = [], []
    monkeypatch.setattr(RF.audit, "_iter_records", lambda: iter(records))
    monkeypatch.setattr(RF.ST, "append", lambda r: appended.append(r))
    monkeypatch.setattr(RF.ST, "already_processed",
                        lambda k: any(r.get("message_id") == k for r in appended))
    monkeypatch.setattr(RF.slack_client, "dm", lambda u, t: dms.append((u, t)))
    monkeypatch.setattr(RF.hs, "_get", lambda p, params=None: {"properties": {"hubspot_owner_id": "80047202",
                                                                              "dealname": "Reyna - Diego"}})
    monkeypatch.setattr(RF, "email_cfg", lambda: {"staff": {"janelle": {"hubspot_owner_id": "80047202",
                                                                         "slack_user_id": "UJ"}},
                                                  "hubspot": {"portal_id": "6312752"}})
    return dms, appended


def test_refresh_writes_teachworks_id_text_and_welcome(monkeypatch):
    dms, _ = _wire(monkeypatch, [
        {"message_id": "deal:D1", "source": "deal_sync", "deal_id": "D1", "tw_customer_id": 4321},
        {"message_id": "sms-sent:D1", "source": "sms", "action_taken": "sms_sent", "deal_id": "D1",
         "timestamp": "2026-09-15T17:05:00Z", "welcome_email_to": "reyna.family@gmail.com"}])
    sheet = FakeSheet()
    RF.refresh(sheet, ["x"], {9: "D1"}, dry_run=False)
    assert sheet.writes == [(9, {"Teachworks ID": "4321", "Text Sent": "2026-09-15 17:05",
                                 "Welcome Sent": "reyna.family@gmail.com"})]
    assert dms == []


def test_refresh_dms_the_deal_owner_once_when_the_text_was_skipped(monkeypatch):
    dms, appended = _wire(monkeypatch, [
        {"message_id": "sms-skip:D1", "source": "sms", "action_taken": "sms_skipped_unverified",
         "deal_id": "D1", "reason": "no family phone"}])
    sheet = FakeSheet()
    RF.refresh(sheet, ["x"], {9: "D1"}, dry_run=False)
    assert dms and dms[0][0] == "UJ" and "no family phone" in dms[0][1]
    assert appended[0]["message_id"] == "hsa-sms-skip-dm:D1"
    RF.refresh(sheet, ["x"], {9: "D1"}, dry_run=False)             # second pass: no second DM
    assert len(dms) == 1
