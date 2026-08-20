# Zapier census — manual, one sitting

Zapier exposes **no zap-listing API**, so this half of the automation audit is
a human pass. Budget ~30–45 minutes, do it in one sitting so the snapshot is
coherent.

## How to run the census

1. Open [zapier.com/app/zaps](https://zapier.com/app/zaps) and set the filter
   to **All zaps** (on and off).
2. Sort by **last modified** so stale zaps cluster at the bottom.
3. For every zap, fill one row below. Open the zap only if the name doesn't
   tell you the trigger/action apps — don't refactor anything mid-census.
4. Bucket per #AP016, same rules as the HubSpot audit:
   - `DOORBELL` — trigger → notification/webhook only. Keep.
   - `PLUMBING` — mechanical, zero judgment. Keep.
   - `DECIDER` — any branching on business meaning. Verdict `ABSORB` + name
     the fleet agent (Email Engine v2 / Onboarding / Revival / Low-Balance-PO /
     Tutor Onboarding / Conversation / NEW).
   - `GUARDRAIL` — deliberately deterministic safety logic. Keep dumb, keep
     forever.
5. Verdict column: `KEEP` / `KILL` / `ABSORB → <agent>` / `INVESTIGATE`.
   Nothing gets turned off during the census — verdicts are proposals for the
   Decision Log, same as the HubSpot kill list.

## The table

| zap name | trigger app | action app | last active | bucket | verdict |
|---|---|---|---|---|---|
| Teachworks family-creation zap | Teachworks | HubSpot | | DECIDER | ABSORB → Onboarding (succession per #AP011) |
| Google Docs Decision Log append pipe | (chat/agent) | Google Docs | | GUARDRAIL | KEEP — house logging rail |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |

(Add rows until every zap — on **and** off — appears exactly once.)

## Known gotcha (today's Zapier lesson)

The Google Docs append action's document parameter key is `file`. Always pass
the Decision Log ID explicitly
(`1rulyEYlUldSEPvlZtoM6KcKBa2tJ8ZlZ-HMDybbMYCI`), and treat any
`resolvedParams` status of `guessed` on the `file` field as a **FAILED write**
— never assume the append landed in the right doc.

## Going forward

Enable the **Zapier Manager** app with a "zap turned on/off" trigger →
Slack notification, so on/off drift is detected instead of discovered. That
zap is itself a `DOORBELL` — add it to this table when it exists.
