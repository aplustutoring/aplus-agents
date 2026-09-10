// deal-sync-relay — HubSpot deal webhook -> GitHub workflow_dispatch
//
// Same worker as ops/call_agent/webhook-relay (reviewed + merged in PR #146),
// deployed as a second instance with different vars: a HubSpot private-app
// webhook (deal.creation / deal.propertyChange on dealstage) hits
// /call-completed?delay=1 and email-deal-sync.yml runs a minute later — the
// family's text + welcome email go out minutes after the deal exists instead
// of whenever GitHub's cron wakes up (Roman 2026-09-04: no cron unless
// necessary; on go-live day two families waited HOURS on a starved cron).
// Deal-sync is cursor-driven and idempotent, so duplicate, coalesced, or
// dropped dispatches are all harmless; the demoted cron stays as backstop.
//
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
    body: JSON.stringify({
      ref: "main",
      inputs: JSON.parse(env.DISPATCH_INPUTS || "{}"),
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
    if (new URL(request.url).pathname === "/status") {
      return new Response(JSON.stringify(await this.status()), { headers: { "Content-Type": "application/json" } });
    }
    const { wantedAt } = await request.json();
    const latest = Math.max((await this.state.storage.get("latestWantedAt")) || 0, wantedAt);
    await this.state.storage.put("latestWantedAt", latest);
    const alarm = await this.state.storage.getAlarm();
    // A past alarm that never fired (2026-09-09: retries exhausted while
    // GITHUB_TOKEN was unset, then nothing re-armed) must not block new work.
    const stale = alarm !== null && alarm < Date.now() - 120_000;
    if (alarm === null || alarm > wantedAt || stale) {
      await this.state.storage.setAlarm(wantedAt);
    }
    await this.state.storage.put("lastScheduledAt", Date.now());
    return new Response(JSON.stringify({ scheduled: true, at: new Date(wantedAt).toISOString(), replacedStale: stale }), {
      headers: { "Content-Type": "application/json" },
    });
  }

  async status() {
    return {
      alarm: await this.state.storage.getAlarm(),
      latestWantedAt: (await this.state.storage.get("latestWantedAt")) || null,
      lastScheduledAt: (await this.state.storage.get("lastScheduledAt")) || null,
      lastDispatchAt: (await this.state.storage.get("lastDispatchAt")) || null,
      lastDispatchError: (await this.state.storage.get("lastDispatchError")) || null,
      now: Date.now(),
    };
  }

  async alarm() {
    // A throw here makes the platform retry the alarm with backoff — exactly
    // what we want for a transient GitHub API failure.
    try {
      await dispatchWorkflow(this.env);
    } catch (e) {
      await this.state.storage.put("lastDispatchError", `${new Date().toISOString()} ${String(e).slice(0, 300)}`);
      console.error("dispatch failed", String(e));
      throw e;
    }
    await this.state.storage.put("lastDispatchAt", Date.now());
    await this.state.storage.delete("lastDispatchError");
    console.log("dispatched email-deal-sync");
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

    if (url.pathname === "/status") {
      const stub = env.DISPATCHER.get(env.DISPATCHER.idFromName("dispatcher"));
      const resp = await stub.fetch("https://dispatcher/status");
      return new Response(await resp.text(), { headers: { "Content-Type": "application/json" } });
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
