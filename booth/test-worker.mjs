/**
 * A+ photo booth Worker tests.   node booth/test-worker.mjs
 *
 * Covers what has actually broken before, plus the multi-event contract:
 *   1. aplus_event_tag overwritten instead of appended (#AP032)
 *   2. enum LABELS written instead of VALUES
 *   3. an event page naming a tag the Worker or the schema does not know
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import worker, { EVENTS, VALID_ROLES, mergeEventTags, corsOrigin, ownerForRole,
                 withoutUnsyncedProps, normalizePhone } from "./worker.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");
let pass = 0;
const t = (name, fn) => {
  try { fn(); pass++; console.log(`  ok  ${name}`); }
  catch (e) { console.error(`  FAIL ${name}\n       ${e.message}`); process.exitCode = 1; }
};
const ta = async (name, fn) => {
  try { await fn(); pass++; console.log(`  ok  ${name}`); }
  catch (e) { console.error(`  FAIL ${name}\n       ${e.message}`); process.exitCode = 1; }
};

console.log("\nmergeEventTags (#AP032)");
t("adds onto an existing tag", () =>
  assert.equal(mergeEventTags("blue_ridge_btsc_2026", "sage_oak_btsc_2026"),
               "blue_ridge_btsc_2026;sage_oak_btsc_2026"));
t("is idempotent", () =>
  assert.equal(mergeEventTags("sage_oak_btsc_2026", "sage_oak_btsc_2026"),
               "sage_oak_btsc_2026"));
t("handles empty / null", () => {
  assert.equal(mergeEventTags("", "sage_oak_btsc_2026"), "sage_oak_btsc_2026");
  assert.equal(mergeEventTags(null, "sage_oak_btsc_2026"), "sage_oak_btsc_2026");
});

// ── harness: fake HubSpot / Resend / JustCall / KV ──────────────────────────
const ENV = {
  HUBSPOT_TOKEN: "t", RESEND_API_KEY: "r", RESEND_FROM: "A+ <photos@wetutorathome.com>",
  JUSTCALL_API_KEY: "k", JUSTCALL_API_SECRET: "s", JUSTCALL_FROM: "+18188506284",
  ALLOWED_ORIGIN: "https://sage-oak-booth.nameless-mountain-bafa.workers.dev,https://sage-oak-booth.pages.dev",
  OWNER_SALES: "227538487", OWNER_CHARTER_SALES: "81494333",
  PHOTOS: { store: new Map(),
            async put(k, v, o) { this.store.set(k, { v, o }); },
            async get(k) { return this.store.get(k)?.v ?? null; } },
};
const PHOTO = "data:image/jpeg;base64," + Buffer.from("jpegbytes").toString("base64");

async function submit(payload, { existingTag = null, found = false, fail = null, origin = null, env = ENV } = {}) {
  const sent = [];
  globalThis.fetch = async (url, opts) => {
    const u = String(url);
    const body = opts?.body ? JSON.parse(opts.body) : {};
    sent.push({ url: u, method: opts?.method, body });
    if (u.includes("/contacts/search")) {
      return new Response(JSON.stringify(found
        ? { total: 1, results: [{ id: "5", properties: { email: payload.email, aplus_event_tag: existingTag } }] }
        : { total: 0, results: [] }), { status: 200 });
    }
    if (fail && fail.match(u, opts) && !fail.spent) {
      fail.spent = true;
      return new Response(fail.body, { status: fail.status });
    }
    return new Response(JSON.stringify({ id: "5" }), { status: 200 });
  };
  const headers = { "Content-Type": "application/json" };
  if (origin) headers.Origin = origin;
  const res = await worker.fetch(new Request("https://sage-oak-booth.nameless-mountain-bafa.workers.dev/submit", {
    method: "POST", headers, body: JSON.stringify(payload),
  }), env);
  const out = await res.json();
  const contactWrite = sent.find((s) => /\/contacts\/5$/.test(s.url) && s.method === "PATCH")
    || sent.find((s) => /\/contacts$/.test(s.url) && s.method === "POST");
  return { res, out, sent, props: contactWrite?.body?.properties || {} };
}

const SAGE = { firstName: "Ann", lastName: "Lee", email: "ann@example.com",
               role: "teacher", marketingConsent: true, goal: "Best. Year. Ever.",
               eventTag: "sage_oak_btsc_2026" };
const CEJA = { firstName: "Dana", lastName: "Reyes", email: "Dana@Outlook.com", phone: "(555) 213-8890",
               role: "parent", marketingConsent: true, goal: "Family first",
               delivery: "print", eventTag: "ceja_park_2026", photo: PHOTO };

console.log("\n#AP032: the event tag is appended, never replaced");
await ta("a Blue Ridge attendee returning to Sage Oak keeps BOTH tags", async () => {
  const { props } = await submit(SAGE, { found: true, existingTag: "blue_ridge_btsc_2026" });
  assert.equal(props.aplus_event_tag, "blue_ridge_btsc_2026;sage_oak_btsc_2026");
});
await ta("a Sage Oak teacher who comes to Ceja carries both", async () => {
  const { props } = await submit({ ...CEJA, role: "teacher" }, { found: true, existingTag: "sage_oak_btsc_2026" });
  assert.equal(props.aplus_event_tag, "sage_oak_btsc_2026;ceja_park_2026");
});
await ta("the search asks for the tag, or the merge has nothing to merge", async () => {
  const { sent } = await submit(SAGE, { found: true, existingTag: "blue_ridge_btsc_2026" });
  const search = sent.find((s) => s.url.includes("/search"));
  assert.ok(search.body.properties.includes("aplus_event_tag"));
});
await ta("a brand-new contact gets the event's tag", async () => {
  const { props } = await submit(CEJA);
  assert.equal(props.aplus_event_tag, "ceja_park_2026");
});
await ta("re-submitting does not duplicate the tag", async () => {
  const { props } = await submit(SAGE, { found: true, existingTag: "sage_oak_btsc_2026" });
  assert.equal(props.aplus_event_tag, "sage_oak_btsc_2026");
});

console.log("\nmulti-event contract");
const YAML = readFileSync(join(ROOT, "ops/hubspot-schema/properties.yml"), "utf8");
const tagOptions = (() => {
  const block = YAML.split("- name: aplus_event_tag\n")[1].split(/\n {4}- name: /)[0];
  return [...block.matchAll(/- value: "?([\w.]+)"?/g)].map((m) => m[1]);
})();
t("every event the Worker knows is a declared aplus_event_tag option", () => {
  for (const tag of Object.keys(EVENTS)) assert.ok(tagOptions.includes(tag), `${tag} missing from properties.yml`);
});
const CEJA_HTML = readFileSync(join(HERE, "public/ceja/index.html"), "utf8");
t("the Ceja page sends a tag the Worker knows", () => {
  const tag = CEJA_HTML.match(/EVENT_TAG:\s*"([^"]+)"/)[1];
  assert.ok(EVENTS[tag], `${tag} is not a row in EVENTS`);
  assert.equal(tag, "ceja_park_2026");
});
t("the Ceja page posts same-origin and its roles are Worker values", () => {
  assert.ok(CEJA_HTML.includes('WORKER_URL: "/submit"'));
  for (const m of CEJA_HTML.matchAll(/data-role="([^"]+)"/g)) {
    assert.ok(VALID_ROLES.includes(m[1]), `role ${m[1]} is not a Worker value`);
  }
  assert.ok(CEJA_HTML.includes('data-role="parent"'), "parents first at a park");
});
await ta("an unknown tag falls back to Sage Oak rather than writing garbage", async () => {
  const { props, out } = await submit({ ...SAGE, eventTag: "made_up_2027" });
  assert.equal(props.aplus_event_tag, "sage_oak_btsc_2026");
  assert.equal(out.results.eventTag, "sage_oak_btsc_2026");
});
await ta("email copy follows the event", async () => {
  const { sent } = await submit({ ...CEJA, sendEmail: true });
  const resend = sent.find((s) => s.url.includes("api.resend.com"));
  assert.equal(resend.body.subject, EVENTS.ceja_park_2026.emailSubject);
  assert.equal(resend.body.attachments[0].filename, "ceja-park-day-2026.jpg");
  assert.ok(!resend.body.html.includes("Sage Oak"), "Sage Oak copy leaked into the Ceja email");
});
await ta("MMS copy follows the event and uses the request origin for the photo", async () => {
  const { sent } = await submit({ ...CEJA, sendText: true });
  const jc = sent.find((s) => s.url.includes("justcall"));
  assert.ok(jc.body.body.startsWith("Hi Dana!"));
  assert.ok(!jc.body.body.includes("Sage Oak"));
  assert.ok(jc.body.media_url.startsWith("https://sage-oak-booth.nameless-mountain-bafa.workers.dev/photo/"));
});
await ta("the timeline note names the event", async () => {
  const { sent } = await submit(CEJA);
  const note = sent.find((s) => s.url.includes("/objects/notes"));
  assert.ok(note.body.properties.hs_note_body.includes("Ceja Park Day 2026"));
});

console.log("\nenum values, never labels");
await ta("role and delivery reach HubSpot as internal values", async () => {
  const { props } = await submit(CEJA);
  assert.equal(props.aplus_event_role, "parent");
  assert.equal(props.aplus_booth_delivery, "print");
  assert.equal(props.aplus_marketing_consent, "true");
});
await ta("a label sent as a role is replaced by the event default, not written raw", async () => {
  const { props } = await submit({ ...CEJA, role: "Parent" });
  assert.equal(props.aplus_event_role, "parent");
});
await ta("email is lowercased so the search-by-email matches next time", async () => {
  const { props } = await submit(CEJA);
  assert.equal(props.email, "dana@outlook.com");
});

console.log("\npersona and owner are CREATE-ONLY");
await ta("a new parent gets the Family persona and the charter sales seat", async () => {
  const { props } = await submit(CEJA);
  assert.equal(props.a_persona, "Family");
  assert.equal(props.hubspot_owner_id, "81494333");
});
await ta("a new teacher gets the TOR persona and the sales seat", async () => {
  const { props } = await submit({ ...CEJA, role: "teacher" });
  assert.equal(props.a_persona, "Teacher of Record/EF/ES");
  assert.equal(props.hubspot_owner_id, "227538487");
});
await ta("an existing contact is never re-personaed or reassigned", async () => {
  const { props } = await submit(CEJA, { found: true, existingTag: "" });
  assert.ok(!("a_persona" in props));
  assert.ok(!("hubspot_owner_id" in props));
});
await ta("an update never blanks a field with an empty string", async () => {
  const { props } = await submit({ ...CEJA, phone: "", goal: "" }, { found: true });
  assert.ok(!("phone" in props));
  assert.ok(!("aplus_booth_goal" in props));
});
t("a missing seat var yields no owner, never a literal seat name", () => {
  assert.equal(ownerForRole({}, "parent"), "");
});

console.log("\nresilience");
t("an unsynced enum option is dropped, not fatal", () => {
  const r = withoutUnsyncedProps({ email: "a@b.com", aplus_event_tag: "ceja_park_2026" }, 400,
    '{"message":"Property values were not valid: ... aplus_event_tag ... is not one of the allowed options"}');
  assert.deepEqual(r.dropped, ["aplus_event_tag"]);
  assert.ok(!("aplus_event_tag" in r.props));
});
t("a non-schema 400 is NOT swallowed", () => {
  assert.equal(withoutUnsyncedProps({ email: "a@b.com" }, 400, '{"message":"rate limited"}'), null);
});
await ta("HubSpot rejecting the tag still captures the contact", async () => {
  const { out } = await submit(CEJA, {
    fail: { match: (u, o) => /\/contacts$/.test(u) && o.method === "POST", status: 400,
            body: '{"message":"aplus_event_tag is not one of the allowed options"}' } });
  assert.equal(out.ok, true);
  assert.deepEqual(out.results.hubspot.dropped, ["aplus_event_tag"]);
});
await ta("text delivery without a usable phone is a 400 before anything is sent", async () => {
  const { res, sent } = await submit({ ...CEJA, phone: "555", sendText: true });
  assert.equal(res.status, 400);
  assert.equal(sent.length, 0);
});
t("normalizePhone accepts the formats a parent types", () => {
  assert.equal(normalizePhone("(555) 213-8890"), "+15552138890");
  assert.equal(normalizePhone("1 555 213 8890"), "+15552138890");
  assert.equal(normalizePhone("213-8890"), null);
});

console.log("\nCORS: a list of origins, echoed back exactly");
t("the Pages origin and the Worker origin are both allowed", () => {
  assert.equal(corsOrigin(ENV, "https://sage-oak-booth.pages.dev"), "https://sage-oak-booth.pages.dev");
  assert.equal(corsOrigin(ENV, "https://sage-oak-booth.nameless-mountain-bafa.workers.dev"),
               "https://sage-oak-booth.nameless-mountain-bafa.workers.dev");
});
t("an unknown origin gets the first allowed one, never itself", () => {
  assert.equal(corsOrigin(ENV, "https://evil.example"), "https://sage-oak-booth.nameless-mountain-bafa.workers.dev");
});
t("wrangler.toml lists both origins", () => {
  const toml = readFileSync(join(HERE, "wrangler.toml"), "utf8");
  const line = toml.match(/^ALLOWED_ORIGIN = "([^"]+)"/m)[1];
  assert.ok(line.includes("sage-oak-booth.pages.dev"));
  assert.ok(line.includes("sage-oak-booth.nameless-mountain-bafa.workers.dev"));
  assert.ok(/\[assets\]\s*\ndirectory = "\.\/public"/.test(toml), "assets block serves public/");
});
await ta("GET / redirects to the Ceja page", async () => {
  const res = await worker.fetch(new Request("https://sage-oak-booth.nameless-mountain-bafa.workers.dev/"), ENV);
  assert.equal(res.status, 302);
  assert.equal(res.headers.get("Location"), "https://sage-oak-booth.nameless-mountain-bafa.workers.dev/ceja/");
});

console.log("\nCeja page copy");
t("one-tap chips for the three consumer domains", () => {
  for (const d of ["@gmail.com", "@outlook.com", "@yahoo.com"]) assert.ok(CEJA_HTML.includes(`data-domain="${d}"`));
});
t("no-spam line and a phone field", () => {
  assert.ok(/We will not spam you/.test(CEJA_HTML));
  assert.ok(CEJA_HTML.includes('id="f-phone"'));
});
t("no em dashes or double hyphens in the family-facing copy", () => {
  // Roman 2026-08-24, locked: never in customer-facing communication.
  const visible = CEJA_HTML.split("<body>")[1]
    .replace(/<script[\s\S]*?<\/script>/g, "").replace(/<!--[\s\S]*?-->/g, "");
  assert.ok(!/—|--/.test(visible));
  const strings = [...CEJA_HTML.matchAll(/`[^`]*`/g)].map((m) => m[0]).join("");
  assert.ok(!/—/.test(strings), "em dash inside a JS message string");
  for (const e of Object.values(EVENTS)) {
    for (const v of [e.emailSubject, e.emailIntro, e.emailPitch, e.smsBody]) assert.ok(!/—|--/.test(v), v);
  }
});

console.log(`\n${pass} passed\n`);
