"""Danielle's blueprint example: Group 1 English 9, cohort 1, three students,
$1,250 each. Reused by the parser, writer, messages and main tests."""
from agents.cohort_intake import rows as R

HEADERS = ["Student ID", "Student First Name", "Student Last Name", "Grade", "School",
           "Student Email (Not IEM email)", "Parent Name", "Parent Email",
           "Contact Phone Number", "ES Name", "ES Email", "Tutoring Subject", "Notes",
           "Day/Time", "Cohort #/Start Date", "Group #", "A+ Status"] + R.OUTPUT_HEADERS

# canonical names as ops/hubspot-schema/school-aliases.yml resolves them
OG, SM, SS = "Ocean Grove Charter School", "Sky Mountain Charter School", "South Sutter Charter School"
SCHOOLS = {"og": OG, "ocean grove": OG, "ocean grove charter school": OG,
           "sm": SM, "sky mountain": SM, "ss": SS, "south sutter": SS}


def resolve_school(raw: str):
    return SCHOOLS.get((raw or "").strip().lower())


def _row(sid, first, last, grade, school, semail, pname, pemail, phone, es, es_email,
         subject="English 9", notes="", slot="Mon 10:00 AM", cohort="1, 9/21/26",
         group="1", status="Ready", outputs=None):
    base = [sid, first, last, grade, school, semail, pname, pemail, phone, es, es_email,
            subject, notes, slot, cohort, group, status]
    return base + [(outputs or {}).get(h, "") for h in R.OUTPUT_HEADERS]


GROUP1 = [
    _row("IEM-1001", "Diego", "Reyna", "9", "OG", "diego@ieminc.org", "Reyna",
         "reyna.family@gmail.com", "(818) 555-0101", "Karen Ortiz", "kortiz@ieminc.org",
         notes="4th grade on i-Ready"),
    _row("IEM-1002", "Maya", "Chen", "9th", "Ocean Grove", "lin.chen@gmail.com", "Lin Chen",
         "lin.chen@gmail.com", "818-555-0102", "Karen Ortiz", "kortiz@ieminc.org"),
    _row("IEM-1003", "Owen", "Park", "Grade 9", "OG", "", "Susan Park",
         "susan.park@yahoo.com", "8185550103", "Karen Ortiz", "KOrtiz@ieminc.org"),
]

LATE_ADD = _row("IEM-1004", "Ana", "Lopez", "9", "OG", "", "Rosa Lopez", "rosa.lopez@gmail.com",
                "8185550104", "Karen Ortiz", "kortiz@ieminc.org")

TEST_001 = _row("TEST-001", "Test", "Student", "9", "OG", "", "Roman Test",
                "roman@wetutorathome.com", "818-384-4845", "Danielle Brodetsky",
                "danielle@wetutorathome.com", group="4")


def parsed_group1(extra=()):
    idx = R.header_map(HEADERS)
    cells = list(GROUP1) + list(extra)
    return [R.parse_row(i + 2, c, idx, resolve_school) for i, c in enumerate(cells)]
