"""The A+-owned intake sheet (spec §3): Intake in, agent columns out, one Log
line per run. gspread over the retention service account (GOOGLE_SHEETS_CREDS
= Actions secret RETENTION_SA_JSON, same as the email agents). The IEM sheet
id is refused outright.
"""
from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from . import rows as R
from ._bootstrap import DRY_RUN, agent_cfg, google_creds_dict

PT = ZoneInfo("America/Los_Angeles")


class SheetError(RuntimeError):
    pass


def sheet_id(explicit: str | None = None) -> str:
    sc = agent_cfg()["sheet"]
    sid = (explicit or os.getenv(sc["id_env"], "") or sc["default_id"]).strip()
    if sid in (sc.get("forbidden_ids") or []):
        raise SheetError("that is IEM's sheet; the agent never reads or writes it (spec §3)")
    return sid


def _col(n: int) -> str:
    """1-based column index → A1 letters."""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


class Sheet:
    def __init__(self, sid: str, dry_run: bool = DRY_RUN):
        self.id = sid
        self.dry_run = dry_run
        self._book = None
        self._intake = None
        self._log = None

    # ── connection ────────────────────────────────────────────────────────
    def _open(self):
        if self._book is not None:
            return
        creds = google_creds_dict()
        if not creds:
            raise SheetError("GOOGLE_SHEETS_CREDS is unset (RETENTION_SA_JSON in Actions, "
                             "or a service-account JSON path locally)")
        import gspread
        from google.oauth2.service_account import Credentials
        scoped = Credentials.from_service_account_info(
            creds, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        gc = gspread.authorize(scoped, http_client=gspread.BackOffHTTPClient)
        self._book = gc.open_by_key(self.id)
        sc = agent_cfg()["sheet"]
        self._intake = self._book.worksheet(sc["intake_tab"])
        try:
            self._log = self._book.worksheet(sc["log_tab"])
        except gspread.exceptions.WorksheetNotFound:
            if self.dry_run:
                self._log = None
            else:
                self._log = self._book.add_worksheet(sc["log_tab"], rows=1000, cols=8)
                self._log.append_row(["When (PT)", "Mode", "Rows", "Did", "Refused", "By"])

    # ── reads ─────────────────────────────────────────────────────────────
    def read_intake(self) -> tuple[list[str], list[tuple[int, list[str]]]]:
        """(headers, [(1-based row number, cells)...]) for every non-empty row."""
        self._open()
        values = self._intake.get_all_values()
        if not values:
            raise SheetError("Intake tab is empty")
        headers = [h.strip() for h in values[0]]
        body = [(i + 2, cells) for i, cells in enumerate(values[1:]) if any(c.strip() for c in cells)]
        return headers, body

    # ── writes ────────────────────────────────────────────────────────────
    def ensure_output_columns(self, headers: list[str]) -> list[str]:
        """Append any missing agent column to the header row. Returns the
        header list as it now stands (positions are what write_outputs uses)."""
        have = {h.strip().lower() for h in headers}
        missing = [h for h in R.OUTPUT_HEADERS if h.lower() not in have]
        if not missing:
            return headers
        new = headers + missing
        if self.dry_run:
            print(f"[DRY_RUN] sheet: would add columns {missing}")
            return new
        self._open()
        start = _col(len(headers) + 1)
        self._intake.update(f"{start}1", [missing])
        return new

    def write_outputs(self, headers: list[str], row_number: int, values: dict[str, str]) -> None:
        """Write agent columns on ONE Intake row (never an input column)."""
        cells = []
        for name, val in values.items():
            if name not in R.OUTPUT_HEADERS:
                raise SheetError(f"refusing to write non-agent column {name!r}")
            try:
                col = [h.strip().lower() for h in headers].index(name.lower()) + 1
            except ValueError:
                raise SheetError(f"column {name!r} missing; call ensure_output_columns first")
            cells.append((col, str(val)))
        if self.dry_run:
            print(f"[DRY_RUN] sheet row {row_number}: {values}")
            return
        self._open()
        self._intake.batch_update([{"range": f"{_col(c)}{row_number}", "values": [[v]]}
                                   for c, v in cells])

    def append_log(self, mode: str, rows: int, did: str, refused: str, by: str) -> None:
        when = datetime.now(PT).strftime("%Y-%m-%d %H:%M")
        line = [when, mode, str(rows), did[:4000], refused[:4000], by]
        if self.dry_run or self._log is None:
            print(f"[DRY_RUN] sheet log: {line}")
            return
        self._open()
        self._log.append_row(line)


def now_stamp() -> str:
    return datetime.now(PT).strftime("%Y-%m-%d %H:%M PT")
