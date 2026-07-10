"""Monday.com client — vendored from aplus-sync/aplus_weekly_sync.py.

Same API patterns and Sun-Sat week-keying so the email measurables land in the
same weekly columns as the rest of the L10 Scorecard (board 18402267902).
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta

import requests

from .config import MONDAY_TOKEN

MONDAY_URL = "https://api.monday.com/v2"


def monday_query(query: str, variables: dict | None = None) -> dict:
    headers = {"Authorization": MONDAY_TOKEN, "Content-Type": "application/json"}
    payload = {"query": query, "variables": variables or {}}
    for attempt in range(3):
        try:
            r = requests.post(MONDAY_URL, headers=headers, json=payload, timeout=60)
            r.raise_for_status()
            return r.json()
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
            else:
                raise


def update_item(board_id, item_id, column_values: dict) -> None:
    """Update column values on an existing item (numbers must be strings)."""
    sanitized = {k: (str(v) if isinstance(v, (int, float)) else v) for k, v in column_values.items()}
    q = """
    mutation ($boardId: ID!, $itemId: ID!, $colVals: JSON!) {
      change_multiple_column_values(board_id: $boardId, item_id: $itemId,
                                    column_values: $colVals) { id }
    }"""
    monday_query(q, {"boardId": str(board_id), "itemId": str(item_id), "colVals": json.dumps(sanitized)})


def get_or_create_scorecard_week_col(board_id, start_date: date, end_date: date) -> str:
    """Find or create the weekly numbers column. Title format: '3/8/26-3/14/26'."""
    col_title = f"{start_date.strftime('%-m/%-d/%y')}-{end_date.strftime('%-m/%-d/%y')}"
    q = '{ boards(ids: [%s]) { columns { id title type } } }' % board_id
    data = monday_query(q)
    for c in data["data"]["boards"][0]["columns"]:
        if c["title"] == col_title:
            return c["id"]
    q = """
    mutation ($boardId: ID!, $title: String!) {
      create_column(board_id: $boardId, title: $title, column_type: numbers) { id }
    }"""
    data = monday_query(q, {"boardId": str(board_id), "title": col_title})
    return data["data"]["create_column"]["id"]


def get_last_week_range() -> tuple[date, date]:
    """(sunday, saturday) of the most recently completed week (Sun-Sat)."""
    today = datetime.now().date()
    days_since_saturday = (today.weekday() + 2) % 7
    if days_since_saturday == 0:
        days_since_saturday = 7
    last_saturday = today - timedelta(days=days_since_saturday)
    return last_saturday - timedelta(days=6), last_saturday
