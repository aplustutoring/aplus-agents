/**
 * APLUS+ Conference 2026 booth — Cloudflare Worker
 *
 * The booth page (public/index.html, served by this Worker) takes a group
 * selfie, then collects one row per person who wants a copy. Each row is a
 * HubSpot contact AND a print job. A Mac at the table runs
 * print-agent/print_agent.py, which pulls the queue and feeds the Selphy.
 *
 * POST /group   { photo (dataURL jpeg, framed 1200x1800), school: {label, domain} }
 *   -> archives the print in KV (permanent), mirrors to Google Drive in the
 *      background, returns { groupId, key, url }.
 * POST /copy    { groupId, key, firstName, email, phone?, role?, school: {label} }
 *   -> HubSpot upsert (event tag merged, role persona on create, photo URL,
 *      timeline note with the school), JustCall MMS if a phone was given,
 *      then a print job is queued. Returns { queueId, position, hubspot, text }.
 * GET  /queue?status=queued|printing|done|failed|all   (booth display + agent)
 * POST /queue/<id>/claim | /done | /failed    (agent; header X-Agent-Token)
 * POST /queue   { key, name, school }          re-print / manual enqueue
 * GET  /photo/<key>, GET /photos, POST /drive-backfill  (as booth/delilah)
 *
 * No email send, no scheduled handler, no storybook print (text-only storybook
 * is a later switch). Deterministic: no CARE pointer needed.
 */

const cors = (env) => ({
  "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-Agent-Token",
});

export default {
  async fetch(request, env, ctx) {
    if (request.method === "OPTIONS") return new Response(null, { headers: cors(env) });
    const url = new URL(request.url);
    const path = url.pathname;

    if (request.method === "GET" && path.startsWith("/photo/")) {
      const img = await env.PHOTOS.get(path.slice("/photo/".length), "arrayBuffer");
      if (!img) return new Response("Gone", { status: 404 });
      return new Response(img, { headers: { "Content-Type": "image/jpeg", "Cache-Control": "public, max-age=604800" } });
    }

    if (request.method === "GET" && path === "/photos") {
      const list = await env.PHOTOS.list({ limit: 1000 });
      const photos = list.keys
        .filter((k) => !k.name.startsWith("drive/") && !k.name.startsWith("q/"))
        .map((k) => ({ key: k.name, at: k.metadata?.at || "", school: k.metadata?.school || "", copies: k.metadata?.copies || 0, url: `${url.origin}/photo/${k.name}` }))
        .sort((a, b) => (a.at < b.at ? -1 : 1));
      return json({ photos }, 200, env);
    }

    if (request.method === "GET" && path === "/queue") {
      const want = url.searchParams.get("status") || "all";
      const items = await listQueue(env);
      return json({ queue: want === "all" ? items : items.filter((q) => q.status === want), now: new Date().toISOString() }, 200, env);
    }

    if (request.method === "POST" && path.startsWith("/queue/")) {
      if (!agentOk(request, env)) return json({ error: "agent token" }, 401, env);
      const [, , id, action] = path.split("/");
      const item = await env.PHOTOS.get(`q/${id}`, "json");
      if (!item) return json({ error: "no such job" }, 404, env);
      let body = {};
      try { body = await request.json(); } catch {}
      const next = { claim: "printing", done: "done", failed: "failed", requeue: "queued" }[action];
      if (!next) return json({ error: "action" }, 400, env);
      item.status = next;
      item[`${next}At`] = new Date().toISOString();
      if (action === "failed") item.error = String(body.error || "").slice(0, 200);
      if (action === "claim") item.agent = String(body.agent || "").slice(0, 60);
      await env.PHOTOS.put(`q/${id}`, JSON.stringify(item));
      return json({ ok: true, job: { id, ...item } }, 200, env);
    }

    if (request.method === "POST" && path === "/queue") {
      let body;
      try { body = await request.json(); } catch { return json({ error: "Invalid JSON" }, 400, env); }
      if (!body.key) return json({ error: "key required" }, 400, env);
      const job = await enqueue(env, { key: body.key, name: body.name || "Reprint", school: body.school || "", reprint: true });
      return json({ ok: true, ...job }, 200, env);
    }

    if (request.method === "POST" && path === "/drive-backfill") {
      const list = await env.PHOTOS.list({ limit: 1000 });
      const report = { uploaded: [], skipped: 0, failed: [] };
      for (const k of list.keys) {
        if (k.name.startsWith("drive/") || k.name.startsWith("q/")) continue;
        if (await env.PHOTOS.get(`drive/${k.name}`)) { report.skipped++; continue; }
        try { report.uploaded.push({ key: k.name, id: await mirrorToDrive(env, k.name, k.metadata || {}) }); }
        catch (e) { report.failed.push({ key: k.name, error: String(e) }); }
      }
      return json(report, 200, env);
    }

    if (request.method === "POST" && path === "/group") {
      let body;
      try { body = await request.json(); } catch { return json({ error: "Invalid JSON" }, 400, env); }
      const { photo, school = {} } = body;
      if (!photo || !/^data:image\/jpeg;base64,/.test(photo)) return json({ error: "photo (jpeg dataURL) required" }, 400, env);
      const bytes = Uint8Array.from(atob(photo.replace(/^data:image\/jpeg;base64,/, "")), (c) => c.charCodeAt(0));
      const groupId = crypto.randomUUID();
      const key = `${new Date().toISOString().slice(0, 10)}-${groupId}.jpg`;
      const meta = { at: new Date().toISOString(), school: String(school.label || "").slice(0, 80), copies: 0, kind: "group" };
      await env.PHOTOS.put(key, bytes, { metadata: meta });
      if (env.DRIVE_FOLDER_ID && env.GOOGLE_SA_JSON) {
        const job = mirrorToDrive(env, key, meta, bytes).catch((e) => console.error("drive mirror", key, String(e)));
        if (ctx?.waitUntil) ctx.waitUntil(job); else await job;
      }
      return json({ ok: true, groupId, key, url: `${url.origin}/photo/${key}` }, 200, env);
    }

    if (request.method === "POST" && path === "/copy") {
      let body;
      try { body = await request.json(); } catch { return json({ error: "Invalid JSON" }, 400, env); }
      const { groupId = "", key, firstName = "", email = "", phone = "", role = "", school = {} } = body;
      if (!key) return json({ error: "key required" }, 400, env);
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return json({ error: "Valid email required" }, 400, env);
      const photoUrl = `${url.origin}/photo/${key}`;
      const results = {};

      // 1. HubSpot: contact + event tag + photo URL + school note.
      try {
        results.hubspot = await upsertContact(env, {
          email: email.trim().toLowerCase(),
          firstname: String(firstName).trim().slice(0, 60),
          ...(normalizePhone(phone) ? { phone: normalizePhone(phone) } : {}),
          aplus_event_tag: env.EVENT_TAG || "aplus_conference_2026",
          aplus_event_role: ["administrator", "teacher", "support_staff"].includes(role) ? role : "",
          aplus_booth_photo_url: photoUrl,
        }, role);
        if (results.hubspot?.id) {
          try { await logPhotoNote(env, results.hubspot.id, photoUrl, school.label || "", groupId); }
          catch (e) { results.hubspot.noted = String(e); }
        }
      } catch (e) {
        results.hubspot = { error: String(e) };
      }

      // 2. Text (only if a phone was entered)
      const to = normalizePhone(phone);
      if (to) {
        try { results.text = await sendPhotoText(env, { to, name: firstName, mediaUrl: photoUrl }); }
        catch (e) { results.text = { error: String(e) }; }
      } else if (phone) {
        results.text = { error: "Phone number not recognised" };
      }

      // 3. Print job. The copy IS the print: every row prints exactly once.
      const job = await enqueue(env, { key, name: String(firstName).trim() || email.split("@")[0], school: school.label || "", groupId, email: email.trim().toLowerCase() });
      // bump copies on the photo metadata (best effort)
      try {
        const { value, metadata } = await env.PHOTOS.getWithMetadata(key, "arrayBuffer");
        if (value) await env.PHOTOS.put(key, value, { metadata: { ...(metadata || {}), copies: (metadata?.copies || 0) + 1 } });
      } catch {}

      return json({ ok: true, ...job, ...results }, 200, env);
    }

    // Everything else is the booth page itself (public/ assets binding).
    if (request.method === "GET" && env.ASSETS) return env.ASSETS.fetch(request);
    return json({ error: "Not found" }, 404, env);
  },
};

// ---------- queue ----------
function agentOk(request, env) {
  if (!env.AGENT_TOKEN) return true;
  return request.headers.get("X-Agent-Token") === env.AGENT_TOKEN;
}

async function enqueue(env, { key, name, school, groupId = "", email = "", reprint = false }) {
  const id = `${Date.now().toString().padStart(13, "0")}-${crypto.randomUUID().slice(0, 8)}`;
  const item = { key, name, school, groupId, email, reprint, status: "queued", queuedAt: new Date().toISOString() };
  await env.PHOTOS.put(`q/${id}`, JSON.stringify(item));
  const queued = (await listQueue(env)).filter((q) => q.status === "queued" || q.status === "printing");
  const position = Math.max(1, queued.findIndex((q) => q.id === id) + 1);
  return { queueId: id, position, ahead: position - 1 };
}

export async function listQueue(env) {
  const list = await env.PHOTOS.list({ prefix: "q/", limit: 1000 });
  const items = [];
  for (const k of list.keys) {
    const v = await env.PHOTOS.get(k.name, "json");
    if (v) items.push({ id: k.name.slice(2), ...v });
  }
  return items.sort((a, b) => (a.id < b.id ? -1 : 1));   // id starts with a ms timestamp
}

// ---------- HubSpot ----------
// Create-only persona stamp by self-identified role (existing contacts are
// never overwritten; a_persona is multi-select). Ported from booth/worker.js.
const ROLE_CREATE_PROPS = {
  teacher: { a_persona: "Teacher of Record/EF/ES", hs_lead_status: "Charter School Teacher TOR/EF" },
  administrator: { a_persona: "Decision Maker/Director" },
  support_staff: {},
};

// aplus_event_tag is a MULTI-SELECT and append-only per #AP032.
export function mergeEventTags(existing, newTag) {
  const have = String(existing || "").split(";").map((s) => s.trim()).filter(Boolean);
  if (newTag && !have.includes(newTag)) have.push(newTag);
  return have.join(";");
}

async function upsertContact(env, properties, role) {
  if (!env.HUBSPOT_TOKEN) throw new Error("HUBSPOT_TOKEN not set");
  const headers = { Authorization: `Bearer ${env.HUBSPOT_TOKEN}`, "Content-Type": "application/json" };
  const search = await fetch("https://api.hubapi.com/crm/v3/objects/contacts/search", {
    method: "POST", headers,
    body: JSON.stringify({ filterGroups: [{ filters: [{ propertyName: "email", operator: "EQ", value: properties.email }] }], properties: ["email", "aplus_event_tag"], limit: 1 }),
  });
  if (!search.ok) throw new Error(`HubSpot search ${search.status}: ${await search.text()}`);
  const found = await search.json();
  if (found.total > 0) {
    const hit = found.results[0];
    const upd = await fetch(`https://api.hubapi.com/crm/v3/objects/contacts/${hit.id}`, {
      method: "PATCH", headers,
      body: JSON.stringify({ properties: { ...properties, aplus_event_tag: mergeEventTags(hit.properties?.aplus_event_tag, properties.aplus_event_tag) } }),
    });
    if (!upd.ok) throw new Error(`HubSpot update ${upd.status}: ${await upd.text()}`);
    return { action: "updated", id: hit.id };
  }
  const crt = await fetch("https://api.hubapi.com/crm/v3/objects/contacts", {
    method: "POST", headers,
    body: JSON.stringify({ properties: { ...properties, ...(ROLE_CREATE_PROPS[role] || ROLE_CREATE_PROPS.administrator) } }),
  });
  if (!crt.ok) throw new Error(`HubSpot create ${crt.status}: ${await crt.text()}`);
  return { action: "created", id: (await crt.json()).id };
}

// Photo breadcrumb on the contact timeline (note -> contact assoc 202). The
// school label is here so a human sees it even when no domain stamp applies.
async function logPhotoNote(env, contactId, photoUrl, schoolLabel, groupId) {
  const res = await fetch("https://api.hubapi.com/crm/v3/objects/notes", {
    method: "POST",
    headers: { Authorization: `Bearer ${env.HUBSPOT_TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      properties: {
        hs_timestamp: new Date().toISOString(),
        hs_note_body: `📸 Team photo from the A+ booth, ${env.EVENT_NAME || "APLUS+ Conference 2026"}: ${photoUrl}\nSchool (as entered at the booth): ${schoolLabel || "not given"}\nGroup: ${groupId || "n/a"}`,
      },
      associations: [{ to: { id: contactId }, types: [{ associationCategory: "HUBSPOT_DEFINED", associationTypeId: 202 }] }],
    }),
  });
  if (!res.ok) throw new Error(`HubSpot photo note ${res.status}: ${await res.text()}`);
}

// ---------- phone + text ----------
export function normalizePhone(raw) {
  const d = String(raw || "").replace(/\D/g, "");
  if (d.length === 10) return `+1${d}`;
  if (d.length === 11 && d.startsWith("1")) return `+${d}`;
  return null;
}

export function smsBody(env, name) {
  const first = String(name || "").trim().split(/\s+/)[0] || "there";
  return (env.SMS_BODY || "Hi {name}! Here is your team photo from the A+ Tutoring booth.").replace("{name}", first);
}

async function sendPhotoText(env, { to, name, mediaUrl }) {
  const res = await fetch("https://api.justcall.io/v2.1/texts/new", {
    method: "POST",
    headers: { Authorization: `${env.JUSTCALL_API_KEY}:${env.JUSTCALL_API_SECRET}`, "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ justcall_number: env.JUSTCALL_FROM, contact_number: to, body: smsBody(env, name), media_url: mediaUrl }),
  });
  if (!res.ok) throw new Error(`JustCall ${res.status}: ${await res.text()}`);
  return { sent: true, to };
}

// ---------- Google Drive mirror (as booth/delilah; must be a Shared Drive) ----------
export function driveFileName(key, meta) {
  const at = meta.at ? new Date(meta.at) : new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const la = new Date(at.toLocaleString("en-US", { timeZone: "America/Los_Angeles" }));
  const stamp = `${la.getFullYear()}-${pad(la.getMonth() + 1)}-${pad(la.getDate())} ${pad(la.getHours())}.${pad(la.getMinutes())}.${pad(la.getSeconds())}`;
  const school = String(meta.school || "").replace(/[\\/:*?"<>|]+/g, " ").replace(/\s+/g, " ").trim();
  return `${stamp}${school ? " " + school : ""} team.jpg`;
}

async function mirrorToDrive(env, key, meta, bytes) {
  if (!bytes) { bytes = await env.PHOTOS.get(key, "arrayBuffer"); if (!bytes) throw new Error("archive object missing"); }
  const token = await driveToken(env);
  const boundary = "booth" + crypto.randomUUID();
  const metaPart = JSON.stringify({ name: driveFileName(key, meta), parents: [env.DRIVE_FOLDER_ID] });
  const enc = new TextEncoder();
  const head = enc.encode(`--${boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n${metaPart}\r\n--${boundary}\r\nContent-Type: image/jpeg\r\n\r\n`);
  const tail = enc.encode(`\r\n--${boundary}--`);
  const body = new Uint8Array(head.length + bytes.byteLength + tail.length);
  body.set(head, 0); body.set(new Uint8Array(bytes), head.length); body.set(tail, head.length + bytes.byteLength);
  const res = await fetch("https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true&fields=id", {
    method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": `multipart/related; boundary=${boundary}` }, body,
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
  const res = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: `grant_type=${encodeURIComponent("urn:ietf:params:oauth:grant-type:jwt-bearer")}&assertion=${header}.${claim}.${b64url(sig)}`,
  });
  if (!res.ok) throw new Error(`Google token ${res.status}: ${(await res.text()).slice(0, 300)}`);
  const { access_token } = await res.json();
  await env.PHOTOS.put("drive/_token", access_token, { expirationTtl: 3000 });
  return access_token;
}

function json(obj, status, env) {
  return new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json", ...cors(env) } });
}
