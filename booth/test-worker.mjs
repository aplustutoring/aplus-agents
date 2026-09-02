/**
 * Sage Oak booth Worker — #AP032 regression test.
 *   node booth/test-worker.mjs
 *
 * This booth shipped writing aplus_event_tag flat. Harmless while it was the
 * only event; a data-loss bug the moment Blue Ridge existed, because the field
 * is fieldType: checkbox and a flat PATCH replaces the whole set.
 */
import assert from "node:assert/strict";
import worker, { mergeEventTags } from "./worker.js";

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

console.log("\nmergeEventTags");
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

async function submit(payload, { existingTag = null, found = false } = {}) {
  const sent = [];
  globalThis.fetch = async (url, opts) => {
    const body = opts?.body ? JSON.parse(opts.body) : {};
    sent.push({ url: String(url), method: opts?.method, body });
    if (String(url).includes("/search")) {
      return new Response(JSON.stringify(found
        ? { total: 1, results: [{ id: "5", properties: { email: payload.email, aplus_event_tag: existingTag } }] }
        : { total: 0, results: [] }), { status: 200 });
    }
    return new Response(JSON.stringify({ id: "5" }), { status: 200 });
  };
  const res = await worker.fetch(new Request("https://w/submit", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }), { HUBSPOT_TOKEN: "t", ALLOWED_ORIGIN: "*" });
  const write = sent.find((s) => s.method === "PATCH"
    || (s.method === "POST" && !s.url.includes("/search")));
  return { res, sent, props: write?.body?.properties || {} };
}

const BASE = { firstName: "Ann", lastName: "Lee", email: "ann@example.com",
               role: "teacher", marketingConsent: true, goal: "Best. Year. Ever." };

console.log("\n#AP032 — the bug this test exists for");
await ta("a Blue Ridge attendee returning to Sage Oak keeps BOTH tags", async () => {
  const { props } = await submit(BASE, { found: true, existingTag: "blue_ridge_btsc_2026" });
  assert.equal(props.aplus_event_tag, "blue_ridge_btsc_2026;sage_oak_btsc_2026");
});
await ta("the search asks for the tag, or the merge has nothing to merge", async () => {
  const { sent } = await submit(BASE, { found: true, existingTag: "blue_ridge_btsc_2026" });
  const search = sent.find((s) => s.url.includes("/search"));
  assert.ok(search.body.properties.includes("aplus_event_tag"));
});
await ta("a brand-new contact still gets the Sage Oak tag", async () => {
  const { props } = await submit(BASE);
  assert.equal(props.aplus_event_tag, "sage_oak_btsc_2026");
});
await ta("re-submitting does not duplicate the tag", async () => {
  const { props } = await submit(BASE, { found: true, existingTag: "sage_oak_btsc_2026" });
  assert.equal(props.aplus_event_tag, "sage_oak_btsc_2026");
});

console.log(`\n${pass} passed\n`);
