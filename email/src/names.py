"""One definition of "what do we call this person to a family".

Teachworks returns people as "Last, First" in `employee_name` and
`student_name`. Two agents have now shipped a text to a real family with that
raw value in it:

  2026-09-09  the low-balance replay texted a family about "Torres,"
  2026-09-16  the charter PO confirmation told Nikita Brixey her son's
              schedule was "Mondays 10:00 AM with Karl, Sonya". Karl is
              Sonya's SURNAME. Nikita replied: "I don't know who Karl is?
              We've never talked about anyone named Karl."

The first one was fixed privately inside low_balance.py, so when po_inbox grew
the same need it had nothing to reuse and did it raw. This module exists so
there is one place to fix it, and so the next caller finds it.

Customer-facing copy is FIRST NAMES ONLY for students, parents, tutors and
teachers (Roman, LOCKED 2026-09-09). first_name() is therefore the right
default for anything a family or teacher reads; full names stay staff-side.
"""
from __future__ import annotations


def first_name(full: str) -> str:
    """The first name to use in customer-facing copy.

    Handles the three shapes Teachworks and HubSpot actually return:
      "Karl, Sonya"  -> "Sonya"     (Teachworks "Last, First")
      "Sonya Karl"   -> "Sonya"     (plain "First Last")
      "Sonya"        -> "Sonya"
    A trailing comma with nothing after it ("Torres,") falls back to the part
    before the comma rather than returning an empty string, because a surname
    reads better than a blank in a sentence.
    """
    full = (full or "").strip()
    if not full:
        return ""
    if "," in full:
        after = full.split(",", 1)[1].strip()
        if after:
            return after.split()[0].strip()
        return full.split(",")[0].strip()
    return full.split()[0].strip(" ,")
