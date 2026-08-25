"""Credential gate tests (#AP044). The gate must fail CLOSED."""
import datetime as dt
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import credentials as C  # noqa: E402

CID = "nssa_program_design_badge"


@pytest.fixture
def creds(tmp_path, monkeypatch):
    """A writable copy of the real file, so tests never mutate the repo."""
    real = yaml.safe_load((Path(__file__).resolve().parents[2] / "knowledge" / "credentials.yml").read_text())

    def write(**overrides):
        data = {"credentials": {CID: {**real["credentials"][CID], **overrides}}}
        p = tmp_path / "credentials.yml"
        p.write_text(yaml.safe_dump(data))
        monkeypatch.setattr(C, "CREDENTIALS_PATH", p)
        C.reload()
        return p
    yield write
    C.reload()


def test_real_file_is_gated_shut():
    """The committed file must not claim publicly until Roman confirms terms."""
    C.reload()
    assert C.is_public_ready(CID) is False


def test_real_claim_string_carries_the_term_window():
    C.reload()
    s = C.get(CID)["claim_string"]
    assert "2026-2029" in s, "a claim without its date range is a defect"
    assert s == "NSSA Tutoring Program Design Badge, 2026-2029"


def test_claim_raises_while_not_public(creds):
    creds(public_ready=False)
    with pytest.raises(C.CredentialNotPublic):
        C.claim(CID, surface="website")


def test_claim_works_once_public(creds):
    creds(public_ready=True)
    assert C.claim(CID, surface="website") == "NSSA Tutoring Program Design Badge, 2026-2029"


def test_unapproved_surface_raises(creds):
    creds(public_ready=True)
    with pytest.raises(C.CredentialSurfaceNotApproved):
        C.claim(CID, surface="tiktok")


def test_prohibited_surface_raises_even_when_public(creds):
    creds(public_ready=True)
    with pytest.raises(C.CredentialSurfaceNotApproved):
        C.claim(CID, surface="sms")


def test_expired_credential_raises(creds):
    creds(public_ready=True)
    with pytest.raises(C.CredentialExpired):
        C.claim(CID, surface="website", today=dt.date(2029, 9, 1))


def test_not_expired_the_day_before(creds):
    creds(public_ready=True)
    assert C.claim(CID, surface="website", today=dt.date(2029, 8, 31))


def test_resolve_substitutes_when_permitted(creds):
    creds(public_ready=True)
    out = C.resolve("We hold the {{credentials.nssa_program_design_badge.claim_string}}.",
                    surface="case_studies")
    assert out == "We hold the NSSA Tutoring Program Design Badge, 2026-2029."


def test_resolve_raises_by_default_when_gated(creds):
    creds(public_ready=False)
    with pytest.raises(C.CredentialNotPublic):
        C.resolve("{{credentials.nssa_program_design_badge.claim_string}}", surface="website")


def test_resolve_strip_leaves_no_trace(creds):
    """strip mode must remove the whole token, never emit a half-claim."""
    creds(public_ready=False)
    out = C.resolve("A[{{credentials.nssa_program_design_badge.claim_string}}]B",
                    surface="website", missing="strip")
    assert out == "A[]B"
    assert "NSSA" not in out


def test_null_field_never_renders_none(creds):
    """asset_path is null today. It must not render the string 'None'."""
    creds(public_ready=True)
    with pytest.raises(C.CredentialNotFound):
        C.resolve("{{credentials.nssa_program_design_badge.asset_path}}", surface="website")
    out = C.resolve("{{credentials.nssa_program_design_badge.asset_path}}",
                    surface="website", missing="strip")
    assert out == "" and "None" not in out


def test_unknown_credential_raises():
    C.reload()
    with pytest.raises(C.CredentialNotFound):
        C.claim("nonexistent_badge")


def test_days_until_expiry():
    C.reload()
    assert C.days_until_expiry(CID, today=dt.date(2029, 8, 1)) == 30
    assert C.days_until_expiry(CID, today=dt.date(2029, 9, 30)) == -30


def test_no_hardcoded_claim_strings_in_repo():
    """DoD: grep -ri 'program design badge' hits only the credentials file+docs."""
    root = Path(__file__).resolve().parents[2]
    allowed = {"knowledge/credentials.yml", "docs/CHANGELOG.md",
               "scripts/tests/test_credentials.py", "scripts/credentials.py",
               "scripts/credential_expiry_check.py", "registry.yml",
               ".github/workflows/credential-expiry.yml"}
    offenders = []
    for p in root.rglob("*"):
        if not p.is_file() or ".git/" in str(p) or "/archive/" in str(p):
            continue
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".mp4", ".pdf", ".woff", ".woff2"}:
            continue
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        if "program design badge" in text.lower():
            rel = str(p.relative_to(root))
            if rel not in allowed:
                offenders.append(rel)
    assert not offenders, f"hardcoded badge claim found in: {offenders}"
