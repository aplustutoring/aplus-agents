#!/usr/bin/env python3
"""Download a single file from Google Drive by ID to a local path.

Tiny sibling of download-drive-folder.py used by the CI workflow to pull
the A+ logo PNG into ~/Desktop/logo.png (where composite-logo.py expects
it). Same service-account auth path; same lazy-import pattern.

Usage:
    python3 scripts/watcher/download-drive-file.py \\
        --file-id 1A2b3CdEf... --dest ~/Desktop/logo.png
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _lazy_imports():
    try:
        from google.oauth2 import service_account  # type: ignore
        from googleapiclient.discovery import build  # type: ignore
        from googleapiclient.http import MediaIoBaseDownload  # type: ignore
    except ImportError as exc:
        sys.stderr.write(
            "ERROR: google-api-python-client + google-auth not installed.\n"
            f"Root cause: {exc}\n"
        )
        sys.exit(2)
    return service_account, build, MediaIoBaseDownload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file-id", required=True)
    parser.add_argument("--dest", required=True)
    args = parser.parse_args()

    service_account, build, MediaIoBaseDownload = _lazy_imports()
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path or not Path(creds_path).exists():
        sys.stderr.write(
            "ERROR: GOOGLE_APPLICATION_CREDENTIALS env var must point at a "
            "service-account JSON file.\n"
        )
        return 2
    creds = service_account.Credentials.from_service_account_file(
        creds_path,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    drive = build("drive", "v3", credentials=creds)

    dest = Path(args.dest).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)

    req = drive.files().get_media(fileId=args.file_id)
    with open(dest, "wb") as fp:
        dl = MediaIoBaseDownload(fp, req)
        done = False
        while not done:
            _, done = dl.next_chunk()
    print(f"Downloaded {args.file_id} -> {dest} ({dest.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
