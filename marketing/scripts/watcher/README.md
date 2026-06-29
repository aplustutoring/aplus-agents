# Spotlight Watcher — Deployment Guide

End-to-end flow once deployed:

```
Paola drops a folder    Apps Script polls the intake     GitHub Actions
into her Drive          folder every 5 minutes, calls    downloads the
intake folder    -->    repository_dispatch on this  --> Drive folder,
                        repo with the folder ID          runs the
                                                         orchestrator,
                                                         ships HubSpot
                                                         draft + Slack
                                                         delivery
```

This directory ships three pieces:

| File                          | Where it runs              | What it does                          |
|-------------------------------|-----------------------------|----------------------------------------|
| `apps-script.gs`              | Google Apps Script          | Polls Drive, fires the GitHub workflow |
| `download-drive-folder.py`    | GitHub Actions runner       | Downloads the Drive folder into /tmp   |
| `spotlight-orchestrator.yml`  | GitHub Actions (`.github/`) | Wraps the orchestrator in a CI job     |

The A+ logo lives in the repo at `marketing/assets/logo.png`. The graphics
compositor (`marketing/scripts/shared/composite-logo.py`) and the IG-story builder
prefer that path and fall back to `~/Desktop/logo.png` for local dev, so
CI works with no extra Drive download step.

The orchestrator itself is unchanged — it still takes `--source <local-dir>` and runs locally for development.

---

## Deployment checklist

### 1. Create a Google service account for Drive read access

1. In the **same Google Cloud project** that owns the Drive workspace (or any project you control), go to **IAM & Admin > Service Accounts**.
2. **Create service account** — name it `aplus-spotlight-drive-reader` or similar.
3. Skip the "Grant access" step for the project (no GCP roles needed).
4. Open the new service account, go to **Keys > Add Key > Create new key > JSON**. Download the JSON.
5. In Drive, **share the intake folder** with the service account's email (something like `aplus-spotlight-drive-reader@<project>.iam.gserviceaccount.com`) as **Viewer**. The watcher only needs read access. (The logo lives in the repo at `marketing/assets/logo.png`, so the service account does NOT need access to any other Drive file.)

### 2. Add GitHub repo secrets

Go to **Settings > Secrets and variables > Actions > Secrets** on the `aplustutoring/aplus-agents` repo and add:

| Secret                              | Value                                                  |
|-------------------------------------|--------------------------------------------------------|
| `ANTHROPIC_API_KEY`                 | Same key the orchestrator uses locally                 |
| `OPENAI_API_KEY`                    | Same key the orchestrator uses locally                 |
| `GEMINI_API_KEY`                    | Same key the orchestrator uses locally                 |
| `HUBSPOT_PRIVATE_APP_TOKEN`         | The Private App token (NOT the MCP connector — that's a different path) |
| `SLACK_BOT_TOKEN`                   | The A+ Tutoring Slack bot token                        |
| `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` | Paste the full JSON content of the key from step 1     |
| `SPOTLIGHT_LOG_SHEET_ID` (optional) | ID of the master case-study decode-log Google Sheet (one row per study: date, pseudonym, real name, school, grade, subject, link, bundle). Share that sheet as **Editor** with the service account and enable the **Google Sheets API** in the project. Unset → the `logsheet` stage skips. |

### 3. Add GitHub repo variables (optional)

Go to **Settings > Secrets and variables > Actions > Variables** if you want to override the default failure channel:

| Variable                       | Value                                       |
|--------------------------------|---------------------------------------------|
| `SLACK_FAILURE_CHANNEL`        | (optional) channel for failure pings — defaults to `#student-spotlight-ready` |

### 4. Create a GitHub fine-grained PAT for the Apps Script

1. On `github.com`: **Settings > Developer settings > Personal access tokens > Fine-grained tokens > Generate new token**.
2. Resource owner: `aplustutoring`. Repository access: only `aplus-agents`.
3. Repository permissions: **Actions: Read and write**, **Contents: Read** (Contents is needed because `repository_dispatch` is technically a contents-level call on the GitHub API).
4. Expiration: pick a date you'll remember (a year is fine, the watcher will fail loudly when it expires).
5. Copy the token immediately — you can't view it later.

### 5. Deploy the Apps Script

1. In Drive, **create a new Apps Script project** (New > More > Google Apps Script). Name it `A+ Spotlight Watcher`.
2. **Paste the entire contents** of `apps-script.gs` into `Code.gs`.
3. **Project Settings > Script Properties > Edit script properties** — add:
   - `INTAKE_FOLDER_ID` → the Drive folder ID Paola drops into
   - `GITHUB_OWNER` → `aplustutoring`
   - `GITHUB_REPO` → `aplus-agents`
   - `GITHUB_PAT` → the PAT from step 4
   - `ERROR_NOTIFY_EMAIL` → (optional) your email for poll-cycle errors
4. **Save**, then in the editor switch to function `checkConfig` and click **Run**. Authorize the script when prompted (it needs Drive read/write and outbound URL fetch). The execution log should show every property as `set`.
5. Switch to `listIntakeFolders` and **Run**. You should see your existing subfolders listed with status `READY` / `INCOMPLETE` / `DISPATCHED`.
6. **Triggers** (the clock icon in the left sidebar) > **Add Trigger**:
   - Function: `pollIntakeFolder`
   - Event source: `Time-driven`
   - Type: `Minutes timer`
   - Interval: `Every 5 minutes`
   - Failure notification: `Notify me immediately`

The watcher is now live. The next time Paola drops a folder containing `parent-call*`, `lesson-notes*`/`lesson-report*`, and `paola-brief*`, the next poll cycle dispatches the workflow and drops a `.spotlight-dispatched` sentinel into the folder.

---

## How to test end-to-end without bothering Paola

1. In the **intake folder**, create a new subfolder named e.g. `2026-06-test`.
2. Drop three test files into it:
   - `parent-call-transcript.txt`
   - `lesson-report.pdf` (or a `.txt` for fastest iteration)
   - `paola-brief.txt`
3. Either wait up to 5 minutes for the next poll OR open the Apps Script editor and **Run > `pollIntakeFolder`** to fire immediately.
4. Watch **the GitHub Actions tab** of the repo. A run named "Spotlight Orchestrator" should appear within ~10 seconds.
5. The workflow runs ~5 minutes end-to-end. On success:
   - A HubSpot DRAFT is created (idempotent on slug — re-runs reuse).
   - In-body graphics are embedded.
   - A Slack thread lands in `#student-spotlight-ready` with the file pack.
   - The bundle is uploaded as a workflow artifact (downloadable from the run page for 30 days).

If anything fails, the workflow posts a `:rotating_light:` ping to `#student-spotlight-ready` (or `SLACK_FAILURE_CHANNEL` if you set it). Open the Actions run and read the orchestrator log artifact.

---

## Re-running a folder

The sentinel-file design means a successful dispatch is durable: re-polling won't double-fire. If you need to re-run the orchestrator against the same source folder (e.g. you fixed a metadata prompt and want a fresh bundle):

**Option A — workflow_dispatch.** In GitHub Actions UI, click **Run workflow** on the Spotlight Orchestrator and paste the Drive folder ID. The orchestrator's HubSpot stage is idempotent on slug, so the existing draft gets reused (with `--reset-figures` passed to embed-pull-quotes so figures don't duplicate).

**Option B — clear the sentinel.** In the Apps Script editor, edit `resetSentinel`'s `FOLDER_NAME`, run it once, then either wait for the next poll or run `pollIntakeFolder` manually.

---

## Failure modes worth knowing

- **HubSpot Private App token expires or loses permissions.** The orchestrator's `stage_publish` raises `HubSpotPublishFailure` with a clear 401 message. The workflow exits non-zero and the Slack ping fires. The MCP-connector `REQUIRES_REAUTHORIZATION` state is a separate path and doesn't affect this token.
- **Service account loses Drive access.** `download-drive-folder.py` exits 2 with a "cannot fetch Drive folder" message. Re-share the intake folder with the service account.
- **Google Drive folder contains a `.docx` that's actually a Google Doc.** The download script skips Google-native mimeTypes; Paola should "File > Download > .docx" first. The Stage 1 required-file check then surfaces the missing source if she forgot.
- **PAT expires.** Apps Script polls log "GitHub dispatch returned HTTP 401" on every cycle. Generate a new PAT, update the `GITHUB_PAT` Script Property.
- **Concurrency.** `concurrency.group` is keyed on folder ID, so a quick double-dispatch of the same folder won't double-publish. Different folders run in parallel.
