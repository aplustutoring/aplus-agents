import os
import sys

# Tests must never write to live systems.
os.environ["DRY_RUN"] = "true"

# Repo root on the path so `agents.cohort_intake` and `email.src` import.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_live_http(monkeypatch):
    def blocked(*a, **k):
        raise AssertionError("live HTTP in a unit test — mock the client function instead")
    for name in ("get", "post", "patch", "put", "delete", "request"):
        monkeypatch.setattr(f"requests.{name}", blocked)
