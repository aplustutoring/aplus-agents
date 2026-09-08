import os
import sys

# Tests must NEVER write to live systems: force DRY_RUN before src.config is imported
# (short-circuits every HubSpot/Slack/Gmail write). Tests that need write-path logic
# monkeypatch the client functions or module-level DRY_RUN explicitly.
os.environ["DRY_RUN"] = "true"

sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_live_http(monkeypatch):
    """DRY_RUN only short-circuits WRITES. Reads (searches, gets) still went out
    over the wire, and `load_dotenv()` at import means a local run carries a real
    HubSpot token — so unit tests were quietly hitting the live API, and CI was
    making calls that could only fail. Any test needing a response must mock the
    client function it calls.
    """
    def blocked(*a, **k):
        raise AssertionError(
            "live HTTP in a unit test — mock the client function instead")

    for name in ("get", "post", "patch", "put", "delete", "request"):
        monkeypatch.setattr(f"requests.{name}", blocked)
