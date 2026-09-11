/**
 * Delilah's 5th Birthday / Rosh Hashanah 5787 photo booth — Cloudflare Worker
 *
 * POST /submit    { name, phone, photo (dataURL jpeg), kind: "photo" | "storybook" }
 *   1. Archives the framed print in KV (permanent), served at GET /photo/<key>
 *   2. If phone given: texts it via JustCall MMS from JUSTCALL_FROM
 * POST /storybook { raw (dataURL jpeg of the un-framed capture), name }
 *   Asks Gemini to repaint the guests into a Rosh Hashanah storybook orchard,
 *   faces preserved. Returns { image: <base64 jpeg> } for the booth to frame + print.
 * GET  /photo/<key>   public photo host (unguessable UUID keys)
 * GET  /photos        JSON list of archived keys (for reprints / the album)
 * POST /drive-backfill  uploads every archived print not yet in the Drive folder
 *
 * Every archived print is also mirrored to a Google Drive folder (DRIVE_FOLDER_ID)
 * with the service account in the GOOGLE_SA_JSON secret, in the background
 * (ctx.waitUntil) so the guest never waits on Drive. Marker keys drive/<key> in
 * KV hold the Drive file id so nothing uploads twice.
 *
 * No HubSpot, no email, no scheduled handler. Personal event, not a lead source.
 */

const cors = (env) => ({
  "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
});

export default {
  async fetch(request, env, ctx) {
    if (request.method === "OPTIONS") return new Response(null, { headers: cors(env) });
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname.startsWith("/photo/")) {
      const key = url.pathname.slice("/photo/".length);
      const img = await env.PHOTOS.get(key, "arrayBuffer");
      if (!img) return new Response("Gone", { status: 404 });
      return new Response(img, {
        headers: { "Content-Type": "image/jpeg", "Cache-Control": "public, max-age=604800" },
      });
    }

    if (request.method === "POST" && url.pathname === "/drive-backfill") {
      const list = await env.PHOTOS.list({ limit: 1000 });
      const report = { uploaded: [], skipped: 0, failed: [] };
      for (const k of list.keys) {
        if (k.name.startsWith("drive/") || k.name.startsWith("err/")) continue;
        if (await env.PHOTOS.get(`drive/${k.name}`)) { report.skipped++; continue; }
        try {
          const id = await mirrorToDrive(env, k.name, k.metadata || {});
          report.uploaded.push({ key: k.name, id });
        } catch (e) {
          report.failed.push({ key: k.name, error: String(e) });
        }
      }
      return json(report, 200, env);
    }

    if (request.method === "GET" && url.pathname === "/photos") {
      const list = await env.PHOTOS.list({ limit: 1000 });
      const photos = list.keys
        .filter((k) => !k.name.startsWith("drive/") && !k.name.startsWith("err/"))
        .map((k) => ({ key: k.name, name: k.metadata?.name || "", at: k.metadata?.at || "", kind: k.metadata?.kind || "photo", url: `${url.origin}/photo/${k.name}` }))
        .sort((a, b) => (a.at < b.at ? -1 : 1));
      return json({ photos }, 200, env);
    }

    if (request.method === "POST" && url.pathname === "/storybook") {
      let body;
      try { body = await request.json(); } catch { return json({ error: "Invalid JSON" }, 400, env); }
      const raw = body.raw || "";
      const m = /^data:(image\/(?:jpeg|png));base64,(.+)$/s.exec(raw);
      if (!m) return json({ error: "raw (jpeg/png dataURL) required" }, 400, env);
      // Two attempts inside the Worker: Gemini 429/5xx and empty responses are
      // transient (2026-09-11: a shot failed once and replayed fine 30 min later).
      let lastErr = null;
      for (let attempt = 1; attempt <= 2; attempt++) {
        try {
          const image = await paintStorybook(env, { mimeType: m[1], base64: m[2] });
          return json({ ok: true, image, attempt }, 200, env);
        } catch (e) {
          lastErr = String(e);
          if (attempt === 1) await new Promise((r) => setTimeout(r, 1500));
        }
      }
      // Never silent: the failure is written where the host view can see it.
      try {
        await env.PHOTOS.put(`err/${new Date().toISOString()}-${crypto.randomUUID().slice(0, 8)}`, JSON.stringify({ at: new Date().toISOString(), name: String(body.name || "").slice(0, 60), error: lastErr }), { expirationTtl: 60 * 60 * 24 * 30 });
      } catch {}
      console.error("storybook failed", body.name, lastErr);
      return json({ ok: false, error: lastErr }, 502, env);
    }

    if (request.method === "GET" && url.pathname === "/errors") {
      const list = await env.PHOTOS.list({ prefix: "err/", limit: 200 });
      const errors = [];
      for (const k of list.keys) { const v = await env.PHOTOS.get(k.name, "json"); if (v) errors.push(v); }
      return json({ errors }, 200, env);
    }

    if (request.method !== "POST" || url.pathname !== "/submit") {
      // Everything else is the booth page itself (public/ assets binding).
      if (request.method === "GET" && env.ASSETS) return env.ASSETS.fetch(request);
      return json({ error: "Not found" }, 404, env);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: "Invalid JSON" }, 400, env);
    }
    const { name = "", phone = "", photo } = body;
    const kind = body.kind === "storybook" ? "storybook" : "photo";
    if (!photo || !/^data:image\/jpeg;base64,/.test(photo)) {
      return json({ error: "photo (jpeg dataURL) required" }, 400, env);
    }

    const results = {};

    // 1. Archive (permanent, no TTL): every shot is recoverable for reprints.
    let archiveUrl = null;
    try {
      const bytes = Uint8Array.from(atob(photo.replace(/^data:image\/jpeg;base64,/, "")), (c) => c.charCodeAt(0));
      const key = `${new Date().toISOString().slice(0, 10)}-${crypto.randomUUID()}.jpg`;
      const meta = { name: String(name).slice(0, 60), at: new Date().toISOString(), kind };
      await env.PHOTOS.put(key, bytes, { metadata: meta });
      archiveUrl = `${url.origin}/photo/${key}`;
      results.archive = { url: archiveUrl };
      // Drive mirror in the background: the print sheet is already open on the iPad.
      if (env.DRIVE_FOLDER_ID && env.GOOGLE_SA_JSON) {
        const job = mirrorToDrive(env, key, meta, bytes).catch((e) => console.error("drive mirror", key, String(e)));
        if (ctx?.waitUntil) ctx.waitUntil(job); else await job;
      }
    } catch (e) {
      results.archive = { error: String(e) };
    }

    // 2. Text (only if a phone was entered)
    const to = normalizePhone(phone);
    if (to && archiveUrl) {
      try {
        results.text = await sendPhotoText(env, { to, name, mediaUrl: archiveUrl, kind });
      } catch (e) {
        results.text = { error: String(e) };
      }
    } else if (phone && !to) {
      results.text = { error: "Phone number not recognised" };
    }

    return json({ ok: true, ...results }, 200, env);
  },
};

export function normalizePhone(raw) {
  const digits = String(raw || "").replace(/\D/g, "");
  if (digits.length === 10) return `+1${digits}`;
  if (digits.length === 11 && digits.startsWith("1")) return `+${digits}`;
  return null;
}

export function smsBody(env, name, kind = "photo") {
  const first = String(name || "").trim().split(/\s+/)[0] || "there";
  const tpl = kind === "storybook"
    ? (env.STORYBOOK_SMS_BODY || "And here is your storybook version, {name}!")
    : (env.SMS_BODY || "Hi {name}! Here is your photo.");
  return tpl.replace("{name}", first);
}

// Gemini image edit: the guest photo goes in as a reference part, the prompt
// asks for a repaint that keeps every person recognizable. ~10 s in testing.
export const STORYBOOK_PROMPT =
  "Repaint the people in this photo as a hand-painted children's storybook illustration. " +
  "Keep every person, their faces, hair, expressions, glasses and clothing colors recognizable, " +
  "in the same positions and group pose. Place them in a sunlit pomegranate orchard for Rosh Hashanah: " +
  "pomegranate trees heavy with fruit, baskets of red apples, a big jar of golden honey with a wooden dipper, " +
  "a round challah, a few bees, and a soft golden sky. Warm watercolor and gouache style, gentle outlines, " +
  "festive and cozy. No text, no letters, no watermark.";

async function paintStorybook(env, { mimeType, base64 }) {
  if (!env.GEMINI_API_KEY) throw new Error("GEMINI_API_KEY not set");
  const model = env.GEMINI_MODEL || "gemini-3.1-flash-image";
  const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${env.GEMINI_API_KEY}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contents: [{ parts: [{ inlineData: { mimeType, data: base64 } }, { text: STORYBOOK_PROMPT }] }],
      generationConfig: { responseModalities: ["TEXT", "IMAGE"], imageConfig: { aspectRatio: "4:5" } },
    }),
  });
  if (!res.ok) throw new Error(`Gemini ${res.status}: ${(await res.text()).slice(0, 300)}`);
  const out = await res.json();
  const parts = out?.candidates?.[0]?.content?.parts || [];
  const img = parts.find((p) => p.inlineData?.data);
  if (!img) throw new Error(`Gemini returned no image (${out?.candidates?.[0]?.finishReason || "unknown"})`);
  return img.inlineData.data;
}

async function sendPhotoText(env, { to, name, mediaUrl, kind = "photo" }) {
  const res = await fetch("https://api.justcall.io/v2.1/texts/new", {
    method: "POST",
    headers: {
      Authorization: `${env.JUSTCALL_API_KEY}:${env.JUSTCALL_API_SECRET}`,
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({
      justcall_number: env.JUSTCALL_FROM,
      contact_number: to,
      body: smsBody(env, name, kind),
      media_url: mediaUrl,
    }),
  });
  if (!res.ok) throw new Error(`JustCall ${res.status}: ${await res.text()}`);
  return { sent: true, to };
}

// ---------- Google Drive mirror ----------
// Service-account JWT (RS256 via WebCrypto) -> access token (cached in KV ~50 min)
// -> multipart upload into DRIVE_FOLDER_ID. File names read like
// "2026-09-11 19.05.12 Ari Cohen (storybook).jpg" in Los Angeles time.
export function driveFileName(key, meta) {
  const at = meta.at ? new Date(meta.at) : new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const la = new Date(at.toLocaleString("en-US", { timeZone: "America/Los_Angeles" }));
  const stamp = `${la.getFullYear()}-${pad(la.getMonth() + 1)}-${pad(la.getDate())} ${pad(la.getHours())}.${pad(la.getMinutes())}.${pad(la.getSeconds())}`;
  const who = String(meta.name || "Guest").replace(/[\\/:*?"<>|]+/g, " ").replace(/\s+/g, " ").trim() || "Guest";
  const kind = meta.kind === "storybook" ? " (storybook)" : "";
  return `${stamp} ${who}${kind}.jpg`;
}

async function mirrorToDrive(env, key, meta, bytes) {
  if (!bytes) {
    bytes = await env.PHOTOS.get(key, "arrayBuffer");
    if (!bytes) throw new Error("archive object missing");
  }
  const token = await driveToken(env);
  const boundary = "booth" + crypto.randomUUID();
  const metaPart = JSON.stringify({ name: driveFileName(key, meta), parents: [env.DRIVE_FOLDER_ID] });
  const enc = new TextEncoder();
  const head = enc.encode(`--${boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n${metaPart}\r\n--${boundary}\r\nContent-Type: image/jpeg\r\n\r\n`);
  const tail = enc.encode(`\r\n--${boundary}--`);
  const body = new Uint8Array(head.length + bytes.byteLength + tail.length);
  body.set(head, 0);
  body.set(new Uint8Array(bytes), head.length);
  body.set(tail, head.length + bytes.byteLength);
  const res = await fetch("https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true&fields=id", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": `multipart/related; boundary=${boundary}` },
    body,
  });
  if (!res.ok) throw new Error(`Drive upload ${res.status}: ${(await res.text()).slice(0, 300)}`);
  const { id } = await res.json();
  await env.PHOTOS.put(`drive/${key}`, id, { metadata: { fileId: id } });
  return id;
}

async function driveToken(env) {
  const cached = await env.PHOTOS.get("drive/_token");
  if (cached) return cached;
  const sa = JSON.parse(env.GOOGLE_SA_JSON);
  const now = Math.floor(Date.now() / 1000);
  const b64url = (s) => btoa(typeof s === "string" ? s : String.fromCharCode(...new Uint8Array(s))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const header = b64url(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const claim = b64url(JSON.stringify({ iss: sa.client_email, scope: "https://www.googleapis.com/auth/drive", aud: "https://oauth2.googleapis.com/token", iat: now, exp: now + 3600 }));
  const pem = sa.private_key.replace(/-----[A-Z ]+-----/g, "").replace(/\s+/g, "");
  const der = Uint8Array.from(atob(pem), (c) => c.charCodeAt(0));
  const cryptoKey = await crypto.subtle.importKey("pkcs8", der, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", cryptoKey, new TextEncoder().encode(`${header}.${claim}`));
  const jwt = `${header}.${claim}.${b64url(sig)}`;
  const res = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: `grant_type=${encodeURIComponent("urn:ietf:params:oauth:grant-type:jwt-bearer")}&assertion=${jwt}`,
  });
  if (!res.ok) throw new Error(`Google token ${res.status}: ${(await res.text()).slice(0, 300)}`);
  const { access_token } = await res.json();
  await env.PHOTOS.put("drive/_token", access_token, { expirationTtl: 3000 });
  return access_token;
}

function json(obj, status, env) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...cors(env) },
  });
}
