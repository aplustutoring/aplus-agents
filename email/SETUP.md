# SETUP — aplus_email_agent (~30 min)

Do these in order. The agent will not run live until step 1 (scopes) and the
`config.yaml` IDs are filled. Everything is draft-only except two auto-actions
(junk archive, tutor-doc receipt).

---

## 1. HubSpot — private app, scopes, ticket pipeline, inbox id

**1a. Private app + scopes.** HubSpot → Settings → Integrations → Private Apps →
*Create a private app* (or edit the existing one). Grant scopes:
- `conversations.read`, `conversations.write`
- `tickets`
- `crm.objects.contacts.read`, `crm.objects.contacts.write`
- `crm.objects.deals.read` (for enrichment)
- `crm.objects.notes.write` (for ticket notes)

Copy the access token → this is `HUBSPOT_PRIVATE_APP_TOKEN`.
> The marketing-skills private app (blog publishing) does **not** have these scopes.
> Either extend it or mint a new app dedicated to the inbox agent.

> **No Service Hub on this portal.** That's fine — the Conversations inbox and the
> Tickets object + API + one default ticket pipeline are all FREE. We do NOT create a
> custom pipeline and do NOT use a ticket workflow (both need Service Hub Pro). Instead
> the agent uses the default pipeline and flips ticket status itself.

**1b. Inbox id + default pipeline ids (auto-discovered).** Once 1a's scopes are saved,
run `DRY_RUN=true python smoke_test.py` — it prints the inbox(es) and the default ticket
pipeline with its stage ids. Paste into `config.yaml`:
- `hubspot.inbox_id` ← the admin@wetutorathome.com inbox id
- `hubspot.ticket_pipeline_id` ← the default pipeline id (usually `0`)
- `hubspot.ticket_stages.needs_approval` ← the "New" stage id
- `hubspot.ticket_stages.handled` ← the "Waiting on contact" stage id (agent flips here after a human reply)
- `hubspot.ticket_stages.closed` ← the "Closed" stage id

**1c. No workflow needed.** The hourly SLA sweep calls `reconcile_handled()`: it checks each
open ticket's thread for a human's outbound reply (excluding the agent's own doc receipt)
and moves the ticket to the Handled stage via the API. That is how "a human approves and
sends from HubSpot" closes the loop — no Service Hub automation required.

---

## 2. Monday — two L10 Scorecard rows (board 18402267902)

On the L10 Scorecard board, add two measurable rows by hand:
- **Email SLA Breaches** (goal 0)
- **Email Median Response Time (hrs)** (goal < 8)

Get their item ids (open each item → "..." → it's in the URL, or
`check_scorecard.py` style query) and paste into
`config.yaml: monday.measurables.sla_breaches_item_id` / `median_response_hrs_item_id`.
The digest writes them into the same Sun-Sat weekly column the rest of the scorecard uses.

---

## 3. Slack — app, scopes, channel, member ids

Reuse the A+ Slack app (bot **@aplus**, same `SLACK_BOT_TOKEN` as marketing-skills).
Validated 2026-06-09: token works (team "A+ Tutoring"); it already has `chat:write` +
`chat:write.public`. STILL NEEDED:

**3a. Add bot scope `im:write`** (so the agent can DM owners), then **reinstall** the app
to the workspace. Optionally add `users:read` (only needed to look up / verify member
names; the agent DMs by id and doesn't require it at runtime).
- Alternative: skip `im:write` and switch owner pings to **`#email-agent` @mentions**
  (needs no extra scope). Tell the builder which you want; default is DMs.

**3b. Create channel `#email-agent`** (does not exist yet) for the digest + (optionally)
owner pings. The bot can post via `chat:write.public` even without joining.

**3c. Verify member ids.** Already in `config.yaml: staff` (Danielle, Mandy, Paola,
Janelle, Yolanda, Kath, Emily, Roman). These could NOT be auto-verified because
`users:read` isn't granted — once it is, re-run the Slack check, or just confirm the
first real DM lands. Member id = Profile → ⋯ → *Copy member ID* (`Uxxxxxxxx`).

---

## 4. Google Sheet (dashboard)  — one manual step

The service account can't create files (no Drive quota), but it CAN append to a sheet
you create and share with it. So, once:
1. New Google Sheet → rename a tab to **Email Agent** (exact).
2. Share → Editor → **`aplus-retention@a-plus-retention.iam.gserviceaccount.com`**.
3. Paste the Sheet id (from its URL) → `config.yaml: google_sheets.dashboard_sheet_id`.

`GOOGLE_SHEETS_CREDS` secret is already loaded (the service-account JSON). Until the
Sheet id is set, the digest just skips the Sheet write (Slack + Monday still post).

---

## 5. GitHub secrets

Repo → Settings → Secrets and variables → Actions → add all six:
`HUBSPOT_PRIVATE_APP_TOKEN`, `TEACHWORKS_TOKEN`, `ANTHROPIC_API_KEY`,
`SLACK_BOT_TOKEN`, `MONDAY_TOKEN`, `GOOGLE_SHEETS_CREDS`.

> `ANTHROPIC_API_KEY` here is a **dedicated key for the email agent** — intentionally a
> different token than aplus-marketing-skills uses. Secrets are per-repo, so the two
> never share a key or quota.

---

## 6. Smoke test (before enabling cron)

Locally, with `.env` filled:
```
python -m pytest -q          # all green, incl. Fri 7 PM → Mon 1 PM SLA case
DRY_RUN=true python smoke_test.py
```
The smoke test prints the scope probe (all ✅) and a dry-run triage pass that logs
intended tickets/routes/drafts/Slack DMs and writes nothing. When it looks right,
the three workflows are already scheduled — they'll start on their next cron tick.
Use each workflow's **Run workflow** (workflow_dispatch) with *dry_run = true* to test
in CI first.

---

## Notes / known limitations
- **No native HubSpot draft.** The proposed reply is posted as an internal **COMMENT**
  on the thread (team-only). A human sends the real reply; the hourly sweep's
  `reconcile_handled()` then flips the ticket to Handled (no Service Hub workflow).
- **No Service Hub.** Default ticket pipeline only; status transitions are agent-managed.
- **Tickets associate to the contact** via the API. The conversation thread is linked
  by the COMMENT the agent posts on it (threads aren't CRM objects you can associate to).
- **The only outbound email the agent sends** is the tutor-document receipt. Any other
  send path raises in code.

---

## 7. Charter PO inbox (separate Gmail) — one-time setup

The agent reads the PO Gmail with the existing service account via domain-wide
delegation (read + label + create drafts; it can never send or delete).

**7a. Grant delegation (Workspace admin, ~2 min):**
[admin.google.com](https://admin.google.com) → Security → Access and data control →
API controls → **Domain-wide delegation** → *Add new*:
- Client ID: `115715582460957390030`
- OAuth scope: `https://www.googleapis.com/auth/gmail.modify`

**7b. Set the address:** `config.yaml → po_inbox.address` = the PO mailbox
(e.g. po@wetutorathome.com). Empty = the whole flow stays off.

**7c. First run baselines** (no backlog replay); after that, every PO:
ticket → Kath, deal advanced past "Waiting for PO" (or created), Gmail labeled
(`A+ Agent/Processed`, `School/<name>`), a real draft reply left in Drafts, Slack DM.
