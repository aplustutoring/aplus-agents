/**
 * Blue Ridge BTSC 2026 "Spin Back to School" — Cloudflare Worker
 *
 * POST /submit
 *   { firstName, lastName, email, phone, role, marketingConsent, prize, eventTag }
 *
 * Does ONE thing: upserts the HubSpot contact (portal 6312752) and tags them
 * with the event. No email, no MMS, no print — unlike the Sage Oak booth this
 * is modeled on (booth/worker.js).
 *
 * Secrets (wrangler secret put ...):
 *   HUBSPOT_TOKEN   — private app token with crm.objects.contacts read+write
 * Vars (wrangler.toml):
 *   ALLOWED_ORIGIN  — booth Pages URL, e.g. "https://blue-ridge-booth.pages.dev"
 *
 * Property manifest doctrine: aplus_booth_prize and the new aplus_event_tag /
 * aplus_event_role options must be merged in properties.yml and synced by
 * create_properties.py BEFORE go-live. Until then the prize write is dropped
 * and the capture still succeeds (see PROPERTY_DOESNT_EXIST retry below).
 */

const EVENT_TAG = "blue_ridge_btsc_2026";

// Enumeration INTERNAL VALUES. The fleet "always read labels" rule is about
// READING; writes take values. The Sage Oak build shipped with labels here and
// HubSpot silently rejected them, so this list is the contract and
// test-worker.mjs asserts every one of them.
const VALID_ROLES = ["administrator", "teacher", "support_staff", "parent", "student"];
const PRIZES = ["Tic-Tac-Toe", "Bookmark Scratcher", "Pop-it", "Squishy Pen"];

const cors = (env) => ({
  "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
});

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: cors(env) });
    }
    const url = new URL(request.url);
    if (request.method !== "POST" || url.pathname !== "/submit") {
      return json({ error: "Not found" }, 404, env);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: "Invalid JSON" }, 400, env);
    }

    const { firstName, lastName, email, phone, role, marketingConsent, prize, eventTag } = body;
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return json({ error: "Valid email required" }, 400, env);
    }
    if (!firstName || !lastName) {
      return json({ error: "First and last name required" }, 400, env);
    }

    const results = { hubspot: null };
    try {
      results.hubspot = await upsertContact(env, {
        email: String(email).trim().toLowerCase(),
        firstname: String(firstName).trim(),
        lastname: String(lastName).trim(),
        phone: phone ? String(phone).trim() : "",
        aplus_event_role: VALID_ROLES.includes(role) ? role : "",
        aplus_marketing_consent: marketingConsent ? "true" : "false",
        aplus_booth_prize: PRIZES.includes(prize) ? prize : "",
      }, { role, eventTag: eventTag || EVENT_TAG });
    } catch (e) {
      results.hubspot = { error: String(e) };
    }

    const ok = !results.hubspot?.error;
    return json({ ok, results }, ok ? 200 : 502, env);
  },
};

function json(obj, status, env) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...cors(env) },
  });
}

/**
 * aplus_event_tag is a MULTI-SELECT (fieldType: checkbox) and is append-only
 * per #AP032: a teacher who came to Sage Oak and then Blue Ridge must end up
 * carrying BOTH tags. A flat PATCH replaces the whole set, which is what the
 * Sage Oak worker does — correct there because it was the only event, wrong
 * the moment a second one exists. So: read the existing value, union, write
 * semicolon-delimited.
 */
export function mergeEventTags(existing, newTag) {
  const have = String(existing || "")
    .split(";")
    .map((s) => s.trim())
    .filter(Boolean);
  if (newTag && !have.includes(newTag)) have.push(newTag);
  return have.join(";");
}

// Create-only persona stamp by self-identified role. Existing contacts are
// never overwritten (a_persona is multi-select; po_inbox doctrine). Blue Ridge
// adds the family-side roles Sage Oak never had.
const ROLE_CREATE_PROPS = {
  teacher: { a_persona: "Teacher of Record/EF/ES", hs_lead_status: "Charter School Teacher TOR/EF" },
  administrator: { a_persona: "Decision Maker/Director" },
  support_staff: {},
  parent: { a_persona: "Family" },
  student: { a_persona: "Student" },
};

/**
 * Which seat owns the lead (Roman 2026-09-01): teachers and school staff to
 * sales, families to charter sales. Seats, not people — the ids live in
 * wrangler.toml so a team change never touches code.
 */
const ROLE_SEAT = {
  teacher: "OWNER_SALES",
  administrator: "OWNER_SALES",
  support_staff: "OWNER_SALES",
  parent: "OWNER_CHARTER_SALES",
  student: "OWNER_CHARTER_SALES",
};

export function ownerForRole(env, role) {
  const seat = ROLE_SEAT[role];
  return (seat && env[seat]) || "";
}

async function upsertContact(env, properties, { role, eventTag }) {
  const headers = {
    Authorization: `Bearer ${env.HUBSPOT_TOKEN}`,
    "Content-Type": "application/json",
  };

  // Fetch aplus_event_tag alongside the id — the merge below needs the current
  // value, and Sage Oak's search asked for email only, which is how a flat
  // overwrite became possible.
  const search = await fetch("https://api.hubapi.com/crm/v3/objects/contacts/search", {
    method: "POST",
    headers,
    body: JSON.stringify({
      filterGroups: [{ filters: [{ propertyName: "email", operator: "EQ", value: properties.email }] }],
      properties: ["email", "aplus_event_tag"],
      limit: 1,
    }),
  });
  if (!search.ok) throw new Error(`HubSpot search ${search.status}: ${await search.text()}`);
  const found = await search.json();

  if (found.total > 0) {
    const hit = found.results[0];
    const props = {
      ...properties,
      aplus_event_tag: mergeEventTags(hit.properties?.aplus_event_tag, eventTag),
    };
    // Never blank an existing value with an empty string.
    for (const k of Object.keys(props)) if (props[k] === "") delete props[k];
    return {
      action: "updated",
      id: hit.id,
      ...(await patchContact(env, headers, hit.id, props)),
    };
  }

  // Owner is CREATE-ONLY, like the persona stamp. An existing family may already
  // be worked by someone; reassigning them from a booth tablet would silently
  // take a live relationship off whoever owns it.
  const createProps = {
    ...properties,
    aplus_event_tag: eventTag,
    hubspot_owner_id: ownerForRole(env, role),
    ...(ROLE_CREATE_PROPS[role] || {}),
  };
  for (const k of Object.keys(createProps)) if (createProps[k] === "") delete createProps[k];
  return { action: "created", id: await createContact(env, headers, createProps) };
}

async function patchContact(env, headers, id, props) {
  let res = await fetch(`https://api.hubapi.com/crm/v3/objects/contacts/${id}`, {
    method: "PATCH", headers, body: JSON.stringify({ properties: props }),
  });
  if (res.ok) return {};
  const text = await res.text();
  const retry = withoutUnsyncedProps(props, res.status, text);
  if (!retry) throw new Error(`HubSpot update ${res.status}: ${text}`);
  res = await fetch(`https://api.hubapi.com/crm/v3/objects/contacts/${id}`, {
    method: "PATCH", headers, body: JSON.stringify({ properties: retry.props }),
  });
  if (!res.ok) throw new Error(`HubSpot update ${res.status}: ${await res.text()}`);
  return { dropped: retry.dropped };
}

async function createContact(env, headers, props) {
  let res = await fetch("https://api.hubapi.com/crm/v3/objects/contacts", {
    method: "POST", headers, body: JSON.stringify({ properties: props }),
  });
  if (!res.ok) {
    const text = await res.text();
    const retry = withoutUnsyncedProps(props, res.status, text);
    if (!retry) throw new Error(`HubSpot create ${res.status}: ${text}`);
    res = await fetch("https://api.hubapi.com/crm/v3/objects/contacts", {
      method: "POST", headers, body: JSON.stringify({ properties: retry.props }),
    });
    if (!res.ok) throw new Error(`HubSpot create ${res.status}: ${await res.text()}`);
  }
  return (await res.json()).id;
}

/**
 * properties.yml is PR-gated and create_properties.py runs only after merge, so
 * the Worker can legitimately go live before the schema does. A brand-new
 * property must never cost us the lead: drop the offending keys and retry.
 * Returns null when the failure is anything else.
 */
export function withoutUnsyncedProps(props, status, body) {
  if (status !== 400 || !/PROPERTY_DOESNT_EXIST|does not exist/i.test(String(body))) return null;
  const NEW = ["aplus_booth_prize", "aplus_event_role", "aplus_event_tag"];
  const dropped = NEW.filter((k) => k in props && String(body).includes(k));
  if (!dropped.length) return null;
  const out = { ...props };
  for (const k of dropped) delete out[k];
  return { props: out, dropped };
}
