"""Dry-run smoke test: verify scopes and process real inbox mail WITHOUT writing.

    DRY_RUN=true python smoke_test.py

Forces DRY_RUN on, prints the HubSpot scope probe, then runs one triage pass that
logs every intended action (ticket/route/draft/Slack) but writes nothing to
HubSpot / Slack / Monday / Sheets. Run this before enabling the cron.
"""
import os

os.environ["DRY_RUN"] = "true"  # set before importing src.config

from src import hubspot_client as hs  # noqa: E402
from src.main import run  # noqa: E402


def main() -> None:
    print("── HubSpot scope probe ──")
    scopes = {}
    try:
        scopes = hs.check_scopes()
        for label, status in scopes.items():
            mark = "✅" if status == "ok" else "❌"
            print(f"  {mark} {label}: {status}")
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ scope probe failed: {e}")
        print("  (check HUBSPOT_PRIVATE_APP_TOKEN and its scopes)")

    # Discovery: print the IDs to paste into config.yaml.
    if scopes.get("conversations") == "ok":
        print("\n── Inboxes (→ config.yaml hubspot.inbox_id) ──")
        try:
            for i in hs.list_inboxes():
                print(f"  {i.get('id')} | {i.get('name')}")
        except Exception as e:  # noqa: BLE001
            print(f"  error: {e}")
    if scopes.get("tickets") == "ok":
        print("\n── Ticket pipelines (→ ticket_pipeline_id + ticket_stages) ──")
        try:
            for p in hs.list_ticket_pipelines():
                print(f"  PIPELINE {p.get('id')} | {p.get('label')}")
                for s in p.get("stages", []):
                    print(f"     STAGE {s.get('id')} | {s.get('label')}")
        except Exception as e:  # noqa: BLE001
            print(f"  error: {e}")

    print("\n── Dry-run triage pass ──")
    run()
    print("\nSmoke test complete. Nothing was written (DRY_RUN=true).")


if __name__ == "__main__":
    main()
