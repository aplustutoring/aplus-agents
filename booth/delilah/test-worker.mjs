// node test-worker.mjs
import assert from "node:assert/strict";
import worker, { normalizePhone, smsBody } from "./worker.js";

assert.equal(normalizePhone("(818) 555-0123"), "+18185550123");
assert.equal(normalizePhone("1 818 555 0123"), "+18185550123");
assert.equal(normalizePhone("+1 818-555-0123"), "+18185550123");
assert.equal(normalizePhone("555-0123"), null);
assert.equal(normalizePhone(""), null);

const env = { SMS_BODY: "Hi {name}! Photo.", ALLOWED_ORIGIN: "https://x.pages.dev", JUSTCALL_FROM: "+18185736293", JUSTCALL_API_KEY: "k", JUSTCALL_API_SECRET: "s" };
assert.equal(smsBody(env, "Ari Cohen"), "Hi Ari! Photo.");
assert.equal(smsBody(env, ""), "Hi there! Photo.");

// End-to-end submit with a fake KV and a fake JustCall
const store = new Map();
const kv = {
  put: async (k, v, o) => store.set(k, { v, o }),
  get: async (k) => store.get(k)?.v ?? null,
  list: async () => ({ keys: [...store.keys()].map((name) => ({ name, metadata: store.get(name).o.metadata })) }),
};
const calls = [];
globalThis.fetch = async (url, init) => { calls.push({ url, body: JSON.parse(init.body) }); return { ok: true, text: async () => "" }; };
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

// Bad input
res = await worker.fetch(new Request("https://w.dev/submit", { method: "POST", body: JSON.stringify({ name: "x" }) }), { ...env, PHOTOS: kv });
assert.equal(res.status, 400);

console.log("ok: 22 assertions");
