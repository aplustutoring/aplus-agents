---
reporter: Danielle
reporter_slack_id: U05NMABF3B2
date: 2026-08-12
agent: call-agent
agent_label: Call agent — daily digest (~5:30 PM PT)
type: IDEA
severity: normal
channel: C0BL05MCJ4B
thread_ts: "1786554388.265099"
permalink: https://atutoringworkspace.slack.com/archives/C0BL05MCJ4B/p1786554388265099?thread_ts=1786554388.265099&cid=C0BL05MCJ4B
status: open
---

## Report (Danielle)

> all low balance alerts go to Paola - do not include me on the low balance, only Paola

## Classification

Request to route low-balance alerts exclusively to Paola and remove the reporter from that notification.

## Resolution (2026-09-08)

Misfiled against the call agent: the "low balance alerts" are the Teachworks
Package Balance Alerts emails (and the Monday board / HubSpot flow they fed).
The low-balance renewal agent built 2026-09-08 (`email/src/low_balance.py`)
routes every case to the `charter_sales` seat only: ticket owner, follow-up
task, and the single Slack DM (`low_balance.notify: [charter_sales]`). The
sales seat is not copied. Applied in code; status stays open until the
close-loop workflow confirms.
