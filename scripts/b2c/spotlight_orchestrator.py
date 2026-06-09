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
    import fitz  # PyMuPDF — used for TEXT extraction (not OCR/vision)
except ImportError:  # pragma: no cover
    fitz = None

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None

# A PDF must yield at least this much extractable text to count as readable.
# Order: pypdf -> PyMuPDF (handles font/encoding quirks) -> OCR as LAST RESORT.
# Most exports read for free via the two text extractors; OCR fires only for
# image-only exports with no text layer at all (some rasterized lesson reports).
PDF_MIN_TEXT_LEN = 120

# Last-resort OCR config. Only runs when BOTH text extractors come up empty.
# Kept on a high-quality vision model so scores/percentiles transcribe exactly.
OCR_RENDER_DPI = 200
OCR_VISION_MODEL = "claude-opus-4-7"
OCR_MAX_PAGES = 30

STAGE_ORDER = [
    "init",
    "read_sources",
    "hubspot",
    "bundle",
    "names",
    "draft",
    "anonymization",
    "archive",
    "metadata",
    "grammar",
    "support",
    "graphics",
    "hashtags",
    "publish",
    "embed_graphics",
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
    parser.add_argument("--force-update", action="store_true", help="When a HubSpot draft already exists for the slug, refresh its body with this run's Doc 1 (PATCH) instead of reusing the stale draft. Re-runs should pass this so embed matches the current document.")
    parser.add_argument("--slack-channel", default=None, help="Override the Slack delivery channel (default: #student-spotlight-ready)")
    parser.add_argument("--verbose", action="store_true", help="Print extra diagnostic details")
    return parser.parse_args()


def is_matching_source_file(name: str) -> bool:
    lower = name.lower()
    for pattern in REQUIRED_SOURCE_PATTERNS:
        if re.match(pattern, lower):
            return True
    return False


# Files the orchestrator itself emits into a bundle. If one is ever left
# behind in (or copied into) a source folder, it must NEVER be ingested as
# input — a stale case-study/archive/source-texts file would feed a prior
# student's names and pseudonyms back into a new run.
_OUTPUT_FILENAMES = {"source_texts.json", "source_categories.json", "bundle-manifest.json"}
_OUTPUT_NAME_RE = re.compile(r"^(?:case-study|archive)-.*\.md$", re.IGNORECASE)


def is_orchestrator_output(name: str) -> bool:
    """True if `name` is a file this pipeline produces (not a real source)."""
    return name in _OUTPUT_FILENAMES or bool(_OUTPUT_NAME_RE.match(name))


# When the same document is dropped in multiple formats (e.g. a scanned
# Report.pdf AND a Report.txt export), prefer the most text-native one so we
# never read a scanned PDF that's also present as text. Lower rank wins.
_EXT_PREFERENCE = {".txt": 0, ".md": 1, ".csv": 2, ".docx": 3, ".pdf": 4,
                   ".png": 5, ".jpg": 6, ".jpeg": 6, ".webp": 7}


def find_source_files(source_dir: Path) -> list[Path]:
    candidates = []
    for item in sorted(source_dir.iterdir()):
        if not item.is_file() or item.name.startswith("."):
            continue
        if is_orchestrator_output(item.name):
            print(
                f"  Skipping orchestrator output file found in source folder: {item.name}",
                file=sys.stderr,
            )
            continue
        # Skip 0-byte files (e.g. a failed/empty Drive export). They have no
        # content and would crash a reader; the real file is usually present in
        # another format (e.g. an 82KB .csv next to a 0-byte .pdf).
        try:
            if item.stat().st_size == 0:
                print(f"  Skipping empty (0-byte) source file: {item.name}", file=sys.stderr)
                continue
        except OSError:
            continue
        candidates.append(item)

    # De-dupe by stem (case-insensitive): if one document is present in several
    # formats, keep the most text-native (.txt > .md > .csv > .docx > .pdf) and
    # drop the rest. A text twin therefore replaces a scanned .pdf — no OCR, no
    # duplicated content fed downstream.
    def rank(p: Path) -> int:
        return _EXT_PREFERENCE.get(p.suffix.lower(), 99)

    best: dict[str, Path] = {}
    for item in candidates:
        key = item.stem.lower()
        cur = best.get(key)
        if cur is None or rank(item) < rank(cur):
            if cur is not None:
                print(
                    f"  Multiple formats for {item.stem!r}: preferring "
                    f"{item.name} over {cur.name}.",
                    file=sys.stderr,
                )
            best[key] = item
        elif cur is not None:
            print(
                f"  Multiple formats for {item.stem!r}: keeping {cur.name}, "
                f"skipping {item.name}.",
                file=sys.stderr,
            )
    return sorted(best.values(), key=lambda p: p.name)


def pending_dir_for_run(run_id: str) -> Path:
    """Per-run staging dir for extracted source text, keyed by run_id.

    No two runs ever share a source-text path. The old shared
    `aplus-content/_pending/` singleton let a concurrent or interleaved run
    overwrite the file another run later read at `bundle` time, bleeding one
    student's source text (and therefore pseudonym) into another's draft.
    """
    if not run_id:
        raise OrchestratorError("pending_dir_for_run requires a run_id.")
    return BUNDLE_ROOT / "_pending" / run_id


def categorize_source_files(files: list[Path]) -> dict[str, list[Path]]:
    categories = {"parent_call": [], "lesson_report": [], "paola_brief": [], "others": []}
    transcript_re = re.compile(r"\b(transcription|transcript|call)\b", re.IGNORECASE)
    lesson_re = re.compile(r"\blesson\b", re.IGNORECASE)
    brief_re = re.compile(r"\b(survey|brief|handoff|spotlight)\b", re.IGNORECASE)
    for path in files:
        name = path.name.lower()
        if transcript_re.search(name):
            categories["parent_call"].append(path)
        elif lesson_re.search(name):
            categories["lesson_report"].append(path)
        elif brief_re.search(name):
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


def _pdf_text_pypdf(path: Path) -> str:
    if PdfReader is None:
        return ""
    try:
        reader = PdfReader(path)
    except Exception:
        return ""
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return "\n\n".join(pages).strip()


def _pdf_text_pymupdf(path: Path) -> str:
    """PyMuPDF text extraction — handles font/encoding quirks in exported PDFs
    that make pypdf return little or nothing. Plain text, no OCR/vision."""
    if fitz is None:
        return ""
    try:
        doc = fitz.open(str(path))
        try:
            return "\n\n".join(page.get_text() for page in doc).strip()
        finally:
            doc.close()
    except Exception:
        return ""


def extract_text_from_pdf(path: Path) -> str:
    """Extract text from a PDF: pypdf -> PyMuPDF -> OCR (last resort).

    pypdf and PyMuPDF cover digitally-generated PDFs for free (PyMuPDF handles
    font/encoding quirks that make some exports yield 0 chars in pypdf). Only if
    BOTH come up empty — an image-only export with no text layer — do we fall
    back to vision OCR, so cost is incurred solely for those files. A same-named
    .txt export avoids OCR entirely (prefer-text dedupe uses it)."""
    best = max((_pdf_text_pypdf(path), _pdf_text_pymupdf(path)), key=len)
    if len(best) >= PDF_MIN_TEXT_LEN and best.count("\n") >= 3:
        return best
    print(
        f"  No text layer in {path.name} ({len(best)} chars via pypdf+PyMuPDF); "
        "falling back to vision OCR (drop a .txt export to skip this).",
        file=sys.stderr,
    )
    return ocr_pdf(path)


def ocr_pdf(path: Path) -> str:
    """Last-resort: rasterize each page with PyMuPDF and transcribe with Claude
    vision. Only reached when a PDF has no extractable text layer."""
    if fitz is None:
        raise OrchestratorError(
            f"PDF '{path.name}' has no text layer and PyMuPDF is unavailable for "
            "OCR. Provide a .txt/.docx export."
        )
    if anthropic is None:
        raise OrchestratorError(
            f"PDF '{path.name}' has no text layer and the anthropic SDK is "
            "unavailable for OCR. Provide a .txt/.docx export."
        )
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise OrchestratorError(
            f"PDF '{path.name}' needs OCR but ANTHROPIC_API_KEY is not set."
        )

    import base64

    client = anthropic.Anthropic(api_key=api_key)
    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        raise OrchestratorError(
            f"PDF '{path.name}' could not be opened ({exc}). It may be empty or "
            "corrupt — re-export it as a text (.txt/.docx/.csv) or a valid PDF."
        )
    try:
        if doc.page_count == 0:
            raise OrchestratorError(f"PDF has zero pages: {path.name}")
        if doc.page_count > OCR_MAX_PAGES:
            raise OrchestratorError(
                f"PDF '{path.name}' has {doc.page_count} pages, exceeds "
                f"OCR_MAX_PAGES={OCR_MAX_PAGES}. Split it or supply a text export."
            )
        zoom = OCR_RENDER_DPI / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        pages_text: list[str] = []
        for i in range(doc.page_count):
            pix = doc.load_page(i).get_pixmap(matrix=matrix, alpha=False)
            b64 = base64.standard_b64encode(pix.tobytes("png")).decode("ascii")
            print(
                f"    OCR page {i + 1}/{doc.page_count}...", file=sys.stderr
            )
            message = client.messages.create(
                model=OCR_VISION_MODEL,
                max_tokens=4096,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64",
                            "media_type": "image/png", "data": b64}},
                        {"type": "text", "text": (
                            "Transcribe this page of a K-12 tutoring source "
                            "document to plain text. Preserve paragraph breaks, "
                            "headings, and bullets. Preserve ALL numeric data "
                            "(RIT scores, percentiles, benchmarks, dates) exactly "
                            "as written. Do not summarize or comment. Output only "
                            "the transcribed text."
                        )},
                    ],
                }],
            )
            pages_text.append("".join(
                b.text for b in message.content if getattr(b, "type", "") == "text"
            ).strip())
    finally:
        doc.close()
    joined = "\n\n".join(pages_text).strip()
    if not joined:
        raise OrchestratorError(
            f"OCR returned no text for {path.name}. Supply a .txt/.docx export."
        )
    return joined


def ocr_image(path: Path) -> str:
    """Vision-transcribe a single image source (e.g. a score-report screenshot
    or photo of an i-Ready / MAP / STAR report). Only called for images that
    is_readable_score_image() classified as an assessment."""
    if anthropic is None:
        raise OrchestratorError(
            f"Image '{path.name}' needs vision OCR but the anthropic SDK is "
            "unavailable."
        )
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise OrchestratorError(
            f"Image '{path.name}' needs vision OCR but ANTHROPIC_API_KEY is not set."
        )
    import base64

    media = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
    }.get(path.suffix.lower(), "image/png")
    b64 = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    print(f"    Vision-OCR score image {path.name}...", file=sys.stderr)
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=OCR_VISION_MODEL,
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64",
                    "media_type": media, "data": b64}},
                {"type": "text", "text": (
                    "Transcribe this K-12 student assessment / score report image "
                    "to plain text. Preserve ALL numbers exactly: scores, RIT, "
                    "percentiles, grade-level equivalents, Lexile, benchmark "
                    "bands, dates, and subtest/domain names. Keep the structure "
                    "(tables as readable rows). Do not summarize or add "
                    "commentary. Output only the transcribed report."
                )},
            ],
        }],
    )
    text = "".join(
        b.text for b in message.content if getattr(b, "type", "") == "text"
    ).strip()
    if not text:
        raise OrchestratorError(f"Vision OCR returned no text for image {path.name}.")
    return text
SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".pdf", ".docx"}

# Image sources are read via vision OCR, but ONLY when the filename looks like a
# student assessment / score report (i-Ready, MAP, STAR, percentiles, ...).
# Award certificates, photos and headshots are intentionally NOT OCR'd.
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_SCORE_IMAGE_KEYWORDS = (
    "i-ready", "iready", "i ready", "map growth", "map-growth", "nwea", "star ",
    "star360", "star reading", "star math", "dibels", "acadience", "aimsweb",
    "istation", "renaissance", "lexile", "fountas", "running record", "fast ",
    "benchmark", "percentile", "rit", "diagnostic", "assessment", "score",
    "scores", "report card", "progress report", "results", "reading level",
)
_NONCONTENT_IMAGE_KEYWORDS = (
    "certificate", "award", "diploma", "headshot", "selfie", "logo", "photo",
)


def is_readable_score_image(name: str) -> bool:
    """True if an image filename looks like a student score report/assessment
    (so we vision-OCR it). Certificates/photos return False (skip OCR)."""
    low = name.lower()
    if any(k in low for k in _NONCONTENT_IMAGE_KEYWORDS):
        return False
    return any(k in low for k in _SCORE_IMAGE_KEYWORDS)


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".csv"}:
        return read_text_file(path)
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    if suffix == ".docx":
        return extract_text_from_docx(path)
    if suffix in IMAGE_EXTENSIONS:
        return ocr_image(path)
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
# pseudonym does not Anglicize a non-Anglo name. Pools are hand-curated,
# split by gender so the pseudonym matches the real student's gender
# (pronouns in source quotes carry through to the published doc, so a
# gender mismatch produces a visible "he"/"she" inconsistency). Never
# expand via Claude generation — we want a fixed, auditable list.
# Pools are keyed culture -> cohort -> gender. The cohort axis makes a
# pseudonym read as the right *generation*: students draw from names popular
# for ~2010-2020 births, parents/guardians/other adults from names popular for
# ~1980-early-2000s births. (Otherwise a mom ends up named like a 6th-grader.)
# Hand-curated, fixed, and auditable — never expanded via Claude generation.
PSEUDONYM_POOLS: dict[str, dict[str, dict[str, list[str]]]] = {
    "latino_hispanic": {
        "student": {
            "girl": ["Camila", "Sofia", "Valentina", "Isabella", "Mia", "Gabriela", "Luciana", "Ximena", "Renata", "Antonella", "Regina", "Victoria", "Emilia", "Catalina", "Daniela"],
            "boy":  ["Mateo", "Santiago", "Diego", "Sebastian", "Gabriel", "Emiliano", "Leonardo", "Maximiliano", "Thiago", "Benjamin", "Joaquin", "Tomas", "Andres", "Nicolas", "Lorenzo"],
        },
        "adult": {
            "girl": ["Adriana", "Maria", "Carolina", "Veronica", "Diana", "Patricia", "Claudia", "Sandra", "Rosa", "Gloria", "Marisol", "Lorena", "Yolanda", "Norma", "Alejandra"],
            "boy":  ["Javier", "Carlos", "Jose", "Luis", "Marco", "Eduardo", "Roberto", "Miguel", "Sergio", "Ricardo", "Fernando", "Hector", "Raul", "Arturo", "Alberto"],
        },
    },
    "african_american": {
        "student": {
            "girl": ["Aaliyah", "Imani", "Zuri", "Nia", "Amara", "Kennedy", "Jade", "Skylar", "Aniyah", "Saniyah", "Journee", "Sariah", "Laila", "Nyla", "Amari"],
            "boy":  ["Jayden", "Elijah", "Josiah", "Malik", "Xavier", "Isaiah", "Amir", "Jamal", "Khalil", "Zion", "Cameron", "Damari", "Kingston", "Tyrese", "Marquis"],
        },
        "adult": {
            "girl": ["Jasmine", "Brianna", "Tiffany", "Danielle", "Crystal", "Monique", "Latoya", "Shanice", "Kiara", "Ebony", "Tamara", "Nakia", "Tanisha", "Keisha", "Andrea"],
            "boy":  ["Marcus", "Andre", "Brandon", "Darius", "Maurice", "Terrence", "Dwayne", "Reginald", "Marlon", "Cedric", "Tyrone", "Lamar", "Demetrius", "Jerome", "Roderick"],
        },
    },
    "asian_east": {
        "student": {
            "girl": ["Aiko", "Mei", "Yuna", "Sora", "Hana", "Mina", "Emi", "Rina", "Saki", "Yui", "Hina", "Aya", "Nana", "Riko", "Sana"],
            "boy":  ["Kai", "Jin", "Ren", "Hiro", "Daiki", "Akira", "Haru", "Sota", "Yuto", "Riku", "Kenta", "Takumi", "Sho", "Ryo", "Daichi"],
        },
        "adult": {
            "girl": ["Lin", "Yuki", "Jia", "Min", "Hyun", "Wen", "Ling", "Hua", "Xiu", "Yan", "Fang", "Ai", "Jung", "Soo", "Hye"],
            "boy":  ["Wei", "Jun", "Hiroshi", "Kenji", "Tao", "Sung", "Ming", "Cheng", "Feng", "Jian", "Hong", "Bo", "Yong", "Jae", "Dong"],
        },
    },
    "asian_south": {
        "student": {
            "girl": ["Anika", "Diya", "Saanvi", "Aanya", "Ishani", "Myra", "Anaya", "Avni", "Riya", "Aadhya", "Pari", "Navya", "Kyra", "Siya", "Tara"],
            "boy":  ["Arjun", "Aarav", "Rohan", "Vihaan", "Kabir", "Ishaan", "Reyansh", "Vivaan", "Aditya", "Krishna", "Ayaan", "Dhruv", "Rudra", "Aryan", "Shaurya"],
        },
        "adult": {
            "girl": ["Anita", "Deepa", "Sunita", "Meena", "Kavita", "Neha", "Pooja", "Anjali", "Shalini", "Rekha", "Sangeeta", "Geeta", "Asha", "Nisha", "Radha"],
            "boy":  ["Raj", "Sanjay", "Amit", "Vijay", "Anil", "Deepak", "Sunil", "Rajesh", "Manish", "Ashok", "Vikram", "Suresh", "Pradeep", "Naveen", "Ramesh"],
        },
    },
    "middle_eastern": {
        "student": {
            "girl": ["Layla", "Amira", "Zara", "Noor", "Sara", "Yasmin", "Maryam", "Aya", "Lina", "Rana", "Salma", "Jana", "Mariam", "Dina", "Hiba"],
            "boy":  ["Omar", "Yusuf", "Karim", "Adam", "Hamza", "Zayd", "Ali", "Ibrahim", "Khaled", "Bilal", "Ahmad", "Rayan", "Idris", "Faris", "Samir"],
        },
        "adult": {
            "girl": ["Fatima", "Leila", "Mona", "Rania", "Hala", "Dalia", "Nadia", "Samira", "Huda", "Amal", "Lubna", "Reem", "Iman", "Sahar", "Hanan"],
            "boy":  ["Khalid", "Sami", "Tariq", "Hassan", "Nabil", "Bassam", "Fadi", "Walid", "Rami", "Ziad", "Mahmoud", "Ayman", "Tarek", "Nasser", "Adel"],
        },
    },
    "white_american": {
        "student": {
            "girl": ["Emma", "Olivia", "Ava", "Charlotte", "Sophia", "Harper", "Amelia", "Evelyn", "Abigail", "Emily", "Ella", "Scarlett", "Grace", "Chloe", "Lily"],
            "boy":  ["Liam", "Noah", "Ethan", "Owen", "Henry", "Caleb", "Mason", "Logan", "Lucas", "Jackson", "Jack", "Wyatt", "Carter", "Levi", "Hudson"],
        },
        "adult": {
            "girl": ["Jennifer", "Jessica", "Ashley", "Amanda", "Sarah", "Melissa", "Nicole", "Stephanie", "Heather", "Rachel", "Lauren", "Megan", "Kelly", "Amber", "Brittany"],
            "boy":  ["Michael", "Christopher", "Matthew", "Joshua", "David", "Brian", "Ryan", "Justin", "Andrew", "Kevin", "Jason", "Eric", "Aaron", "Nicholas", "Jacob"],
        },
    },
}

PSEUDONYM_CATEGORIES = list(PSEUDONYM_POOLS.keys())
PSEUDONYM_GENDERS = ("girl", "boy")
PSEUDONYM_COHORTS = ("student", "adult")

# Which cohort each role draws from. Tutors are kept verbatim (not pooled).
ROLE_COHORT = {
    "student": "student",
    "sibling": "student",
    "parent": "adult",
    "guardian": "adult",
    "tor": "adult",
    "other": "adult",
}


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


def classify_gender(source_texts: dict[str, str], brief_fields: dict | None = None) -> str:
    """Return 'girl' or 'boy'. Reads the source texts (parent quotes are the
    strongest signal: she/her/daughter vs he/him/son) plus Paola's parsed
    brief. Defaults to 'girl' with a warning if Claude returns garbage.
    """
    if brief_fields:
        # If the brief explicitly has a Gender: field, trust it.
        explicit = (brief_fields.get("gender") or "").strip().lower()
        if explicit in PSEUDONYM_GENDERS:
            return explicit
    sources_block = "\n\n".join(
        f"--- {name} ---\n{text}" for name, text in source_texts.items()
    )
    system = (
        "You are a gender classifier for K-12 case-study anonymization. "
        "Read the source documents and infer the student's gender from "
        "pronouns, parent references (daughter/son), and any explicit "
        "gender fields. Output exactly one of: girl, boy. No punctuation, "
        "no explanation, no surrounding whitespace."
    )
    user = sources_block + "\n\nOutput one word: girl or boy."
    raw = claude_complete(system, user, max_tokens=10).strip().lower()
    raw = re.sub(r"[^a-z]", "", raw)
    if raw in PSEUDONYM_GENDERS:
        return raw
    print(
        f"  WARN: gender classifier returned {raw!r}; defaulting to girl.",
        file=sys.stderr,
    )
    return "girl"


def pick_pseudonym(
    real_name: str,
    gender: str,
    category: str,
    cohort: str,
    used: set[str] | None = None,
) -> str:
    """Deterministically SHA-256-pick a pseudonym from the
    culture x cohort x gender pool, skipping the real first name and any name
    already taken (`used`, lowercased) so two people in one case study never
    collide. Returns the chosen name with its pool capitalization."""
    if gender not in PSEUDONYM_GENDERS:
        raise OrchestratorError(
            f"pick_pseudonym needs gender in {PSEUDONYM_GENDERS}, got {gender!r}."
        )
    if cohort not in PSEUDONYM_COHORTS:
        raise OrchestratorError(
            f"pick_pseudonym needs cohort in {PSEUDONYM_COHORTS}, got {cohort!r}."
        )
    used = used or set()
    pool = PSEUDONYM_POOLS[category][cohort][gender]
    real_first = (real_name.split() or ["x"])[0].lower()
    # Cohort in the hash seed so a parent and a same-named-hashing student
    # don't land on parallel indices.
    digest_int = int(
        hashlib.sha256(f"{cohort}:{real_name}".encode("utf-8")).hexdigest()[:12], 16
    )
    n = len(pool)
    for k in range(n):
        cand = pool[(digest_int + k) % n]
        if cand.lower() == real_first or cand.lower() in used:
            continue
        return cand
    return pool[digest_int % n]  # pool exhausted by collisions — accept a repeat


def pseudonym_for_name(real_name: str, gender: str, used: set[str] | None = None) -> str:
    """Student pseudonym: classify culture, pick from the STUDENT cohort,
    skipping any name in `used` (pseudonyms already used elsewhere in the
    library) so the published set has variety. Returns a clean single-token
    lowercase name (kept lowercase for slugs/bundle paths, as before)."""
    real_first = (real_name.split() or ["student"])[0]
    category = classify_cultural_background(real_first)
    return pick_pseudonym(real_name, gender, category, "student", used).lower()


def _existing_case_study_slugs() -> list[str]:
    """Best-effort list of existing B2C spotlight slug tails (e.g.
    'caleb-sky-mountain'), DRAFT + published. Skips legacy/template slugs.
    Empty on any error — de-dup is an enhancement, never a blocker."""
    token = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
    if not token:
        return []
    import requests
    out: list[str] = []
    after = None
    try:
        for _ in range(8):
            params = {"contentGroupId": CASE_STUDY_BLOG_ID, "limit": 100, "property": "slug"}
            if after:
                params["after"] = after
            r = requests.get(
                "https://api.hubapi.com/cms/v3/blogs/posts",
                headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30,
            )
            if r.status_code != 200:
                break
            data = r.json()
            for p in data.get("results", []):
                full = (p.get("slug") or "")
                if not full.startswith("case-study/"):
                    continue
                tail = full.split("/", 1)[1].lower()
                # only '{name}-{school}' slugs; skip legacy/template/test posts
                if "-" not in tail or tail.startswith(("test-", "case-study-")):
                    continue
                out.append(tail)
            after = (data.get("paging") or {}).get("next", {}).get("after")
            if not after:
                break
    except Exception:
        return out
    return out


def assign_student_pseudonym(real_firstname: str, gender: str, school: str | None) -> str:
    """Pick the student pseudonym with two goals: VARIETY (don't reuse a name
    another student already has) and IDEMPOTENCY (a re-run of the same student
    keeps its name, so we never orphan a duplicate draft).

    If exactly one existing case study sits at this student's school, reuse its
    name (the student already has a draft — keep it). Otherwise de-dup against
    every name already used elsewhere in the library and pick a fresh one."""
    school_slug = normalize_name(school or "")
    existing = _existing_case_study_slugs()
    mine = [t for t in existing if school_slug and t.endswith(f"-{school_slug}")]
    if len(mine) == 1:
        pseudonym = mine[0].split("-", 1)[0]
        print(f"  Reusing existing pseudonym for this student/school: {pseudonym}")
        return pseudonym
    used = {
        t.split("-", 1)[0] for t in existing
        if not (school_slug and t.endswith(f"-{school_slug}"))
    }
    pseudonym = pseudonym_for_name(real_firstname, gender, used=used)
    if used:
        print(f"  ({len(used)} library names avoided for variety)")
    return pseudonym


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


# Map a school's prose dominant_demographics to a pseudonym pool category so a
# case study's family names reflect the SCHOOL population (per-school culture).
# Order matters: more specific phrases first ("south asian" before "asian").
_DEMOGRAPHIC_CATEGORY_KEYWORDS = [
    ("latino_hispanic", ("latin", "hispanic", "mexican", "chicano")),
    ("african_american", ("black", "african american", "african-american")),
    ("asian_south", ("south asian", "indian", "pakistani", "desi", "bangladesh")),
    ("middle_eastern", ("middle eastern", "arab", "persian", "muslim")),
    ("asian_east", ("asian", "chinese", "japanese", "korean", "vietnamese", "filipino", "hmong")),
    ("white_american", ("white", "caucasian", "anglo")),
]


def school_culture_category(school: str | None) -> str:
    """Per-school culture: map the school's dominant_demographics to a
    PSEUDONYM_CATEGORY. Falls back to the most-represented A+ family
    demographic when the school has no recorded demographic."""
    demo = (read_partner_school_demographics(school) or "").lower() if school else ""
    for cat, words in _DEMOGRAPHIC_CATEGORY_KEYWORDS:
        if any(w in demo for w in words):
            return cat
    return "latino_hispanic"


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
    if not any(categories.values()):
        print(
            "Warning: no source file categories could be guessed for this folder. "
            "The pipeline will continue by reading all supported document files.",
            file=sys.stderr,
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
    out["email"] = extract_email(text)
    return out


_FOLDER_NAME_PLACEHOLDERS = {"", "(unnamed)", "(manual run)"}


def _resolve_folder_name(source_dir: Path | None) -> str:
    """Return the authoritative Drive folder name.

    The FOLDER_NAME env var (set by the workflow from
    client_payload.folder_name) is authoritative — that is the actual Drive
    folder name Paola dropped, not the cloud runner's `/tmp/spotlight-source`
    download path. We fall back to the source dir name only for local
    development, where the operator names the --source folder after the
    Drive folder so the same parser works without the env var.
    """
    env_name = (os.environ.get("FOLDER_NAME") or "").strip()
    if env_name and env_name not in _FOLDER_NAME_PLACEHOLDERS:
        return env_name
    if source_dir is None:
        return ""
    return source_dir.name.strip()


def parse_folder_identity(source_dir: Path | None = None) -> dict[str, str | None]:
    """Parse parent/student/school from the Drive folder name.

    Prefers the FOLDER_NAME env var (set by the GitHub Actions workflow
    from the Apps Script dispatch payload). Falls back to source_dir.name
    when the env var is absent so local dev keeps working.

    Expected convention: "{Parent} - {Student} - {School}".
    If there are only 2 segments, assume the first segment is the student
    name and the second segment is the school.
    """
    name = _resolve_folder_name(source_dir)
    parts = [part.strip() for part in name.split(" - ") if part.strip()]
    if len(parts) == 1:
        return {"parent_full_name": None, "student_name": None, "school": None}
    if len(parts) == 2:
        return {
            "parent_full_name": None,
            "student_name": parts[0] or None,
            "school": parts[1] or None,
        }

    parent_full_name = parts[0]
    school = parts[-1]
    student_name = " - ".join(parts[1:-1])
    return {
        "parent_full_name": parent_full_name or None,
        "student_name": student_name or None,
        "school": school or None,
    }


def scan_transcript_email(source_texts: dict[str, str]) -> str | None:
    """Prefer an email address extracted from a parent call transcript file."""
    for name, text in source_texts.items():
        if re.search(r"\b(transcription|transcript|call)\b", name.lower()):
            email = extract_email(text)
            if email:
                return email
    return None


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

    supported_files = [
        path for path in all_files
        if path.suffix.lower() in SUPPORTED_EXTENSIONS
        or (path.suffix.lower() in IMAGE_EXTENSIONS and is_readable_score_image(path.name))
    ]
    # Visibility: flag images we are NOT reading (not a score report), so a
    # misnamed score report can be caught at intake rather than silently lost.
    for path in all_files:
        if path.suffix.lower() in IMAGE_EXTENSIONS and not is_readable_score_image(path.name):
            print(
                f"  Skipping image (not recognized as a score report): {path.name}. "
                "Rename to include e.g. 'i-Ready' / 'MAP' / 'score' to read it.",
                file=sys.stderr,
            )
    if not supported_files:
        raise OrchestratorError(
            "No supported document files were found in the source folder. "
            "The folder must contain at least one readable .txt, .pdf, .docx, or "
            "score-report image file."
        )

    source_texts: dict[str, str] = {}
    for path in supported_files:
        # HARD-FAIL on an unreadable source: never silently drop a file and ship
        # a case study missing (e.g.) its lesson report. Stop and tell the
        # operator to supply a text export instead.
        try:
            text = extract_text(path)
        except OrchestratorError as exc:
            raise OrchestratorError(
                f"Could not read source file {path.name}: {exc} "
                "Aborting rather than drafting a case study with a missing "
                "source. Fix or re-export this file and re-run."
            )
        if not text.strip():
            raise OrchestratorError(
                f"Source file {path.name} extracted to empty text. Aborting "
                "rather than drafting with a missing source — re-export it as "
                "readable text (.txt/.docx) and re-run."
            )
        source_texts[path.name] = text
        if args.verbose:
            print(f"Extracted {len(text)} chars from {path.name}")

    if not source_texts:
        raise OrchestratorError(
            "No readable documents were found in the source folder. "
            "At least one readable .txt, .pdf, or .docx file is required."
        )

    # Per-run staging dir keyed by run_id — never a shared path another run
    # can write. Cleared at the start of this run so a recycled run_id or a
    # half-written prior attempt can't surface stale source text.
    run_dir = pending_dir_for_run(run["run_id"])
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    save_extracted_texts(run_dir, source_texts)

    category_names = {k: [p.name for p in v] for k, v in categories.items()}
    (run_dir / "source_categories.json").write_text(
        json.dumps(category_names, indent=2, ensure_ascii=False)
    )

    run.update(
        {
            "stage": "read_sources",
            "source_files": [str(p.resolve()) for p in all_files],
            "source_categories": category_names,
            "source_categories_path": str((run_dir / "source_categories.json").resolve()),
            "extracted_texts_path": str((run_dir / "source_texts.json").resolve()),
        }
    )
    if args.verbose:
        print("Detected source categories:")
        for category, paths in category_names.items():
            print(f"  {category}: {paths}")
    update_run(run["run_id"], run)
    return run


def _load_brief_fields(run: dict) -> dict:
    """Read Paola's brief text from the extracted-texts cache and parse it."""
    cache = Path(run["extracted_texts_path"]).read_text()
    source_texts = json.loads(cache)
    brief_text = ""
    brief_candidates = []
    for name, text in source_texts.items():
        if re.search(r"\b(brief|survey|handoff|spotlight)\b", name.lower()):
            brief_candidates.append((name, text))
    if brief_candidates:
        brief_text = brief_candidates[0][1]
    if not brief_text:
        return {}
    return parse_paola_brief(brief_text)


def stage_hubspot(args: argparse.Namespace, run: dict) -> dict:
    """Identify the family in HubSpot.

    Strategy:
      1. Pull a candidate parent email from Paola's brief or from parent call transcripts.
      2. If an email is present, try HubSpot lookup by that email.
      3. If the email is missing or doesn't match any contact, continue without hard failure.
      4. Record any fallback identity information from the folder name so downstream
         drafting and anonymization can proceed.
    """
    brief = _load_brief_fields(run)
    source_dir = Path(run["source"])
    folder_identity = parse_folder_identity(source_dir)
    if args.skip_hubspot:
        print("Skipping HubSpot lookup by request.")
        run.update(
            {
                "stage": "hubspot",
                "hubspot_contact": None,
                "brief_fields": brief,
                "folder_identity": folder_identity,
            }
        )
        update_run(run["run_id"], run)
        return run

    source_texts = json.loads(Path(run["extracted_texts_path"]).read_text())
    email = brief.get("email") or scan_transcript_email(source_texts)
    if email:
        print(f"  Searching HubSpot by email: {email}")
    else:
        print("  No parent email found in Paola's brief or call transcripts; HubSpot lookup will be skipped.")

    contact = None
    lookup_kind = None
    hubspot_lookup_error = None
    if email:
        try:
            contact = call_hubspot_lookup(email)
            lookup_kind = "email"
        except HubSpotNotFound:
            hubspot_lookup_error = f"Email lookup for {email} returned no results."
            print(f"  {hubspot_lookup_error}")
        except HubSpotAmbiguous as exc:
            hubspot_lookup_error = str(exc)
            print(f"  HubSpot email lookup is ambiguous: {hubspot_lookup_error}")

    if contact is None and email:
        print(
            "  HubSpot lookup did not return a single contact. "
            "Proceeding with folder-name / source fallback instead of failing."
        )

    run.update(
        {
            "stage": "hubspot",
            "hubspot_contact": None if contact is None else {
                "contact_id": contact.get("id"),
                "email": contact.get("properties", {}).get("email") or email,
                "firstname": contact.get("properties", {}).get("firstname"),
                "lastname": contact.get("properties", {}).get("lastname"),
                "company": contact.get("properties", {}).get("company"),
                "school": contact.get("properties", {}).get("student_school"),
                "lookup_kind": lookup_kind,
            },
            "hubspot_email_candidate": email,
            "hubspot_lookup_error": hubspot_lookup_error,
            "brief_fields": brief,
            "folder_identity": folder_identity,
        }
    )
    update_run(run["run_id"], run)
    return run


def _resolve_student_identity(args: argparse.Namespace, run: dict) -> tuple[str, str | None, str | None]:
    """Return (firstname, lastname, school) using Paola's parsed brief first,
    then folder-name convention, then --student-name / --school args.
    HubSpot returns the parent's contact (used to verify school context only),
    so firstname/lastname must come from brief/folder/args, never from HubSpot."""
    brief = run.get("brief_fields") or {}
    folder_identity = run.get("folder_identity") or parse_folder_identity(Path(run["source"]))
    contact = run.get("hubspot_contact") or {}

    folder_student = folder_identity.get("student_name")
    folder_parent = folder_identity.get("parent_full_name")
    folder_school = folder_identity.get("school")

    # Student firstname: folder → brief → args (folder is authoritative —
    # it is the literal Drive folder name Paola typed, propagated to the
    # runner via the FOLDER_NAME env var).
    firstname = (
        (folder_student.split()[0] if folder_student else None)
        or brief.get("student_firstname")
        or args.student_name
    )
    # Student lastname: folder → brief → args (same priority as firstname).
    lastname = (
        (
            " ".join(folder_student.split()[1:])
            if folder_student and len(folder_student.split()) > 1
            else None
        )
        or brief.get("student_lastname")
    )
    # School: folder → args → contact.student_school → brief.
    # Paola's folder names carry the school explicitly; the workflow's
    # FOLDER_NAME makes that authoritative on the runner too.
    school = (
        folder_school
        or args.school
        or (contact.get("student_school") if contact else None)
        or brief.get("school")
    )

    if not firstname:
        raise OrchestratorError(
            "Could not determine the student's real first name from Paola's brief, "
            "the folder name, or --student-name. Stop."
        )

    if folder_parent and not run.get("parent_full_name"):
        run["parent_full_name"] = folder_parent

    return firstname, lastname, school


def _normalize_identity_token(s: str | None) -> str:
    """Lowercase, strip non-letters, collapse doubled letters so spelling
    variants (Johny/Johnny, Hanna/Hannah) compare equal. Used only by the
    cross-run identity guard below — never by the anonymization gate."""
    s = re.sub(r"[^a-z]", "", (s or "").lower())
    return re.sub(r"(.)\1+", r"\1", s)


def _identity_consistent(a: str | None, b: str | None) -> bool:
    """Whether two first-name tokens plausibly name the same student.
    Tolerates spelling variants and nickname/formal-name prefixes
    (Alex/Alexander, Sam/Samuel) so the guard does not false-fail."""
    na, nb = _normalize_identity_token(a), _normalize_identity_token(b)
    if not na or not nb:
        return True
    if na == nb:
        return True
    if len(na) >= 3 and len(nb) >= 3 and (na.startswith(nb) or nb.startswith(na)):
        return True
    return False


def _assert_source_matches_folder(run: dict, source_texts: dict[str, str]) -> None:
    """Hard-stop if this run's cached source text does not belong to the
    student named by the folder. The staging cache is now run-scoped, but
    this is the last safe point before the draft prompt is built from
    `source_texts`, so we verify identity here too (defense in depth).

    Fires only when the folder names a student (the authoritative production
    identity from FOLDER_NAME); local runs without a 3-segment folder name
    have nothing external to compare against and are left to the run-scoping
    fix alone.
    """
    folder_identity = run.get("folder_identity") or parse_folder_identity(Path(run["source"]))
    folder_student = (folder_identity or {}).get("student_name")
    folder_first = folder_student.split()[0] if folder_student else None
    if not folder_first:
        return

    # (a) Folder first name vs the first name parsed from the cached brief —
    #     two independent identity sources that must agree.
    brief_first = (run.get("brief_fields") or {}).get("student_firstname")
    if brief_first and not _identity_consistent(folder_first, brief_first):
        raise OrchestratorError(
            "Cross-run identity mismatch before draft: folder names student "
            f"{folder_first!r} but the cached source brief names {brief_first!r}. "
            "The extracted source text does not belong to this run (stale or "
            "bled source cache). Refusing to draft."
        )

    # (b) The folder's student first name must actually appear in the cached
    #     source documents (Paola's brief always carries the real first name,
    #     so a correct cache always satisfies this). If it does not, the cache
    #     belongs to a different student.
    target = _normalize_identity_token(folder_first)
    tokens = {
        _normalize_identity_token(t)
        for t in re.findall(r"[A-Za-z]+", "\n".join(source_texts.values()))
    }
    if target and target not in tokens:
        raise OrchestratorError(
            f"Cross-run identity guard: the student first name {folder_first!r} "
            "from the folder does not appear anywhere in the extracted source "
            "text for this run. The source cache does not match the student — "
            "refusing to draft (prevents a prior run's text/pseudonym from "
            "bleeding into this case study)."
        )


def stage_bundle(args: argparse.Namespace, run: dict) -> dict:
    real_firstname, real_lastname, school = _resolve_student_identity(args, run)

    # Gender from source texts (parent pronouns carry through to published
    # quotes, so the pseudonym must match — otherwise the body keeps "he/his"
    # while the pull-quote graphic gets bracket-edited to "[she]/[her]").
    run_source_root = Path(run["extracted_texts_path"]).parent
    source_texts = json.loads((run_source_root / "source_texts.json").read_text())
    # Last safe point before the draft consumes source_texts: confirm the
    # cache actually belongs to this run's student.
    _assert_source_matches_folder(run, source_texts)
    gender = classify_gender(source_texts, run.get("brief_fields"))
    print(f"  Inferred gender: {gender}")

    # Variety + idempotency: reuse this student's existing name if they already
    # have a draft at their school; otherwise pick a fresh, unused name.
    pseudonym = assign_student_pseudonym(real_firstname, gender, run.get("school"))
    print(f"  Real first name: {real_firstname}  ->  pseudonym: {pseudonym}")

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    bundle_dir = build_bundle_path(pseudonym, date_str)
    if bundle_dir.exists():
        raise OrchestratorError(
            f"Bundle directory already exists: {bundle_dir}. "
            "Delete it or pick a different date to re-run."
        )

    copy_source_files(bundle_dir, [Path(p) for p in run["source_files"]])
    save_extracted_texts(bundle_dir, source_texts)

    bundle_manifest = {
        "bundle_path": str(bundle_dir.resolve()),
        "real_firstname": real_firstname,
        "real_lastname": real_lastname,
        "pseudonym": pseudonym,
        "gender": gender,
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
            "gender": gender,
            "school": school,
        }
    )
    update_run(run["run_id"], run)
    return run


# ---------------------------------------------------------------------------
# Stage 3.5: name registry — extract every real person once, assign ONE
# canonical pseudonym each, so every downstream stage reads the same map
# (no more a parent showing up as "Susan" on one card and "Adriana" on another).
# ---------------------------------------------------------------------------

NAME_EXTRACTION_SYSTEM = (
    "You extract the real people named in K-12 case-study source documents so "
    "they can be consistently anonymized. Output STRICT JSON, no markdown "
    "fence, exactly:\n"
    '{"people": [{"name": "<as written in the sources>", '
    '"role": "<student|parent|guardian|sibling|tutor|tor|other>", '
    '"gender": "<girl|boy|unknown>", "is_quoted": <true|false>}]}\n'
    "Rules:\n"
    "- One entry per DISTINCT person; use the fullest form of the name seen.\n"
    "- role 'student' = the child the case study is about; 'parent'/'guardian' "
    "= a caregiver; 'tutor' = the A+ tutor; 'tor' = teacher of record / school "
    "teacher; 'sibling'; 'other' = anyone else named.\n"
    "- gender from pronouns/context; 'unknown' if unclear.\n"
    "- is_quoted = true only if the person is directly quoted.\n"
    "- Do NOT include A+ Tutoring internal staff — the intake coordinator who "
    "wrote the brief (e.g. Paola) or any A+ marketing/admin team member. Only "
    "people in the student's actual story: the student, their family, their A+ "
    "tutor, and school teachers (TOR).\n"
    "- Include every other named real person. Never invent names."
)

# A+ Tutoring internal staff who appear in intake briefs but are NOT case-study
# subjects. Dropped from the registry (unless the same first name is genuinely a
# family member) so they don't consume a pseudonym slot or land in the table.
A_PLUS_STAFF_FIRST_NAMES = {"paola", "danielle", "roman"}


def _extract_people(source_texts: dict[str, str]) -> list[dict]:
    blob = "\n\n".join(f"--- {n} ---\n{t}" for n, t in source_texts.items())
    raw = claude_complete(
        NAME_EXTRACTION_SYSTEM,
        blob + "\n\nReturn strict JSON only.",
        max_tokens=2000,
        temperature=0,
    )
    try:
        data = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError as e:
        raise OrchestratorError(
            f"Name extraction returned invalid JSON: {e}. First 300 chars: {raw[:300]!r}"
        )
    return data.get("people", []) or []


def build_name_registry(run: dict, source_texts: dict[str, str]) -> dict:
    """Return {category, entries:[{real, role, action, pseudonym}]} pinning ONE
    canonical replacement per real name. action ∈ replace|keep. Family members
    inherit the student's cultural category so a Latino student's mom gets a
    Latino adult name; tutors are kept verbatim (brand rule)."""
    student_first = run["real_firstname"]
    student_pseud = (run["pseudonym"] or "").capitalize()
    student_gender = run.get("gender") if run.get("gender") in PSEUDONYM_GENDERS else "girl"
    # Per-school culture: family pseudonyms reflect the school's demographic
    # (your choice), so a parent at a Latino-demographic school gets a Latino
    # adult name regardless of the student's first name.
    category = school_culture_category(run.get("school"))

    entries: list[dict] = []
    used = {student_pseud.lower()}
    # Student first-name spelling variants -> the student pseudonym.
    student_variants = firstname_variants_in_sources(student_first, source_texts)
    student_real_lowers = {v.lower() for v in student_variants}
    for v in student_variants:
        entries.append({"real": v, "role": "student", "action": "replace", "pseudonym": student_pseud})

    assigned: dict[str, str] = {}  # real-first-lower -> pseudonym (dedupe same person)
    for p in _extract_people(source_texts):
        name = (p.get("name") or "").strip()
        if not name:
            continue
        first = name.split()[0]
        fl = first.lower()
        role = (p.get("role") or "other").lower()
        if role == "student" or fl in student_real_lowers:
            continue  # already covered by the student variants above
        if fl in assigned:
            continue  # same person seen twice
        if fl in A_PLUS_STAFF_FIRST_NAMES and role not in ("parent", "guardian", "sibling"):
            continue  # A+ internal staff (intake coordinator etc.), not a subject
        if role == "tutor":
            entries.append({"real": first, "role": "tutor", "action": "keep", "pseudonym": first})
            assigned[fl] = first
            continue
        if role not in ROLE_COHORT:
            role = "other"
        gender = (p.get("gender") or "").lower()
        if gender not in PSEUDONYM_GENDERS:
            gender = "girl" if role in ("parent", "guardian") else student_gender
        pseud = pick_pseudonym(name, gender, category, ROLE_COHORT[role], used)
        used.add(pseud.lower())
        assigned[fl] = pseud
        entries.append({"real": first, "role": role, "action": "replace", "pseudonym": pseud})

    return {"category": category, "entries": entries}


def registry_replacements(registry: dict) -> list[tuple[str, str]]:
    """(real, pseudonym) pairs to swap in Doc 1, longest real first so a short
    name can't partially consume a longer one."""
    pairs = [
        (e["real"], e["pseudonym"])
        for e in (registry or {}).get("entries", [])
        if e.get("action") == "replace" and e.get("real") and e.get("pseudonym")
    ]
    return sorted(pairs, key=lambda p: len(p[0]), reverse=True)


def stage_names(args: argparse.Namespace, run: dict) -> dict:
    bundle = Path(run["bundle_path"])
    source_texts = json.loads((bundle / "source_texts.json").read_text())
    registry = build_name_registry(run, source_texts)
    (bundle / "name-map.json").write_text(
        json.dumps(registry, indent=2, ensure_ascii=False)
    )
    print(
        f"  Name registry ({registry['category']}): {len(registry['entries'])} entr(ies):"
    )
    for e in registry["entries"]:
        verb = "KEEP" if e["action"] == "keep" else "->"
        print(f"    {e['real']!r} [{e['role']}] {verb} {e['pseudonym']!r}")
    run.update(
        {
            "stage": "names",
            "name_map_path": str((bundle / "name-map.json").resolve()),
            "name_registry": registry,
        }
    )
    update_run(run["run_id"], run)
    return run


# ---------------------------------------------------------------------------
# Stage 4: draft — Doc 1 (anonymized) + Doc 2 (archive with name-mapping table)
# ---------------------------------------------------------------------------

DRAFT_DOC1_DELIM = "===== DOC 1: PUBLISHED CASE STUDY (anonymized) ====="
DRAFT_DOC2_DELIM = "===== DOC 2: ARCHIVE (un-anonymized, NEVER published) ====="


# Fixed anonymization note that opens every published case study. Deterministic
# (not LLM-generated) so the privacy statement is exact and consistent. It is
# what lets a story responsibly mention a specific, person-first diagnosis.
# ONE short privacy note that covers consent + anonymization + the real tutor,
# so the published doc carries a single statement (not this plus an LLM-written
# "names have been changed" note).
ANONYMIZATION_DISCLAIMER = (
    "_A note on privacy: this is a real A+ Tutoring student's story, shared with "
    "their family's consent. Names and identifying details have been changed to "
    "protect their privacy; the tutor is named with permission._"
)


def _strip_llm_privacy_note(doc1: str) -> str:
    """Drop any privacy/anonymization disclaimer the drafting model added on its
    own (e.g. 'Note: To protect privacy, names have been changed.') so it does
    not duplicate the canonical note injected below. Targets paragraphs that
    read like a names-changed disclaimer; leaves real body prose alone."""
    kept = []
    for para in doc1.split("\n\n"):
        low = para.lower()
        is_privacy_note = (
            "name" in low and "chang" in low
            and ("privacy" in low or "protect" in low or "identifying" in low)
            and "note on privacy" not in low  # never strip the canonical one
            and len(para) < 400
        )
        if is_privacy_note:
            continue
        kept.append(para)
    return "\n\n".join(kept)


def _insert_disclaimer_after_h1(doc1: str) -> str:
    """Strip any model-written privacy note, then place the single canonical
    anonymization note as the first thing under the H1 title."""
    if ANONYMIZATION_DISCLAIMER.strip() in doc1:
        return doc1  # idempotent (resume/re-run safety)
    doc1 = _strip_llm_privacy_note(doc1)
    parts = doc1.split("\n", 1)
    if parts and parts[0].lstrip().startswith("#"):
        rest = parts[1].lstrip("\n") if len(parts) > 1 else ""
        return f"{parts[0]}\n\n{ANONYMIZATION_DISCLAIMER}\n\n{rest}"
    return f"{ANONYMIZATION_DISCLAIMER}\n\n{doc1}"


def _build_draft_system_prompt() -> str:
    skill = load_skill("aplus-spotlight-case-study")
    inclusive = load_skill("aplus-inclusive-language")
    return (
        "You are the A+ Tutoring spotlight case-study drafting agent. "
        "Follow the SKILL spec below verbatim — the 8-section Hero's Journey "
        "structure, the 1,200-1,500 word count, the pull-quote grammar gate, "
        "the anonymization protocol, the parent-facing voice cues. ALSO obey "
        "the inclusive-language rules: person-first disability language ('a "
        "student who has dyslexia,' never 'a dyslexic student') and accurate, "
        "non-deficit English-learner terminology. Output two documents "
        "separated by the literal delimiters provided in the user "
        "instructions. Do not add commentary outside the documents.\n\n"
        "===== aplus-spotlight-case-study SKILL.md =====\n\n" + skill +
        "\n\n===== aplus-inclusive-language SKILL.md =====\n\n" + inclusive
    )


def _collapse_doubles(s: str) -> str:
    """Lowercase and collapse any run of a repeated letter to one, so
    doubled-consonant spelling variants compare equal
    ('Johnny' -> 'johny', 'Johny' -> 'johny', 'Aaron' -> 'aron')."""
    return re.sub(r"(.)\1+", r"\1", (s or "").lower())


def firstname_variants_in_sources(real_firstname: str, source_texts: dict[str, str]) -> list[str]:
    """Distinct surface spellings of the student's first name that appear in
    the source docs, by doubled-consonant-collapse equivalence (Johny/Johnny),
    ordered by frequency (canonical/most-common first). The resolved spelling
    is always included even if it never appears verbatim in the sources.

    This feeds the real->pseudonym mapping so the replacement step catches a
    source spelling that differs from the folder/brief spelling. The pseudonym
    hash stays on the resolved name — variants only widen what gets replaced."""
    target = _collapse_doubles(re.sub(r"[^A-Za-z]", "", real_firstname or ""))
    counts: dict[str, int] = {}
    if target:
        blob = "\n".join(source_texts.values())
        for tok in re.findall(r"\b[A-Za-z][A-Za-z'’-]*\b", blob):
            core = re.sub(r"[^A-Za-z]", "", tok)
            if core and _collapse_doubles(core) == target:
                counts[tok] = counts.get(tok, 0) + 1
    if real_firstname:
        counts.setdefault(real_firstname, counts.get(real_firstname, 0))
    return sorted(counts, key=lambda t: (-counts[t], -len(t), t.lower()))


def _doubled_letter_variant_pattern(token: str) -> str:
    """Regex source matching `token` with any letter allowed to repeat, so
    doubled-consonant spellings (Johny <-> Johnny) are covered. Mirrors the
    gate's matcher in check-anonymization.py so this sweep replaces everything
    the gate would flag."""
    return "".join(
        (re.escape(ch) + "+") if ch.isalpha() else re.escape(ch) for ch in token
    )


def anonymize_firstname_variants(
    text: str, real_firstname: str, source_texts: dict[str, str], pseudonym: str
) -> tuple[str, int]:
    """Deterministically replace every spelling variant of the student's real
    first name (and doubled-consonant forms) with the pseudonym in Doc 1, as a
    safety net for occurrences the drafting LLM failed to anonymize. Word-
    boundary, case-insensitive. Returns (new_text, replacement_count).

    Scope is the STUDENT first name only — the highest-frequency leak. The
    anonymization gate remains the hard backstop for every other token; this
    only makes the replacement catch more, it does not relax the check.

    Caveat: a first name that is also a common word (Faith, Grace, Hope) would
    be over-replaced. Such drafts are reviewed at Gate 2 before publish.
    """
    variants = firstname_variants_in_sources(real_firstname, source_texts)
    if not variants:
        return text, 0
    replacement = (pseudonym or "").capitalize()
    if not replacement:
        return text, 0
    total = 0
    # Longest variant first so a shorter spelling can't partially consume it.
    for v in sorted(set(variants), key=len, reverse=True):
        pattern = re.compile(
            rf"\b{_doubled_letter_variant_pattern(v)}\b", re.IGNORECASE
        )
        text, n = pattern.subn(replacement, text)
        total += n
    return text, total


def anonymize_all_names(
    text: str,
    registry: dict | None,
    real_firstname: str,
    source_texts: dict[str, str],
    pseudonym: str,
) -> tuple[str, int]:
    """Deterministically replace EVERY real first name in the canonical registry
    (student variants + parents/guardians/siblings/etc.) with its pinned
    pseudonym in Doc 1, after brand-check. Word-boundary, case-insensitive,
    doubled-consonant tolerant. Tutors (action=keep) are left verbatim. Falls
    back to the student-first-name-only sweep when no registry is present.

    Same common-word caveat as the firstname sweep: a name that is also an
    English word can be over-replaced; drafts are reviewed at Gate 2.
    """
    pairs = registry_replacements(registry) if registry else []
    if not pairs:
        return anonymize_firstname_variants(text, real_firstname, source_texts, pseudonym)
    total = 0
    for real, pseud in pairs:  # registry_replacements is already longest-first
        pattern = re.compile(
            rf"\b{_doubled_letter_variant_pattern(real)}\b", re.IGNORECASE
        )
        text, n = pattern.subn(pseud, text)
        total += n
    return text, total


def _build_draft_user_prompt(
    *,
    real_firstname: str,
    real_lastname: str | None,
    pseudonym: str,
    school: str | None,
    source_texts: dict[str, str],
    registry: dict | None = None,
) -> str:
    sources_block = "\n\n".join(
        f"--- {name} ---\n{text}" for name, text in source_texts.items()
    )
    real_full = f"{real_firstname} {real_lastname}" if real_lastname else real_firstname
    # Mapping table is seeded from the canonical name registry so every person
    # has ONE pinned pseudonym. Fall back to student spelling variants only if
    # the registry is unavailable (older runs / resume).
    if registry and registry.get("entries"):
        mapping_rows = "\n".join(
            f"| {e['real']} | {e['pseudonym']} |" for e in registry["entries"]
        )
    else:
        name_variants = firstname_variants_in_sources(real_firstname, source_texts)
        mapping_rows = "\n".join(
            f"| {v} | {pseudonym.capitalize()} |" for v in name_variants
        ) or f"| {real_firstname} | {pseudonym.capitalize()} |"
    return f"""Draft the master case study for this student.

REAL NAME (use only in Doc 2): {real_full}
PSEUDONYM (use in Doc 1): {pseudonym}
SCHOOL: {school or "(unknown — anonymize as 'a charter school in California')"}

Output format — two documents separated by the exact delimiters below.

{DRAFT_DOC1_DELIM}
<Document 1 here — anonymized, 1,200-1,500 words, the 8 Hero's Journey
sections from the SKILL spec, parent-facing voice, pull quotes marked
inline with [PULL QUOTE]. Start with a markdown H1 title using the
pseudonym. Do NOT include real names anywhere in Document 1.

Do NOT add any privacy, anonymization, or "names have been changed"
disclaimer, note, or footer of your own — a single standard privacy
note is appended automatically. Document 1 must contain no such note.

DO NOT include the SEO metadata frontmatter block at the top of
Document 1. The SKILL spec describes a "--- SEO METADATA ... ---"
header block for human-handoff workflows. In this orchestrated
pipeline the SEO source-of-truth is the separate metadata.md file
produced by Stage 7; including a frontmatter block in Document 1
makes the HubSpot publisher render the entire block as visible body
text. Document 1 MUST start with the markdown H1 title and nothing
above it. No "---", no "SEO METADATA" label, no url_slug or meta_title
or meta_description lines at the top of the file.>

{DRAFT_DOC2_DELIM}
<Document 2 here — same structure as Doc 1 but with real names restored.
Include at the end a section "## Name-mapping table" formatted as a
two-column markdown table:

| Real | Published |
|------|-----------|
{mapping_rows}
| (any other real-name token) | (its published replacement) |

CRITICAL — the rows above are the CANONICAL name map for this case study.
Each real name has ONE pinned replacement. Use EXACTLY that replacement for
that person EVERYWHERE in Doc 1 — body prose, pull quotes, and the
attribution line. Never invent a different pseudonym, never vary it, never
use two different names for the same person. (Rows where Real == Published
are kept verbatim, e.g. the tutor.) Spelling variants of the student's name
all map to the same student pseudonym.

Every distinct real-name token that appears in the sources MUST appear
in this table — student first/last name, parent name(s), tutor name(s),
TOR name(s), school name.

ANONYMIZATION RULES — apply these strictly when writing Doc 1 and when
populating the mapping table:

- Parent / guardian / sibling / other first names: use the EXACT pinned
  replacement from the canonical map above — do not choose your own. The
  real first name never appears in Doc 1.
- Parent last names: dropped from Doc 1 entirely. Mapping row uses
  `(dropped)`.
- Student last name: dropped from Doc 1 entirely. Mapping row uses
  `(dropped)`.
- Tutor first name + last initial: KEEP verbatim (tutors are part of
  the brand promise). Mapping row sets Real == Published.
- TOR (teacher-of-record) names: pseudonymize if quoted in Doc 1,
  otherwise refer to as "his teacher" / "her teacher" without naming.
- School name: anonymize in Doc 1 to "a charter school in [region]"
  unless the school is on the explicit-permission list. Mapping row
  shows the real name on the left and the anonymized phrase on the
  right.
- Email addresses, phone numbers, exact addresses: dropped, mapping
  row uses `(dropped)`.
- For tokens that are kept verbatim in Doc 1 (tutor first names,
  permission-granted schools), set Real == Published.>

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


class BrandCheckFailure(OrchestratorError):
    pass


def brand_check_and_clean(doc1_text: str) -> tuple[str, list[str]]:
    """Run aplus-brand-check on Doc 1 and return (cleaned_text, violations).

    Single Claude call: the brand-check SKILL is loaded as the system
    prompt, and Claude is asked to both list violations AND rewrite the
    document to clear them. If the document already passes, `cleaned_text`
    is the input verbatim and `violations` is empty.

    The cleaned text preserves the document's structure: SEO metadata
    header, H1, H2 sections, [PULL QUOTE] markers, attributions, and CTA.
    Only the offending tokens are rewritten.
    """
    skill = load_skill("aplus-brand-check")
    inclusive = load_skill("aplus-inclusive-language")
    system = (
        "You are the A+ Tutoring brand-check enforcement layer. The SKILLs "
        "below list every rule. Apply the CRITICAL FAILURES section "
        "(em dashes, banned phrases, AI-detection vocabulary, profanity, "
        "corporate fluff, rule-of-three, AI opener patterns, "
        "adverb-adjective inflation) and any B2C brand-kit rules that "
        "apply to a parent-facing case-study blog post. Skip B2B-only "
        "rules and rules tagged 'blog post' that don't apply to a "
        "case-study channel.\n\n"
        "ALSO enforce the inclusive-language SKILL: rewrite any non-person-"
        "first disability phrasing ('a dyslexic student' -> 'a student who has "
        "dyslexia'), deficit/pity framing, and incorrect or deficit English-"
        "learner terminology. Follow a family's stated preference if the doc "
        "records one. Do NOT edit person-first phrasing inside a verbatim "
        "parent/tutor quote — leave quotes intact.\n\n"
        "Output strict JSON with NO surrounding markdown fence and NO "
        "commentary, exactly this shape:\n\n"
        '{\n'
        '  "violations": [\n'
        '    {"rule": "em dash", "location": "<short quote>", "fix": "<replacement>"}\n'
        '  ],\n'
        '  "cleaned": "<the full document text after applying every fix>"\n'
        '}\n\n'
        "If the document already passes every rule, return violations=[] "
        "and cleaned set to the input verbatim. NEVER drop sections, NEVER "
        "rename pseudonyms, NEVER remove or paraphrase any [PULL QUOTE] "
        "marker, NEVER change a verbatim source quote (the rule about "
        "verbatim quotes overrides em-dash and banned-word checks WITHIN "
        "the quoted text). Em dashes OUTSIDE quoted text must be replaced "
        "with periods, colons, or rephrased.\n\n"
        "===== aplus-brand-check SKILL.md =====\n\n" + skill +
        "\n\n===== aplus-inclusive-language SKILL.md =====\n\n" + inclusive
    )
    raw = claude_complete(system, doc1_text, max_tokens=12000)
    try:
        payload = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError as e:
        raise BrandCheckFailure(
            f"Brand-check returned invalid JSON: {e}. "
            f"First 300 chars: {raw[:300]!r}"
        )
    violations = payload.get("violations", []) or []
    cleaned = payload.get("cleaned", "").strip()
    if not cleaned:
        raise BrandCheckFailure("Brand-check returned empty `cleaned` field.")
    # Sanity guard: the cleaned doc should not have shrunk by more than 25%
    # — if it did, Claude probably dropped sections we'd lose.
    if len(cleaned) < int(len(doc1_text) * 0.75):
        raise BrandCheckFailure(
            f"Brand-check cleaned doc is suspiciously short "
            f"({len(cleaned)} chars vs {len(doc1_text)} input). Aborting "
            "rather than overwriting Doc 1 with a truncated version."
        )
    return cleaned, [
        f"{v.get('rule', '?')}: {v.get('location', '')} -> {v.get('fix', '')}"
        for v in violations
    ]


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
        registry=run.get("name_registry"),
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
            print(f"  Running brand-check on Doc 1...")
            doc1_clean, violations = brand_check_and_clean(doc1)
            if violations:
                print(f"    cleared {len(violations)} violation(s):")
                for v in violations:
                    print(f"      - {v}")
            else:
                print(f"    Doc 1 already brand-clean.")
            # Deterministic name sweep: replace any real-first-name variant the
            # drafting LLM left behind (incl. doubled-consonant spellings) with
            # the pseudonym, so the anonymization gate is not the only line of
            # defense. Runs AFTER brand-check so a rewrite can't reintroduce it.
            doc1_clean, n_swept = anonymize_all_names(
                doc1_clean, run.get("name_registry"), run["real_firstname"],
                source_texts, pseudonym,
            )
            if n_swept:
                print(
                    f"    Name sweep: replaced {n_swept} leaked real-name "
                    "token(s) with canonical pseudonyms."
                )
            # Open the published doc with the fixed anonymization note so readers
            # know the student/family are anonymized (only the tutor is real).
            doc1_clean = _insert_disclaimer_after_h1(doc1_clean)
            doc1_path.write_text(doc1_clean + "\n")
            doc2_path.write_text(doc2 + "\n")
            run.update(
                {
                    "stage": "draft",
                    "doc1_path": str(doc1_path.resolve()),
                    "doc2_path": str(doc2_path.resolve()),
                    "doc1_word_count": wc,
                    "brand_check_violations": violations,
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
      comic_stat: <SHORT non-sensitive headline result for the comic's win
                   badge, max ~7 chars, drawn from the case study's numbers,
                   e.g. "92%ile", "+34 pts", "+2 yrs", "Grade 6". NEVER a
                   protected classification (no IEP/ELL/disability/income).
                   Leave blank if there is no clean public stat.>
3. Outside the fence: `cta_url: https://meetings.hubspot.com/successful/consultation`
4. `## Pull quotes` heading then a list named pull_quotes with EXACTLY 2
   verbatim quotes from the source documents. Each must read as a
   complete grammatical sentence in isolation. Add bracketed editorial
   insertions if needed. Then a scalar `pull_quote_attribution: "<Parent
   first name>, <Pseudonym>'s mother"` (or father — match the source).

   Also produce two PARALLEL list fields used by the inline-embed step
   that drops pull-quote graphics into the HubSpot body after the
   paragraphs that contain each quote:

       inline_pull_quote_images:
         - "pull-quote-s1-with-logo.png"
         - "pull-quote-s2-with-logo.png"

   The image filenames are fixed by the graphics builders; emit them
   exactly as shown above.

   And a data-viz pair for the milestone timeline graphic:

       inline_data_viz_images:
         - "topic-graphic-with-logo.png"
       inline_data_viz_anchors:
         - "<a short verbatim phrase from Doc 1 prose that appears in the
            paragraph the timeline graphic should follow>"

   The anchor must be a unique substring of a Doc 1 paragraph the case
   study uses to introduce the "weeks of work" narrative. Pick a phrase
   that does NOT appear in any other paragraph (so the embedder anchors
   exactly once). Strip surrounding quotation marks. Keep it under 80
   characters. The graphic appears AFTER that paragraph, so anchor on
   prose near the end of "The Work" or just before "The Outcome".
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

    HARD CONSTRAINTS on milestone entries (the topic graphic is a
    matplotlib timeline; long labels overlap and render unreadable):
      - Topic: 1-3 words, max 14 characters. Examples: "Integer review",
        "Sign errors", "MAP retest", "Two-step eqs". Never a sentence.
      - Verbatim phrase: max 8 words, no quotation marks around it.
        Just the lift from the lesson note. Examples: "Caught his own
        sign error on #9", "Tried first on every problem".
      - Month / Week label: max 8 chars. "Feb", "Early Mar", "Week 6".
      - Prefer 4 milestones over 6 when the case study only has a few
        strong inflection points — fewer milestones space cleanly.

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

    # Canonical name map so pull_quote_attribution + any names inside the
    # pull quotes use the SAME pseudonyms as Doc 1 (no Susan-vs-Adriana split).
    registry = run.get("name_registry") or {}
    name_map_lines = "\n".join(
        f"  - {e['real']} ({e['role']}) -> {e['pseudonym']}"
        for e in registry.get("entries", [])
    )
    name_map_block = (
        "CANONICAL NAME MAP (use these EXACT names — the parent attribution and "
        "any name inside a pull quote must match Doc 1; never introduce a "
        "different pseudonym for the same person):\n" + name_map_lines + "\n\n"
        if name_map_lines
        else ""
    )

    user = (
        f"Pseudonym: {pseudonym}\n"
        f"School (canonical name): {school}\n"
        f"School URL slug: {school_slug}\n"
        f"Today's date: {today.isoformat()}\n"
        f"Target publish date: {target_publish.isoformat()}\n"
        f"student_ethnicity prose: {demographics}\n\n"
        + name_map_block +
        "DRAFT CASE STUDY (Doc 1):\n\n" + doc1 +
        "\n\nSOURCE LESSON / TUTOR TEXT (for milestone extraction):\n\n" +
        milestone_seed +
        "\n\nProduce the metadata.md content now. Output the file content only."
    )
    print(f"  Generating metadata.md...")
    # Inclusive-language rules apply to the social copy this stage produces
    # (Facebook headline/subhead, IG carousel + stories) — that's where the
    # "Liam is dyslexic" violation leaked, since the social copy isn't otherwise
    # language-checked.
    metadata_system = (
        METADATA_SYSTEM
        + "\n\nINCLUSIVE-LANGUAGE RULES (apply to EVERY field you write — "
        "FB/IG copy, carousel, captions, pull quotes): person-first disability "
        "language ('a student who has dyslexia,' never 'a dyslexic student'), "
        "no deficit/pity framing, accurate non-deficit English-learner terms. "
        "Follow a family's stated preference if recorded. Never edit a verbatim "
        "parent/tutor quote.\n\n"
        "===== aplus-inclusive-language SKILL.md =====\n\n"
        + load_skill("aplus-inclusive-language")
    )
    text = claude_complete(metadata_system, user, max_tokens=8000, temperature=0.2)
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


def _parse_meta_list(meta_text: str, field: str) -> list[str]:
    """Parse a simple `field:` / `  - "item"` YAML-ish list from metadata.md."""
    m = re.search(rf"^{re.escape(field)}:\s*$", meta_text, re.MULTILINE)
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


def _replace_meta_list(meta_text: str, field: str, new_items: list[str]) -> str:
    m = re.search(rf"^{re.escape(field)}:\s*$", meta_text, re.MULTILINE)
    if not m:
        raise OrchestratorError(f"metadata.md is missing `{field}:` list.")
    end_offset = m.end()
    for line in meta_text[m.end():].split("\n")[1:]:
        if not line.strip() or not line.strip().startswith("-"):
            break
        end_offset += len(line) + 1
    rebuilt = "\n".join(f'  - "{q}"' for q in new_items)
    return (
        meta_text[: m.end()] + "\n" + rebuilt + "\n" + meta_text[end_offset:]
    ).rstrip() + "\n"


def _embed_pull_quote_anchor(quote: str) -> str:
    """Mirror embed-pull-quotes.py's pull-quote anchor derivation exactly."""
    a = quote.strip().strip('"').strip("'").rstrip(".,;:")
    return a[:60]


def _embed_data_viz_anchor(anchor: str) -> str:
    """Mirror embed-pull-quotes.py's data-viz anchor derivation exactly."""
    a = anchor.strip().strip('"').strip("'")
    return a[:80]


ANCHOR_REPICK_SYSTEM = (
    "You re-align embed anchors to the FINAL published case-study body. You are "
    "given the final Doc 1 text and stale pull quotes and/or stale data-viz "
    "anchor phrases that no longer appear verbatim in it (the body was lightly "
    "rewritten by the brand-check / grammar passes after they were captured). "
    "For each stale item, return the closest VERBATIM replacement copied EXACTLY "
    "from the Doc 1 text provided — do not paraphrase, do not add or drop words, "
    "copy character for character including punctuation and casing.\n"
    "- Pull quote: return the full verbatim quote/sentence as it appears in Doc 1 "
    "(so its first 60 characters are an exact substring of Doc 1).\n"
    "- Data-viz anchor: return a unique verbatim phrase (<= 80 chars) from the "
    "SAME paragraph the timeline graphic should follow.\n"
    "Output strict JSON with NO markdown fence, exactly:\n"
    '{"pull_quotes": {"<stale quote>": "<verbatim replacement>"}, '
    '"data_viz_anchors": {"<stale anchor>": "<verbatim replacement>"}}\n'
    "Include only the stale items you were given. If an item has no verbatim "
    "equivalent in Doc 1, map it to an empty string."
)


def _llm_repick_embed_anchors(doc1: str, bad_quotes: list[str], bad_anchors: list[str]) -> dict:
    user = (
        "FINAL Doc 1 body:\n\n" + doc1
        + "\n\nStale items to re-pick (return verbatim replacements lifted from "
        "the body above):\n"
        + json.dumps(
            {"stale_pull_quotes": bad_quotes, "stale_data_viz_anchors": bad_anchors},
            ensure_ascii=False,
        )
        + "\n\nReturn strict JSON only."
    )
    raw = claude_complete(ANCHOR_REPICK_SYSTEM, user, max_tokens=2000, temperature=0)
    try:
        data = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError as e:
        raise OrchestratorError(
            f"Embed-anchor repair returned invalid JSON: {e}. "
            f"First 300 chars: {raw[:300]!r}"
        )
    return {
        "pull_quotes": data.get("pull_quotes", {}) or {},
        "data_viz_anchors": data.get("data_viz_anchors", {}) or {},
    }


def _verify_and_fix_embed_anchors(run: dict) -> None:
    """Ensure every embed anchor is a verbatim, case-insensitive substring of
    the FINAL cleaned Doc 1 body — the same text embed-pull-quotes.py matches
    against at insert time.

    Pull-quote anchors and inline_data_viz_anchors are captured before the
    brand-check / grammar passes finish mutating the body, so a rewritten
    sentence can break an anchor ('expected 3 insertions, got 2'). Re-pick any
    anchor that no longer matches, verify the replacement is verbatim in Doc 1,
    and hard-fail if it cannot be recovered rather than ship a broken embed.
    """
    bundle = Path(run["bundle_path"])
    doc1 = Path(run["doc1_path"]).read_text()
    doc1_l = doc1.lower()
    meta_path = bundle / "metadata.md"
    meta_text = meta_path.read_text()

    quotes = _parse_pull_quotes(meta_text)
    dv_anchors = _parse_meta_list(meta_text, "inline_data_viz_anchors")

    bad_q = [q for q in quotes if _embed_pull_quote_anchor(q).lower() not in doc1_l]
    bad_a = [a for a in dv_anchors if _embed_data_viz_anchor(a).lower() not in doc1_l]

    if not bad_q and not bad_a:
        print(
            f"  Embed-anchor check: {len(quotes)} quote + {len(dv_anchors)} "
            "data-viz anchor(s) all verbatim in final Doc 1."
        )
        return

    print(
        f"  Embed-anchor check: re-picking {len(bad_q)} quote + {len(bad_a)} "
        "data-viz anchor(s) that no longer match the cleaned Doc 1..."
    )
    repick = _llm_repick_embed_anchors(doc1, bad_q, bad_a)

    if bad_q:
        qmap = repick["pull_quotes"]
        new_quotes = []
        for q in quotes:
            if q in bad_q:
                fixed = (qmap.get(q) or "").strip()
                if not fixed or _embed_pull_quote_anchor(fixed).lower() not in doc1_l:
                    raise OrchestratorError(
                        "Embed-anchor repair could not find a verbatim Doc 1 "
                        f"replacement for pull quote: {q!r}. Fix metadata.md by hand."
                    )
                new_quotes.append(fixed)
            else:
                new_quotes.append(q)
        meta_text = _replace_pull_quotes(meta_text, new_quotes)

    if bad_a:
        amap = repick["data_viz_anchors"]
        new_anchors = []
        for a in dv_anchors:
            if a in bad_a:
                fixed = (amap.get(a) or "").strip()
                if not fixed or _embed_data_viz_anchor(fixed).lower() not in doc1_l:
                    raise OrchestratorError(
                        "Embed-anchor repair could not find a verbatim Doc 1 "
                        f"replacement for data-viz anchor: {a!r}. Fix metadata.md by hand."
                    )
                new_anchors.append(fixed)
            else:
                new_anchors.append(a)
        meta_text = _replace_meta_list(meta_text, "inline_data_viz_anchors", new_anchors)

    meta_path.write_text(meta_text)
    print("    metadata.md anchors re-synced to the final Doc 1 body.")


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
            # Anchors are now final (pull_quotes won't change again). Verify
            # every embed anchor is verbatim in the cleaned Doc 1 and re-pick
            # any the brand-check/grammar rewrites desynced. (BUG 1)
            _verify_and_fix_embed_anchors(run)
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


# ---------------------------------------------------------------------------
# Stage 10: graphics (shell out to the six builders + composite-logo)
# ---------------------------------------------------------------------------

class GraphicsFailure(OrchestratorError):
    pass


# Order matters: composite-logo runs LAST because it reads the PNGs the
# builders emit. The first six are image-generators (Gemini / OpenAI /
# matplotlib); composite is local-only PIL work.
GRAPHICS_BUILDERS: list[tuple[str, str]] = [
    ("hero+social-card",       "scripts/b2c/build-case-study-hero-card.py"),
    ("topic-graphic",          "scripts/b2c/build-case-study-topic-graphic.py"),
    ("pull-quotes",            "scripts/b2c/build-case-study-pull-quotes.py"),
    ("ig-carousel",            "scripts/b2c/build-case-study-ig-carousel.py"),
    ("ig-stories",             "scripts/b2c/build-instagram-stories.py"),
    ("facebook",               "scripts/b2c/build-case-study-facebook.py"),
    ("composite-logo",         "scripts/shared/composite-logo.py"),
    # Comic runs last: it's self-contained (own Gemini gen + own logo
    # compositing) and is the slowest step (~6 pro-image gens).
    ("comic",                  "scripts/b2c/build-case-study-comic.py"),
]


def _run_builder_with_retry(name: str, script: str, bundle: Path) -> bool:
    """Shell out to a builder with one retry on non-zero exit.

    Returns True on success; False if both attempts fail. On failure,
    flushes the last attempt's stdout and stderr so the orchestrator's
    GraphicsFailure has the full error context.
    """
    script_path = REPO_ROOT / script
    if not script_path.exists():
        print(f"  [{name}] script missing: {script_path}", file=sys.stderr)
        return False
    cmd = ["python3", str(script_path), "--bundle", str(bundle)]
    last_result = None
    for attempt in range(2):
        print(f"  [{name}] attempt {attempt + 1}...")
        last_result = subprocess.run(cmd, capture_output=True, text=True)
        if last_result.returncode == 0:
            # Echo a one-line summary of stdout so the run log shows what
            # the builder produced (useful for debugging "did Gemini ship
            # a real image or a 200-byte error blob").
            tail = (last_result.stdout or "").strip().splitlines()[-1:]
            if tail:
                print(f"    {tail[0]}")
            return True
        print(
            f"  [{name}] returncode={last_result.returncode} on attempt {attempt + 1}",
            file=sys.stderr,
        )
    if last_result is not None:
        sys.stderr.write("---- stdout ----\n")
        sys.stderr.write(last_result.stdout or "")
        sys.stderr.write("\n---- stderr ----\n")
        sys.stderr.write(last_result.stderr or "")
        sys.stderr.write("\n")
    return False


def stage_graphics(args: argparse.Namespace, run: dict) -> dict:
    bundle = Path(run["bundle_path"])
    meta_path = bundle / "metadata.md"
    if not meta_path.exists():
        raise GraphicsFailure(
            f"metadata.md missing in {bundle}. Stage 7 must run before graphics."
        )
    results: dict[str, str] = {}
    for name, script in GRAPHICS_BUILDERS:
        ok = _run_builder_with_retry(name, script, bundle)
        results[name] = "ok" if ok else "failed"
        if not ok:
            run.update({"stage": "graphics", "graphics_results": results})
            update_run(run["run_id"], run)
            raise GraphicsFailure(
                f"Graphics builder {name!r} ({script}) failed twice. "
                "See the stdout/stderr dump above. No further builders run."
            )

    # Verify the composite step produced the -with-logo variants the
    # Slack delivery pack expects. These are the assets paola receives.
    gfx = bundle / "graphics"
    expected = [
        "hero.png",  # ships without a composited logo by design
        "social-card-with-logo.png",
        "topic-graphic-with-logo.png",
        "pull-quote-s1-with-logo.png",
        "pull-quote-s2-with-logo.png",
        "facebook-with-logo.png",
        "instagram-carousel-slide-1-with-logo.png",
        "instagram-carousel-slide-2-with-logo.png",
        "instagram-carousel-slide-3-with-logo.png",
        "instagram-carousel-slide-4-with-logo.png",
        "instagram-carousel-slide-5-with-logo.png",
        "instagram-story-1.png",  # composited in build-instagram-stories.py
        "instagram-story-2.png",
        "instagram-story-3.png",
        # comic: representative feed + story frames (full set is 5 of each)
        "comic-1-struggle.png",
        "comic-5-cta.png",
        "comic-story-1-struggle.png",
        "comic-story-5-cta.png",
    ]
    missing = [name for name in expected if not (gfx / name).exists()]
    if missing:
        run.update({"stage": "graphics", "graphics_results": results, "graphics_missing": missing})
        update_run(run["run_id"], run)
        raise GraphicsFailure(
            f"Graphics builders ran but expected files are missing: {missing}"
        )

    run.update({"stage": "graphics", "graphics_results": results})
    update_run(run["run_id"], run)
    return run


# ---------------------------------------------------------------------------
# Stage 11: hashtags + captions (aplus-b2c-hashtag-analyst skill)
# ---------------------------------------------------------------------------

def _build_hashtag_user_prompt(*, pseudonym: str, school: str, doc1: str, meta_text: str) -> str:
    return (
        f"Pseudonym: {pseudonym}\n"
        f"School: {school}\n\n"
        "Case study draft (Doc 1):\n\n" + doc1 +
        "\n\nExisting metadata.md (already produced — for context, do NOT "
        "rewrite this content; only produce the four new sections below):\n\n"
        + meta_text +
        "\n\nProduce ONLY the four sections to append to metadata.md, in this "
        "exact format and order. Use YAML block scalars (`field: |`) with "
        "two-space indented content so downstream parsers pick them up. "
        "No em dashes anywhere. Use curly quotation marks if quoting. The "
        "pseudonym in the body and CTA must match the case study; never use "
        "real names.\n\n"
        "## Instagram caption (from aplus-b2c-hashtag-analyst)\n\n"
        "instagram_caption: |\n"
        "  <HOOK line>\n"
        "  \n"
        "  <40-60 word BODY paragraph>\n"
        "  \n"
        f"  Read {pseudonym.capitalize()}'s full story. Link in bio.\n"
        "  \n"
        "  #hashtag1\n"
        "  #hashtag2\n"
        "  #hashtag3\n"
        "  #hashtag4\n"
        "  #hashtag5\n\n"
        "## Instagram Story captions (one per frame, from aplus-b2c-hashtag-analyst)\n\n"
        "instagram_story_captions:\n"
        "  - \"\"\n"
        "  - \"\"\n"
        f"  - \"Tap to read {pseudonym.capitalize()}'s story \\u2192\"\n\n"
        "## Facebook caption (from aplus-b2c-hashtag-analyst)\n\n"
        "facebook_caption: |\n"
        "  <2-sentence HOOK paragraph>\n"
        "  \n"
        "  <80-120 word BODY paragraph>\n"
        "  \n"
        "  Read the full case study at blog.wetutorathome.com/case-study/<slug>\n\n"
        "## Hashtag research log (transparency for Roman)\n\n"
        "hashtag_research_notes:\n"
        "  - \"#hashtag1 (trending) — <rationale, audience match, approx post volume>\"\n"
        "  - \"#hashtag2 (trending) — <rationale>\"\n"
        "  - \"#hashtag3 (trending) — <rationale>\"\n"
        "  - \"#hashtag4 (brand voice) — <why this brand hashtag matches this case>\"\n"
        "  - \"#hashtag5 (Roman voice) — <why this Roman hashtag matches this case>\"\n\n"
        "Output the four sections above and NOTHING ELSE."
    )


def stage_hashtags(args: argparse.Namespace, run: dict) -> dict:
    bundle = Path(run["bundle_path"])
    meta_path = bundle / "metadata.md"
    if not meta_path.exists():
        raise OrchestratorError(
            f"metadata.md missing in {bundle}; Stage 7 must run before hashtags."
        )
    meta_text = meta_path.read_text()
    doc1 = Path(run["doc1_path"]).read_text()
    pseudonym = run["pseudonym"]
    school = run.get("school") or "(unknown school)"

    skill = load_skill("aplus-b2c-hashtag-analyst")
    system = (
        "You are the aplus-b2c-hashtag-analyst skill. Apply the SKILL "
        "spec below verbatim. You don't have live web access in this "
        "context, so reason about trending hashtags from your training "
        "knowledge (Anthropic knowledge cutoff January 2026) for the "
        "case study's topic area: K-12 math / reading tutoring, parent "
        "audience, especially homeschool / charter families. Pick three "
        "currently-active topic hashtags per the SKILL schema, plus one "
        "brand-voice hashtag and one Roman-voice hashtag from the "
        "libraries the SKILL lists. Every quote, hook, and caption must "
        "read as a complete grammatical sentence (grammar gate). No em "
        "dashes anywhere. No straight ASCII quotation marks inside "
        "quoted speech — use curly quotation marks.\n\n"
        "Every caption/hook must follow the inclusive-language SKILL: person-"
        "first disability language ('a student who has dyslexia,' never 'a "
        "dyslexic student'), no deficit framing, accurate English-learner "
        "terms. Never edit a verbatim parent/tutor quote.\n\n"
        "===== aplus-b2c-hashtag-analyst SKILL.md =====\n\n" + skill +
        "\n\n===== aplus-inclusive-language SKILL.md =====\n\n"
        + load_skill("aplus-inclusive-language")
    )
    user = _build_hashtag_user_prompt(
        pseudonym=pseudonym, school=school, doc1=doc1, meta_text=meta_text
    )
    print(f"  Generating hashtags + captions for {pseudonym}...")
    text = claude_complete(system, user, max_tokens=4000)

    # Append the new sections to metadata.md.
    appended = meta_text.rstrip() + "\n\n" + text.strip() + "\n"
    meta_path.write_text(appended)
    print(f"    appended {len(text):,} chars of hashtag + caption content")

    run.update({"stage": "hashtags"})
    update_run(run["run_id"], run)
    return run


# ---------------------------------------------------------------------------
# Stage 12: HubSpot DRAFT publish (idempotent on slug)
# ---------------------------------------------------------------------------

class HubSpotPublishFailure(OrchestratorError):
    pass


PUBLISH_SCRIPT = REPO_ROOT / "scripts" / "shared" / "publish-to-hubspot.py"
HUBSPOT_PORTAL_ID = "6312752"
CASE_STUDY_BLOG_ID = "81499394054"


def _search_hubspot_draft_by_slug(slug: str) -> dict | None:
    """Look for an existing DRAFT post in the case-study blog matching this slug.

    HubSpot's v3 blog-posts list endpoint silently ignores the `slug` query
    parameter, so we fetch DRAFT posts and filter client-side. Stored slugs
    include the blog's URL prefix (e.g. `case-study/caleb-ilead`) rather
    than the bare slug we send when publishing, so we accept either form.

    Auth failures bubble up as HubSpotPublishFailure so the operator sees
    the real problem rather than the orchestrator silently re-creating
    duplicate drafts.
    """
    token = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
    if not token:
        raise HubSpotPublishFailure(
            "HUBSPOT_PRIVATE_APP_TOKEN is not set; cannot pre-check for "
            "an existing draft."
        )
    import requests
    slug_clean = slug.lstrip("/")
    url = "https://api.hubapi.com/cms/v3/blogs/posts"
    params = {
        "contentGroupId": CASE_STUDY_BLOG_ID,
        "state": "DRAFT",
        "limit": 100,
    }
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=30,
    )
    if r.status_code == 401:
        raise HubSpotPublishFailure(
            "HubSpot returned 401 on the slug pre-check. The Private App "
            "token may need re-authorization. Per Roman's note, do NOT "
            "silently bypass this — flag and stop."
        )
    if r.status_code != 200:
        raise HubSpotPublishFailure(
            f"HubSpot pre-check failed: HTTP {r.status_code} {r.text[:300]}"
        )
    results = r.json().get("results", []) or []
    for post in results:
        stored = (post.get("slug") or "").lstrip("/")
        if stored == slug_clean or stored.endswith("/" + slug_clean):
            return post
    return None


def _extract_url_slug(meta_text: str) -> str | None:
    block = re.search(r"```\n(.*?)\n```", meta_text, re.DOTALL)
    if block:
        for line in block.group(1).split("\n"):
            if line.strip().startswith("url_slug:"):
                return line.split(":", 1)[1].strip()
    m = re.search(r"^url_slug:\s*(.+)$", meta_text, re.MULTILINE)
    return m.group(1).strip() if m else None


_POST_ID_RE = re.compile(r"Post ID:\s*(\d+)")


def stage_publish(args: argparse.Namespace, run: dict) -> dict:
    bundle = Path(run["bundle_path"])
    meta_text = (bundle / "metadata.md").read_text()
    slug = _extract_url_slug(meta_text)
    if not slug:
        raise HubSpotPublishFailure(
            f"metadata.md has no url_slug; cannot publish or pre-check."
        )

    # Idempotency pre-check.
    existing = _search_hubspot_draft_by_slug(slug)
    if existing:
        post_id = str(existing.get("id"))
        edit_url = (
            f"https://app.hubspot.com/blog/{HUBSPOT_PORTAL_ID}/editor/"
            f"{post_id}/content"
        )
        if not args.force_update:
            # Reuse as-is. WARNING: the published body is whatever a prior run
            # left there — it is NOT refreshed with this run's Doc 1, so embed
            # will match this run's anchors against a possibly-stale body. Pass
            # --force-update on a re-run to overwrite it.
            print(
                f"  Existing draft for slug {slug!r}: post_id={post_id}; reusing "
                "as-is (body NOT refreshed — pass --force-update to overwrite)."
            )
            run.update(
                {
                    "stage": "publish",
                    "hubspot_post_id": post_id,
                    "hubspot_edit_url": edit_url,
                    "hubspot_reused_existing": True,
                    "hubspot_body_refreshed": False,
                }
            )
            update_run(run["run_id"], run)
            return run

        # --force-update: refresh the existing draft's body with this run's
        # Doc 1 so embed matches the current document, not a stale one.
        print(
            f"  Existing draft for slug {slug!r}: post_id={post_id}; refreshing "
            "body with this run's Doc 1 (--force-update)."
        )
        cmd = [
            "python3", str(PUBLISH_SCRIPT),
            "--bundle", str(bundle),
            "--update-existing", post_id,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            sys.stderr.write(result.stdout or "")
            sys.stderr.write(result.stderr or "")
            raise HubSpotPublishFailure(
                "publish-to-hubspot.py --update-existing exited non-zero. "
                "See stdout/stderr above."
            )
        m = _POST_ID_RE.search(result.stdout or "")
        refreshed_id = m.group(1) if m else post_id
        run.update(
            {
                "stage": "publish",
                "hubspot_post_id": refreshed_id,
                "hubspot_edit_url": edit_url,
                "hubspot_reused_existing": True,
                "hubspot_body_refreshed": True,
            }
        )
        update_run(run["run_id"], run)
        return run

    # Fresh draft.
    cmd = ["python3", str(PUBLISH_SCRIPT), "--bundle", str(bundle)]
    print(f"  Creating new HubSpot DRAFT for slug {slug!r}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout or "")
        sys.stderr.write(result.stderr or "")
        raise HubSpotPublishFailure(
            "publish-to-hubspot.py exited non-zero. See stdout/stderr above."
        )
    # The publish script prints "Draft created. Post ID: <id>".
    m = _POST_ID_RE.search(result.stdout or "")
    if not m:
        sys.stderr.write(result.stdout or "")
        raise HubSpotPublishFailure(
            "publish-to-hubspot.py succeeded but the post_id was not in "
            "its stdout. Cannot record it in run state."
        )
    post_id = m.group(1)
    edit_url = (
        f"https://app.hubspot.com/blog/{HUBSPOT_PORTAL_ID}/editor/"
        f"{post_id}/content"
    )
    print(f"  HubSpot DRAFT created: post_id={post_id}")
    print(f"  Edit URL: {edit_url}")
    run.update(
        {
            "stage": "publish",
            "hubspot_post_id": post_id,
            "hubspot_edit_url": edit_url,
            "hubspot_reused_existing": False,
        }
    )
    update_run(run["run_id"], run)
    return run


# ---------------------------------------------------------------------------
# Stage 12.5: embed in-body graphics into the HubSpot post body
# ---------------------------------------------------------------------------

class EmbedGraphicsFailure(OrchestratorError):
    pass


EMBED_SCRIPT = REPO_ROOT / "scripts" / "shared" / "embed-pull-quotes.py"


def stage_embed_graphics(args: argparse.Namespace, run: dict) -> dict:
    """Insert pull-quote and topic-graphic figures into the HubSpot draft body.

    publish-to-hubspot.py creates the post with featured-image set to the hero
    but the body itself has no in-line images — just the article prose. This
    stage shells out to scripts/shared/embed-pull-quotes.py, which uploads
    the pull-quote and data-viz PNGs to HubSpot Files (idempotent), fetches
    the current postBody, inserts a `<figure><img></figure>` block after each
    paragraph whose text contains the configured anchor, and PATCHes the
    body back. State stays DRAFT throughout.

    If we reused an existing draft in stage_publish, pass --reset-figures so
    we don't accumulate duplicate figure tags across re-runs.
    """
    bundle = Path(run["bundle_path"])
    post_id = run.get("hubspot_post_id")
    if not post_id:
        raise EmbedGraphicsFailure(
            "No hubspot_post_id in run state; Stage 12 (publish) must run first."
        )

    cmd = [
        "python3", str(EMBED_SCRIPT),
        "--bundle", str(bundle),
        "--post-id", str(post_id),
    ]
    if run.get("hubspot_reused_existing"):
        cmd.append("--reset-figures")

    print(f"  Embedding in-body figures into post {post_id}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout or "")
        sys.stderr.write(result.stderr or "")
        raise EmbedGraphicsFailure(
            "embed-pull-quotes.py exited non-zero. See stdout/stderr above. "
            "Common cause: an anchor in metadata.md (inline_data_viz_anchors "
            "or one of the pull_quotes) is not a verbatim substring of any "
            "paragraph in Doc 1."
        )
    # Echo a short tail so the orchestrator log shows what got inserted.
    for line in (result.stdout or "").strip().splitlines()[-4:]:
        print(f"    {line}")
    run.update({"stage": "embed_graphics"})
    update_run(run["run_id"], run)
    return run


# ---------------------------------------------------------------------------
# Stage 13: Slack delivery (text bundle, then graphics + captions)
# ---------------------------------------------------------------------------

class SlackDeliveryFailure(OrchestratorError):
    pass


SLACK_TEXT_SCRIPT = REPO_ROOT / "scripts" / "b2c" / "deliver-case-study-to-slack.py"
SLACK_GRAPHICS_SCRIPT = REPO_ROOT / "scripts" / "b2c" / "deliver-case-study-graphics-to-slack.py"


def stage_slack(args: argparse.Namespace, run: dict) -> dict:
    bundle = Path(run["bundle_path"])
    post_id = run.get("hubspot_post_id")
    if not post_id:
        raise SlackDeliveryFailure(
            "No hubspot_post_id in run state; Stage 12 must run before Slack delivery."
        )

    common_args = ["--bundle", str(bundle)]
    if args.slack_channel:
        common_args.extend(["--channel", args.slack_channel])

    # 1. Text bundle (header + Paola feedback + file list).
    cmd1 = ["python3", str(SLACK_TEXT_SCRIPT), *common_args, "--post-id", post_id]
    print(f"  Posting Slack header + Paola feedback...")
    result = subprocess.run(cmd1, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout or "")
        sys.stderr.write(result.stderr or "")
        raise SlackDeliveryFailure("deliver-case-study-to-slack.py exited non-zero.")
    tail = (result.stdout or "").strip().splitlines()[-1:]
    if tail:
        print(f"    {tail[0]}")

    # 2. Graphics + captions pack (mentions Paola).
    cmd2 = ["python3", str(SLACK_GRAPHICS_SCRIPT), *common_args]
    print(f"  Posting Slack graphics + captions pack...")
    result = subprocess.run(cmd2, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout or "")
        sys.stderr.write(result.stderr or "")
        raise SlackDeliveryFailure(
            "deliver-case-study-graphics-to-slack.py exited non-zero."
        )
    tail = (result.stdout or "").strip().splitlines()[-1:]
    if tail:
        print(f"    {tail[0]}")

    run.update(
        {
            "stage": "slack",
            "slack_channel": args.slack_channel or "#student-spotlight-ready",
        }
    )
    update_run(run["run_id"], run)
    return run


def stage_complete(args: argparse.Namespace, run: dict) -> dict:
    """Final state finalization + stdout summary.

    Stage timings are populated in the main loop; here we mark the run
    completed and print a comprehensive summary so the operator sees
    bundle path, HubSpot URL, Slack channel, and any Gate 2 items in one
    place at the end of the orchestration log.
    """
    run.update({"stage": "complete", "status": "completed"})
    update_run(run["run_id"], run)

    print("")
    print("=" * 68)
    print(f"SPOTLIGHT ORCHESTRATION COMPLETE — run_id={run['run_id']}")
    print("=" * 68)
    print(f"Bundle:         {run['bundle_path']}")
    print(f"Real student:   {run['real_firstname']} {run.get('real_lastname') or ''}".rstrip())
    print(f"Pseudonym:      {run['pseudonym']}  ({run.get('gender', '?')})")
    print(f"School:         {run.get('school') or '(unknown)'}")
    if run.get("hubspot_post_id"):
        reused = " (reused existing)" if run.get("hubspot_reused_existing") else ""
        print(f"HubSpot draft:  {run['hubspot_post_id']}{reused}")
        print(f"  Edit URL:     {run['hubspot_edit_url']}")
    if run.get("slack_channel"):
        print(f"Slack channel:  {run['slack_channel']}")
    if run.get("brand_check_violations"):
        n = len(run["brand_check_violations"])
        print(f"Brand-check:    {n} violations cleaned from Doc 1")
    timings = run.get("stage_timings", {})
    if timings:
        print("Stage timings:")
        for name, ts in timings.items():
            dur = ts.get("duration_s")
            print(f"  {name:18s} {dur:6.1f}s" if dur is not None else f"  {name:18s} (no duration)")
    print("=" * 68)
    return run


STAGE_DISPATCH = {
    "init": stage_init,
    "read_sources": stage_read_sources,
    "hubspot": stage_hubspot,
    "bundle": stage_bundle,
    "names": stage_names,
    "draft": stage_draft,
    "anonymization": stage_anonymization,
    "archive": stage_archive,
    "metadata": stage_metadata,
    "grammar": stage_grammar,
    "support": stage_support,
    "graphics": stage_graphics,
    "hashtags": stage_hashtags,
    "publish": stage_publish,
    "embed_graphics": stage_embed_graphics,
    "slack": stage_slack,
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

    import time
    stage_timings = run.setdefault("stage_timings", {})
    for stage in STAGE_ORDER[1:]:
        if args.dry_run and stage in DRY_RUN_SKIP_STAGES:
            print(f"=== Stage: {stage} (skipped — --dry-run) ===")
            continue
        print(f"=== Stage: {stage} ===")
        t0 = time.monotonic()
        try:
            run = run_stage(stage, args, run)
        except OrchestratorError as exc:
            stage_timings[stage] = {"duration_s": round(time.monotonic() - t0, 2), "status": "failed"}
            update_run(
                run["run_id"],
                {"status": "failed", "stage": stage, "error": str(exc), "stage_timings": stage_timings},
            )
            print(f"ERROR at stage {stage}: {exc}", file=sys.stderr)
            return 1
        stage_timings[stage] = {"duration_s": round(time.monotonic() - t0, 2), "status": "ok"}
        run["stage_timings"] = stage_timings
        update_run(run["run_id"], run)
        if stage == args.stop_after:
            print(f"Stopping after stage: {stage}")
            update_run(run["run_id"], {"status": "stopped", "stage": stage, "stage_timings": stage_timings})
            return 0
    update_run(run["run_id"], {"status": "completed", "stage": args.stop_after, "stage_timings": stage_timings})
    print(f"Orchestration completed through stage: {args.stop_after}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
