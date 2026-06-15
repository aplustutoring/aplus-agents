#!/usr/bin/env python3
"""
sheet_log.py — append/update a row in the master case-study log Google Sheet.

ONE sheet aggregates EVERY spotlight (one row per case study) so the team has a
single pseudonym <-> real-student decode table instead of opening each bundle's
name-map.json. Re-running a bundle UPDATES its existing row (keyed on the bundle
folder name) rather than adding a duplicate.

SECURITY: this sheet is the master decode key — real student names and their
published pseudonyms in one place. Keep it restricted to the team. The pipeline
writes with the same Google service account used for Drive ingest:
    spotlight-watcher@a-plus-spotlight-watcher.iam.gserviceaccount.com
Share the sheet (EDITOR) with that account, enable the Google Sheets API in the
project, and set SPOTLIGHT_LOG_SHEET_ID to the sheet's ID. Without that env var
(or without Google creds) the orchestrator stage simply skips — it is non-fatal.

CLI (manual log / backfill of an already-built bundle):
    python3 scripts/b2c/sheet_log.py --bundle <bundle> --sheet-id <id>
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SHEET_SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]
KEY_COL = "Bundle folder"
HEADER = [
    "Logged at (UTC)", "Study date", "Pseudonym", "Real first name",
    "Real last name", "School", "Grade", "Subject", "Gender",
    "Case study link", "Bundle folder", "Run ID",
]


def _service():
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path or not os.path.exists(creds_path):
        raise RuntimeError(
            "GOOGLE_APPLICATION_CREDENTIALS not set / file missing (in CI this is "
            "written by google-github-actions/auth)")
    from google.oauth2 import service_account  # type: ignore
    from googleapiclient.discovery import build  # type: ignore
    creds = service_account.Credentials.from_service_account_file(
        creds_path, scopes=SHEET_SCOPE)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def append_or_update(sheet_id: str, row: list[str]) -> str:
    """Ensure the header row, then update the row whose KEY_COL matches this
    row's key value, else append. Returns 'updated' or 'appended'."""
    values = _service().spreadsheets().values()
    existing = values.get(
        spreadsheetId=sheet_id, range="A1:Z200000").execute().get("values", [])

    if not existing or existing[0][:1] != HEADER[:1]:
        values.update(spreadsheetId=sheet_id, range="A1",
                      valueInputOption="RAW", body={"values": [HEADER]}).execute()
        existing = existing or []
        existing = [HEADER] + (existing[1:] if existing and existing[0][:1] == HEADER[:1]
                               else existing)

    kidx = HEADER.index(KEY_COL)
    key_value = row[kidx]
    for i, r in enumerate(existing[1:], start=2):  # sheet rows are 1-based; row 1 = header
        if len(r) > kidx and r[kidx] == key_value:
            values.update(spreadsheetId=sheet_id, range=f"A{i}",
                          valueInputOption="RAW", body={"values": [row]}).execute()
            return "updated"
    values.append(spreadsheetId=sheet_id, range="A1",
                  valueInputOption="RAW", insertDataOption="INSERT_ROWS",
                  body={"values": [row]}).execute()
    return "appended"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


def build_row(*, study_date="", pseudonym="", real_first="", real_last="",
              school="", grade="", subject="", gender="", link="",
              bundle_folder="", run_id="") -> list[str]:
    """Build a row in HEADER order. (Caller passes whatever it has; blanks ok.)"""
    return [_now_utc(), study_date, pseudonym, real_first, real_last, school,
            grade, subject, gender, link, bundle_folder, run_id]


# ── CLI: log/backfill from an already-built bundle ──────────────────────────
def _parse_meta(meta_text: str, field: str) -> str:
    block = re.search(r"```\n(.*?)\n```", meta_text, re.DOTALL)
    if block:
        for line in block.group(1).split("\n"):
            if ":" in line:
                k, _, v = line.partition(":")
                if k.strip() == field:
                    return v.strip().strip('"')
    m = re.search(rf"^{re.escape(field)}:\s*(.+)$", meta_text, re.MULTILINE)
    return (m.group(1).strip().strip('"') if m else "")


def _row_from_bundle(bundle: Path) -> list[str]:
    import json
    name = bundle.name
    dm = re.match(r"(\d{4}-\d{2}-\d{2})", name)
    date = dm.group(1) if dm else ""
    nm = {}
    if (bundle / "name-map.json").exists():
        nm = json.loads((bundle / "name-map.json").read_text())
    student = next((e for e in nm.get("entries", []) if e.get("role") == "student"), {})
    meta_text = (bundle / "metadata.md").read_text() if (bundle / "metadata.md").exists() else ""
    return build_row(
        study_date=date,
        pseudonym=(student.get("pseudonym") or "").capitalize(),
        real_first=student.get("real", ""),
        school=_parse_meta(meta_text, "school_named"),
        grade=_parse_meta(meta_text, "grade"),
        subject=_parse_meta(meta_text, "subject"),
        gender=_parse_meta(meta_text, "student_gender"),
        link=_parse_meta(meta_text, "canonical_url"),
        bundle_folder=name,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--sheet-id", default=os.environ.get("SPOTLIGHT_LOG_SHEET_ID"))
    args = ap.parse_args()
    if not args.sheet_id:
        sys.exit("no sheet id (pass --sheet-id or set SPOTLIGHT_LOG_SHEET_ID)")
    row = _row_from_bundle(Path(args.bundle))
    result = append_or_update(args.sheet_id, row)
    print(f"{result} row for {row[HEADER.index(KEY_COL)]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
