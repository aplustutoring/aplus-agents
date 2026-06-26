"""Refresh mode flag (decision #14).

When enabled, lens 0 redundancy checks are skipped so Danielle can intentionally
re-cover old topics. Triggered via env var (set by workflow_dispatch input).
"""

from __future__ import annotations

import os

ENV_VAR = "APLUS_REFRESH_MODE"


def is_refresh_mode() -> bool:
    """True iff APLUS_REFRESH_MODE is set to a truthy string."""
    val = os.environ.get(ENV_VAR, "").strip().lower()
    return val in ("1", "true", "yes", "on", "refresh")


if __name__ == "__main__":
    # Quick smoke test
    os.environ[ENV_VAR] = ""
    assert is_refresh_mode() is False
    for truthy in ("1", "true", "TRUE", "yes", "on", "refresh"):
        os.environ[ENV_VAR] = truthy
        assert is_refresh_mode() is True, f"failed for {truthy!r}"
    for falsy in ("0", "false", "no", "off", "", "maybe"):
        os.environ[ENV_VAR] = falsy
        assert is_refresh_mode() is False, f"failed for {falsy!r}"
    print("OK")
