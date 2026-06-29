# ops/

Operational agents and infrastructure that keep HubSpot (the single source of
truth) and Teachworks in sync — distinct from `marketing/`, which generates
content.

## Subdirectories

- **`scorecard/`** — placeholder for the weekly scorecard sync
  (`aplus_weekly_sync.py`). The live script currently lives **outside this repo**
  at `~/Documents/aplus-sync/` and is not yet version-controlled. It is cataloged
  in `registry.yml` as an external, unverified entrypoint pending a dedicated
  migration PR (secrets must be handled before it can be committed).
- **`hubspot-schema/`** — placeholder for the HubSpot property/schema management
  module (baseline properties + `create_properties.py`). Not present in this repo
  yet; reserved here so the structure exists when it lands.

Both subdirectories hold a `.gitkeep` until their modules are migrated in.
