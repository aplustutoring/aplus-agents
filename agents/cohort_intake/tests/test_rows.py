"""Parser + validator (spec §3 headers, §4 hard-stops, cap 4)."""
from decimal import Decimal

import pytest

from agents.cohort_intake import rows as R
from agents.cohort_intake.tests import fixtures as F


def test_group_1_english_9_parses_to_three_students_at_1250():
    rows = F.parsed_group1()
    groups = R.assemble_groups(rows)
    assert len(groups) == 1
    g = groups[0]
    assert [r.student_name for r in g.rows] == ["Diego Reyna", "Maya Chen", "Owen Park"]
    assert g.cohort.number == 1 and g.number == 1 and g.subject == "English 9"
    assert g.amounts == [Decimal("1250")] * 3
    assert len(g.dates) == 25
    assert g.es_emails == ["kortiz@ieminc.org"]          # one ES, lower-cased
    assert g.label == "Cohort 1 Group 1 English 9 (Monday 10:00 AM)"


def test_school_aliases_resolve_and_grades_normalize():
    rows = F.parsed_group1()
    assert {r.school for r in rows} == {"Ocean Grove Charter School"}
    assert [r.grade for r in rows] == ["9", "9", "9"]
    assert [r.parent_phone for r in rows] == ["+18185550101", "+18185550102", "+18185550103"]


def test_single_name_parent_takes_student_last_name_and_is_flagged():
    diego = F.parsed_group1()[0]
    assert (diego.parent_first, diego.parent_last, diego.parent_name_flagged) == ("Reyna", "Reyna", True)
    lin = F.parsed_group1()[1]
    assert (lin.parent_first, lin.parent_last, lin.parent_name_flagged) == ("Lin", "Chen", False)


def test_student_email_equal_to_parent_email_is_dropped_without_flag():
    maya = F.parsed_group1()[1]
    assert maya.student_email is None
    diego = F.parsed_group1()[0]
    assert diego.student_email == "diego@ieminc.org"


def test_idempotency_key_is_school_student_subject_term():
    assert F.parsed_group1()[0].idempotency_key == "Ocean Grove Charter School|IEM-1001|english 9|26/27"


@pytest.mark.parametrize("col,value,fragment", [
    (7, "", "parent email is blank"),
    (8, "", "parent phone is blank"),
    (8, "555-01", "not a 10-digit US number"),
    (10, "", "es email is blank"),
    (11, "", "subject is blank"),
    (3, "", "grade is blank"),
    (3, "ninth", "unparseable"),
    (14, "", "cohort start is blank"),
    (14, "1, 9/22/26", "not a cohort start"),
    (4, "", "school is blank"),
    (4, "Oceon Grove", "not in school-aliases.yml"),
    (15, "", "group is blank"),
    (15, "one", "not a number"),
    (13, "Tue 4 PM", "not one of the program slots"),
])
def test_every_hard_stop_names_the_problem(col, value, fragment):
    cells = list(F.GROUP1[0])
    cells[col] = value
    idx = R.header_map(F.HEADERS)
    with pytest.raises(R.RowError, match=fragment):
        R.parse_row(2, cells, idx, F.resolve_school)


def test_all_problems_on_a_row_are_reported_together():
    cells = list(F.GROUP1[0])
    cells[7] = ""
    cells[10] = ""
    idx = R.header_map(F.HEADERS)
    with pytest.raises(R.RowError) as e:
        R.parse_row(2, cells, idx, F.resolve_school)
    assert "parent email is blank" in str(e.value) and "es email is blank" in str(e.value)


def test_missing_required_column_is_refused_up_front():
    headers = [h for h in F.HEADERS if h != "Group #"]
    with pytest.raises(R.RowError, match="missing columns for: .*group"):
        R.header_map(headers)


def test_group_of_five_is_refused_with_the_split_ask():
    idx = R.header_map(F.HEADERS)
    five = list(F.GROUP1) + [
        F._row("IEM-1004", "Ana", "Lopez", "9", "OG", "", "Rosa Lopez", "rosa@gmail.com",
               "8185550104", "Karen Ortiz", "kortiz@ieminc.org"),
        F._row("IEM-1005", "Ben", "Kim", "9", "OG", "", "Joon Kim", "joon@gmail.com",
               "8185550105", "Karen Ortiz", "kortiz@ieminc.org"),
    ]
    rows = [R.parse_row(i + 2, c, idx, F.resolve_school) for i, c in enumerate(five)]
    with pytest.raises(R.RowError, match="has 5 students .* cap is 4. Ask Danielle to split"):
        R.assemble_groups(rows)


def test_only_ready_rows_are_ready():
    idx = R.header_map(F.HEADERS)
    assert R.is_ready(F.GROUP1[0], idx)
    cells = list(F.GROUP1[0])
    cells[16] = "Test - done"
    assert not R.is_ready(cells, idx)
    cells[16] = " READY "
    assert R.is_ready(cells, idx)


def test_existing_output_columns_are_read_back():
    cells = F._row("IEM-1001", "Diego", "Reyna", "9", "OG", "", "Reyna", "r@x.com",
                   "8185550101", "K O", "k@ieminc.org", outputs={"HubSpot Deal ID": "123"})
    idx = R.header_map(F.HEADERS)
    assert R.parse_row(2, cells, idx, F.resolve_school).outputs["HubSpot Deal ID"] == "123"
