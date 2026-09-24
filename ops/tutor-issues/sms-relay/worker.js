// tutor-sms-relay - JustCall inbound SMS -> GitHub repository_dispatch (tutor-sms)
//
// Why this exists: PR #217 taught tutor_issues.py to open a scheduler-owned
// ticket when a family texts "our tutor isn't here", and taught
// tutor-issues.yml to accept `repository_dispatch: types: [tutor-sms]`.
// Nothing fired that event, so the real latency stayed at the weekday
// every-2-hours cron: a family could report a no-show at 10:05 and the ticket
// would not exist until noon. This Worker is the doorbell. JustCall fires its
// `sms.received` webhook the moment the text lands, the Worker coalesces the
// burst, and a `tutor-sms` repository_dispatch runs the inbound leg about a
// minute later.
//
// Same Dispatcher as ops/call_agent/webhook-relay (PR #146) and
// ops/deal-relay: one Durable Object, one alarm, "guarantee a dispatch at or
// after my wanted time". Two deliberate differences:
//   1. it POSTs /repos/<repo>/dispatches (repository_dispatch), not
//      /actions/workflows/<file>/dispatches (workflow_dispatch),
//   2. a MIN_INTERVAL_SECONDS floor, because inbound texts are not rare the
//      way deal creations are. A win-back blast can draw dozens of replies in
//      minutes, and every one of them would otherwise be an Actions run.
//
// Duplicate or coalesced dispatches are harmless: the engine keeps a stable
// key per event in ops/tutor-issues/state/processed.json plus the weekly
// per-tutor dedupe, and PR #217 made repository_dispatch runs commit that
// state the same way scheduled runs do. Running twice on the same text
// produces the same one ticket. The weekday cron stays as the backstop, so a
// dead relay costs hours, not reports.
//
// Routes:
//   POST /sms      JustCall `sms.received` target (?token=<WEBHOOK_TOKEN>,
//                  optional ?delay=N minutes). Fires only for inbound texts
//                  (see isInbound below). No line or number filter: the
//                  engine already reads every line on the account.
//   GET  /health   Unauthenticated liveness check. 200 "ok" only when both
//                  secrets are set; 503 naming the missing ones otherwise
//                  (2026-09-09: the call relay ran a day with neither secret
//                  and nothing said so).
//   GET  /status   Dispatcher state: alarm, latestWantedAt, lastScheduledAt,
//                  lastDispatchAt, lastDispatchError.
//
// Secrets (wrangler secret put ...): GITHUB_TOKEN, WEBHOOK_TOKEN.
// Vars (wrangler.toml): GITHUB_REPO, EVENT_TYPE, DEFAULT_DELAY_MINUTES,
// MIN_INTERVAL_SECONDS.

const MAX_DELAY_MINUTES = 60;
const MAX_MIN_INTERVAL_SECONDS = 3600;
const DEFAULT_MIN_INTERVAL_SECONDS = 90;

// Fields that might carry the direction of a text, in preference order. The
// real payload shape is NOT verified yet (see README: the shape log exists to
// settle it off the first live delivery).
const DIRECTION_FIELDS = ["direction", "sms_direction", "type"];

export function clampDelay(raw, fallback) {
  const n = Number.parseInt(raw, 10);
  if (Number.isNaN(n) || n < 0) return fallback;
  return Math.min(n, MAX_DELAY_MINUTES);
}

export function clampInterval(raw, fallback) {
  const n = Number.parseInt(raw, 10);
  if (Number.isNaN(n) || n < 0) return fallback;
  return Math.min(n, MAX_MIN_INTERVAL_SECONDS);
}

// Only a value that actually looks like a direction counts as a direction.
// `type` is on the candidate list because JustCall might put "inbound" there,
// but it might equally hold "sms" or "message". Reading "sms" as "not inbound"
// would drop every late report on the floor, which is the exact failure this
// relay exists to prevent, so a non-direction value is treated as "this field
// does not answer the question" and we fall through to the next candidate.
function directionish(value) {
  if (typeof value !== "string") return null;
  const v = value.trim().toLowerCase();
  if (v.startsWith("in") || v.startsWith("out")) return v;
  return null;
}

/**
 * Decide whether a webhook body describes an INBOUND text.
 *
 * Defensive on purpose, the way booth/eo/worker.js reads the same account's
 * SMS payloads: unwrap `data` if present, then take the first field that
 * carries a direction-shaped value. A value starting with "in" is inbound.
 *
 * With no direction field at all we fire ANYWAY. The event we subscribe to is
 * named `sms.received`, so a missing field almost certainly means inbound, and
 * one spurious run of an idempotent engine costs a GitHub Actions minute while
 * a missed run costs a family two hours of nobody knowing their tutor never
 * showed up.
 *
 * Returns { inbound, field, value, reason } - never the message body, the
 * phone number, or the contact name.
 */
export function isInbound(body) {
  const d = (body && body.data) || body || {};
  for (const field of DIRECTION_FIELDS) {
    const value = directionish(d[field]);
    if (value === null) continue;
    const inbound = value.startsWith("in");
    return {
      inbound,
      field,
      value,
      reason: inbound ? "direction field says inbound" : "direction field says outbound",
    };
  }
  return {
    inbound: true,
    field: null,
    value: null,
    reason: "no direction field present; sms.received implies inbound",
  };
}

/**
 * Key NAMES only, never values. This is how the payload shape gets learned
 * from a real delivery without a single phone number or message body reaching
 * the Workers log. Remove or reduce it once the shape is settled.
 */
export function shapeLog(body) {
  const keys = body && typeof body === "object" ? Object.keys(body) : [];
  const inner =
    body && typeof body.data === "object" && body.data !== null ? Object.keys(body.data) : [];
  return { keys, data_keys: inner };
}

/**
 * Cost floor: never dispatch more often than once per minIntervalMs.
 *
 * Pure so it can be reasoned about (and exercised) on its own. Returns the
 * time the dispatch should actually happen, which is the requested time
 * pushed out to lastDispatchAt + minIntervalMs when the floor has not elapsed.
 * With no dispatch on record the requested time stands.
 */
export function floorWantedAt(wantedAt, lastDispatchAt, minIntervalMs) {
  if (!lastDispatchAt || !minIntervalMs) return wantedAt;
  return Math.max(wantedAt, lastDispatchAt + minIntervalMs);
}

async function dispatchRepositoryEvent(env) {
  const url = `https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`;
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "aplus-tutor-sms-relay",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ event_type: env.EVENT_TYPE || "tutor-sms" }),
  });
  if (resp.status !== 204) {
    const body = await resp.text();
    throw new Error(`repository_dispatch failed: ${resp.status} ${body.slice(0, 300)}`);
  }
}

export class Dispatcher {
  constructor(state, env) {
    this.state = state;
    this.env = env;
  }

  // Guarantee a dispatch at or after wantedAt, and never sooner than
  // MIN_INTERVAL_SECONDS after the last one. Keeps at most one alarm: pull it
  // earlier if this request wants an earlier time, and remember the latest
  // wanted time so the alarm handler can re-arm for stragglers.
  async fetch(request) {
    if (new URL(request.url).pathname === "/status") {
      return new Response(JSON.stringify(await this.status()), {
        headers: { "Content-Type": "application/json" },
      });
    }
    const body = await request.json();
    const minIntervalMs = clampInterval(this.env.MIN_INTERVAL_SECONDS, DEFAULT_MIN_INTERVAL_SECONDS) * 1000;
    const lastDispatchAt = (await this.state.storage.get("lastDispatchAt")) || 0;
    const wantedAt = floorWantedAt(body.wantedAt, lastDispatchAt, minIntervalMs);
    const floored = wantedAt > body.wantedAt;

    const latest = Math.max((await this.state.storage.get("latestWantedAt")) || 0, wantedAt);
    await this.state.storage.put("latestWantedAt", latest);
    const alarm = await this.state.storage.getAlarm();
    // A past alarm that never fired (2026-09-09, deal relay: retries exhausted
    // while GITHUB_TOKEN was unset, then nothing re-armed) must not block new
    // work. Same Dispatcher, same latent bug here.
    const stale = alarm !== null && alarm < Date.now() - 120_000;
    if (alarm === null || alarm > wantedAt || stale) {
      await this.state.storage.setAlarm(wantedAt);
    }
    await this.state.storage.put("lastScheduledAt", Date.now());
    return new Response(
      JSON.stringify({
        scheduled: true,
        at: new Date(wantedAt).toISOString(),
        floored,
        replacedStale: stale,
      }),
      { headers: { "Content-Type": "application/json" } },
    );
  }

  async status() {
    return {
      alarm: await this.state.storage.getAlarm(),
      latestWantedAt: (await this.state.storage.get("latestWantedAt")) || null,
      lastScheduledAt: (await this.state.storage.get("lastScheduledAt")) || null,
      lastDispatchAt: (await this.state.storage.get("lastDispatchAt")) || null,
      lastDispatchError: (await this.state.storage.get("lastDispatchError")) || null,
      minIntervalSeconds: clampInterval(this.env.MIN_INTERVAL_SECONDS, DEFAULT_MIN_INTERVAL_SECONDS),
      now: Date.now(),
    };
  }

  async alarm() {
    // A throw here makes the platform retry the alarm with backoff, exactly
    // what we want for a transient GitHub API failure.
    try {
      await dispatchRepositoryEvent(this.env);
    } catch (e) {
      await this.state.storage.put("lastDispatchError", `${new Date().toISOString()} ${String(e).slice(0, 300)}`);
      console.error("dispatch failed", String(e));
      throw e;
    }
    const dispatchedAt = Date.now();
    await this.state.storage.put("lastDispatchAt", dispatchedAt);
    await this.state.storage.delete("lastDispatchError");
    console.log(`dispatched ${this.env.EVENT_TYPE || "tutor-sms"}`);
    const latest = (await this.state.storage.get("latestWantedAt")) || 0;
    if (latest > dispatchedAt + 30_000) {
      // Stragglers arrived after this alarm was set. They wait out the floor
      // too, so a long burst cannot turn into a run per text.
      const minIntervalMs = clampInterval(this.env.MIN_INTERVAL_SECONDS, DEFAULT_MIN_INTERVAL_SECONDS) * 1000;
      await this.state.storage.setAlarm(floorWantedAt(latest, dispatchedAt, minIntervalMs));
    } else {
      await this.state.storage.delete("latestWantedAt");
    }
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      const missing = ["GITHUB_TOKEN", "WEBHOOK_TOKEN"].filter((k) => !env[k]);
      if (missing.length) {
        return new Response(`missing secrets: ${missing.join(", ")}`, { status: 503 });
      }
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

    if (url.pathname !== "/sms") {
      return new Response("not found", { status: 404 });
    }

    let body = {};
    try {
      body = await request.json();
    } catch {
      // An unparseable body is still a delivery. JustCall sent something; the
      // engine reads the texts itself, so fire and log the nothing we saw.
      body = {};
    }

    const verdict = isInbound(body);
    const shape = shapeLog(body);
    // Shape learning, key names only. See README before removing.
    console.log(
      JSON.stringify({
        at: "sms.received",
        keys: shape.keys,
        data_keys: shape.data_keys,
        direction_field: verdict.field,
        direction_value: verdict.value,
        inbound: verdict.inbound,
        reason: verdict.reason,
      }),
    );

    if (!verdict.inbound) {
      return new Response(JSON.stringify({ skipped: "outbound" }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    const delay = clampDelay(
      url.searchParams.get("delay"),
      clampDelay(env.DEFAULT_DELAY_MINUTES, 1),
    );
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
