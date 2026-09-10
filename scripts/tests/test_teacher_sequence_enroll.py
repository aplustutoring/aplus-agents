"""Teacher sequence enroller eligibility tests.

The recent-touch gate exists because on 2026-09-10 Ashley Pontell (iLEAD) got
Danielle's sequence email at 11:58 AM and Paola's PO request at 12:14 PM.
Importing the module must not hit the network (it loads env and defines
functions only)."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import teacher_sequence_enroll as E  # noqa: E402

NOW = datetime.now(timezone.utc)
CUTOFF_MS = int((NOW - timedelta(days=7)).timestamp() * 1000)


def base(**overrides):
    p = {
        "email": "teacher@school.org",
        "firstname": "Ashley",
        "hs_email_optout": "false",
        "hs_email_bounce": "0",
        "generic_inbox": "false",
        "campaign_replied": "false",
        "hs_sequences_is_enrolled": "false",
    }
    p.update(overrides)
    return p


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def test_base_contact_is_eligible():
    assert E.ineligible(base(), {}) is None


def test_touched_yesterday_is_skipped():
    p = base(notes_last_contacted=iso(NOW - timedelta(days=1)))
    assert E.ineligible(p, {}, CUTOFF_MS, 7) == "contacted by a seat in the last 7 days"


def test_touched_30_days_ago_is_eligible():
    p = base(notes_last_contacted=iso(NOW - timedelta(days=30)))
    assert E.ineligible(p, {}, CUTOFF_MS, 7) is None


def test_never_contacted_is_eligible():
    assert E.ineligible(base(), {}, CUTOFF_MS, 7) is None


def test_feature_off_ignores_recent_touch():
    p = base(notes_last_contacted=iso(NOW - timedelta(days=1)))
    assert E.ineligible(p, {}, None, 0) is None


def test_epoch_ms_string_is_accepted():
    ms = str(int((NOW - timedelta(days=1)).timestamp() * 1000))
    p = base(notes_last_contacted=ms)
    assert E.ineligible(p, {}, CUTOFF_MS, 7) == "contacted by a seat in the last 7 days"


def test_ts_ms_rejects_empty_and_garbage():
    assert E._ts_ms("") is None
    assert E._ts_ms(None) is None
    assert E._ts_ms("garbage") is None


def test_ts_ms_parses_hubspot_iso():
    # Ashley Pontell's real value on 2026-09-10 (Paola's 12:14 PM PT email).
    expected = int(datetime(2026, 9, 10, 19, 14, 27, 240000, tzinfo=timezone.utc).timestamp() * 1000)
    assert E._ts_ms("2026-09-10T19:14:27.240Z") == expected


def test_last_contacted_is_requested_from_hubspot():
    assert "notes_last_contacted" in E.PROPS


def test_config_declares_recent_touch_days():
    cfg = yaml.safe_load((Path(__file__).resolve().parents[2] / "ops" / "messenger" / "teacher-sequences.yml").read_text())
    assert isinstance(cfg["recent_touch_days"], int)
    assert cfg["recent_touch_days"] >= 1
