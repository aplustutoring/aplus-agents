// call-agent-webhook-relay — JustCall webhook -> delayed GitHub workflow_dispatch
//
// Why this exists: GitHub was honoring only a handful of the call agent's ~50
// daily poll crons (hours-long gaps), so coaching cards and follow-up tasks
// landed hours after calls. This Worker makes the pipeline event-driven:
// JustCall fires a webhook the moment a call completes; the Worker waits a few
// minutes (JustCall's AI transcript lags the call), then dispatches the
// existing `call-agent.yml` workflow. The agent itself is unchanged — it still
// polls from its cursor and dedupes via state.json, so duplicate or dropped
// dispatches are harmless. The daily 5:30 PM PT digest cron remains the
// backstop sweep.
//
// Routes (all require ?token=<WEBHOOK_TOKEN>):
//   POST /call-completed   JustCall webhook target. Schedules a dispatch
//                          DEFAULT_DELAY_MINUTES out (override: ?delay=N).
//                          Point the missed-call webhook here with ?delay=1 —
//                          missed-call alerts are metadata-only and shouldn't
//                          wait for a transcript.
//   POST /redispatch       Called by the Actions workflow when calls are still
//                          inside the transcript grace window (?delay=N).
//   GET  /health           Unauthenticated liveness check.
//
// Dispatches coalesce: one Durable Object holds a single alarm, and every
// request only guarantees "a dispatch happens at or after my wanted time".
// A burst of calls produces one or two workflow runs, not one per call.
//
// Secrets (wrangler secret put ...): GITHUB_TOKEN, WEBHOOK_TOKEN.
// Vars (wrangler.toml): GITHUB_REPO, WORKFLOW_FILE, DEFAULT_DELAY_MINUTES.

const MAX_DELAY_MINUTES = 60;

function clampDelay(raw, fallback) {
  const n = Number.parseInt(raw, 10);
  if (Number.isNaN(n) || n < 0) return fallback;
  return Math.min(n, MAX_DELAY_MINUTES);
}

async function dispatchWorkflow(env) {
  const url = `https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/${env.WORKFLOW_FILE}/dispatches`;
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "aplus-call-agent-webhook-relay",
      "Content-Type": "application/json",
    },
    // Live run, digest entries held for the daily flush — mirrors what the
    // old 15-min poll crons did. CALL_AGENT_LIVE still gates real writes.
    body: JSON.stringify({
      ref: "main",
      inputs: { dry_run: "false", no_digest: "true" },
    }),
  });
  if (resp.status !== 204) {
    const body = await resp.text();
    throw new Error(`workflow_dispatch failed: ${resp.status} ${body.slice(0, 300)}`);
  }
}

export class Dispatcher {
  constructor(state, env) {
    this.state = state;
    this.env = env;
  }

  // Guarantee a dispatch at or after wantedAt. Keeps at most one alarm:
  // pull it earlier if this request wants an earlier time, and remember the
  // latest wanted time so the alarm handler can re-arm for stragglers.
  async fetch(request) {
    const { wantedAt } = await request.json();
    const latest = Math.max((await this.state.storage.get("latestWantedAt")) || 0, wantedAt);
    await this.state.storage.put("latestWantedAt", latest);
    const alarm = await this.state.storage.getAlarm();
    if (alarm === null || alarm > wantedAt) {
      await this.state.storage.setAlarm(wantedAt);
    }
    return new Response(JSON.stringify({ scheduled: true, at: new Date(wantedAt).toISOString() }), {
      headers: { "Content-Type": "application/json" },
    });
  }

  async alarm() {
    // A throw here makes the platform retry the alarm with backoff — exactly
    // what we want for a transient GitHub API failure.
    await dispatchWorkflow(this.env);
    const latest = (await this.state.storage.get("latestWantedAt")) || 0;
    if (latest > Date.now() + 30_000) {
      await this.state.storage.setAlarm(latest); // stragglers arrived after this alarm was set
    } else {
      await this.state.storage.delete("latestWantedAt");
    }
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      return new Response("ok");
    }

    if (url.searchParams.get("token") !== env.WEBHOOK_TOKEN) {
      return new Response("forbidden", { status: 403 });
    }

    if (request.method !== "POST") {
      return new Response("method not allowed", { status: 405 });
    }

    const defaultDelay = clampDelay(env.DEFAULT_DELAY_MINUTES, 6);
    let delay;
    if (url.pathname === "/call-completed") {
      delay = clampDelay(url.searchParams.get("delay"), defaultDelay);
    } else if (url.pathname === "/redispatch") {
      delay = clampDelay(url.searchParams.get("delay"), 10);
    } else {
      return new Response("not found", { status: 404 });
    }

    const wantedAt = Date.now() + delay * 60_000;
    const stub = env.DISPATCHER.get(env.DISPATCHER.idFromName("dispatcher"));
    const resp = await stub.fetch("https://dispatcher/schedule", {
      method: "POST",
      body: JSON.stringify({ wantedAt }),
    });
    return new Response(await resp.text(), {
      status: resp.status,
      headers: { "Content-Type": "application/json" },
    });
  },
};
