# A+ Automation Fleet — current breakdown

**Generated from `registry.yml` — do not edit by hand.** Regenerated on every merge to `main` by `ops/fleet-health/fleet_brief.py`. Safe to paste anywhere (a Claude chat, an email, a doc) knowing it matches what is actually running.

**36 registered agents** — 23 active · 10 manual · 3 deprecated · across 9 engines.

Everything runs on GitHub Actions cron out of one repo (`aplustutoring/aplus-agents`). No always-on machine. HubSpot owns families and all communication; Teachworks owns lessons; engines sync from Teachworks into HubSpot. For architecture and governance read `ARCHITECTURE.md`; for the full per-agent detail read `registry.yml`.

## At a glance

| Engine | Agents | Active |
|---|---|---|
| B2B blogs | 6 | 3 |
| B2C spotlights | 4 | 1 |
| Email / inbox ops | 9 | 9 |
| Data sync | 3 | 3 |
| Call agent | 1 | 1 |
| Messenger | 2 | 1 |
| Feedback agent | 2 | 2 |
| Fleet health | 4 | 3 |
| Charter analysis | 5 | 0 |

## Autonomy — what acts without asking

The distinction that matters most, and it does not follow engine lines.

**Writes to live systems on its own (13):** `content-build`, `spotlight-orchestrator`, `scorecard-weekly-sync`, `retention-sync`, `missed-lessons-sync`, `call-agent`, `feedback-fix`, `fleet-retry`, `email-triage`, `email-sla-sweep`, `email-po-inbox`, `email-deal-sync`, `campaign-launch`.

**Reports, drafts, or waits for a human (10):** `topic-gen`, `blog-metrics`, `feedback-agent`, `email-weekly-digest`, `email-daily-summary`, `email-hourly-update`, `email-po-daily-report`, `email-draft-feedback`, `fleet-docs`, `branch-hygiene`.

**Manual dispatch only (10):** `rerender-textstory`, `backfill-logsheet`, `verify-logsheet`, `charter-gap-analysis`, `tw-tutor-active-check`, `tw-invoice-status`, `tw-invoice-xref`, `tw-invoice-backfill`, `hubspot-schema`, `bulk-messenger`.

Note: *writes to live systems* includes agents whose only write is a **draft** (blog drafts, draft replies) — the agent creates the object, a human still ships it. `ARCHITECTURE.md` draws that finer line.

## By engine

### B2B blogs

| Agent | Runs | Status | Reads | Writes |
|---|---|---|---|---|
| **blog-metrics**<br>Blog metrics scorecard (Monday 9 AM PT) | 09:00 PDT Mon | active | marketing/state/history.json, HubSpot:blog_posts | Slack |
| **content-build**<br>Content build (Saturday — approved slate → HubSpot drafts) | 08:00 PDT Sat | active | marketing/state/topic-queue.json, HubSpot:blog_posts | HubSpot:blog_posts, Slack, marketing/state/topic-queue.json, marketing/state/history.json |
| **topic-gen**<br>Topic generation (Thursday 5 PM PT) | 17:00 PDT Thu | active | marketing/state/topic-registry.json | marketing/state/topic-queue.json, marketing/state/history.json |
| **approval-deadline**<br>Approval deadline check (DEPRECATED — approval gate removed) | manual | deprecated | marketing/state/topic-queue.json | marketing/state/topic-queue.json, marketing/state/history.json |
| **approval-poll**<br>Approval poll (DEPRECATED — approval gate removed) | manual | deprecated | marketing/state/topic-queue.json | marketing/state/topic-queue.json, marketing/state/history.json |
| **blog-publish**<br>Blog publish (DEPRECATED — superseded by content-build) | manual | deprecated | marketing/state/topic-queue.json | HubSpot:blog_posts, marketing/state/topic-queue.json, marketing/state/history.json |

### B2C spotlights

| Agent | Runs | Status | Reads | Writes |
|---|---|---|---|---|
| **spotlight-orchestrator**<br>Spotlight Orchestrator | on event | active | GoogleDrive, marketing/data/partner-schools.md, HubSpot:contacts | HubSpot:blog_posts, Slack, marketing/data/partner-schools.md, marketing/aplus-content/<bundle>/ |
| **backfill-logsheet**<br>Backfill case-study log sheet | manual | manual | GoogleDrive | GoogleSheets |
| **rerender-textstory**<br>Re-render textstories for a bundle | manual | manual | bundle artifact (passed via --bundle), marketing/assets/sfx/ | Slack |
| **verify-logsheet**<br>Verify case-study log sheet | manual | manual | GoogleSheets | — |

### Email / inbox ops

| Agent | Runs | Status | Reads | Writes |
|---|---|---|---|---|
| **email-daily-summary**<br>Daily summary (6 PM PT DM) | daily 6 PM PT | active | email/state/audit_log.jsonl, HubSpot:tickets | Slack |
| **email-deal-sync**<br>Deal sync (HubSpot → Teachworks) + invoice sweep | every 15 min during business hours + hourly | active | HubSpot:deals, HubSpot:contacts, Teachworks:customers/students/lessons | Teachworks:customers+students (family upsert by email; per-pipeline billing; guards: charter contact must match deal-name parent, internal domains skipped), Slack (needs-review flags; invoice-sweep submit prompts to Kath) |
| **email-draft-feedback**<br>Draft feedback weekly (Fri 4 PM PT) | 16:00 PDT Fri / 15:00 PST | active | Gmail:drafts, email/state/draft_registry.jsonl | corrections/email-drafts/, email/state/, Slack |
| **email-hourly-update**<br>Hourly launch-monitoring update | hourly, business hours | active | email/state/audit_log.jsonl | Slack |
| **email-po-daily-report**<br>PO day report (6 PM PT) | 18:00 PDT Mon-Fri / 17:00 PST | active | HubSpot:deals, Teachworks:invoices | Slack |
| **email-po-inbox**<br>Charter PO inbox (charter@wetutorathome.com) | every 15 min during business hours + hourly | active | Gmail:charter@ (incl. PDF/image PO attachments), HubSpot:deals, HubSpot:contacts, Teachworks:lessons (upcoming-calendar check) | HubSpot:deals (create; Level Up A 88841552 routing; props: po_number, number_of_hours_in_this_po, student_first_name, student_last_name_if_diff_from_parent, student_grade, student_school, parent_email, parent_phone, lessons_fulfilled_date), HubSpot:contacts (find-or-create parent + TOR, associate to deal), HubSpot:files+notes (PO PDF pinned to the deal), HubSpot:tickets+tasks (Kath ticket; same-day convert-PO-to-TW-invoice task), Gmail:labels (drafts only on non-PO mail — POs never get replies), Slack (Kath DM; URGENT duplicate-PO alert; no-lessons scheduling nudge) |
| **email-sla-sweep**<br>SLA sweep | hourly | active | HubSpot:tickets | Slack, HubSpot:tickets |
| **email-triage**<br>Inbox triage | every 15 min during business hours + hourly | active | HubSpot:conversations, HubSpot:contacts, Teachworks | HubSpot:tickets, HubSpot:conversations(comment), Slack |
| **email-weekly-digest**<br>Weekly digest | Mon 8 AM PT | active | HubSpot:tickets, email/state/audit_log.jsonl | Slack |

- **email-po-inbox** — Chains deal_sync.sync_deal for the new deal in the SAME run (no cron lag).
- **email-deal-sync** — Invoice sweep (daily 9 AM PT inside this workflow): active charter PO deals — attended TW hours >= PO hours → prompt Kath to submit to the school's ops system now, else prompt at end of PO month (lessons_fulfilled_date)
- **email-po-daily-report** — Read-only + one DM
- **email-draft-feedback** — The team's edits ARE the training signal (#AP008 corrections path)

### Data sync

| Agent | Runs | Status | Reads | Writes |
|---|---|---|---|---|
| **missed-lessons-sync**<br>Missed-lessons sync | 08:55 PDT / 07:55 PST Mon | active | Teachworks | Monday |
| **retention-sync**<br>Retention sync | 09:00 PDT / 08:00 PST Mon | active | Teachworks | GoogleSheets, Slack |
| **scorecard-weekly-sync**<br>Weekly scorecard sync | 10:00 PDT / 09:00 PST Mon | active | Teachworks | HubSpot, Monday |

- **scorecard-weekly-sync** — CHECK_ONLY smoke mode for CI (no DRY_RUN)
- **retention-sync** — Has built-in DRY_RUN
- **missed-lessons-sync** — CHECK_ONLY smoke mode for CI (no DRY_RUN).

### Call agent

| Agent | Runs | Status | Reads | Writes |
|---|---|---|---|---|
| **call-agent**<br>Call agent — daily digest (~5:30 PM PT) | 17:30 PDT / 16:30 PST daily | active | JustCall, HubSpot:contacts, ops/call_agent/state/state.json | HubSpot:calls, HubSpot:contacts, HubSpot:tasks, HubSpot:notes, HubSpot:tickets, Slack, ops/call_agent/state/state.json |

- **call-agent** — Claude summarization + record-update proposal (claude-opus-4-7, structured outputs)

### Messenger

| Agent | Runs | Status | Reads | Writes |
|---|---|---|---|---|
| **campaign-launch**<br>Campaign launch (Monday enrollments) | 09:00 PDT / 08:00 PST daily — gated in enroll.py | active | ops/messenger/campaign.yml, HubSpot | HubSpot |
| **bulk-messenger**<br>Bulk messenger (on-demand email/SMS to a HubSpot list) | manual | manual | HubSpot | HubSpot, JustCall |

- **bulk-messenger** — BULK ONLY (min_bulk 25) — refuses 1:1 sends
- **campaign-launch** — The daily cron is a no-op unless campaign.yml has `armed: true` AND today (PT) == launch_date — arming is a deliberate config change in a PR, so a launch is a human decision that the cron merely executes

### Feedback agent

| Agent | Runs | Status | Reads | Writes |
|---|---|---|---|---|
| **feedback-agent**<br>Feedback agent — #agent-feedback intake + Friday digest | on event | active (draft) | Slack, registry.yml, ops/feedback-agent/state/state.json | Slack, corrections/<agent>/, registry.yml, HubSpot:tickets, ops/feedback-agent/state/ |
| **feedback-fix**<br>Feedback agent — execute approved fix | on event | active | corrections/<agent>/, registry.yml, the agent's own source | GitHub: fix/ branch + PR to main (never merged by the agent), Slack |

- **feedback-agent** — Claude classification (structured outputs): agent (registry id or UNKNOWN -> Zapier-census flag) x type (BROKEN/WRONG/ANNOYING/IDEA/ DEMOTE) x severity (critical/normal/low)
- **feedback-fix** — Confirms or corrects the diagnosis before changing anything; stays scoped to the approved plan (implements the honest minimal version and says so if the real fix differs)

### Fleet health

| Agent | Runs | Status | Reads | Writes |
|---|---|---|---|---|
| **branch-hygiene**<br>Fleet — branch hygiene (Mon 9 AM PT) | 09:00 PDT / 08:00 PST Mon | active | git | Slack |
| **fleet-docs**<br>Fleet — registry check + FLEET.md | event | active | registry.yml, .github/workflows/, docs/FLEET.md | docs/FLEET.md |
| **fleet-retry**<br>Fleet retry sweeper (every 20 min) | every 20 min, offset from agent crons | active | GitHub:actions_runs, ops/feedback-agent/config.yml | GitHub:actions_runs, Slack |
| **hubspot-schema**<br>HubSpot schema sync (manual) | manual | manual | ops/hubspot-schema/properties.yml, registry.yml, HubSpot | HubSpot |

- **fleet-retry** — Excludes itself and the approved-fix executor (paid coding-agent runs are never blindly retried)
- **hubspot-schema** — Idempotent + additive only
- **fleet-docs** — ROLLOUT: PR runs use --warn, so an unregistered workflow annotates the PR without blocking the merge
- **branch-hygiene** — Catches work stranded outside main (2026-08-05 incidents: PR #47 sat unmerged for a week; a CallRail matching fix sat unpushed locally for 16 days)

### Charter analysis

| Agent | Runs | Status | Reads | Writes |
|---|---|---|---|---|
| **charter-gap-analysis**<br>Charter gap analysis (manual report) | manual | manual | HubSpot:deals, HubSpot:contacts, Teachworks | GitHub: run artifact charter_gap_analysis.xlsx (7-day retention), HubSpot:contacts — ONLY with write_props=true: last_tutor_name + student_first_name onto list-3104 contacts, UPDATE-only import |
| **tw-invoice-backfill**<br>TW invoice-submitted backfill (verified) | manual | manual | HubSpot:deals, Teachworks:invoices | HubSpot:deals — ONLY with apply=true: invoice_submitted_date + Invoice Submitted stage, on TW-verified deals |
| **tw-invoice-status**<br>TW invoice status by list (read-only) | manual | manual | HubSpot:contacts, Teachworks:invoices (with payment status) | — |
| **tw-invoice-xref**<br>TW invoice cross-reference (read-only) | manual | manual | HubSpot:deals, Teachworks:invoices | — |
| **tw-tutor-active-check**<br>TW tutor active check (charter gap) | manual | manual | HubSpot:contacts — [Agent] Last Tutor Name on the gap contacts, Teachworks:employees | HubSpot:contacts — ONLY with write_props=true: [Agent] Last Tutor Active |

- **charter-gap-analysis** — Read-only by default
- **tw-tutor-active-check** — Guards the campaign's personalization tokens — never promise a family a tutor who has left
- **tw-invoice-xref** — Recent PO deals <-> Teachworks invoices
- **tw-invoice-backfill** — One-off, written to clear the 2026-08-07..09 invoice-sweep backlog

