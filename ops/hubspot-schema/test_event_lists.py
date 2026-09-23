"""python3 -m pytest ops/hubspot-schema/test_event_lists.py"""
from event_lists import list_name, filter_branch, create_payload, plan, is_duplicate_name, TAG_PROPERTY


def test_list_name_is_prefixed_label():
    assert list_name("Sage Oak Park Day 2026") == "Event: Sage Oak Park Day 2026"
    assert list_name("  Blue Ridge BTSC 2026 ") == "Event: Blue Ridge BTSC 2026"


def test_filter_matches_contacts_carrying_the_tag_value_not_label():
    fb = filter_branch("sage_oak_park_2026")
    leaf = fb["filterBranches"][0]["filters"][0]
    assert leaf["property"] == TAG_PROPERTY
    assert leaf["operation"]["operator"] == "IS_ANY_OF"
    assert leaf["operation"]["values"] == ["sage_oak_park_2026"]
    assert leaf["operation"]["includeObjectsWithNoValueSet"] is False


def test_create_payload_is_an_active_contact_list():
    p = create_payload("blue_ridge_btsc_2026", "Blue Ridge BTSC 2026")
    assert p["processingType"] == "DYNAMIC"
    assert p["objectTypeId"] == "0-1"
    assert p["name"] == "Event: Blue Ridge BTSC 2026"


def test_plan_is_idempotent_and_matches_by_exact_name():
    opts = [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}]
    create, keep = plan(opts, {"Event: A"})
    assert [c["value"] for c in create] == ["b"]
    assert [k["value"] for k in keep] == ["a"]
    create2, keep2 = plan(opts, {"Event: A", "Event: B"})
    assert create2 == [] and len(keep2) == 2


def test_duplicate_name_from_search_lag_is_recognised():
    assert is_duplicate_name('POST /crm/v3/lists -> 400: {"category":"VALIDATION_ERROR","subCategory":"ILS.DUPLICATE_LIST_NAMES"}')
    assert not is_duplicate_name('POST /crm/v3/lists -> 401: {"category":"INVALID_AUTHENTICATION"}')
