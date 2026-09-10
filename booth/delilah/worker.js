/**
 * Delilah's 5th Birthday / Rosh Hashanah 5787 photo booth — Cloudflare Worker
 *
 * POST /submit   { name, phone, photo (dataURL jpeg) }
 *   1. Archives the framed photo in KV (permanent), served at GET /photo/<key>
 *   2. If phone given: texts the photo via JustCall MMS from JUSTCALL_FROM
 * GET  /photo/<key>   public photo host (unguessable UUID keys)
 * GET  /photos        JSON list of archived keys (for reprints / the album)
 *
 * No HubSpot, no email, no scheduled handler. Personal event, not a lead source.
 */

const cors = (env) => ({
  "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
});

export default {
  async fetch(request, env) {
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

    if (request.method === "GET" && url.pathname === "/photos") {
      const list = await env.PHOTOS.list({ limit: 1000 });
      const photos = list.keys
        .map((k) => ({ key: k.name, name: k.metadata?.name || "", at: k.metadata?.at || "", url: `${url.origin}/photo/${k.name}` }))
        .sort((a, b) => (a.at < b.at ? -1 : 1));
      return json({ photos }, 200, env);
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
    if (!photo || !/^data:image\/jpeg;base64,/.test(photo)) {
      return json({ error: "photo (jpeg dataURL) required" }, 400, env);
    }

    const results = {};

    // 1. Archive (permanent, no TTL): every shot is recoverable for reprints.
    let archiveUrl = null;
    try {
      const bytes = Uint8Array.from(atob(photo.replace(/^data:image\/jpeg;base64,/, "")), (c) => c.charCodeAt(0));
      const key = `${new Date().toISOString().slice(0, 10)}-${crypto.randomUUID()}.jpg`;
      await env.PHOTOS.put(key, bytes, { metadata: { name: String(name).slice(0, 60), at: new Date().toISOString() } });
      archiveUrl = `${url.origin}/photo/${key}`;
      results.archive = { url: archiveUrl };
    } catch (e) {
      results.archive = { error: String(e) };
    }

    // 2. Text (only if a phone was entered)
    const to = normalizePhone(phone);
    if (to && archiveUrl) {
      try {
        results.text = await sendPhotoText(env, { to, name, mediaUrl: archiveUrl });
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

export function smsBody(env, name) {
  const first = String(name || "").trim().split(/\s+/)[0] || "there";
  return (env.SMS_BODY || "Hi {name}! Here is your photo.").replace("{name}", first);
}

async function sendPhotoText(env, { to, name, mediaUrl }) {
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
      body: smsBody(env, name),
      media_url: mediaUrl,
    }),
  });
  if (!res.ok) throw new Error(`JustCall ${res.status}: ${await res.text()}`);
  return { sent: true, to };
}

function json(obj, status, env) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...cors(env) },
  });
}
