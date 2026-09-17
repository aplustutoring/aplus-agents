/**
 * A+ photo booth — Cloudflare Worker (`sage-oak-booth`)
 *
 * One Worker, several events. It shipped for Sage Oak BTSC 2026 and kept the
 * name because a Worker's secrets and KV live with its name: renaming it would
 * mean re-entering four secrets the morning of an event. Each event is a row
 * in EVENTS below; the front end says which one it is with `eventTag`.
 *
 *   sage_oak_btsc_2026   booth/index.html, on Cloudflare Pages (historical)
 *   sage_oak_park_2026   booth/public/sage-oak-park/, served by this Worker via [assets]
 *
 * POST /submit
 *   { firstName, lastName, email, phone, role, marketingConsent,
 *     goal, delivery, sendEmail, sendText, eventTag, photo (dataURL jpeg) }
 *
 * Does:
 *   1. Upserts the HubSpot contact (portal 6312752) by email and appends the
 *      event to aplus_event_tag (#AP032: append-only, never a flat write)
 *   2. Archives the photo in KV (permanent) and notes it on the contact
 *   3. If sendEmail: the framed photo via Resend
 *   4. If sendText: the framed photo via JustCall MMS
 *
 * Secrets (wrangler secret put ...):
 *   HUBSPOT_TOKEN, RESEND_API_KEY, JUSTCALL_API_KEY, JUSTCALL_API_SECRET
 * Vars (wrangler.toml):
 *   RESEND_FROM, JUSTCALL_FROM, ALLOWED_ORIGIN (comma-separated list),
 *   OWNER_SALES, OWNER_CHARTER_SALES (HubSpot owner ids, by SEAT)
 *
 * Property manifest doctrine: a new event's aplus_event_tag option must be in
 * properties.yml and synced by create_properties.py before go-live. If it is
 * not, HubSpot rejects the tag and the Worker retries the write without it, so
 * the contact is still captured (see withoutUnsyncedProps).
 */

const LEARN_URL = "https://wetutorathome.com/home-school-tutoring";

// Everything that names the event lives here. Add a row, never edit copy in
// the handlers. `defaultRole` covers a legacy client that sends no role.
export const EVENTS = {
  sage_oak_btsc_2026: {
    name: "Sage Oak Back to School 2026",
    eyebrow: "SAGE OAK · BACK TO SCHOOL 2026",
    emailSubject: "Your Sage Oak Back to School photo is here! 📸",
    filename: "sage-oak-btsc-2026.jpg",
    emailIntro: "Thanks for stopping by the A+ Tutoring booth. Here's to an amazing 2026–2027 school year ahead.",
    emailPitch: "A+ Tutoring partners with Sage Oak to provide one-on-one tutoring and intervention programs for your students, often at no cost through enrichment funds.",
    smsBody: "Hi {name}! Here's your Sage Oak Back to School photo from the A+ Tutoring booth. Ask us about one-on-one tutoring and intervention programs: " + LEARN_URL,
    noteLabel: "Sage Oak BTSC 2026",
    logoUrl: "https://sage-oak-booth.pages.dev/logo.png",
    defaultRole: "teacher",
  },
  // Sage Oak family park day (Ceja), 2026-09-18. Parents outnumber teachers.
  sage_oak_park_2026: {
    name: "Sage Oak Park Day 2026",
    eyebrow: "SAGE OAK · PARK DAY 2026",
    emailSubject: "Your Sage Oak Park Day photo is here! 📸",
    filename: "sage-oak-park-day-2026.jpg",
    emailIntro: "Thanks for stopping by the A+ Tutoring booth at the park. We hope the rest of your day is a great one.",
    emailPitch: "A+ Tutoring partners with Sage Oak to provide one-on-one tutoring for your student, often at no cost to you through enrichment funds.",
    smsBody: "Hi {name}! Here's your Sage Oak Park Day photo from the A+ Tutoring booth. Ask us about one-on-one tutoring for your student: " + LEARN_URL,
    noteLabel: "Sage Oak Park Day 2026",
    logoUrl: "https://sage-oak-booth.nameless-mountain-bafa.workers.dev/logo.png",
    defaultRole: "parent",
  },
};
const DEFAULT_EVENT = "sage_oak_btsc_2026";
export const VALID_ROLES = ["administrator", "teacher", "support_staff", "parent", "student"];
const VALID_DELIVERY = ["email", "print", "both", "text", "all"];

// ALLOWED_ORIGIN is a comma-separated list. The park day page is served by
// this Worker (same origin, no CORS at all); the BTSC page lives on Pages.
export function corsOrigin(env, requestOrigin) {
  const allowed = String(env.ALLOWED_ORIGIN || "*").split(",").map((s) => s.trim()).filter(Boolean);
  if (allowed.includes("*")) return "*";
  if (requestOrigin && allowed.includes(requestOrigin)) return requestOrigin;
  return allowed[0] || "*";
}
const cors = (env, request) => ({
  "Access-Control-Allow-Origin": corsOrigin(env, request?.headers?.get("Origin")),
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Vary": "Origin",
});

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: cors(env, request) });
    }
    const url = new URL(request.url);

    // The booth tablet opens the bare Worker URL; send it to the current event.
    if (request.method === "GET" && url.pathname === "/") {
      return Response.redirect(`${url.origin}/sage-oak-park/`, 302);
    }

    // Public photo host for MMS media_url and the archive links on HubSpot
    // timelines (unguessable UUID keys). Must keep resolving after every event.
    if (request.method === "GET" && url.pathname.startsWith("/photo/")) {
      const key = url.pathname.slice("/photo/".length);
      const img = await env.PHOTOS.get(key, "arrayBuffer");
      if (!img) return new Response("Gone", { status: 404 });
      return new Response(img, {
        headers: { "Content-Type": "image/jpeg", "Cache-Control": "public, max-age=604800" },
      });
    }

    if (request.method !== "POST" || url.pathname !== "/submit") {
      return json({ error: "Not found" }, 404, env, request);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: "Invalid JSON" }, 400, env, request);
    }

    const { firstName, lastName, email, phone, marketingConsent, goal, delivery, sendEmail, sendText, photo } = body;
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return json({ error: "Valid email required" }, 400, env, request);
    }
    if (sendText && !normalizePhone(phone)) {
      return json({ error: "Valid phone required for text delivery" }, 400, env, request);
    }
    const eventTag = EVENTS[body.eventTag] ? body.eventTag : DEFAULT_EVENT;
    const event = EVENTS[eventTag];
    const role = VALID_ROLES.includes(body.role) ? body.role : event.defaultRole;

    const results = { hubspot: null, email: null, text: null, eventTag };

    // ---------- 1. HubSpot upsert ----------
    try {
      results.hubspot = await upsertContact(env, {
        email: String(email).trim().toLowerCase(),
        firstname: String(firstName || "").trim(),
        lastname: String(lastName || "").trim(),
        phone: phone ? String(phone).trim() : "",
        aplus_booth_goal: goal || "",
        // Enum writes take INTERNAL VALUES, not labels (the fleet "read
        // labels" rule is about reading). Values match properties.yml.
        aplus_booth_delivery: VALID_DELIVERY.includes(delivery) ? delivery : "",
        aplus_event_role: role,
        aplus_marketing_consent: marketingConsent ? "true" : "false",
      }, { role, eventTag });
    } catch (e) {
      results.hubspot = { error: String(e) };
    }

    // ---------- 2. Photo archive (every submission, permanent) ----------
    // Stored in KV under an unguessable key, served at /photo/<key>; the MMS
    // path reuses this object instead of storing its own 7-day copy. The
    // archive URL is logged on the contact's timeline so any photo can be
    // recovered/resent later (Katie Lane bounced-email lesson, 2026-08).
    let archiveUrl = null;
    if (photo) {
      try {
        const bytes = jpegBytes(photo);
        const key = `${new Date().toISOString().slice(0, 10)}-${crypto.randomUUID()}.jpg`;
        await env.PHOTOS.put(key, bytes); // no TTL: permanent archive
        archiveUrl = `${url.origin}/photo/${key}`;
        results.archive = { url: archiveUrl };
        if (results.hubspot?.id) {
          try {
            await logPhotoNote(env, results.hubspot.id, archiveUrl, { goal, delivery, event });
          } catch (e) {
            results.archive.noted = String(e);
          }
        }
      } catch (e) {
        results.archive = { error: String(e) };
      }
    }

    // ---------- 3. Resend email ----------
    if (sendEmail && photo) {
      try {
        results.email = await sendPhotoEmail(env, { email, firstName, photo, event });
        if (results.hubspot?.id) {
          try {
            await logEmailEngagement(env, results.hubspot.id, email, event);
          } catch (e) {
            results.email.logged = String(e);
          }
        }
      } catch (e) {
        results.email = { error: String(e) };
      }
    }

    // ---------- 4. JustCall MMS ----------
    if (sendText && photo) {
      try {
        results.text = await sendPhotoText(env, { phone, firstName, photo, archiveUrl, origin: url.origin, event });
      } catch (e) {
        results.text = { error: String(e) };
      }
    }

    const ok = !(results.hubspot?.error) && !(sendEmail && results.email?.error) && !(sendText && results.text?.error);
    return json({ ok, results }, ok ? 200 : 502, env, request);
  },
};

function json(obj, status, env, request) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...cors(env, request) },
  });
}

function jpegBytes(dataUrl) {
  const base64 = String(dataUrl).replace(/^data:image\/jpeg;base64,/, "");
  return Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
}

/**
 * aplus_event_tag is a MULTI-SELECT (fieldType: checkbox) and is append-only
 * per #AP032. A flat PATCH replaces the whole set, which was harmless while
 * Sage Oak was the only event and became a data-loss bug the moment Blue Ridge
 * shipped: a teacher who attended both would have had Sage Oak erased on their
 * second visit. Ported from booth/blue-ridge/worker.js (Roman 2026-09-02).
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
// never overwritten (a_persona is multi-select; po_inbox doctrine). The
// family-side roles arrived with Blue Ridge; the Sage Oak park day is the
// first photo booth where parents outnumber teachers.
const ROLE_CREATE_PROPS = {
  teacher: { a_persona: "Teacher of Record/EF/ES", hs_lead_status: "Charter School Teacher TOR/EF" },
  administrator: { a_persona: "Decision Maker/Director" },
  support_staff: {},
  parent: { a_persona: "Family" },
  student: { a_persona: "Student" },
};

/**
 * Which seat owns the lead (Roman 2026-09-01): teachers and school staff to
 * sales, families to charter sales. Seats, not people: the ids live in
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

  // aplus_event_tag comes back so the merge below can union rather than
  // replace (see mergeEventTags).
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
    return { action: "updated", id: hit.id, ...(await patchContact(env, headers, hit.id, props)) };
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
  return { action: "created", ...(await createContact(env, headers, createProps)) };
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
  let dropped;
  if (!res.ok) {
    const text = await res.text();
    const retry = withoutUnsyncedProps(props, res.status, text);
    if (!retry) throw new Error(`HubSpot create ${res.status}: ${text}`);
    res = await fetch("https://api.hubapi.com/crm/v3/objects/contacts", {
      method: "POST", headers, body: JSON.stringify({ properties: retry.props }),
    });
    if (!res.ok) throw new Error(`HubSpot create ${res.status}: ${await res.text()}`);
    dropped = retry.dropped;
  }
  const id = (await res.json()).id;
  return dropped ? { id, dropped } : { id };
}

/**
 * properties.yml is PR-gated and create_properties.py runs only after merge, so
 * a booth can legitimately go live before the schema does. A missing property
 * OR a not-yet-synced enum option (a new event's tag) must never cost us the
 * lead: drop the offending keys and retry. Returns null for any other failure.
 */
export function withoutUnsyncedProps(props, status, body) {
  const text = String(body);
  if (status !== 400 || !/PROPERTY_DOESNT_EXIST|does not exist|not one of the allowed options|INVALID_OPTION/i.test(text)) return null;
  const NEW = ["aplus_event_tag", "aplus_event_role", "aplus_booth_goal", "aplus_booth_delivery", "aplus_marketing_consent"];
  const dropped = NEW.filter((k) => k in props && text.includes(k));
  if (!dropped.length) return null;
  const out = { ...props };
  for (const k of dropped) delete out[k];
  return { props: out, dropped };
}

async function sendPhotoEmail(env, { email, firstName, photo, event }) {
  const base64 = String(photo).replace(/^data:image\/jpeg;base64,/, "");
  const name = firstName || "there";

  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: env.RESEND_FROM,
      to: [email],
      subject: event.emailSubject,
      attachments: [{ filename: event.filename, content: base64 }],
      html: `
        <div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto;background:#F7F4EC;padding:32px;border-radius:16px;">
          <img src="${event.logoUrl}" alt="A+ Tutoring" width="110" style="display:block;margin:0 0 18px;">
          <p style="font-size:13px;letter-spacing:2px;color:#46603F;font-weight:bold;margin:0 0 12px;">${escapeHtml(event.eyebrow)}</p>
          <h1 style="color:#2E4030;font-size:26px;margin:0 0 16px;">Hi ${escapeHtml(name)}, your photo is attached!</h1>
          <p style="color:#1E281C;font-size:16px;line-height:1.6;">${escapeHtml(event.emailIntro)}</p>
          <p style="color:#1E281C;font-size:16px;line-height:1.6;">${escapeHtml(event.emailPitch)}</p>
          <p style="margin:28px 0;">
            <a href="${LEARN_URL}" style="background:#E2A33B;color:#1E281C;font-weight:bold;text-decoration:none;padding:14px 28px;border-radius:999px;display:inline-block;">Learn how it works</a>
          </p>
          <p style="color:#46603F;font-size:13px;">A+ Tutoring · wetutorathome.com</p>
        </div>`,
    }),
  });
  if (!res.ok) throw new Error(`Resend ${res.status}: ${await res.text()}`);
  return { sent: true };
}

// Timeline logging: the booth photo email shows on the contact record like
// any logged email (association 198 = email->contact).
async function logEmailEngagement(env, contactId, toEmail, event) {
  const res = await fetch("https://api.hubapi.com/crm/v3/objects/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.HUBSPOT_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      properties: {
        hs_timestamp: new Date().toISOString(),
        hs_email_direction: "EMAIL",
        hs_email_status: "SENT",
        hs_email_subject: event.emailSubject,
        hs_email_text: `Booth photo emailed to ${toEmail} from ${env.RESEND_FROM} (${event.noteLabel} photo booth). CTA: ${LEARN_URL}`,
      },
      associations: [{
        to: { id: contactId },
        types: [{ associationCategory: "HUBSPOT_DEFINED", associationTypeId: 198 }],
      }],
    }),
  });
  if (!res.ok) throw new Error(`HubSpot email log ${res.status}: ${await res.text()}`);
}

// Photo-archive breadcrumb on the contact timeline (note->contact assoc 202)
async function logPhotoNote(env, contactId, photoUrl, { goal, delivery, event }) {
  const res = await fetch("https://api.hubapi.com/crm/v3/objects/notes", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.HUBSPOT_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      properties: {
        hs_timestamp: new Date().toISOString(),
        hs_note_body: `📸 Booth photo (archived): ${photoUrl}\nBanner: "${goal || ""}" · Delivery: ${delivery || ""} · ${event.noteLabel}`,
      },
      associations: [{
        to: { id: contactId },
        types: [{ associationCategory: "HUBSPOT_DEFINED", associationTypeId: 202 }],
      }],
    }),
  });
  if (!res.ok) throw new Error(`HubSpot photo note ${res.status}: ${await res.text()}`);
}

// "(818) 850-6284" / "818-850-6284" / "+18188506284" -> "+18188506284"
export function normalizePhone(raw) {
  const d = String(raw || "").replace(/\D/g, "");
  if (d.length === 10) return `+1${d}`;
  if (d.length === 11 && d.startsWith("1")) return `+${d}`;
  return null;
}

async function sendPhotoText(env, { phone, firstName, photo, archiveUrl, origin, event }) {
  const to = normalizePhone(phone);

  // Reuse the permanent archive object when available; store a 7-day copy
  // only as fallback (e.g. archive write failed).
  let mediaUrl = archiveUrl;
  if (!mediaUrl) {
    const key = `${crypto.randomUUID()}.jpg`;
    await env.PHOTOS.put(key, jpegBytes(photo), { expirationTtl: 604800 });
    mediaUrl = `${origin}/photo/${key}`;
  }

  const name = firstName || "there";
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
      body: event.smsBody.replace("{name}", name),
      media_url: mediaUrl,
    }),
  });
  if (!res.ok) throw new Error(`JustCall ${res.status}: ${await res.text()}`);
  return { sent: true };
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
