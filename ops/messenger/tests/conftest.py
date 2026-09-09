import os
import sys

# Tests never write to live systems.
os.environ["DRY_RUN"] = "true"

# Import one_to_few.py / messenger.py from the parent directory (not a package).
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_live_http(monkeypatch):
    def blocked(*a, **k):
        raise AssertionError("live HTTP in a unit test; mock the client function instead")
    for name in ("get", "post", "patch", "put", "delete", "request"):
        monkeypatch.setattr(f"requests.{name}", blocked)
