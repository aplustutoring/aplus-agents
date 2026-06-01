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
from datetime import datetime
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


def normalize_name(name: str) -> str:
    name = name.strip()
    return re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()


def pseudonym_for_name(real_name: str) -> str:
    stem = normalize_name(real_name.split()[0] if real_name else "student")
    digest = hashlib.sha256(real_name.encode("utf-8")).hexdigest()[:6]
    return f"{stem}-{digest}"


def build_bundle_path(student_name: str | None, date_str: str) -> Path:
    if student_name:
        pseudonym = pseudonym_for_name(student_name)
    else:
        pseudonym = f"student-{uuid.uuid4().hex[:6]}"
    bundle_name = f"{date_str}-case-study-{pseudonym}"
    return BUNDLE_ROOT / bundle_name


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


def call_hubspot_lookup(email: str) -> dict | None:
    token = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
    if not token:
        raise HubSpotSearchError("HUBSPOT_PRIVATE_APP_TOKEN is not configured for HubSpot lookup.")
    url = "https://api.hubapi.com/crm/v3/objects/contacts/search"
    payload = {
        "filterGroups": [
            {
                "filters": [
                    {"propertyName": "email", "operator": "EQ", "value": email}
                ]
            }
        ],
        "properties": ["email", "firstname", "lastname", "jobtitle", "company", "student_school"],
        "limit": 10,
    }
    import requests

    r = requests.post(url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json=payload, timeout=30)
    if r.status_code != 200:
        raise HubSpotSearchError(f"HubSpot search failed: {r.status_code} {r.text}")
    data = r.json()
    total = data.get("total", 0)
    results = data.get("results", [])
    if total == 1:
        return results[0]
    if total == 0:
        raise HubSpotSearchError(f"HubSpot contact search returned no results for email {email}.")
    raise HubSpotSearchError(f"HubSpot contact search returned multiple results for email {email}.")


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


def stage_hubspot(args: argparse.Namespace, run: dict) -> dict:
    if args.skip_hubspot:
        print("Skipping HubSpot lookup by request.")
        run.update({"stage": "hubspot", "hubspot": None})
        update_run(run["run_id"], run)
        return run

    source_texts = json.loads(Path(run["extracted_texts_path"]).read_text())
    email = None
    for text in source_texts.values():
        email = extract_email(text)
        if email:
            break
    if not email:
        raise HubSpotSearchError("No email address found in source texts for HubSpot lookup.")

    print(f"Found email candidate: {email}")
    contact = call_hubspot_lookup(email)
    props = contact.get("properties", {})
    run.update(
        {
            "stage": "hubspot",
            "hubspot_contact": {
                "email": email,
                "firstname": props.get("firstname"),
                "lastname": props.get("lastname"),
                "company": props.get("company"),
                "school": props.get("student_school"),
            },
        }
    )
    update_run(run["run_id"], run)
    return run


def stage_bundle(args: argparse.Namespace, run: dict) -> dict:
    if args.student_name:
        student_name = args.student_name
    else:
        contact = run.get("hubspot_contact")
        if contact and contact.get("firstname"):
            student_name = contact["firstname"]
        else:
            raise OrchestratorError(
                "Student name is required when HubSpot lookup is unavailable or does not return a first name."
            )

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    bundle_dir = build_bundle_path(student_name, date_str)
    if bundle_dir.exists():
        raise OrchestratorError(f"Bundle directory already exists: {bundle_dir}")

    run_source_root = Path(run["extracted_texts_path"]).parent
    source_texts = json.loads((run_source_root / "source_texts.json").read_text())
    copy_source_files(bundle_dir, [Path(p) for p in run["source_files"]])
    save_extracted_texts(bundle_dir, source_texts)

    bundle_manifest = {
        "bundle_path": str(bundle_dir.resolve()),
        "student_name": student_name,
        "school": args.school or (run.get("hubspot_contact") or {}).get("school"),
        "created_at": datetime.utcnow().isoformat() + "Z",
        "source_folder": str(Path(args.source).resolve()),
    }
    (bundle_dir / "bundle-manifest.json").write_text(json.dumps(bundle_manifest, indent=2))

    run.update(
        {
            "stage": "bundle",
            "bundle_path": str(bundle_dir.resolve()),
            "bundle_manifest_path": str((bundle_dir / "bundle-manifest.json").resolve()),
        }
    )
    update_run(run["run_id"], run)
    return run


def stage_complete(args: argparse.Namespace, run: dict) -> dict:
    run.update({"stage": "complete"})
    update_run(run["run_id"], run)
    return run


def run_stage(stage_name: str, args: argparse.Namespace, run: dict) -> dict:
    if stage_name == "init":
        return stage_init(args, run)
    if stage_name == "read_sources":
        return stage_read_sources(args, run)
    if stage_name == "hubspot":
        return stage_hubspot(args, run)
    if stage_name == "bundle":
        return stage_bundle(args, run)
    if stage_name == "complete":
        return stage_complete(args, run)
    raise OrchestratorError(f"Stage {stage_name} is not implemented yet.")


def main() -> int:
    args = parse_args()
    run = stage_init(args, load_state())

    if args.stop_after == "init":
        print("Stopping after stage: init")
        update_run(run["run_id"], {"status": "stopped", "stage": "init"})
        return 0

    for stage in STAGE_ORDER[1:]:
        if stage == "draft" and args.dry_run:
            print("Dry run requested; stopping before draft stage.")
            update_run(run["run_id"], {"status": "stopped", "stage": run.get("stage", "bundle")})
            return 0
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
