# A+ Automation Fleet — handoff brief

**Generated from `registry.yml` — do not edit by hand.** Regenerated on every merge to `main` by `ops/fleet-health/fleet_brief.py`. Self-contained on purpose: paste the whole thing into a Claude chat (or hand it to a new person) and it is everything needed to reason about the fleet, current as of the last merge.

**47 registered agents** — 32 active · 11 manual · 3 deprecated · across 12 engines.

## What this is

A+ Tutoring runs its operations on a fleet of automated agents. They live in one
repo (`aplustutoring/aplus-agents`) and run on GitHub Actions cron — there is no
always-on server. Each run commits its own state back to the repo, which is why
the remote is usually well ahead of any local checkout.

**Not everything is a GitHub Action.** Most agents are Actions cron jobs, but some
run elsewhere — Google Apps Scripts (the Drive watcher, the Slack relay), and
Cloudflare Workers. Those carry a `runtime:` in the registry and show it in the
tables below. It matters because they deploy by hand, outside CI: editing the
file in this repo does **not** make the change live, and if one stops, nothing in
GitHub goes red.

**Systems in play:** HubSpot (CRM, portal 6312752) · Teachworks (lessons and
scheduling) · JustCall (phones + SMS) · Monday (boards) · Slack (where agents
talk to humans) · Google Drive/Sheets (spotlight intake, retention log).

**Sources of truth — these two settle every argument:**

| System | Owns |
|---|---|
| **HubSpot** | Families: all contact information AND all communication — contacts, deals, tickets, conversations, blog posts |
| **Teachworks** | Lessons: scheduling, attendance, invoices |

Agents sync **from Teachworks into HubSpot**. No sheet, cache, or state file
outranks those two. HubSpot is where humans act.

## At a glance

| Engine | Agents | Active |
|---|---|---|
| B2B blogs | 6 | 3 |
| B2C spotlights | 5 | 2 |
| Email / inbox ops | 10 | 10 |
| Data sync | 3 | 3 |
| Call agent | 2 | 2 |
| Messenger | 2 | 1 |
| Feedback agent | 3 | 3 |
| Fleet health | 6 | 5 |
| Charter analysis | 7 | 1 |
| Events | 1 | 1 |
| Email ops | 1 | 0 |
| Tutor issues | 1 | 1 |

## Autonomy — what acts without asking

The distinction that matters most, and it does not follow engine lines.

**Writes to live systems on its own (18):** `content-build`, `spotlight-orchestrator`, `scorecard-weekly-sync`, `retention-sync`, `missed-lessons-sync`, `call-agent`, `feedback-fix`, `fleet-retry`, `email-triage`, `email-sla-sweep`, `email-po-inbox`, `email-deal-sync`, `teacher-sequence-enroll`, `sage-oak-booth`, `spotlight-drive-watcher`, `feedback-slack-relay`, `campaign-launch`, `tutor-issues`.

**Reports, drafts, or waits for a human (15):** `topic-gen`, `blog-metrics`, `deal-sync-relay`, `call-agent-webhook-relay`, `feedback-agent`, `task-completion-sweep`, `email-weekly-digest`, `email-daily-summary`, `email-hourly-update`, `email-po-daily-report`, `email-draft-feedback`, `credential-expiry`, `fleet-docs`, `pr-merge-nudge`, `branch-hygiene`.

**Manual dispatch only (11):** `rerender-textstory`, `backfill-logsheet`, `verify-logsheet`, `charter-gap-analysis`, `teacher-outreach-2026-09`, `tw-tutor-active-check`, `tw-invoice-status`, `tw-invoice-xref`, `tw-invoice-backfill`, `hubspot-schema`, `bulk-messenger`.

Note: *writes to live systems* includes agents whose only write is a **draft** (blog drafts, draft replies) — the agent creates the object, a human still ships it. `ARCHITECTURE.md` draws that finer line.

## By engine

### B2B blogs

| Agent | Runs | Status | Reads | Writes |
|---|---|---|---|---|
| **blog-metrics**<br>Blog metrics scorecard (Monday 9 AM PT) | 09:00 PDT Mon | active (draft) | marketing/state/history.json, HubSpot:blog_posts | Slack |
| **content-build**<br>Content build (Saturday — approved slate → HubSpot drafts) | 08:00 PDT Sat | active | marketing/state/topic-queue.json, HubSpot:blog_posts | HubSpot:blog_posts, Slack, marketing/state/topic-queue.json, marketing/state/history.json |
| **topic-gen**<br>Topic generation (Thursday 5 PM PT) | 17:00 PDT Thu | active | marketing/state/topic-registry.json | marketing/state/topic-queue.json, marketing/state/history.json |
| **approval-deadline**<br>Approval deadline check (DEPRECATED — approval gate removed) | manual | deprecated | marketing/state/topic-queue.json | marketing/state/topic-queue.json, marketing/state/history.json |
| **approval-poll**<br>Approval poll (DEPRECATED — approval gate removed) | manual | deprecated | marketing/state/topic-queue.json | marketing/state/topic-queue.json, marketing/state/history.json |
| **blog-publish**<br>Blog publish (DEPRECATED — superseded by content-build) | manual | deprecated | marketing/state/topic-queue.json | HubSpot:blog_posts, marketing/state/topic-queue.json, marketing/state/history.json |

### B2C spotlights

| Agent | Runs | Status | Reads | Writes |
|---|---|---|---|---|
| **spotlight-drive-watcher**<br>Spotlight Drive watcher (Google Apps Script) | Apps Script time-driven trigger<br>*apps-script* | active | GoogleDrive | GitHub: repository_dispatch -> spotlight-orchestrator, GoogleDrive |
| **spotlight-orchestrator**<br>Spotlight Orchestrator | on event | active | GoogleDrive, marketing/data/partner-schools.md, HubSpot:contacts | HubSpot:blog_posts, Slack, marketing/data/partner-schools.md, marketing/aplus-content/<bundle>/ |
| **backfill-logsheet**<br>Backfill case-study log sheet | manual | manual | GoogleDrive | GoogleSheets |
| **rerender-textstory**<br>Re-render textstories for a bundle | manual | manual | bundle artifact (passed via --bundle), marketing/assets/sfx/ | Slack |
| **verify-logsheet**<br>Verify case-study log sheet | manual | manual | GoogleSheets | — |

- **spotlight-drive-watcher** — Fires only for subfolders holding all three required source files (parent-call*, lesson-notes/report*, paola-brief*) that have no sentinel yet

### Email / inbox ops

| Agent | Runs | Status | Reads | Writes |
|---|---|---|---|---|
| **email-daily-summary**<br>Daily summary (6 PM PT DM) | daily 6 PM PT | active | email/state/audit_log.jsonl, HubSpot:tickets | Slack |
| **email-deal-sync**<br>Deal sync (HubSpot → Teachworks) + invoice sweep | every 15 min during business hours + hourly | active | HubSpot:deals, HubSpot:contacts, Teachworks:customers/students/lessons | Teachworks:customers+students (family upsert by email; per-pipeline billing; guards: charter contact must match deal-name parent, internal domains skipped), Slack (needs-review flags; invoice-sweep submit prompts to Kath) |
| **email-draft-feedback**<br>Draft feedback weekly (Fri 4 PM PT) | 16:00 PDT Fri / 15:00 PST | active | Gmail:drafts, email/state/draft_registry.jsonl | corrections/email-drafts/, email/state/, Slack |
| **email-hourly-update**<br>Hourly launch-monitoring update | hourly, business hours | active | email/state/audit_log.jsonl | Slack |
| **email-po-daily-report**<br>PO day report (6 PM PT) | 18:00 PDT Mon-Fri / 17:00 PST | active | HubSpot:deals, Teachworks:invoices | Slack |
| **email-po-inbox**<br>Charter PO inbox (charter@wetutorathome.com) | every 15 min during business hours + hourly | active | Gmail:charter@ (incl. PDF/image PO attachments), HubSpot:deals, HubSpot:contacts, Teachworks:lessons (upcoming-calendar check) | HubSpot:deals, HubSpot:contacts, HubSpot:files+notes, HubSpot:tickets+tasks, Gmail:labels, Slack |
| **email-sla-sweep**<br>SLA sweep | hourly | active | HubSpot:tickets | Slack, HubSpot:tickets |
| **email-triage**<br>Inbox triage | every 15 min during business hours + hourly | active | HubSpot:conversations, HubSpot:contacts, Teachworks | HubSpot:tickets, HubSpot:conversations(comment), Slack |
| **email-weekly-digest**<br>Weekly digest | Mon 8 AM PT | active | HubSpot:tickets, email/state/audit_log.jsonl | Slack |
| **task-completion-sweep**<br>Task-completion sweep (team HubSpot tasks) | weekdays 8 AM PT | active | HubSpot:tasks, email/state/audit_log.jsonl | Slack, email/state/audit_log.jsonl |

- **task-completion-sweep** — First agent to READ HubSpot Tasks back (two agents create them; nothing checked completion)
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
| **call-agent**<br>Call agent — webhook-triggered polls + daily digest (~5:30 PM PT) | 17:30 PDT / 16:30 PST daily — digest flush + backstop sweep | active | JustCall, HubSpot:contacts, ops/call_agent/state/state.json | HubSpot:calls, HubSpot:contacts, HubSpot:tasks, HubSpot:notes, HubSpot:tickets, Slack, ops/call_agent/state/state.json |
| **call-agent-webhook-relay**<br>Call agent webhook relay | event<br>*cloudflare-worker* | active | — | GitHub Actions API: workflow_dispatch on call-agent.yml (dry_run=false, no_digest=true) |

- **call-agent** — Claude summarization + record-update proposal (claude-opus-4-7, structured outputs)
- **call-agent-webhook-relay** — Deterministic dispatch relay — no call content is read (the webhook body is not even parsed) and no reasoning happens here, so no CARE pointer

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
| **feedback-slack-relay**<br>Feedback agent Slack relay (Google Apps Script) | event<br>*apps-script* | active | Slack | GitHub: repository_dispatch feedback-report -> feedback-agent |

- **feedback-agent** — Claude classification (structured outputs): agent (registry id or UNKNOWN -> Zapier-census flag) x type (BROKEN/WRONG/ANNOYING/IDEA/ DEMOTE) x severity (critical/normal/low)
- **feedback-fix** — Confirms or corrects the diagnosis before changing anything; stays scoped to the approved plan (implements the honest minimal version and says so if the real fix differs)
- **feedback-slack-relay** — The doorbell and nothing more — all classification lives in git

### Fleet health

| Agent | Runs | Status | Reads | Writes |
|---|---|---|---|---|
| **branch-hygiene**<br>Fleet — branch hygiene (Mon 9 AM PT) | 09:00 PDT / 08:00 PST Mon | active | git | Slack |
| **credential-expiry**<br>Credential expiry check (#AP044) | manual | active | knowledge/credentials.yml | Slack: warning to CREDENTIAL_ALERT_CHANNEL when a credential is within 180 days of expiry |
| **fleet-docs**<br>Fleet — registry check + FLEET.md | event | active | registry.yml, .github/workflows/, docs/FLEET.md | docs/FLEET.md |
| **fleet-retry**<br>Fleet retry sweeper (every 20 min) | every 20 min, offset from agent crons | active | GitHub:actions_runs, ops/feedback-agent/config.yml | GitHub:actions_runs, Slack |
| **pr-merge-nudge**<br>PR merge nudge (green fixes) | manual | active | GitHub: open PRs + check-run state, ops/feedback-agent/config.yml | Slack: one digest to |
| **hubspot-schema**<br>HubSpot schema sync (manual) | manual | manual | ops/hubspot-schema/properties.yml, registry.yml, HubSpot | HubSpot |

- **fleet-retry** — Excludes itself and the approved-fix executor (paid coding-agent runs are never blindly retried)
- **credential-expiry** — NEVER REMEDIATES
- **hubspot-schema** — Idempotent + additive only
- **fleet-docs** — ROLLOUT: PR runs use --warn, so an unregistered workflow annotates the PR without blocking the merge
- **pr-merge-nudge** — NEVER MERGES
- **branch-hygiene** — Catches work stranded outside main (2026-08-05 incidents: PR #47 sat unmerged for a week; a CallRail matching fix sat unpushed locally for 16 days)

### Charter analysis

| Agent | Runs | Status | Reads | Writes |
|---|---|---|---|---|
| **teacher-sequence-enroll**<br>Teacher outreach 26/27 daily sequence enroller | schedule | active | ops/messenger/teacher-sequences.yml, HubSpot:lists 3210 / 3214 / 3211, HubSpot:contacts | HubSpot:sequence enrollments — POST /automation/v4/sequences/enrollments as Danielle, ops/messenger/state/teacher-outreach-2026-09/sequence_enroll_state.json, Slack DM: batch summary to Danielle |
| **charter-gap-analysis**<br>Charter gap analysis (manual report) | manual | manual | HubSpot:deals, HubSpot:contacts, Teachworks | GitHub: run artifact charter_gap_analysis.xlsx (7-day retention), HubSpot:contacts — ONLY with write_props=true: last_tutor_name + student_first_name onto list-3104 contacts, UPDATE-only import |
| **teacher-outreach-2026-09**<br>Teacher outreach 26/27 (lists, drafts, workflows, roster) | manual<br>*local* | manual | HubSpot:contacts, HubSpot:deals | HubSpot:lists 3210-3215 — static audience lists, HubSpot:marketing emails 221134168440/845/849, HubSpot:workflows 1878517306 |
| **tw-invoice-backfill**<br>TW invoice-submitted backfill (verified) | manual | manual | HubSpot:deals, Teachworks:invoices | HubSpot:deals — ONLY with apply=true: invoice_submitted_date + Invoice Submitted stage, on TW-verified deals |
| **tw-invoice-status**<br>TW invoice status by list (read-only) | manual | manual | HubSpot:contacts, Teachworks:invoices (with payment status) | — |
| **tw-invoice-xref**<br>TW invoice cross-reference (read-only) | manual | manual | HubSpot:deals, Teachworks:invoices | — |
| **tw-tutor-active-check**<br>TW tutor active check (charter gap) | manual | manual | HubSpot:contacts — [Agent] Last Tutor Name on the gap contacts, Teachworks:employees | HubSpot:contacts — ONLY with write_props=true: [Agent] Last Tutor Active |

- **charter-gap-analysis** — Read-only by default
- **teacher-outreach-2026-09** — Roman "Go" 2026-09-04
- **teacher-sequence-enroll** — Built 2026-09-04 (Danielle: "I love that idea")
- **tw-tutor-active-check** — Guards the campaign's personalization tokens — never promise a family a tutor who has left
- **tw-invoice-xref** — Recent PO deals <-> Teachworks invoices
- **tw-invoice-backfill** — One-off, written to clear the 2026-08-07..09 invoice-sweep backlog

### Events

| Agent | Runs | Status | Reads | Writes |
|---|---|---|---|---|
| **sage-oak-booth**<br>Sage Oak BTSC 2026 photo booth | event<br>*cloudflare-worker* | active | HubSpot:contacts (search by email — find-or-create), Cloudflare KV (PHOTOS binding — serves GET /photo/<key>) | HubSpot:contacts, HubSpot:contacts persona stamp, CREATE-ONLY, HubSpot:emails, HubSpot:notes, Resend, JustCall, Cloudflare KV |

- **sage-oak-booth** — HAND-DEPLOYED, two pieces: `npx wrangler deploy` for the Worker and `npx wrangler pages deploy` for the front-end

### Email ops

| Agent | Runs | Status | Reads | Writes |
|---|---|---|---|---|
| **deal-sync-relay**<br>Deal-sync webhook relay | event<br>*cloudflare-worker* | pending-deploy | — | GitHub Actions API: workflow_dispatch on email-deal-sync.yml (defaults) |

### Tutor issues

| Agent | Runs | Status | Reads | Writes |
|---|---|---|---|---|
| **tutor-issues**<br>Tutor-issue ticketing (sweep + inbound reports + intake) | Monday sweep, 09/10 PT | active | Teachworks, email/state/audit_log.jsonl, HubSpot, JustCall, Slack | HubSpot, Slack, ops/tutor-issues/state/ |

- **tutor-issues** — Tickets on the tutor's contact record for 5 issue types; owner = Operations role (Mandy); silent internal log in v1 (nothing tutor-facing)

## Working rules every agent follows

Anyone reasoning about this fleet — human or Claude — needs these.

- **Registration.** If it isn't in `registry.yml`, it doesn't exist. That file is
  also the feedback agent's vocabulary and the DEMOTE path's target list, so an
  unregistered agent cannot be reported against or paused. Enforced in CI by
  `ops/fleet-health/registry_check.py`.
- **Read labels, never values.** Agents read HubSpot enumeration LABELS. Internal
  values differ from what humans see (e.g. lead status value `We Connected` is
  labeled "QTL - NEW").
- **Agent-written properties are marked.** Any property an agent writes carries
  the `[Agent] ` label prefix and a description starting "AGENT PROPERTY — written
  by <script>", so humans can tell agent fields from intake capture at a glance.
  New properties are declared in `ops/hubspot-schema/properties.yml` and synced by
  workflow — never created ad hoc.
- **Roles, not names.** Config keys, properties, and audit actions name roles
  (`charter_sales`), never people. Only the `staff:` block maps roles to humans.
- **Five personas.** Contacts are typed by `a_persona` (multi-select): Decision
  Maker/Director · Teacher of Record/EF/ES · Family · Tutors · Student.
- **Family→Teacher-of-Record is an association**, contact-to-contact, paired label
  "Teacher of Record" (typeId 15; reverse "Family" = 14). The stamped
  `teacher_of_record_name/email` text fields are legacy intake capture, not truth.
- **Charter PO deals** are named `Parent - Student - School N - YY/YY`. PO numbers
  are stored bare, with no "PO" prefix.
- **Pacific time.** Every workflow sets `TZ=America/Los_Angeles`. Human-facing
  output and date windows are PT; state cursors and audit logs are explicit UTC.
- **Exit codes.** An agent that accomplished NONE of its work must exit non-zero —
  the retry sweeper only reacts to non-zero exits, so a script that prints failures
  and exits 0 is invisible. Narrow on purpose: isolating one bad item so it can't
  kill a batch is good design. 0 of 50 is a failed run; 49 of 50 is a warning.
- **Concurrency.** Multiple Claude sessions share this checkout. Branch/PR work
  happens in a git worktree, never in the shared checkout.
- **Approval-first.** Nothing outbound ships without Roman's explicit go.

## How a problem gets fixed

Report it in the Slack channel `#agent-feedback` in plain English. The feedback
agent works out which agent you mean and how bad it is, asks at most one
clarifying question, files it as a correction, and proposes a fix in the thread.
Approve in the thread and a coding agent implements it on a branch and opens a PR
for Roman to merge; merging replies in the original thread to close the loop.

To stop a misbehaving agent, say so — the DEMOTE path produces a one-click PR
flipping it to draft-only. Honored first, reviewed after.

## Not built (deliberately)

**Charter prospecting / B2B sales engine.** Discussed, never built — no code, no
automation. What exists are five manual, read-only-by-default charter analysis
reports. If it is ever built for real it goes in as a fresh engine with registry
entries.

---

*Deeper detail: `ARCHITECTURE.md` for the engine map, autonomy, and known weak points · `registry.yml` for every trigger, read, and write per agent · `docs/CHANGELOG.md` for why things changed.*
