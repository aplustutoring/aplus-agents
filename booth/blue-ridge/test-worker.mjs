/**
 * Blue Ridge booth Worker tests.   node booth/blue-ridge/test-worker.mjs
 *
 * Covers the two things that actually broke before:
 *   1. enum LABELS written instead of VALUES (the Sage Oak bug)
 *   2. aplus_event_tag overwritten instead of appended (#AP032)
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import worker, { mergeEventTags, withoutUnsyncedProps, ownerForRole } from "./worker.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
let pass = 0;
const t = (name, fn) => {
  try {
    fn();
    pass++;
    console.log(`  ok  ${name}`);
  } catch (e) {
    console.error(`  FAIL ${name}\n       ${e.message}`);
    process.exitCode = 1;
  }
};
const ta = async (name, fn) => {
  try {
    await fn();
    pass++;
    console.log(`  ok  ${name}`);
  } catch (e) {
    console.error(`  FAIL ${name}\n       ${e.message}`);
    process.exitCode = 1;
  }
};

// ── the values the Worker is allowed to write, straight out of the manifest ──
const YAML = readFileSync(join(ROOT, "ops/hubspot-schema/properties.yml"), "utf8");
function declaredOptions(prop) {
  const block = YAML.split(`- name: ${prop}\n`)[1];
  assert.ok(block, `${prop} is not declared in properties.yml`);
  const upTo = block.split(/\n {4}- name: /)[0];
  return [...upTo.matchAll(/- value: "?([\w.]+)"?/g)].map((m) => m[1]);
}

console.log("\nmanifest agreement");
t("aplus_event_tag declares the Blue Ridge option", () => {
  assert.ok(declaredOptions("aplus_event_tag").includes("blue_ridge_btsc_2026"));
});
t("aplus_event_tag keeps Sage Oak (additive only)", () => {
  assert.ok(declaredOptions("aplus_event_tag").includes("sage_oak_btsc_2026"));
});
t("aplus_event_role gains parent + student, keeps the original three", () => {
  const o = declaredOptions("aplus_event_role");
  for (const v of ["administrator", "teacher", "support_staff", "parent", "student"]) {
    assert.ok(o.includes(v), `missing ${v}`);
  }
});
t("aplus_booth_prize is declared", () => {
  assert.ok(YAML.includes("- name: aplus_booth_prize"));
});
t("aplus_booth_goal is NOT reused for the prize", () => {
  const w = readFileSync(join(HERE, "worker.js"), "utf8");
  assert.ok(!w.includes("aplus_booth_goal"), "photo-banner property must not be overloaded");
  assert.ok(!w.includes("aplus_booth_delivery"));
  assert.ok(!w.includes("aplus_booth_photo_url"));
});

// ── the enum-write bug ──────────────────────────────────────────────────────
console.log("\nenum writes use VALUES, never labels");
const LABELS = ["Teacher", "Blue Ridge BTSC 2026", "Yes", "No", "Parent / Guardian",
                "Support Staff", "Administrator"];

async function submit(payload, { existingTag = null, found = false } = {}) {
  const sent = [];
  globalThis.fetch = async (url, opts) => {
    const body = opts?.body ? JSON.parse(opts.body) : {};
    sent.push({ url, method: opts?.method, body });
    if (String(url).includes("/search")) {
      return new Response(JSON.stringify(found
        ? { total: 1, results: [{ id: "77", properties: { email: payload.email, aplus_event_tag: existingTag } }] }
        : { total: 0, results: [] }), { status: 200 });
    }
    return new Response(JSON.stringify({ id: "77" }), { status: 200 });
  };
  const res = await worker.fetch(new Request("https://w/submit", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }), { HUBSPOT_TOKEN: "t", ALLOWED_ORIGIN: "*",
        OWNER_SALES: "227538487", OWNER_CHARTER_SALES: "81494333" });
  const write = sent.find((s) => s.method === "PATCH" || (s.method === "POST" && !String(s.url).includes("/search")));
  return { res, sent, props: write?.body?.properties || {} };
}

const BASE = {
  firstName: "Nikki", lastName: "Cate", email: "nikki@theblueridgeacademy.com",
  role: "teacher", marketingConsent: true, prize: "Pop-it",
};

await ta("writes teacher/true/blue_ridge_btsc_2026 as values", async () => {
  const { props } = await submit(BASE);
  assert.equal(props.aplus_event_role, "teacher");
  assert.equal(props.aplus_marketing_consent, "true");
  assert.equal(props.aplus_event_tag, "blue_ridge_btsc_2026");
});

await ta("no HubSpot write ever contains a human-facing label", async () => {
  for (const role of ["teacher", "parent", "student", "administrator", "support_staff"]) {
    const { props } = await submit({ ...BASE, role });
    const blob = JSON.stringify(props);
    for (const label of LABELS) {
      assert.ok(!blob.includes(`"${label}"`), `label "${label}" written for role=${role}`);
    }
  }
});

await ta("consent false is the string \"false\", not a boolean", async () => {
  const { props } = await submit({ ...BASE, marketingConsent: false });
  assert.equal(props.aplus_marketing_consent, "false");
  assert.notEqual(props.aplus_marketing_consent, false);
});

await ta("an unknown role is dropped, never written raw", async () => {
  const { props } = await submit({ ...BASE, role: "Teacher / School Staff" });
  assert.ok(!("aplus_event_role" in props), "UI text must not reach HubSpot");
});

await ta("prize is stored verbatim on aplus_booth_prize", async () => {
  const { props } = await submit({ ...BASE, prize: "Squishy Pen" });
  assert.equal(props.aplus_booth_prize, "Squishy Pen");
});

await ta("an off-list prize is dropped", async () => {
  const { props } = await submit({ ...BASE, prize: "iPad" });
  assert.ok(!("aplus_booth_prize" in props));
});

// ── #AP032: append-only event tag ───────────────────────────────────────────
console.log("\nevent tag is append-only (#AP032)");
t("merges onto an existing Sage Oak tag", () => {
  assert.equal(mergeEventTags("sage_oak_btsc_2026", "blue_ridge_btsc_2026"),
               "sage_oak_btsc_2026;blue_ridge_btsc_2026");
});
t("is idempotent — a second spin does not double-tag", () => {
  assert.equal(mergeEventTags("blue_ridge_btsc_2026", "blue_ridge_btsc_2026"),
               "blue_ridge_btsc_2026");
});
t("handles an empty / missing existing value", () => {
  assert.equal(mergeEventTags("", "blue_ridge_btsc_2026"), "blue_ridge_btsc_2026");
  assert.equal(mergeEventTags(null, "blue_ridge_btsc_2026"), "blue_ridge_btsc_2026");
});
t("preserves any other event already on the record", () => {
  assert.equal(mergeEventTags("eo_lav_agents_2026;sage_oak_btsc_2026", "blue_ridge_btsc_2026"),
               "eo_lav_agents_2026;sage_oak_btsc_2026;blue_ridge_btsc_2026");
});

await ta("a returning Sage Oak attendee keeps BOTH tags", async () => {
  const { props } = await submit(BASE, { found: true, existingTag: "sage_oak_btsc_2026" });
  assert.equal(props.aplus_event_tag, "sage_oak_btsc_2026;blue_ridge_btsc_2026");
});

await ta("an update never blanks a field with an empty string", async () => {
  const { props } = await submit({ ...BASE, phone: "", prize: "" },
                                 { found: true, existingTag: "sage_oak_btsc_2026" });
  assert.ok(!("phone" in props));
  assert.ok(!("aplus_booth_prize" in props));
});

// ── lead routing: teachers -> sales, families -> charter sales ─────────────
console.log("\nowner routing (Roman 2026-09-01)");
const ENV = { OWNER_SALES: "227538487", OWNER_CHARTER_SALES: "81494333" };
t("teacher and school staff route to the sales seat", () => {
  for (const r of ["teacher", "administrator", "support_staff"]) {
    assert.equal(ownerForRole(ENV, r), "227538487", r);
  }
});
t("families route to the charter sales seat", () => {
  for (const r of ["parent", "student"]) {
    assert.equal(ownerForRole(ENV, r), "81494333", r);
  }
});
t("an unknown role gets no owner rather than a wrong one", () => {
  assert.equal(ownerForRole(ENV, "visitor"), "");
  assert.equal(ownerForRole(ENV, undefined), "");
});
t("a missing var yields no owner, never the literal seat name", () => {
  assert.equal(ownerForRole({}, "teacher"), "");
});

await ta("a NEW teacher is assigned to sales", async () => {
  const { props } = await submit({ ...BASE, role: "teacher" });
  assert.equal(props.hubspot_owner_id, "227538487");
});
await ta("a NEW parent is assigned to charter sales", async () => {
  const { props } = await submit({ ...BASE, role: "parent" });
  assert.equal(props.hubspot_owner_id, "81494333");
});
await ta("an EXISTING contact is never reassigned", async () => {
  const { props } = await submit({ ...BASE, role: "parent" }, { found: true });
  assert.ok(!("hubspot_owner_id" in props),
            "owner must be create-only: a live relationship is not reassigned from a booth");
});

// ── create-only persona stamp ───────────────────────────────────────────────
console.log("\npersona stamp is create-only");
await ta("a new parent gets the Family persona", async () => {
  const { props } = await submit({ ...BASE, role: "parent" });
  assert.equal(props.a_persona, "Family");
});
await ta("a new teacher gets the TOR persona and lead status", async () => {
  const { props } = await submit({ ...BASE, role: "teacher" });
  assert.equal(props.a_persona, "Teacher of Record/EF/ES");
});
await ta("an EXISTING contact's persona is never touched", async () => {
  const { props } = await submit({ ...BASE, role: "parent" }, { found: true });
  assert.ok(!("a_persona" in props), "a_persona must not be written on update");
  assert.ok(!("hs_lead_status" in props));
});

// ── validation + resilience ─────────────────────────────────────────────────
console.log("\nvalidation and resilience");
await ta("rejects a bad email", async () => {
  const { res } = await submit({ ...BASE, email: "nope" });
  assert.equal(res.status, 400);
});
await ta("requires both names", async () => {
  const { res } = await submit({ ...BASE, lastName: "" });
  assert.equal(res.status, 400);
});
t("an unsynced property is dropped, not fatal", () => {
  const r = withoutUnsyncedProps(
    { email: "a@b.com", aplus_booth_prize: "Pop-it" }, 400,
    '{"message":"Property \\"aplus_booth_prize\\" does not exist"}');
  assert.deepEqual(r.dropped, ["aplus_booth_prize"]);
  assert.ok(!("aplus_booth_prize" in r.props));
  assert.equal(r.props.email, "a@b.com");
});
t("a non-schema 400 is NOT swallowed", () => {
  assert.equal(withoutUnsyncedProps({ email: "a@b.com" }, 400, "INVALID_EMAIL"), null);
  assert.equal(withoutUnsyncedProps({ email: "a@b.com" }, 500, "boom"), null);
});

console.log(`\n${pass} passed\n`);
