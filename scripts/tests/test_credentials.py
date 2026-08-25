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


def test_text_claim_is_cleared_for_use():
    """Roman 2026-08-25 cleared the TEXT claim: agents may state it."""
    C.reload()
    assert C.is_public_ready(CID) is True


def test_badge_image_cleared_but_files_not_in_repo_yet():
    """Guidelines received 2026-08-25, so the image is permitted — but the
    files still live in NSSA's Drive folder. A consumer must check asset_path,
    not just logo_ready, or it will try to render a path of None."""
    C.reload()
    c = C.get(CID)
    assert c["logo_ready"] is True
    assert c["usage_guidelines_received"] is True
    assert c["asset_path"] is None, "update this test when the files land in the repo"


def test_usage_rules_encode_the_design_not_effectiveness_limit():
    """The single most consequential term NSSA imposes."""
    C.reload()
    rules = C.get(CID)["usage_rules"]
    assert "DESIGN" in rules["denotes"]
    assert "effectiveness" in rules["does_not_denote"]
    assert rules["image"]["alteration_permitted"] is False
    assert rules["style"]["capitalize_badge_word"] is True


def test_fact_check_skill_carries_the_effectiveness_rule():
    """A rule only in the yaml does not reach the agent that writes copy."""
    skill = (Path(__file__).resolve().parents[2]
             / "marketing" / "skills" / "aplus-fact-check" / "SKILL.md").read_text()
    assert "not quality of implementation or effectiveness" in skill.lower() or \
           "design is not effectiveness" in skill.lower()
    assert "Stanford-validated results" in skill


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


def test_no_duplicated_claim_string_in_repo():
    """The CLAIM STRING (name + term window) must exist in exactly one place.

    Naming the credential in guidance is fine and necessary — a skill cannot
    teach a badge it may not name. What must never be duplicated is the full
    claim string, because that is what carries the term window and therefore
    what goes stale when the badge is renewed."""
    root = Path(__file__).resolve().parents[2]
    C.reload()
    CLAIM = C.get(CID)["claim_string"]
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
        if CLAIM.lower() in text.lower():
            rel = str(p.relative_to(root))
            if rel not in allowed:
                offenders.append(rel)
    assert not offenders, f"hardcoded badge claim found in: {offenders}"
