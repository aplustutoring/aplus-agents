// node test-worker.mjs
import assert from "node:assert/strict";
import worker, { normalizePhone, smsBody, STORYBOOK_PROMPT, driveFileName } from "./worker.js";
import { generateKeyPairSync } from "node:crypto";

// Drive file names: LA time, guest name, kind suffix, no path characters
assert.equal(driveFileName("k", { at: "2026-09-12T02:05:12.000Z", name: "Ari Cohen", kind: "photo" }), "2026-09-11 19.05.12 Ari Cohen.jpg");
assert.equal(driveFileName("k", { at: "2026-09-12T02:05:12.000Z", name: "Bubbe/Zayde: <3", kind: "storybook" }), "2026-09-11 19.05.12 Bubbe Zayde 3 (storybook).jpg");
assert.match(driveFileName("k", {}), / Guest\.jpg$/);

assert.equal(normalizePhone("(818) 555-0123"), "+18185550123");
assert.equal(normalizePhone("1 818 555 0123"), "+18185550123");
assert.equal(normalizePhone("+1 818-555-0123"), "+18185550123");
assert.equal(normalizePhone("555-0123"), null);
assert.equal(normalizePhone(""), null);

const env = { SMS_BODY: "Hi {name}! Photo.", ALLOWED_ORIGIN: "https://x.pages.dev", JUSTCALL_FROM: "+18185736293", JUSTCALL_API_KEY: "k", JUSTCALL_API_SECRET: "s" };
assert.equal(smsBody(env, "Ari Cohen"), "Hi Ari! Photo.");
assert.equal(smsBody(env, ""), "Hi there! Photo.");
assert.equal(smsBody({ ...env, STORYBOOK_SMS_BODY: "Story for {name}." }, "Ari", "storybook"), "Story for Ari.");
assert.ok(!/—|--/.test(STORYBOOK_PROMPT));

// End-to-end submit with a fake KV and a fake JustCall
const store = new Map();
const kv = {
  put: async (k, v, o) => store.set(k, { v, o }),
  get: async (k) => store.get(k)?.v ?? null,
  list: async () => ({ keys: [...store.keys()].map((name) => ({ name, metadata: store.get(name).o.metadata })) }),
};
const calls = [];
const fakeStory = Buffer.from([0xff, 0xd8, 0xff, 0xd9]).toString("base64");
globalThis.fetch = async (url, init) => {
  const u = String(url);
  if (u.startsWith("https://oauth2.googleapis.com/token")) {
    calls.push({ url, body: init.body });
    return { ok: true, json: async () => ({ access_token: "tok-1" }) };
  }
  if (u.startsWith("https://www.googleapis.com/upload/drive/v3/files")) {
    calls.push({ url, headers: init.headers, bytes: init.body.byteLength });
    return { ok: true, json: async () => ({ id: "drive-" + calls.length }) };
  }
  calls.push({ url, body: JSON.parse(init.body) });
  if (String(url).includes("generativelanguage")) {
    if (globalThis.__geminiFail) return { ok: false, status: 429, text: async () => "quota" };
    return { ok: true, json: async () => ({ candidates: [{ content: { parts: [{ text: "here" }, { inlineData: { mimeType: "image/jpeg", data: fakeStory } }] } }] }) };
  }
  return { ok: true, text: async () => "" };
};
const tinyJpeg = "data:image/jpeg;base64," + Buffer.from([0xff, 0xd8, 0xff, 0xd9]).toString("base64");

let res = await worker.fetch(new Request("https://w.dev/submit", { method: "POST", body: JSON.stringify({ name: "Ari Cohen", phone: "818-555-0123", photo: tinyJpeg }) }), { ...env, PHOTOS: kv });
let out = await res.json();
assert.equal(res.status, 200);
assert.ok(out.archive.url.startsWith("https://w.dev/photo/"));
assert.deepEqual(out.text, { sent: true, to: "+18185550123" });
assert.equal(calls.length, 1);
assert.equal(calls[0].body.justcall_number, "+18185736293");
assert.equal(calls[0].body.contact_number, "+18185550123");
assert.equal(calls[0].body.media_url, out.archive.url);
assert.equal(calls[0].body.body, "Hi Ari! Photo.");
assert.ok(!/—|--/.test(calls[0].body.body), "no em dashes in outbound copy");

// No phone: archive only, no text
res = await worker.fetch(new Request("https://w.dev/submit", { method: "POST", body: JSON.stringify({ name: "", phone: "", photo: tinyJpeg }) }), { ...env, PHOTOS: kv });
out = await res.json();
assert.equal(out.text, undefined);
assert.equal(calls.length, 1);

// Photo host + list
const key = out.archive.url.split("/photo/")[1];
res = await worker.fetch(new Request(`https://w.dev/photo/${key}`), { ...env, PHOTOS: kv });
assert.equal(res.status, 200);
assert.equal(res.headers.get("Content-Type"), "image/jpeg");
res = await worker.fetch(new Request("https://w.dev/photos"), { ...env, PHOTOS: kv });
out = await res.json();
assert.equal(out.photos.length, 2);
assert.equal(out.photos[0].name, "Ari Cohen");

// Storybook: reference image goes to Gemini, base64 comes back
res = await worker.fetch(new Request("https://w.dev/storybook", { method: "POST", body: JSON.stringify({ raw: tinyJpeg, name: "Ari" }) }), { ...env, PHOTOS: kv, GEMINI_API_KEY: "g" });
out = await res.json();
assert.equal(res.status, 200);
assert.equal(out.image, fakeStory);
const g = calls.find((c) => String(c.url).includes("generativelanguage"));
assert.ok(String(g.url).includes("gemini-3.1-flash-image"));
assert.equal(g.body.contents[0].parts[0].inlineData.mimeType, "image/jpeg");
assert.equal(g.body.contents[0].parts[1].text, STORYBOOK_PROMPT);
assert.equal(g.body.generationConfig.imageConfig.aspectRatio, "4:5");
// Storybook failure is a 502 the booth can skip past, never a crash
globalThis.__geminiFail = true;
res = await worker.fetch(new Request("https://w.dev/storybook", { method: "POST", body: JSON.stringify({ raw: tinyJpeg }) }), { ...env, PHOTOS: kv, GEMINI_API_KEY: "g" });
assert.equal(res.status, 502);
assert.match((await res.json()).error, /Gemini 429/);
globalThis.__geminiFail = false;
res = await worker.fetch(new Request("https://w.dev/storybook", { method: "POST", body: JSON.stringify({ raw: "nope" }) }), { ...env, PHOTOS: kv, GEMINI_API_KEY: "g" });
assert.equal(res.status, 400);
// Storybook submit texts with the storybook body and is tagged in the album
const before = calls.length;
res = await worker.fetch(new Request("https://w.dev/submit", { method: "POST", body: JSON.stringify({ name: "Ari", phone: "818-555-0123", photo: tinyJpeg, kind: "storybook" }) }), { ...env, STORYBOOK_SMS_BODY: "Story for {name}.", PHOTOS: kv });
out = await res.json();
assert.equal(calls[calls.length - 1].body.body, "Story for Ari.");
assert.equal(calls.length, before + 1);
res = await worker.fetch(new Request("https://w.dev/photos"), { ...env, PHOTOS: kv });
out = await res.json();
assert.deepEqual(out.photos.map((p) => p.kind), ["photo", "photo", "storybook"]);

// Drive mirror: a submit uploads in the background (ctx.waitUntil), marker key written,
// token fetched once and cached, backfill skips what is mirrored and uploads the rest.
const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
const saJson = JSON.stringify({ client_email: "sa@test.iam", private_key: privateKey.export({ type: "pkcs8", format: "pem" }) });
const denv = { ...env, PHOTOS: kv, DRIVE_FOLDER_ID: "folder-1", GOOGLE_SA_JSON: saJson };
const pending = [];
const ctx = { waitUntil: (p) => pending.push(p) };
const beforeDrive = calls.length;
res = await worker.fetch(new Request("https://w.dev/submit", { method: "POST", body: JSON.stringify({ name: "Noa", phone: "", photo: tinyJpeg, kind: "photo" }) }), denv, ctx);
out = await res.json();
assert.equal(res.status, 200);
assert.equal(pending.length, 1, "drive upload runs via waitUntil");
await Promise.all(pending);
const tokenCalls = calls.filter((c) => String(c.url).startsWith("https://oauth2.googleapis.com/token"));
const uploads = calls.filter((c) => String(c.url).startsWith("https://www.googleapis.com/upload/drive"));
assert.equal(tokenCalls.length, 1);
assert.match(tokenCalls[0].body, /grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion=[\w-]+\.[\w-]+\.[\w-]+$/);
assert.equal(uploads.length, 1);
assert.equal(uploads[0].headers.Authorization, "Bearer tok-1");
assert.match(uploads[0].headers["Content-Type"], /^multipart\/related; boundary=booth/);
assert.ok(uploads[0].bytes > 4);
const newKey = out.archive.url.split("/photo/")[1];
assert.equal(await kv.get(`drive/${newKey}`), "drive-" + (beforeDrive + 2));
assert.equal(await kv.get("drive/_token"), "tok-1");
// /photos hides the marker keys
res = await worker.fetch(new Request("https://w.dev/photos"), denv);
out = await res.json();
assert.ok(out.photos.every((p) => !p.key.startsWith("drive/")));
assert.equal(out.photos.length, 4);
// Backfill: 3 older prints have no marker, the new one does
res = await worker.fetch(new Request("https://w.dev/drive-backfill", { method: "POST" }), denv);
out = await res.json();
assert.equal(out.skipped, 1);
assert.equal(out.uploaded.length, 3);
assert.equal(out.failed.length, 0);
assert.equal(calls.filter((c) => String(c.url).startsWith("https://oauth2.googleapis.com/token")).length, 1, "token reused from KV");
res = await worker.fetch(new Request("https://w.dev/drive-backfill", { method: "POST" }), denv);
out = await res.json();
assert.deepEqual([out.skipped, out.uploaded.length], [4, 0]);
// No Drive config: submit still works and never calls Google
const beforeNo = calls.length;
res = await worker.fetch(new Request("https://w.dev/submit", { method: "POST", body: JSON.stringify({ name: "x", phone: "", photo: tinyJpeg }) }), { ...env, PHOTOS: kv }, ctx);
assert.equal(res.status, 200);
assert.ok(!calls.slice(beforeNo).some((c) => String(c.url).includes("googleapis.com/upload")));

// Bad input
res = await worker.fetch(new Request("https://w.dev/submit", { method: "POST", body: JSON.stringify({ name: "x" }) }), { ...env, PHOTOS: kv });
assert.equal(res.status, 400);

console.log("ok: 60 assertions");
