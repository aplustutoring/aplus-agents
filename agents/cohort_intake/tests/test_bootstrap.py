"""The agent's HubSpot reads are real even in a dry run: the plan must say
update, not create, for a contact that already exists."""
from agents.cohort_intake import _bootstrap as B


def test_dry_run_searches_pass_through():
    assert B.hs.SEARCH_PASSTHROUGH is True
