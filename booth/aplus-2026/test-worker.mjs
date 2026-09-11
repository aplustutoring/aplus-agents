// node test-worker.mjs
import assert from "node:assert/strict";
import { generateKeyPairSync } from "node:crypto";
import worker, { normalizePhone, smsBody, mergeEventTags, driveFileName, listQueue } from "./worker.js";

// ---- pure helpers
assert.equal(normalizePhone("(818) 555-0123"), "+18185550123");
assert.equal(normalizePhone("1 818 555 0123"), "+18185550123");
assert.equal(normalizePhone("555-0123"), null);
assert.equal(mergeEventTags("sage_oak_btsc_2026", "aplus_conference_2026"), "sage_oak_btsc_2026;aplus_conference_2026");
assert.equal(mergeEventTags("aplus_conference_2026", "aplus_conference_2026"), "aplus_conference_2026");
assert.equal(mergeEventTags("", "aplus_conference_2026"), "aplus_conference_2026");
assert.equal(smsBody({ SMS_BODY: "Hi {name}! Photo." }, "Ari Cohen"), "Hi Ari! Photo.");
assert.ok(!/—|--/.test(smsBody({}, "x")), "no em dashes in outbound copy");
assert.equal(driveFileName("k", { at: "2026-10-22T18:05:12.000Z", school: "Compass Charter Schools of Yolo" }), "2026-10-22 11.05.12 Compass Charter Schools of Yolo team.jpg");
assert.equal(driveFileName("k", { at: "2026-10-22T18:05:12.000Z" }), "2026-10-22 11.05.12 team.jpg");

// ---- fake KV + fake network
const store = new Map();
const kv = {
  put: async (k, v, o) => store.set(k, { v, o }),
  get: async (k, type) => { const e = store.get(k); if (!e) return null; if (type === "json") return JSON.parse(e.v); return e.v; },
  getWithMetadata: async (k) => { const e = store.get(k); return e ? { value: e.v, metadata: e.o?.metadata } : { value: null }; },
  list: async ({ prefix = "" } = {}) => ({ keys: [...store.keys()].filter((n) => n.startsWith(prefix)).map((name) => ({ name, metadata: store.get(name).o?.metadata })) }),
};
const calls = [];
let hubspotExisting = null;   // null = not found; else {id, aplus_event_tag}
globalThis.fetch = async (url, init = {}) => {
  const u = String(url);
  let body = init.body;
  if (typeof body === "string") { try { body = JSON.parse(body); } catch { /* form-encoded token request */ } }
  calls.push({ url: u, method: init.method || "GET", body, headers: init.headers });
  if (u.includes("hubapi.com/crm/v3/objects/contacts/search")) {
    return { ok: true, json: async () => (hubspotExisting ? { total: 1, results: [{ id: hubspotExisting.id, properties: { aplus_event_tag: hubspotExisting.aplus_event_tag } }] } : { total: 0, results: [] }) };
  }
  if (u.match(/hubapi.com\/crm\/v3\/objects\/contacts\/\d+$/)) return { ok: true, json: async () => ({}) };
  if (u.endsWith("hubapi.com/crm/v3/objects/contacts")) return { ok: true, json: async () => ({ id: "9001" }) };
  if (u.includes("hubapi.com/crm/v3/objects/notes")) return { ok: true, json: async () => ({ id: "n1" }) };
  if (u.includes("justcall.io")) return { ok: true, text: async () => "" };
  if (u.startsWith("https://oauth2.googleapis.com/token")) return { ok: true, json: async () => ({ access_token: "tok-1" }) };
  if (u.startsWith("https://www.googleapis.com/upload/drive")) return { ok: true, json: async () => ({ id: "drive-1" }) };
  throw new Error("unexpected fetch " + u);
};
const tinyJpeg = "data:image/jpeg;base64," + Buffer.from([0xff, 0xd8, 0xff, 0xd9]).toString("base64");
const env = { ALLOWED_ORIGIN: "https://x", EVENT_TAG: "aplus_conference_2026", EVENT_NAME: "APLUS+ Conference 2026", JUSTCALL_FROM: "+18185736258", JUSTCALL_API_KEY: "k", JUSTCALL_API_SECRET: "s", HUBSPOT_TOKEN: "h", SMS_BODY: "Hi {name}! Team photo.", PHOTOS: kv };
const req = (path, body, headers = {}) => new Request("https://w.dev" + path, body === undefined ? { headers } : { method: "POST", body: JSON.stringify(body), headers });
const pending = []; const ctx = { waitUntil: (p) => pending.push(p) };

// ---- /group archives the photo
let res = await worker.fetch(req("/group", { photo: tinyJpeg, school: { label: "Compass Charter Schools of Yolo", domain: "compasscharters.org" } }), env, ctx);
let out = await res.json();
assert.equal(res.status, 200);
assert.ok(out.groupId && out.key.endsWith(".jpg"));
assert.equal(out.url, `https://w.dev/photo/${out.key}`);
assert.equal(store.get(out.key).o.metadata.school, "Compass Charter Schools of Yolo");
assert.equal(pending.length, 0, "no Drive call without GOOGLE_SA_JSON");
const { groupId, key } = out;
res = await worker.fetch(req("/group", { photo: "nope" }), env, ctx); assert.equal(res.status, 400);

// ---- /copy: new contact -> created with admin persona, note logged, text sent, print queued
res = await worker.fetch(req("/copy", { groupId, key, firstName: "Maria", email: "Maria@CompassCharters.org", phone: "818-555-0123", role: "administrator", school: { label: "Compass Charter Schools of Yolo" } }), env, ctx);
out = await res.json();
assert.equal(res.status, 200);
assert.deepEqual(out.hubspot, { action: "created", id: "9001" });
assert.deepEqual(out.text, { sent: true, to: "+18185550123" });
assert.equal(out.position, 1);
const create = calls.find((c) => c.url.endsWith("/objects/contacts") && c.method === "POST");
assert.equal(create.body.properties.email, "maria@compasscharters.org");
assert.equal(create.body.properties.aplus_event_tag, "aplus_conference_2026");
assert.equal(create.body.properties.aplus_event_role, "administrator");
assert.equal(create.body.properties.a_persona, "Decision Maker/Director");
assert.equal(create.body.properties.aplus_booth_photo_url, `https://w.dev/photo/${key}`);
assert.equal(create.body.properties.phone, "+18185550123");
const note = calls.find((c) => c.url.includes("/objects/notes"));
assert.match(note.body.properties.hs_note_body, /Compass Charter Schools of Yolo/);
assert.equal(note.body.associations[0].to.id, "9001");
const sms = calls.find((c) => c.url.includes("justcall"));
assert.equal(sms.body.justcall_number, "+18185736258");
assert.equal(sms.body.media_url, `https://w.dev/photo/${key}`);
assert.equal(sms.body.body, "Hi Maria! Team photo.");
assert.equal(store.get(key).o.metadata.copies, 1);

// ---- /copy: existing contact keeps its old event tag (append, never replace), teacher role never restamps persona
hubspotExisting = { id: "42", aplus_event_tag: "sage_oak_btsc_2026" };
res = await worker.fetch(req("/copy", { groupId, key, firstName: "Devon", email: "devon@compasscharters.org", role: "teacher", school: { label: "Compass Charter Schools of Yolo" } }), env, ctx);
out = await res.json();
assert.deepEqual(out.hubspot, { action: "updated", id: "42" });
assert.equal(out.text, undefined, "no phone, no text");
assert.equal(out.position, 2, "second copy waits behind the first");
const patch = calls.find((c) => c.url.endsWith("/objects/contacts/42") && c.method === "PATCH");
assert.equal(patch.body.properties.aplus_event_tag, "sage_oak_btsc_2026;aplus_conference_2026");
assert.equal(patch.body.properties.a_persona, undefined);
assert.equal(store.get(key).o.metadata.copies, 2);
hubspotExisting = null;

// ---- /copy validation
res = await worker.fetch(req("/copy", { key, firstName: "x", email: "not-an-email" }), env, ctx); assert.equal(res.status, 400);
res = await worker.fetch(req("/copy", { firstName: "x", email: "a@b.co" }), env, ctx); assert.equal(res.status, 400);

// ---- queue: listing, claim/done by the agent, token enforcement, reprint
res = await worker.fetch(req("/queue?status=queued"), env); out = await res.json();
assert.equal(out.queue.length, 2);
assert.deepEqual(out.queue.map((q) => q.name), ["Maria", "Devon"]);
const first = out.queue[0].id;
const tenv = { ...env, AGENT_TOKEN: "secret" };
res = await worker.fetch(req(`/queue/${first}/claim`, { agent: "mac-1" }), tenv); assert.equal(res.status, 401, "agent token required when set");
res = await worker.fetch(req(`/queue/${first}/claim`, { agent: "mac-1" }, { "X-Agent-Token": "secret" }), tenv); out = await res.json();
assert.equal(out.job.status, "printing"); assert.equal(out.job.agent, "mac-1");
res = await worker.fetch(req(`/queue/${first}/done`, {}, { "X-Agent-Token": "secret" }), tenv); out = await res.json();
assert.equal(out.job.status, "done"); assert.ok(out.job.doneAt);
res = await worker.fetch(req("/queue/nope/done", {}, { "X-Agent-Token": "secret" }), tenv); assert.equal(res.status, 404);
res = await worker.fetch(req("/queue", { key, name: "Reprint Maria", school: "Compass" }), env); out = await res.json();
assert.equal(out.position, 2, "reprint queues behind Devon, the finished job does not count");
const all = await listQueue({ PHOTOS: kv });
assert.deepEqual(all.map((q) => q.status), ["done", "queued", "queued"]);
assert.equal(all[2].reprint, true);
res = await worker.fetch(req(`/queue/${all[1].id}/failed`, { error: "out of paper" }, { "X-Agent-Token": "secret" }), tenv); out = await res.json();
assert.equal(out.job.error, "out of paper");
res = await worker.fetch(req(`/queue/${all[1].id}/requeue`, {}, { "X-Agent-Token": "secret" }), tenv); out = await res.json();
assert.equal(out.job.status, "queued");

// ---- /photos hides queue + drive markers
res = await worker.fetch(req("/photos"), env); out = await res.json();
assert.equal(out.photos.length, 1); assert.equal(out.photos[0].copies, 2);

// ---- Drive mirror on /group when configured (real RSA key signed in-test)
const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
const denv = { ...env, DRIVE_FOLDER_ID: "folder-1", GOOGLE_SA_JSON: JSON.stringify({ client_email: "sa@test.iam", private_key: privateKey.export({ type: "pkcs8", format: "pem" }) }) };
res = await worker.fetch(req("/group", { photo: tinyJpeg, school: { label: "Sage Oak Charter School" } }), denv, ctx); out = await res.json();
assert.equal(pending.length, 1); await Promise.all(pending);
const up = calls.find((c) => c.url.startsWith("https://www.googleapis.com/upload/drive"));
assert.equal(up.headers.Authorization, "Bearer tok-1");
assert.equal(await kv.get(`drive/${out.key}`), "drive-1");
res = await worker.fetch(req("/drive-backfill", {}), denv); out = await res.json();
assert.equal(out.uploaded.length, 1, "the first group photo had no marker");
assert.equal(out.skipped, 1);

console.log("ok: 58 assertions");
