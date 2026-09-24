"""
Every issue type the engine can write must exist as an option of
tutor_issue_type in the HubSpot property registry, with the same label.
2026-09-21: #213 added `unresponsive_in_slack` to ISSUE_TYPES only; the first
ticket of that type was refused by HubSpot (400) and the nightly run died.
"""

import os

import yaml

import tutor_issues as ti

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.path.join(HERE, "..", "..", "hubspot-schema", "properties.yml")


def _registry_options():
    doc = yaml.safe_load(open(REGISTRY))
    props = doc.get("properties") if isinstance(doc, dict) else doc

    def walk(node):
        if isinstance(node, dict):
            if node.get("name") == "tutor_issue_type":
                return node
            for v in node.values():
                r = walk(v)
                if r:
                    return r
        elif isinstance(node, list):
            for v in node:
                r = walk(v)
                if r:
                    return r
        return None

    prop = walk(props)
    assert prop, "tutor_issue_type not declared in properties.yml"
    return {o["value"]: o["label"] for o in prop["options"]}


def test_every_engine_issue_type_is_a_registry_option():
    opts = _registry_options()
    missing = [t for t in ti.ISSUE_TYPES if t not in opts]
    assert not missing, f"declare in ops/hubspot-schema/properties.yml then run the schema sync: {missing}"


def test_engine_labels_match_registry_labels():
    opts = _registry_options()
    for t in ti.ISSUE_TYPES:
        assert ti.TYPE_LABELS[t] == opts[t], f"{t}: engine '{ti.TYPE_LABELS[t]}' vs registry '{opts[t]}'"
