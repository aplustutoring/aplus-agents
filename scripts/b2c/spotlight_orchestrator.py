#!/usr/bin/env python3
"""
A+ Tutoring B2C spotlight orchestrator.

Builds a case study bundle from a folder of raw source files.

Usage:
    python3 scripts/b2c/spotlight_orchestrator.py \
        --source /path/to/raw-folder \
        [--student-name "Gabriela"] \
        [--school "iLEAD"] \
        [--dry-run] \
        [--stop-after bundle]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_ROOT = REPO_ROOT / "aplus-content"
STATE_PATH = REPO_ROOT / "state" / "spotlight-runs.json"

# Load repo-root .env so the orchestrator picks up ANTHROPIC_API_KEY,
# HUBSPOT_PRIVATE_APP_TOKEN, OPENAI_API_KEY, GEMINI_API_KEY, and SLACK_BOT_TOKEN
# the same way every other script in scripts/ does.
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=REPO_ROOT / ".env")
except ImportError:
    pass

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None

try:
    import docx
except ImportError:  # pragma: no cover
    docx = None

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None

# OCR fallback configuration. Image-only PDFs (scanned lesson reports) yield
# no text from pypdf, so we rasterize each page with PyMuPDF and have Claude
# vision transcribe them. No poppler, no tesseract — pure Python + API.
OCR_MIN_TEXT_LEN = 120
OCR_RENDER_DPI = 200
OCR_VISION_MODEL = "claude-opus-4-7"
OCR_MAX_PAGES = 30

STAGE_ORDER = [
    "init",
    "read_sources",
    "hubspot",
    "bundle",
    "draft",
    "anonymization",
    "archive",
    "metadata",
    "grammar",
    "support",
    "graphics",
    "hashtags",
    "publish",
    "slack",
    "complete",
]

REQUIRED_SOURCE_PATTERNS = [
    r"^parent[-_ ]?call",
    r"^(lesson[-_ ]?notes|lesson[-_ ]?report|tutor[-_ ]?notes|tutor[-_ ]?report)",
    r"^paola[-_ ]?brief",
]


class OrchestratorError(Exception):
    pass


class MissingRequiredFiles(OrchestratorError):
    pass


class HubSpotSearchError(OrchestratorError):
    pass


class HubSpotNotFound(HubSpotSearchError):
    pass


class HubSpotAmbiguous(HubSpotSearchError):
    pass


class AnonymizationFailure(OrchestratorError):
    pass


class GrammarGateFailure(OrchestratorError):
    pass


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"runs": []}
    try:
        return json.loads(STATE_PATH.read_text())
    except json.JSONDecodeError:
        return {"runs": []}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def append_run(run: dict) -> None:
    state = load_state()
    state.setdefault("runs", []).append(run)
    save_state(state)


def update_run(run_id: str, updates: dict) -> None:
    # Take the updates as a dict (not **kwargs) so callers can hand us the
    # whole run object — including its own run_id key — without Python raising
    # a duplicate-keyword-argument error before the function body runs.
    state = load_state()
    changed = False
    for run in state.setdefault("runs", []):
        if run.get("run_id") == run_id:
            run.update({k: v for k, v in updates.items() if k != "run_id"})
            changed = True
            break
    if changed:
        save_state(state)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Orchestrate a B2C spotlight case study bundle.")
    parser.add_argument("--source", required=True, help="Raw source folder containing transcripts, lesson reports, and Paola briefs")
    parser.add_argument("--student-name", help="Student real first name (optional if HubSpot lookup can find it)")
    parser.add_argument("--school", help="School name used for slug and demographics")
    parser.add_argument("--dry-run", action="store_true", help="Run stages without HubSpot publish or Slack delivery")
    parser.add_argument("--stop-after", choices=STAGE_ORDER, default="bundle", help="Stop the pipeline after the named stage")
    parser.add_argument("--skip-hubspot", action="store_true", help="Skip HubSpot contact lookup and proceed with local input only")
    parser.add_argument("--verbose", action="store_true", help="Print extra diagnostic details")
    return parser.parse_args()


def is_matching_source_file(name: str) -> bool:
    lower = name.lower()
    for pattern in REQUIRED_SOURCE_PATTERNS:
        if re.match(pattern, lower):
            return True
    return False


def find_source_files(source_dir: Path) -> list[Path]:
    files = []
    for item in sorted(source_dir.iterdir()):
        if item.is_file() and not item.name.startswith("."):
            files.append(item)
    return files


def categorize_source_files(files: list[Path]) -> dict[str, list[Path]]:
    categories = {"parent_call": [], "lesson_report": [], "paola_brief": [], "others": []}
    for path in files:
        name = path.name.lower()
        if re.match(r"^parent[-_ ]?call", name):
            categories["parent_call"].append(path)
        elif re.match(r"^(lesson[-_ ]?notes|lesson[-_ ]?report|tutor[-_ ]?notes|tutor[-_ ]?report)", name):
            categories["lesson_report"].append(path)
        elif re.match(r"^paola[-_ ]?brief", name):
            categories["paola_brief"].append(path)
        else:
            categories["others"].append(path)
    return categories


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def extract_text_from_docx(path: Path) -> str:
    if docx is None:
        raise OrchestratorError("python-docx is required to read .docx files. Install it in requirements.txt.")
    document = docx.Document(path)
    paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def extract_text_from_pdf(path: Path) -> str:
    """Extract text from a PDF. Fall back to vision-OCR if the PDF is image-only.

    Fast path: pypdf's text extractor for text-bearing PDFs.
    Slow path: rasterize each page with PyMuPDF, transcribe with Claude vision.
    The decision is empirical — if the fast path returns less than
    OCR_MIN_TEXT_LEN characters or fewer than 3 newlines, the PDF is treated
    as image-only and routed through the OCR path.
    """
    if PdfReader is None:
        raise OrchestratorError("pypdf is required to read PDF files. Install it in requirements.txt.")
    reader = PdfReader(path)
    pages = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append(text)
    extracted = "\n\n".join(pages).strip()
    if len(extracted) >= OCR_MIN_TEXT_LEN and extracted.count("\n") >= 3:
        return extracted
    print(
        f"  pypdf yielded only {len(extracted)} chars from {path.name}; "
        f"routing through Claude-vision OCR.",
        file=sys.stderr,
    )
    return ocr_pdf(path)


def ocr_pdf(path: Path) -> str:
    """Rasterize each PDF page with PyMuPDF and transcribe with Claude vision.

    No poppler, no tesseract. PyMuPDF renders pages to PNG bytes in-process;
    the Anthropic SDK accepts base64-encoded image blocks directly. Each page
    is sent in a single user turn so the model produces clean per-page text;
    pages are joined with two newlines so the orchestrator's downstream stages
    see one continuous transcript.
    """
    if fitz is None:
        raise OrchestratorError(
            "PyMuPDF (`pymupdf`) is required for PDF OCR fallback. "
            "Install it from requirements.txt."
        )
    if anthropic is None:
        raise OrchestratorError(
            "anthropic SDK is required for Claude-vision OCR. "
            "Install it from requirements.txt."
        )
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise OrchestratorError(
            "ANTHROPIC_API_KEY is not set. Required for Claude-vision OCR."
        )

    import base64

    client = anthropic.Anthropic(api_key=api_key)
    doc = fitz.open(path)
    if doc.page_count == 0:
        doc.close()
        raise OrchestratorError(f"PDF has zero pages: {path.name}")
    if doc.page_count > OCR_MAX_PAGES:
        doc.close()
        raise OrchestratorError(
            f"PDF has {doc.page_count} pages, exceeds OCR_MAX_PAGES={OCR_MAX_PAGES}. "
            f"Split the source or raise the cap."
        )

    zoom = OCR_RENDER_DPI / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    pages_text: list[str] = []
    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        png_bytes = pix.tobytes("png")
        b64 = base64.standard_b64encode(png_bytes).decode("ascii")
        print(
            f"    page {page_index + 1}/{doc.page_count}: "
            f"rasterized {len(png_bytes):,} bytes, transcribing...",
            file=sys.stderr,
        )
        message = client.messages.create(
            model=OCR_VISION_MODEL,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Transcribe this page of a K-12 tutoring source "
                                "document (a parent-call transcript, lesson "
                                "report, or intake brief) to plain text. "
                                "Preserve paragraph breaks, headings, and "
                                "bullet structure. Preserve any numeric data "
                                "(RIT scores, percentiles, grade-level "
                                "benchmarks, dates) exactly as written. Do "
                                "not summarize. Do not add commentary. Output "
                                "only the transcribed text."
                            ),
                        },
                    ],
                }
            ],
        )
        page_text = "".join(
            block.text for block in message.content if getattr(block, "type", "") == "text"
        ).strip()
        if not page_text:
            print(
                f"    page {page_index + 1}: vision returned empty text",
                file=sys.stderr,
            )
        pages_text.append(page_text)
    doc.close()
    joined = "\n\n".join(pages_text).strip()
    if not joined:
        raise OrchestratorError(
            f"Claude vision returned empty text for every page of {path.name}."
        )
    return joined


SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return read_text_file(path)
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    if suffix == ".docx":
        return extract_text_from_docx(path)
    raise OrchestratorError(f"Unsupported source file type: {path.name}")


# ---------------------------------------------------------------------------
# Claude API helper
# ---------------------------------------------------------------------------

CLAUDE_MODEL = "claude-opus-4-7"


def _anthropic_client():
    if anthropic is None:
        raise OrchestratorError(
            "anthropic SDK is required. Install from requirements.txt."
        )
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise OrchestratorError("ANTHROPIC_API_KEY is not set.")
    return anthropic.Anthropic(api_key=api_key)


def claude_complete(
    system: str,
    user: str,
    *,
    max_tokens: int = 8000,
    model: str = CLAUDE_MODEL,
    temperature: float | None = None,
) -> str:
    """Single-turn Claude call. Returns the assistant's text response.

    `temperature` is opt-in: Opus 4.7 deprecated the parameter and returns
    400 if it is passed. Older models still accept it. Callers that need
    deterministic short classifier outputs can pass temperature=0 and we
    silently drop it on Opus 4.7.
    """
    client = _anthropic_client()
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if temperature is not None and "opus-4-7" not in model:
        kwargs["temperature"] = temperature
    message = client.messages.create(**kwargs)
    text = "".join(
        block.text for block in message.content if getattr(block, "type", "") == "text"
    )
    if not text.strip():
        raise OrchestratorError("Claude returned an empty response.")
    return text


# ---------------------------------------------------------------------------
# Pseudonym pool: cultural-category-keyed, deterministic SHA-256 indexing
# ---------------------------------------------------------------------------

# Categories are coarse on purpose: they exist to ensure the published
# pseudonym does not Anglicize a non-Anglo name. The pools are intentionally
# generic, common first names so the pseudonym reads as "a real kid" without
# pointing at a specific identifiable person. Pools are hand-curated; never
# expand via Claude generation (we want a fixed, auditable list).
PSEUDONYM_POOLS: dict[str, list[str]] = {
    "latino_hispanic": [
        "Diego", "Camila", "Mateo", "Sofia", "Lucia", "Gabriel",
        "Valeria", "Daniel", "Isabella", "Marco", "Adriana", "Javier",
    ],
    "african_american": [
        "Marcus", "Aaliyah", "Jayden", "Imani", "Malik", "Zaria",
        "Andre", "Maya", "Justice", "Nia", "Terrell", "Amara",
    ],
    "asian_east": [
        "Kai", "Aiko", "Jin", "Mei", "Ren", "Yuna",
        "Hiro", "Sora", "Daiki", "Lin", "Akira", "Hana",
    ],
    "asian_south": [
        "Arjun", "Priya", "Aarav", "Anika", "Rohan", "Diya",
        "Vikram", "Saanvi", "Kabir", "Ishaan", "Aanya", "Reyansh",
    ],
    "middle_eastern": [
        "Omar", "Layla", "Yusuf", "Amira", "Karim", "Zara",
        "Tariq", "Noor", "Hamza", "Sara", "Ali", "Yasmin",
    ],
    "white_american": [
        "Liam", "Emma", "Noah", "Olivia", "Ethan", "Ava",
        "Owen", "Charlotte", "Henry", "Sophia", "Caleb", "Hannah",
    ],
}

PSEUDONYM_CATEGORIES = list(PSEUDONYM_POOLS.keys())


def classify_cultural_background(real_first_name: str) -> str:
    """Ask Claude to classify a first name into one of PSEUDONYM_CATEGORIES.

    Returns the category key. Temperature is 0 so the classification is
    effectively stable across runs for the same input.
    """
    cats = ", ".join(PSEUDONYM_CATEGORIES)
    system = (
        "You are a careful cultural classifier for student name "
        "anonymization in a K-12 case study workflow. Your only job is to "
        "pick the single best-matching cultural category for a given first "
        "name so the anonymized pseudonym does not Anglicize a non-Anglo "
        "name. Output exactly one of the category keys, lowercased, with no "
        "punctuation, no explanation, and no surrounding whitespace."
    )
    user = (
        f"First name: {real_first_name}\n\n"
        f"Categories: {cats}\n\n"
        "Pick the single best match. Output only the category key."
    )
    raw = claude_complete(system, user, max_tokens=20).strip().lower()
    raw = re.sub(r"[^a-z_]", "", raw)
    if raw in PSEUDONYM_POOLS:
        return raw
    # Defensive fallback: if Claude returned something unexpected, log and
    # default to the most-represented A+ family demographic.
    print(
        f"  WARN: Claude returned unexpected category {raw!r}; "
        f"defaulting to latino_hispanic.",
        file=sys.stderr,
    )
    return "latino_hispanic"


def pseudonym_for_name(real_name: str) -> str:
    """Cultural-classify the real first name, SHA-256-pick from that pool.

    The returned token is a single clean first name (lowercase, no SHA digest
    suffix). If the SHA-chosen name happens to match the real first name,
    we walk forward in the pool to the next entry.
    """
    real_first = (real_name.split() or ["student"])[0]
    category = classify_cultural_background(real_first)
    pool = PSEUDONYM_POOLS[category]
    digest_int = int(hashlib.sha256(real_name.encode("utf-8")).hexdigest()[:12], 16)
    idx = digest_int % len(pool)
    candidate = pool[idx]
    # Avoid picking the real name back as the pseudonym.
    if candidate.lower() == real_first.lower():
        candidate = pool[(idx + 1) % len(pool)]
    return candidate.lower()


def normalize_name(name: str) -> str:
    """Slug-safe normalization of a name for filenames and url slugs."""
    if not name:
        return "student"
    name = name.strip()
    return re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower() or "student"


def build_bundle_path(pseudonym: str, date_str: str) -> Path:
    if not pseudonym:
        raise OrchestratorError("Cannot build bundle path: empty pseudonym.")
    bundle_name = f"{date_str}-case-study-{pseudonym}"
    return BUNDLE_ROOT / bundle_name


# ---------------------------------------------------------------------------
# Partner-school demographics: read from data/partner-schools.md, write back
# when a new school is encountered.
# ---------------------------------------------------------------------------

PARTNER_SCHOOLS_PATH = REPO_ROOT / "data" / "partner-schools.md"


def _match_school_block(file_text: str, school_name: str) -> tuple[int, int] | None:
    """Find (start, end) char offsets of one school block in partner-schools.md.

    A school block starts at `  - name: "<name>"` and ends just before the
    next `  - name:` line OR before the closing `---` of the frontmatter.
    Returns None if no exact-name match is found.
    """
    # Locate the YAML frontmatter (between the first two '---' lines).
    frontmatter_match = re.search(r"^---\n(.*?)\n---\n", file_text, re.DOTALL)
    if not frontmatter_match:
        return None
    fm_start = frontmatter_match.start(1)
    fm_end = frontmatter_match.end(1)
    fm = file_text[fm_start:fm_end]
    name_re = re.compile(
        rf'^  - name:\s*"{re.escape(school_name)}"\s*$', re.MULTILINE
    )
    name_match = name_re.search(fm)
    if not name_match:
        return None
    block_start = fm_start + name_match.start()
    # End at the next school entry or the end of the frontmatter.
    next_name = re.search(r"^  - name:\s*", fm[name_match.end():], re.MULTILINE)
    if next_name:
        block_end = fm_start + name_match.end() + next_name.start()
    else:
        # No more entries — stop at the next top-level key (e.g. fallback_slugs:)
        rest = fm[name_match.end():]
        next_top = re.search(r"^[a-z_]+:\s*$", rest, re.MULTILINE)
        block_end = (
            fm_start + name_match.end() + next_top.start() if next_top else fm_end
        )
    return (block_start, block_end)


def read_partner_school_demographics(school_name: str) -> str | None:
    """Return the `dominant_demographics` value for a school, or None."""
    if not PARTNER_SCHOOLS_PATH.exists():
        return None
    text = PARTNER_SCHOOLS_PATH.read_text()
    span = _match_school_block(text, school_name)
    if not span:
        return None
    block = text[span[0]:span[1]]
    m = re.search(r'^\s{4}dominant_demographics:\s*"(.+?)"\s*$', block, re.MULTILINE)
    return m.group(1) if m else None


def write_partner_school_demographics(school_name: str, demographics: str) -> bool:
    """Insert/update `dominant_demographics:` for a school entry. Returns True
    if the file was modified, False if the school wasn't found or the value
    is already set to the same string.
    """
    if not PARTNER_SCHOOLS_PATH.exists():
        return False
    text = PARTNER_SCHOOLS_PATH.read_text()
    span = _match_school_block(text, school_name)
    if not span:
        return False
    block = text[span[0]:span[1]]
    existing = re.search(
        r'^(\s{4}dominant_demographics:\s*)"(.+?)"\s*$', block, re.MULTILINE
    )
    safe_value = demographics.replace('"', "'")
    if existing:
        if existing.group(2) == safe_value:
            return False
        new_block = (
            block[: existing.start()]
            + existing.group(1) + f'"{safe_value}"'
            + block[existing.end():]
        )
    else:
        # Insert before the `notes:` line so the field sits beside related metadata.
        notes_match = re.search(r"^(\s{4}notes:.*)$", block, re.MULTILINE)
        insert_line = f'    dominant_demographics: "{safe_value}"\n'
        if notes_match:
            new_block = (
                block[: notes_match.start()] + insert_line + block[notes_match.start():]
            )
        else:
            # Append to end of block, before the trailing blank.
            new_block = block.rstrip() + "\n" + insert_line + "\n"
    PARTNER_SCHOOLS_PATH.write_text(text[: span[0]] + new_block + text[span[1]:])
    return True


def derive_or_lookup_demographics(school_name: str) -> str:
    """Return free-form demographic prose for the school's hero scene.

    Pulled from partner-schools.md if the school already has a
    `dominant_demographics:` field; otherwise asked of Claude and written
    back. The demographic is a property of the SCHOOL, not the student.
    Never let a pseudonym category steer this — A+ charter schools are
    minority-majority and the hero scene must reflect that.
    """
    cached = read_partner_school_demographics(school_name)
    if cached:
        return cached
    system = (
        "You are a careful researcher on California K-12 charter school "
        "demographics. Output a single concise free-form prose sentence "
        "describing the dominant student demographic of the named CA "
        "charter school based on California DataQuest enrollment data. "
        "Match this phrasing style: "
        "'Latina (Hispanic), reflecting iLEAD Exploration demographics'. "
        "Pick the dominant NON-WHITE racial/ethnic group when one exists "
        "in the enrollment data — A+ Tutoring's charter partners are "
        "consistently minority-majority and the hero image must reflect "
        "that. Never default to white. Output one sentence only, no "
        "preface, no surrounding quotes."
    )
    user = (
        f"School: {school_name}\n\n"
        "Return one sentence of demographic prose."
    )
    derived = claude_complete(system, user, max_tokens=80).strip().strip('"')
    if not derived:
        raise OrchestratorError(
            f"Failed to derive demographics for school {school_name!r}."
        )
    if write_partner_school_demographics(school_name, derived):
        print(
            f"  Wrote dominant_demographics for {school_name!r} back to partner-schools.md",
            file=sys.stderr,
        )
    return derived


# ---------------------------------------------------------------------------
# Skill loading (drafting agent uses aplus-spotlight-case-study/SKILL.md
# verbatim as its system prompt — that file IS the spec).
# ---------------------------------------------------------------------------

SKILLS_DIR = REPO_ROOT / "skills"


def load_skill(skill_name: str) -> str:
    path = SKILLS_DIR / skill_name / "SKILL.md"
    if not path.exists():
        raise OrchestratorError(f"Skill not found: {path}")
    return path.read_text()


def ensure_source_files(source_dir: Path, categories: dict[str, list[Path]]) -> None:
    missing = []
    for key in ["parent_call", "lesson_report", "paola_brief"]:
        if not categories.get(key):
            missing.append(key.replace("_", " ").title())
    if missing:
        raise MissingRequiredFiles(
            f"Missing required source file categories: {', '.join(missing)}. "
            f"Ensure the source folder contains parent call, lesson report, and Paola brief files."
        )


def extract_email(text: str) -> str | None:
    m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return m.group(0) if m else None


# Paola's v2.0 brief format is "Section N: ..." headings + "- Field: value"
# bullets. These regexes pull out the few fields the orchestrator needs to
# wire HubSpot and the draft. They are lenient on whitespace and capitalization.
_BRIEF_FIRSTNAME_RE = re.compile(
    r"^-\s*Real first name:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE
)
_BRIEF_LASTNAME_RE = re.compile(
    r"^-\s*(?:Real )?last name:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE
)
_BRIEF_GRADE_RE = re.compile(r"^-\s*Grade:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)
_BRIEF_SCHOOL_RE = re.compile(
    r"^-\s*School(?:/[^:]+)?:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE
)
_BRIEF_PARENT_RE = re.compile(
    r"^-\s*Parent:\s*([^(\n]+?)(?:\s*\(|$)", re.MULTILINE | re.IGNORECASE
)


def parse_paola_brief(text: str) -> dict:
    """Extract the few fields the orchestrator needs from Paola's brief.

    Missing fields come back as None so callers can decide whether to fail
    or fall back. We intentionally avoid full structured parsing; the brief
    is for the drafting agent (which sees the raw text), not for us.
    """
    out = {
        "student_firstname": None,
        "student_lastname": None,
        "grade": None,
        "school": None,
        "parent_full_name": None,
    }
    m = _BRIEF_FIRSTNAME_RE.search(text)
    if m:
        out["student_firstname"] = m.group(1).strip()
    m = _BRIEF_LASTNAME_RE.search(text)
    if m:
        out["student_lastname"] = m.group(1).strip()
    m = _BRIEF_GRADE_RE.search(text)
    if m:
        out["grade"] = m.group(1).strip()
    m = _BRIEF_SCHOOL_RE.search(text)
    if m:
        out["school"] = m.group(1).strip()
    m = _BRIEF_PARENT_RE.search(text)
    if m:
        out["parent_full_name"] = m.group(1).strip()
    return out


HUBSPOT_CONTACT_PROPERTIES = [
    "email", "firstname", "lastname", "jobtitle", "company", "student_school",
]


def _hubspot_search(filters: list[dict]) -> dict:
    """POST /crm/v3/objects/contacts/search with the given filters. Returns the raw JSON."""
    token = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
    if not token:
        raise HubSpotSearchError(
            "HUBSPOT_PRIVATE_APP_TOKEN is not configured for HubSpot lookup."
        )
    url = "https://api.hubapi.com/crm/v3/objects/contacts/search"
    payload = {
        "filterGroups": [{"filters": filters}],
        "properties": HUBSPOT_CONTACT_PROPERTIES,
        "limit": 10,
    }
    import requests
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if r.status_code != 200:
        raise HubSpotSearchError(
            f"HubSpot search failed: HTTP {r.status_code} {r.text[:300]}"
        )
    return r.json()


def call_hubspot_lookup(email: str) -> dict:
    """Look up a contact by email. Raises HubSpotNotFound / HubSpotAmbiguous
    so the orchestrator can fall back to a name search or stop with a
    differentiated error.
    """
    data = _hubspot_search(
        [{"propertyName": "email", "operator": "EQ", "value": email}]
    )
    total = data.get("total", 0)
    results = data.get("results", [])
    if total == 1:
        return results[0]
    if total == 0:
        raise HubSpotNotFound(
            f"HubSpot contact search by email {email!r} returned no results."
        )
    raise HubSpotAmbiguous(
        f"HubSpot contact search by email {email!r} returned {total} results."
    )


def call_hubspot_lookup_by_name(firstname: str, lastname: str | None) -> dict:
    """Fallback search by first + (optional) last name. Same Found/NotFound/Ambiguous semantics."""
    filters = [{"propertyName": "firstname", "operator": "EQ", "value": firstname}]
    if lastname:
        filters.append({"propertyName": "lastname", "operator": "EQ", "value": lastname})
    data = _hubspot_search(filters)
    total = data.get("total", 0)
    results = data.get("results", [])
    if total == 1:
        return results[0]
    if total == 0:
        descriptor = f"{firstname} {lastname}" if lastname else firstname
        raise HubSpotNotFound(
            f"HubSpot contact search by name {descriptor!r} returned no results."
        )
    raise HubSpotAmbiguous(
        f"HubSpot contact search by name returned {total} contacts. "
        "Disambiguate by adding more identifying info to Paola's brief."
    )


def save_extracted_texts(bundle_dir: Path, source_texts: dict[str, str]) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    out = bundle_dir / "source_texts.json"
    out.write_text(json.dumps(source_texts, indent=2, ensure_ascii=False))


def copy_source_files(bundle_dir: Path, sources: list[Path]) -> None:
    dest = bundle_dir / "source"
    dest.mkdir(parents=True, exist_ok=True)
    for source in sources:
        target = dest / source.name
        if not target.exists():
            shutil.copy2(source, target)


def run_subprocess(command: list[str], dry_run: bool = False) -> int:
    print("Running:", " ".join(command))
    if dry_run:
        return 0
    result = subprocess.run(command)
    return result.returncode


def stage_init(args: argparse.Namespace, state: dict) -> dict:
    run_id = str(uuid.uuid4())
    start_time = datetime.utcnow().isoformat() + "Z"
    run = {
        "run_id": run_id,
        "started_at": start_time,
        "source": str(Path(args.source).resolve()),
        "status": "running",
        "stage": "init",
        "dry_run": bool(args.dry_run),
        "stop_after": args.stop_after,
        "student_name": args.student_name,
        "school": args.school,
        "skip_hubspot": bool(args.skip_hubspot),
    }
    append_run(run)
    return run


def stage_read_sources(args: argparse.Namespace, run: dict) -> dict:
    source_dir = Path(args.source).resolve()
    if not source_dir.is_dir():
        raise OrchestratorError(f"Source folder not found: {source_dir}")

    all_files = find_source_files(source_dir)
    categories = categorize_source_files(all_files)
    ensure_source_files(source_dir, categories)

    source_texts: dict[str, str] = {}
    for path in all_files:
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            print(f"  Skipping unsupported file: {path.name}", file=sys.stderr)
            continue
        text = extract_text(path)
        if not text.strip():
            raise OrchestratorError(f"Extracted empty text from {path.name}")
        source_texts[path.name] = text
        if args.verbose:
            print(f"Extracted {len(text)} chars from {path.name}")

    run_dir = BUNDLE_ROOT / "_pending"
    run_dir.mkdir(parents=True, exist_ok=True)
    save_extracted_texts(run_dir, source_texts)

    run.update(
        {
            "stage": "read_sources",
            "source_files": [str(p.resolve()) for p in all_files],
            "source_categories": {k: [p.name for p in v] for k, v in categories.items()},
            "extracted_texts_path": str((run_dir / "source_texts.json").resolve()),
        }
    )
    update_run(run["run_id"], run)
    return run


def _load_brief_fields(run: dict) -> dict:
    """Read Paola's brief text from the extracted-texts cache and parse it."""
    cache = Path(run["extracted_texts_path"]).read_text()
    source_texts = json.loads(cache)
    brief_text = ""
    for name, text in source_texts.items():
        if name.lower().startswith("paola"):
            brief_text = text
            break
    if not brief_text:
        return {}
    return parse_paola_brief(brief_text)


def stage_hubspot(args: argparse.Namespace, run: dict) -> dict:
    """Identify the family in HubSpot.

    Strategy:
      1. Pull a candidate parent email from the source texts (regex).
      2. POST contacts/search by email. Exactly-1 -> Found. 0 -> name fallback. >1 -> Ambiguous.
      3. Name fallback: take student first+last name from Paola's brief and search.
      4. Still 0 -> HubSpotNotFound. >1 -> HubSpotAmbiguous.
    """
    brief = _load_brief_fields(run)
    if args.skip_hubspot:
        print("Skipping HubSpot lookup by request.")
        # Even when skipping HubSpot, we surface brief-parsed fields so
        # downstream stages have school/grade/name without a CRM call.
        run.update(
            {
                "stage": "hubspot",
                "hubspot_contact": None,
                "brief_fields": brief,
            }
        )
        update_run(run["run_id"], run)
        return run

    source_texts = json.loads(Path(run["extracted_texts_path"]).read_text())
    email = None
    for text in source_texts.values():
        candidate = extract_email(text)
        if candidate:
            email = candidate
            break

    contact = None
    lookup_kind = None
    if email:
        print(f"  Searching HubSpot by email: {email}")
        try:
            contact = call_hubspot_lookup(email)
            lookup_kind = "email"
        except HubSpotNotFound:
            print(f"  Email lookup returned 0 results; falling back to name search.")
        # HubSpotAmbiguous bubbles up directly — multiple matches on an email
        # is a data-quality issue the operator must resolve.

    if contact is None:
        firstname = brief.get("student_firstname")
        lastname = brief.get("student_lastname")
        if not firstname:
            raise HubSpotNotFound(
                "No email matched in HubSpot and Paola's brief has no "
                "'Real first name:' field for the name-fallback search."
            )
        print(f"  Searching HubSpot by name: {firstname} {lastname or ''}".rstrip())
        contact = call_hubspot_lookup_by_name(firstname, lastname)
        lookup_kind = "name"

    props = contact.get("properties", {})
    run.update(
        {
            "stage": "hubspot",
            "hubspot_contact": {
                "contact_id": contact.get("id"),
                "email": props.get("email") or email,
                "firstname": props.get("firstname"),
                "lastname": props.get("lastname"),
                "company": props.get("company"),
                "school": props.get("student_school"),
                "lookup_kind": lookup_kind,
            },
            "brief_fields": brief,
        }
    )
    update_run(run["run_id"], run)
    return run


def _resolve_student_identity(args: argparse.Namespace, run: dict) -> tuple[str, str | None, str | None]:
    """Return (firstname, lastname, school) using HubSpot contact when present,
    else Paola's parsed brief, else --student-name / --school args."""
    contact = run.get("hubspot_contact") or {}
    brief = run.get("brief_fields") or {}
    firstname = (
        (contact.get("firstname") if contact else None)
        or brief.get("student_firstname")
        or args.student_name
    )
    lastname = (
        (contact.get("lastname") if contact else None)
        or brief.get("student_lastname")
    )
    school = (
        args.school
        or (contact.get("school") if contact else None)
        or brief.get("school")
    )
    if not firstname:
        raise OrchestratorError(
            "Could not determine the student's real first name from HubSpot, "
            "Paola's brief, or --student-name. Stop."
        )
    return firstname, lastname, school


def stage_bundle(args: argparse.Namespace, run: dict) -> dict:
    real_firstname, real_lastname, school = _resolve_student_identity(args, run)
    pseudonym = pseudonym_for_name(real_firstname)
    print(f"  Real first name: {real_firstname}  ->  pseudonym: {pseudonym}")

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    bundle_dir = build_bundle_path(pseudonym, date_str)
    if bundle_dir.exists():
        raise OrchestratorError(
            f"Bundle directory already exists: {bundle_dir}. "
            "Delete it or pick a different date to re-run."
        )

    run_source_root = Path(run["extracted_texts_path"]).parent
    source_texts = json.loads((run_source_root / "source_texts.json").read_text())
    copy_source_files(bundle_dir, [Path(p) for p in run["source_files"]])
    save_extracted_texts(bundle_dir, source_texts)

    bundle_manifest = {
        "bundle_path": str(bundle_dir.resolve()),
        "real_firstname": real_firstname,
        "real_lastname": real_lastname,
        "pseudonym": pseudonym,
        "school": school,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "source_folder": str(Path(args.source).resolve()),
    }
    (bundle_dir / "bundle-manifest.json").write_text(json.dumps(bundle_manifest, indent=2))

    run.update(
        {
            "stage": "bundle",
            "bundle_path": str(bundle_dir.resolve()),
            "bundle_manifest_path": str((bundle_dir / "bundle-manifest.json").resolve()),
            "real_firstname": real_firstname,
            "real_lastname": real_lastname,
            "pseudonym": pseudonym,
            "school": school,
        }
    )
    update_run(run["run_id"], run)
    return run


# ---------------------------------------------------------------------------
# Stage 4: draft — Doc 1 (anonymized) + Doc 2 (archive with name-mapping table)
# ---------------------------------------------------------------------------

DRAFT_DOC1_DELIM = "===== DOC 1: PUBLISHED CASE STUDY (anonymized) ====="
DRAFT_DOC2_DELIM = "===== DOC 2: ARCHIVE (un-anonymized, NEVER published) ====="


def _build_draft_system_prompt() -> str:
    skill = load_skill("aplus-spotlight-case-study")
    return (
        "You are the A+ Tutoring spotlight case-study drafting agent. "
        "Follow the SKILL spec below verbatim — the 8-section Hero's Journey "
        "structure, the 1,200-1,500 word count, the pull-quote grammar gate, "
        "the anonymization protocol, the parent-facing voice cues. Output "
        "two documents separated by the literal delimiters provided in the "
        "user instructions. Do not add commentary outside the documents.\n\n"
        "===== aplus-spotlight-case-study SKILL.md =====\n\n" + skill
    )


def _build_draft_user_prompt(
    *,
    real_firstname: str,
    real_lastname: str | None,
    pseudonym: str,
    school: str | None,
    source_texts: dict[str, str],
) -> str:
    sources_block = "\n\n".join(
        f"--- {name} ---\n{text}" for name, text in source_texts.items()
    )
    real_full = f"{real_firstname} {real_lastname}" if real_lastname else real_firstname
    return f"""Draft the master case study for this student.

REAL NAME (use only in Doc 2): {real_full}
PSEUDONYM (use in Doc 1): {pseudonym}
SCHOOL: {school or "(unknown — anonymize as 'a charter school in California')"}

Output format — two documents separated by the exact delimiters below.

{DRAFT_DOC1_DELIM}
<Document 1 here — anonymized, 1,200-1,500 words, the 8 Hero's Journey
sections from the SKILL spec, parent-facing voice, pull quotes marked
inline with [PULL QUOTE]. Start with a markdown H1 title using the
pseudonym. Do NOT include real names anywhere in Document 1.>

{DRAFT_DOC2_DELIM}
<Document 2 here — same structure as Doc 1 but with real names restored.
Include at the end a section "## Name-mapping table" formatted as a
two-column markdown table:

| Real | Published |
|------|-----------|
| {real_firstname} | {pseudonym.capitalize()} |
| (other real-name tokens) | (their published replacements) |

Every distinct real-name token that appears in the sources MUST appear
in this table — student first/last name, parent name(s), tutor name(s),
TOR name(s), school name. For tokens that are kept verbatim in Doc 1
(e.g. tutor first names, schools when permission is granted), set
Published = Real. For tokens that were dropped entirely (e.g. nicknames
or last-name tokens not surfaced in Doc 1), use "(dropped)".>

SOURCE DOCUMENTS:

{sources_block}
"""


def _split_draft(text: str) -> tuple[str, str]:
    if DRAFT_DOC1_DELIM not in text or DRAFT_DOC2_DELIM not in text:
        raise OrchestratorError(
            "Draft response missing the DOC 1 / DOC 2 delimiters. "
            f"Got first 300 chars: {text[:300]!r}"
        )
    _, rest = text.split(DRAFT_DOC1_DELIM, 1)
    doc1, doc2 = rest.split(DRAFT_DOC2_DELIM, 1)
    return doc1.strip(), doc2.strip()


def _word_count(markdown_text: str) -> int:
    # Strip markdown headings/bullets so the count tracks the prose. This is
    # approximate; the SKILL spec is "1,200-1,500 words" of body prose.
    stripped = re.sub(r"^[#\->\s\*]+", "", markdown_text, flags=re.MULTILINE)
    stripped = re.sub(r"\[PULL QUOTE\]", "", stripped)
    return len(re.findall(r"\b[\w']+\b", stripped))


def stage_draft(args: argparse.Namespace, run: dict) -> dict:
    bundle = Path(run["bundle_path"])
    source_texts = json.loads((bundle / "source_texts.json").read_text())
    system = _build_draft_system_prompt()
    user = _build_draft_user_prompt(
        real_firstname=run["real_firstname"],
        real_lastname=run.get("real_lastname"),
        pseudonym=run["pseudonym"],
        school=run.get("school"),
        source_texts=source_texts,
    )

    pseudonym = run["pseudonym"]
    realname_slug = normalize_name(run["real_firstname"])
    doc1_path = bundle / f"case-study-{pseudonym}.md"
    doc2_path = bundle / f"archive-{realname_slug}.md"

    print(f"  Drafting case study (target 1,200-1,500 words)...")
    last_text = ""
    for attempt in range(2):
        text = claude_complete(system, user, max_tokens=16000, temperature=0.4)
        doc1, doc2 = _split_draft(text)
        wc = _word_count(doc1)
        print(f"    attempt {attempt + 1}: Doc 1 word count = {wc}")
        if 1100 <= wc <= 1600:
            doc1_path.write_text(doc1 + "\n")
            doc2_path.write_text(doc2 + "\n")
            run.update(
                {
                    "stage": "draft",
                    "doc1_path": str(doc1_path.resolve()),
                    "doc2_path": str(doc2_path.resolve()),
                    "doc1_word_count": wc,
                }
            )
            update_run(run["run_id"], run)
            return run
        last_text = text
        # Retry with corrective feedback.
        user += (
            "\n\nPrevious attempt produced Doc 1 with "
            f"{wc} words, outside the 1,200-1,500 target. "
            "Re-draft Doc 1 within range. Keep all 8 sections and the "
            "pull-quote markers. Keep Doc 2 in sync with the new Doc 1."
        )
    raise OrchestratorError(
        f"Draft failed word-count gate after 2 attempts. "
        f"Last raw response first 400 chars: {last_text[:400]!r}"
    )


# ---------------------------------------------------------------------------
# Stage 5: anonymization gate (shell out to check-anonymization.py)
# ---------------------------------------------------------------------------

CHECK_ANON_SCRIPT = REPO_ROOT / "scripts" / "b2c" / "check-anonymization.py"


def stage_anonymization(args: argparse.Namespace, run: dict) -> dict:
    bundle = Path(run["bundle_path"])
    print(f"  Running check-anonymization.py against {bundle.name}...")
    cmd = ["python3", str(CHECK_ANON_SCRIPT), "--bundle", str(bundle)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise AnonymizationFailure(
            f"Anonymization gate failed for {bundle.name}. "
            "Real-name token leaked into the published draft. "
            "No retry — fix Doc 1 manually or re-run from --stop-after bundle."
        )
    print(result.stdout.strip())
    run.update({"stage": "anonymization"})
    update_run(run["run_id"], run)
    return run


# ---------------------------------------------------------------------------
# Stage 6: archive augmentation (append source list + audit trail)
# ---------------------------------------------------------------------------

def stage_archive(args: argparse.Namespace, run: dict) -> dict:
    bundle = Path(run["bundle_path"])
    doc2 = Path(run["doc2_path"])
    existing = doc2.read_text()
    audit_marker = "## Source files used in this case study"
    if audit_marker in existing:
        print(f"  Archive already has audit trail — leaving alone.")
        run.update({"stage": "archive"})
        update_run(run["run_id"], run)
        return run

    source_files = [Path(p).name for p in run.get("source_files", [])]
    lines = [
        "",
        audit_marker,
        "",
        f"Bundle: `{bundle.name}`",
        f"Run id: `{run['run_id']}`",
        f"Drafted: {datetime.utcnow().isoformat()}Z",
        f"Pseudonym: {run['pseudonym']}",
        f"Real first name: {run['real_firstname']}",
        f"Real last name: {run.get('real_lastname') or '(not provided)'}",
        f"School: {run.get('school') or '(unknown)'}",
        "",
        "Sources read by the orchestrator:",
        *[f"- {name}" for name in source_files],
        "",
        "## Audit trail",
        "",
        "- Doc 1 word count gate: PASSED (see run state).",
        "- check-anonymization.py gate: PASSED (see run state).",
        "",
        "Doc 2 (this file) is NEVER published. It exists only as the local",
        "central-library reference and the source-of-truth name mapping.",
        "",
    ]
    doc2.write_text(existing.rstrip() + "\n" + "\n".join(lines))
    print(f"  Archive augmented with audit trail -> {doc2.name}")
    run.update({"stage": "archive"})
    update_run(run["run_id"], run)
    return run


# ---------------------------------------------------------------------------
# Stage 7: metadata.md
# ---------------------------------------------------------------------------

METADATA_SYSTEM = """You write metadata.md for A+ Tutoring B2C case studies.
Your output must be a single complete metadata.md file the downstream
publish + graphics scripts can parse. Adhere strictly to the field schema
and formats below — these field names are load-bearing for downstream
parsers.

Required fields (in this order, no commentary):

1. A leading h1 line: `# {Pseudonym} Case Study — HubSpot Publication Metadata`
2. A `## Publisher inputs (scalar fields)` heading followed by a fenced
   ``` block containing these scalar fields (one per line, no quotes):
      hubspot_blog: case-study
      content_type: case-study
      case_pattern: <one-line descriptor>
      url_slug: <pseudonym>-<school-slug>
      h1_title: <compelling title with pseudonym + outcome>
      subject: <math | reading | writing | science>
      grade: <integer>
      student_gender: <girl | boy>
      student_ethnicity: <free-form prose, e.g. "Latina (Hispanic), reflecting <school> demographics">
      meta_title: <50-60 chars>
      html_title: <same as meta_title>
      meta_description: <150-160 chars, includes pseudonym + outcome + A+ Tutoring>
      canonical_url: https://blog.wetutorathome.com/case-study/<slug>
      primary_keyword: <one high-intent keyword>
      language: en
      hero_alt_text: <descriptive sentence about the photo subject>
      schema_type: Article
      schema_author: A+ Tutoring Team
      schema_publisher: A+ Tutoring
      schema_date_published: <YYYY-MM-DD today>
      school_named: <full canonical school name>
      reading_time: 6 minutes
      target_publish_date: <YYYY-MM-DD, 7 days from today>
3. Outside the fence: `cta_url: https://wetutorathome.com/consultation`
4. `## Pull quotes` heading then a list named pull_quotes with EXACTLY 2
   verbatim quotes from the source documents. Each must read as a
   complete grammatical sentence in isolation. Add bracketed editorial
   insertions if needed. Then a scalar `pull_quote_attribution: "<Parent
   first name>, <Pseudonym>'s mother"` (or father — match the source).
5. `## Keywords` heading then keywords: list of 5 and secondary_keywords:
   list of 5, plus `tag_ids: []`.
6. `## JSON-LD schema` heading then 3 fenced ```json blocks: Article, FAQ
   (with 3 reasonable parent-facing Q+A from the source), Organization.
7. `## Instagram carousel slides (5)` then `carousel_slides:` list of 5.
8. `## Instagram Story 3-frame sequence` then `instagram_story_frames:`
   list of 3 and `instagram_story_subheads:` list of 3.
9. `## Facebook share copy` then `facebook_headline:` and
   `facebook_subhead:` scalars.
10. `## Milestone timeline` then `milestones:` list of 3-6 entries in the
    format "Month | Topic | Verbatim phrase from lesson notes", plus
    `milestone_footer:` and `milestone_footer_sub:` scalars.

RULES:
- No em dashes anywhere.
- No straight ASCII quotes inside quoted strings — use curly quotes when
  quoting a parent or tutor.
- No banned A+ words ("leverage", "delve", "harness").
- Pull quotes must be verbatim from the sources (or with bracketed
  editorial inserts to fix grammar).
- Never invent scores, percentiles, or quotes. If a field is absent in
  the sources, work around it.
- Output the metadata.md content only. No preamble, no postscript."""


def _detect_milestone_text(source_texts: dict[str, str]) -> str:
    """Concatenate the lesson-report-style sources for milestone extraction."""
    parts = []
    for name, text in source_texts.items():
        lower = name.lower()
        if "lesson" in lower or "tutor" in lower:
            parts.append(text)
    return "\n\n".join(parts) if parts else "\n\n".join(source_texts.values())


def stage_metadata(args: argparse.Namespace, run: dict) -> dict:
    bundle = Path(run["bundle_path"])
    pseudonym = run["pseudonym"]
    school = run.get("school") or "a California charter school"

    # Derive demographics from partner-schools.md (or web/Claude lookup +
    # write-back) so the hero scene reads as the school's real population.
    demographics = derive_or_lookup_demographics(school)
    print(f"  student_ethnicity (school-based): {demographics!r}")

    # Find the school's url slug from partner-schools.md (fall back to
    # the school's normalized name).
    school_slug = _lookup_school_slug(school) or normalize_name(school)

    source_texts = json.loads((bundle / "source_texts.json").read_text())
    doc1 = Path(run["doc1_path"]).read_text()
    milestone_seed = _detect_milestone_text(source_texts)

    today = datetime.utcnow().date()
    target_publish = today + timedelta(days=7)

    user = (
        f"Pseudonym: {pseudonym}\n"
        f"School (canonical name): {school}\n"
        f"School URL slug: {school_slug}\n"
        f"Today's date: {today.isoformat()}\n"
        f"Target publish date: {target_publish.isoformat()}\n"
        f"student_ethnicity prose: {demographics}\n\n"
        "DRAFT CASE STUDY (Doc 1):\n\n" + doc1 +
        "\n\nSOURCE LESSON / TUTOR TEXT (for milestone extraction):\n\n" +
        milestone_seed +
        "\n\nProduce the metadata.md content now. Output the file content only."
    )
    print(f"  Generating metadata.md...")
    text = claude_complete(METADATA_SYSTEM, user, max_tokens=8000, temperature=0.2)
    meta_path = bundle / "metadata.md"
    meta_path.write_text(text.strip() + "\n")
    print(f"    metadata.md written ({len(text):,} chars)")
    run.update(
        {
            "stage": "metadata",
            "metadata_path": str(meta_path.resolve()),
            "student_ethnicity": demographics,
        }
    )
    update_run(run["run_id"], run)
    return run


def _lookup_school_slug(school_name: str) -> str | None:
    """Find the school's url_slug in partner-schools.md by exact or fuzzy match."""
    if not PARTNER_SCHOOLS_PATH.exists() or not school_name:
        return None
    text = PARTNER_SCHOOLS_PATH.read_text()
    # Try exact name match first.
    span = _match_school_block(text, school_name)
    if not span:
        # Try short-name match (e.g. "iLEAD" vs "iLEAD Exploration").
        short_re = re.compile(
            rf'^\s{{4}}short_name:\s*"{re.escape(school_name)}"\s*$',
            re.MULTILINE,
        )
        m = short_re.search(text)
        if m:
            # Walk backwards to the enclosing block's name line, then forward
            # to its url_slug.
            up_to = text[:m.start()]
            name_match = list(re.finditer(r'^  - name:\s*"(.+?)"', up_to, re.MULTILINE))
            if name_match:
                return _lookup_school_slug(name_match[-1].group(1))
        return None
    block = text[span[0]:span[1]]
    slug_match = re.search(r'^\s{4}url_slug:\s*"(.+?)"\s*$', block, re.MULTILINE)
    return slug_match.group(1) if slug_match else None


# ---------------------------------------------------------------------------
# Stage 8: pull-quote grammar gate
# ---------------------------------------------------------------------------

GRAMMAR_SYSTEM = """You are a strict editorial grammar gate for B2C
pull-quote graphics. For each quote, answer whether it reads as a complete
grammatical sentence in isolation (no surrounding context).

A quote PASSES if a stranger reading it on a billboard could understand
it as a complete thought. Sentence fragments, dangling clauses, missing
prepositions, and trailing conjunctions FAIL.

If a quote fails, propose a FIX using EITHER:
  - bracketed editorial insertion to complete the grammar, or
  - a substitute verbatim quote from the same source documents that
    captures a similar sentiment and is grammatical.

Output strict JSON, no surrounding markdown fence, no commentary, with
this exact shape:

{
  "results": [
    {"quote": "<original>", "passes": true|false,
     "fixed": "<the original if it passes, else the fixed version>"}
  ]
}"""


def _parse_pull_quotes(meta_text: str) -> list[str]:
    m = re.search(r"^pull_quotes:\s*$", meta_text, re.MULTILINE)
    if not m:
        return []
    items = []
    for line in meta_text[m.end():].split("\n")[1:]:
        s = line.strip()
        if not s or not s.startswith("-"):
            break
        item = s[1:].strip()
        if item.startswith('"') and item.endswith('"'):
            item = item[1:-1]
        items.append(item)
    return items


def _replace_pull_quotes(meta_text: str, new_quotes: list[str]) -> str:
    m = re.search(r"^pull_quotes:\s*$", meta_text, re.MULTILINE)
    if not m:
        raise OrchestratorError("metadata.md is missing `pull_quotes:` list.")
    # Walk forward to find the end of the existing list.
    end_offset = m.end()
    for line in meta_text[m.end():].split("\n")[1:]:
        if not line.strip() or not line.strip().startswith("-"):
            break
        end_offset += len(line) + 1
    rebuilt_list = "\n".join(f'  - "{q}"' for q in new_quotes)
    return (
        meta_text[: m.end()] + "\n" + rebuilt_list + "\n" + meta_text[end_offset:]
    ).rstrip() + "\n"


def stage_grammar(args: argparse.Namespace, run: dict) -> dict:
    bundle = Path(run["bundle_path"])
    meta_path = bundle / "metadata.md"
    meta_text = meta_path.read_text()
    quotes = _parse_pull_quotes(meta_text)
    if len(quotes) < 2:
        raise GrammarGateFailure(
            f"metadata.md must contain at least 2 pull_quotes, found {len(quotes)}."
        )
    source_texts = json.loads((bundle / "source_texts.json").read_text())
    sources_block = "\n\n".join(
        f"--- {name} ---\n{text}" for name, text in source_texts.items()
    )

    for attempt in range(2):
        print(f"  Grammar gate attempt {attempt + 1} on {len(quotes)} quotes...")
        user = (
            "Quotes to check:\n"
            + "\n".join(f"- {q}" for q in quotes)
            + "\n\nSource documents (for substitute candidates):\n\n"
            + sources_block
            + "\n\nReturn strict JSON only."
        )
        raw = claude_complete(GRAMMAR_SYSTEM, user, max_tokens=2000, temperature=0)
        try:
            payload = json.loads(_strip_json_fence(raw))
        except json.JSONDecodeError as e:
            raise GrammarGateFailure(
                f"Grammar gate returned invalid JSON: {e}. First 300 chars: {raw[:300]!r}"
            )
        results = payload.get("results", [])
        if len(results) != len(quotes):
            raise GrammarGateFailure(
                f"Grammar gate returned {len(results)} results for {len(quotes)} quotes."
            )
        all_pass = all(r.get("passes") for r in results)
        if all_pass:
            print(f"    all {len(quotes)} quotes pass.")
            run.update({"stage": "grammar"})
            update_run(run["run_id"], run)
            return run
        # Apply fixes and re-check on the next loop iteration.
        for i, r in enumerate(results):
            if not r.get("passes"):
                print(f"    quote {i + 1} failed: {r.get('quote')!r}")
                print(f"      fix: {r.get('fixed')!r}")
        quotes = [r["fixed"] for r in results]
        meta_text = _replace_pull_quotes(meta_text, quotes)
        meta_path.write_text(meta_text)
    raise GrammarGateFailure(
        "Pull-quote grammar gate failed after 2 attempts. "
        "Inspect metadata.md pull_quotes by hand."
    )


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        # Strip a leading ```json (or ```) and a trailing ```.
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Stage 9: support files (bundle-summary, paola-feedback, qa-checklist,
# seo-research-notes)
# ---------------------------------------------------------------------------

SUPPORT_SYSTEM = """You generate four short support files for an A+
Tutoring B2C case-study bundle. Each file is a short markdown document.
Output them separated by these EXACT delimiters and NOTHING else outside
the documents.

===== bundle-summary.md =====
A one-page index. Required sections:
- `## What this bundle is` (one paragraph)
- `## Files in this bundle` (bulleted list of the bundle's files with
  one-line descriptions)
- `## Items needing Gate 2` (numbered list, each item starts with a
  bolded title in **Markdown bold**, then a one-line explanation. 4-6
  items: typically the hero face composition, pull-quote selection,
  HubSpot final publish decision, IG/FB caption tone, anonymization
  spot-check, and any case-specific judgment calls. Use the case study
  to pick the actual items.)

===== paola-feedback.md =====
A 3-section message back to Paola. Required headings:
- `## What worked in the intake`
- `## What was missing or unclear`
- `## One process suggestion`

===== qa-checklist.md =====
A markdown checklist (- [ ] format) covering the 7 self-checks from
the SKILL spec (word count, anonymization, pull quote, data, turning
point, brand check, first-100-words), plus 5 case-specific items.

===== seo-research-notes.md =====
A short markdown doc with H2 sections for primary_keyword, secondary
keywords, internal links, external link suggestions, and a one-paragraph
SXO/search-intent note for the URL slug."""


SUPPORT_DELIMS = [
    "===== bundle-summary.md =====",
    "===== paola-feedback.md =====",
    "===== qa-checklist.md =====",
    "===== seo-research-notes.md =====",
]


def _split_support(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    indices = [(d, text.find(d)) for d in SUPPORT_DELIMS]
    if any(idx < 0 for _, idx in indices):
        missing = [d for d, idx in indices if idx < 0]
        raise OrchestratorError(
            f"Support output missing delimiter(s): {missing}. First 400 chars: {text[:400]!r}"
        )
    sorted_idx = sorted(indices, key=lambda x: x[1])
    for i, (delim, idx) in enumerate(sorted_idx):
        start = idx + len(delim)
        end = sorted_idx[i + 1][1] if i + 1 < len(sorted_idx) else len(text)
        body = text[start:end].strip()
        fname = delim.strip("= ").strip()
        out[fname] = body
    return out


def stage_support(args: argparse.Namespace, run: dict) -> dict:
    bundle = Path(run["bundle_path"])
    pseudonym = run["pseudonym"]
    school = run.get("school") or "(unknown school)"
    doc1 = Path(run["doc1_path"]).read_text()
    meta_text = (bundle / "metadata.md").read_text()
    user = (
        f"Pseudonym: {pseudonym}\n"
        f"School: {school}\n"
        f"Case study draft (Doc 1):\n\n{doc1}\n\n"
        f"Metadata file (already produced):\n\n{meta_text}\n\n"
        "Produce all four support files now, using the delimiters above."
    )
    print(f"  Generating support files...")
    text = claude_complete(SUPPORT_SYSTEM, user, max_tokens=6000, temperature=0.2)
    parts = _split_support(text)
    for fname, body in parts.items():
        (bundle / fname).write_text(body.rstrip() + "\n")
        print(f"    wrote {fname} ({len(body):,} chars)")
    run.update({"stage": "support"})
    update_run(run["run_id"], run)
    return run


def stage_complete(args: argparse.Namespace, run: dict) -> dict:
    run.update({"stage": "complete"})
    update_run(run["run_id"], run)
    return run


STAGE_DISPATCH = {
    "init": stage_init,
    "read_sources": stage_read_sources,
    "hubspot": stage_hubspot,
    "bundle": stage_bundle,
    "draft": stage_draft,
    "anonymization": stage_anonymization,
    "archive": stage_archive,
    "metadata": stage_metadata,
    "grammar": stage_grammar,
    "support": stage_support,
    "complete": stage_complete,
}

# Stages that --dry-run skips (irreversible external writes).
DRY_RUN_SKIP_STAGES = {"publish", "slack"}


def run_stage(stage_name: str, args: argparse.Namespace, run: dict) -> dict:
    handler = STAGE_DISPATCH.get(stage_name)
    if handler is None:
        raise OrchestratorError(f"Stage {stage_name} is not implemented yet.")
    return handler(args, run)


def main() -> int:
    args = parse_args()
    run = stage_init(args, load_state())

    if args.stop_after == "init":
        print("Stopping after stage: init")
        update_run(run["run_id"], {"status": "stopped", "stage": "init"})
        return 0

    for stage in STAGE_ORDER[1:]:
        if args.dry_run and stage in DRY_RUN_SKIP_STAGES:
            print(f"=== Stage: {stage} (skipped — --dry-run) ===")
            continue
        print(f"=== Stage: {stage} ===")
        try:
            run = run_stage(stage, args, run)
        except OrchestratorError as exc:
            update_run(run["run_id"], {"status": "failed", "stage": stage, "error": str(exc)})
            print(f"ERROR at stage {stage}: {exc}", file=sys.stderr)
            return 1
        if stage == args.stop_after:
            print(f"Stopping after stage: {stage}")
            update_run(run["run_id"], {"status": "stopped", "stage": stage})
            return 0
    update_run(run["run_id"], {"status": "completed", "stage": args.stop_after})
    print(f"Orchestration completed through stage: {args.stop_after}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
