# ops/hubspot-schema — the property registry

Custom HubSpot properties the fleet depends on, declared in
[properties.yml](properties.yml) and synced into the portal by
[create_properties.py](create_properties.py). If an agent writes a custom
property, it must be declared here — the portal follows the file, not the
other way around.

The sync is **idempotent and additive on values**: it creates missing groups
and properties, adds missing enumeration options, and refreshes option
labels that drift from this registry (#AP014 — labels are declared here); it
never deletes options/properties, never changes option values, never touches
HubSpot-defined properties. Safe to re-run any time.

`options_from: registry` builds enum options from `registry.yml` agent ids —
value = internal id, label = the agent's human name (#AP014: labels, never
internal names, in everything the team sees). Re-run the sync after
registering a new agent so `source_agent` picks up the new option.

## Current registry

| Object | Property | Type | Used by |
| --- | --- | --- | --- |
| tickets | `ticket_source` | enum (agent_feedback / call_agent / email_engine) | #AP007 ticket conventions — which mechanism filed the ticket |
| tickets | `source_agent` | enum (registry agent ids + UNKNOWN) | #AP007 — which agent the ticket is about; first consumer is the Feedback Agent |

## Running

```bash
python3 create_properties.py --dry-run   # print the plan, write nothing
python3 create_properties.py             # apply
```

Locally it reads `HUBSPOT_PRIVATE_APP_TOKEN` (or `HUBSPOT_API_KEY`) from the
repo-root `.env`; on Actions use the **HubSpot schema sync** workflow
(`workflow_dispatch`, dry-run by default) with the `HUBSPOT_API_KEY` repo
secret. The private app needs the `crm.schemas.tickets.write` scope.
`CHECK_ONLY=true` smoke-tests secrets + config without any API reads/writes.

Schema changes are deliberate: edit `properties.yml` in a PR, merge, then run
the workflow — the file is the review surface.

## Event segments (Roman 2026-09-22)

Every event gets a HubSpot segment: one **active list per `aplus_event_tag`
option**, named `Event: <option label>` (e.g. `Event: Sage Oak Park Day
2026`), filtered on the contact carrying that tag. Active, not static, so a
late booth submission or a backfill joins the list on its own.

```bash
python3 event_lists.py --dry-run   # plan: which options lack a list
python3 event_lists.py             # create the missing ones
```

The options are read from the PORTAL, not from `properties.yml`, so an option
added by hand still gets its list. The workflow runs this right after the
property sync, so a new event's list exists the moment its tag does. Existing
lists are matched by name and left alone; renaming a list in HubSpot means
the script makes a fresh one, so don't.
