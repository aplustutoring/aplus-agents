#!/usr/bin/env python3
"""Download every non-sentinel file from a Google Drive folder.

Reads the service-account credentials from $GOOGLE_APPLICATION_CREDENTIALS
(set by google-github-actions/auth in the workflow) and downloads every
file in the named folder into a local destination directory.

The orchestrator then runs against that directory with `--source <dest>`
and the existing Stage 1 (read_sources) picks up the files exactly as
if Paola had dropped them locally.

Usage:
    python3 scripts/watcher/download-drive-folder.py \\
        --folder-id 1A2b3CdEfGhIjKlMn \\
        --dest /tmp/spotlight-source

Behavior:
- Skips files whose name starts with `.spotlight` (sentinels the Apps
  Script drops after dispatching, so a re-run of the workflow against
  the same folder doesn't re-ingest them).
- Skips Google-native files (Docs, Sheets, Slides). The orchestrator's
  supported extensions are .txt / .md / .pdf / .docx; if Paola needs to
  ship a Google Doc, she should "File > Download > Microsoft Word
  (.docx)" before dropping it into the intake folder.
- Errors loudly on auth failure or missing folder so the workflow fails
  fast and the operator sees the real cause in the Actions log.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Imported lazily so this script can be `--help`-introspected on a box
# that doesn't have the Google client libraries installed.
def _lazy_imports():
    try:
        from google.oauth2 import service_account  # type: ignore
        from googleapiclient.discovery import build  # type: ignore
        from googleapiclient.http import MediaIoBaseDownload  # type: ignore
    except ImportError as exc:
        sys.stderr.write(
            "ERROR: google-api-python-client + google-auth not installed.\n"
            "Install with: pip install google-api-python-client google-auth\n"
            f"Root cause: {exc}\n"
        )
        sys.exit(2)
    return service_account, build, MediaIoBaseDownload


# Mime types we explicitly do not ingest. Google-native formats need to be
# exported (drive.files.export_media), and the orchestrator can't read them
# anyway — Paola should download as .docx and re-upload.
GOOGLE_NATIVE_MIME_PREFIXES = ("application/vnd.google-apps.",)

# File-name prefixes we always skip (sentinels left behind by the Apps
# Script watcher to mark a folder as already dispatched).
SKIP_NAME_PREFIXES = (".spotlight",)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a Google Drive folder for the spotlight orchestrator."
    )
    parser.add_argument("--folder-id", required=True, help="Google Drive folder ID")
    parser.add_argument(
        "--dest",
        required=True,
        help="Local directory to write the downloaded files into (will be created)",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def _credentials():
    service_account, _, _ = _lazy_imports()
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path or not Path(creds_path).exists():
        sys.stderr.write(
            "ERROR: GOOGLE_APPLICATION_CREDENTIALS env var must point at a "
            "service-account JSON file. In the workflow this is set by "
            "google-github-actions/auth; locally, export it before running.\n"
        )
        sys.exit(2)
    return service_account.Credentials.from_service_account_file(
        creds_path,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )


def main() -> int:
    args = parse_args()
    _, build, MediaIoBaseDownload = _lazy_imports()
    creds = _credentials()
    drive = build("drive", "v3", credentials=creds)

    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)

    # Verify the folder exists and is reachable with these credentials. A
    # bad folder ID or a permission gap is the most common deployment
    # failure mode; surface it clearly.
    try:
        meta = drive.files().get(
            fileId=args.folder_id,
            fields="id, name, mimeType",
            supportsAllDrives=True,
        ).execute()
    except Exception as exc:  # noqa: BLE001 — surface the API error to stderr
        sys.stderr.write(
            f"ERROR: cannot fetch Drive folder {args.folder_id!r}. "
            f"Check that the service account has 'Viewer' access on the "
            f"intake folder and that the ID is correct.\n"
            f"Root cause: {exc}\n"
        )
        return 2

    if meta.get("mimeType") != "application/vnd.google-apps.folder":
        sys.stderr.write(
            f"ERROR: {args.folder_id!r} resolved to mimeType "
            f"{meta.get('mimeType')!r}, not a folder.\n"
        )
        return 2

    print(f"Downloading folder: {meta.get('name')!r} (id={meta.get('id')})")

    # Paginate the list — case-study folders typically have 3-6 files but
    # paginating defensively keeps us future-proof.
    page_token = None
    downloaded: list[str] = []
    skipped: list[str] = []
    while True:
        resp = drive.files().list(
            q=f"'{args.folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType, size)",
            pageSize=100,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()

        for f in resp.get("files", []):
            name = f["name"]
            if any(name.startswith(p) for p in SKIP_NAME_PREFIXES):
                skipped.append(f"{name} (sentinel)")
                continue
            if any(f.get("mimeType", "").startswith(p) for p in GOOGLE_NATIVE_MIME_PREFIXES):
                skipped.append(f"{name} (Google-native — re-export as .docx)")
                continue

            out_path = dest / name
            request = drive.files().get_media(fileId=f["id"])
            with open(out_path, "wb") as fp:
                downloader = MediaIoBaseDownload(fp, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            size = out_path.stat().st_size
            downloaded.append(f"{name} ({size:,} bytes)")
            if args.verbose:
                print(f"  OK {name} -> {out_path} ({size:,} bytes)")

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    print(f"\nDownloaded {len(downloaded)} file(s) into {dest}:")
    for entry in downloaded:
        print(f"  {entry}")
    if skipped:
        print(f"\nSkipped {len(skipped)} item(s):")
        for entry in skipped:
            print(f"  {entry}")
    if not downloaded:
        sys.stderr.write(
            "ERROR: no files downloaded. The folder may be empty or the "
            "service account may lack read access.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
