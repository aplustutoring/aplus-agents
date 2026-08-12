/**
 * Sage Oak BTSC 2026 Photo Booth — Cloudflare Worker
 *
 * POST /submit
 *   { firstName, lastName, email, phone, marketingConsent,
 *     goal, delivery, sendEmail, eventTag, photo (dataURL jpeg) }
 *
 * Does:
 *   1. Upserts HubSpot contact (portal 6312752) by email,
 *      tags with aplus_event_tag = "sage_oak_btsc_2026"
 *   2. If sendEmail: sends the framed photo via Resend as attachment
 *
 * Secrets (wrangler secret put ...):
 *   HUBSPOT_TOKEN   — private app token with crm.objects.contacts write
 *   RESEND_API_KEY
 * Vars (wrangler.toml):
 *   RESEND_FROM     — e.g. "A+ Tutoring <photos@aplustutoring.com>"
 *   ALLOWED_ORIGIN  — booth Pages URL, e.g. "https://sage-oak-booth.pages.dev"
 *
 * NOTE (property manifest doctrine): `aplus_event_tag` must be added to
 * properties.yml in aplus-agents and created in HubSpot before go-live.
 */

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

    const { firstName, lastName, email, phone, marketingConsent, goal, delivery, sendEmail, eventTag, photo } = body;
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return json({ error: "Valid email required" }, 400, env);
    }

    const results = { hubspot: null, email: null };

    // ---------- 1. HubSpot upsert ----------
    try {
      results.hubspot = await upsertContact(env, {
        email,
        firstname: firstName || "",
        lastname: lastName || "",
        phone: phone || "",
        aplus_event_tag: eventTag || "sage_oak_btsc_2026",
        aplus_booth_goal: goal || "",
        // Dropdowns: write per property contract (labels for delivery, true/false values for consent)
        aplus_booth_delivery: { email: "Email", print: "Print", both: "Both" }[delivery] || "",
        aplus_marketing_consent: marketingConsent ? "true" : "false",
      });
    } catch (e) {
      results.hubspot = { error: String(e) };
    }

    // ---------- 2. Resend email ----------
    if (sendEmail && photo) {
      try {
        results.email = await sendPhotoEmail(env, { email, firstName, photo });
      } catch (e) {
        results.email = { error: String(e) };
      }
    }

    const ok = !(results.hubspot?.error) && !(sendEmail && results.email?.error);
    return json({ ok, results }, ok ? 200 : 502, env);
  },
};

function json(obj, status, env) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...cors(env) },
  });
}

async function upsertContact(env, properties) {
  const headers = {
    Authorization: `Bearer ${env.HUBSPOT_TOKEN}`,
    "Content-Type": "application/json",
  };

  // Search by email
  const search = await fetch("https://api.hubapi.com/crm/v3/objects/contacts/search", {
    method: "POST",
    headers,
    body: JSON.stringify({
      filterGroups: [{ filters: [{ propertyName: "email", operator: "EQ", value: properties.email }] }],
      properties: ["email"],
      limit: 1,
    }),
  });
  if (!search.ok) throw new Error(`HubSpot search ${search.status}: ${await search.text()}`);
  const found = await search.json();

  if (found.total > 0) {
    const id = found.results[0].id;
    const upd = await fetch(`https://api.hubapi.com/crm/v3/objects/contacts/${id}`, {
      method: "PATCH",
      headers,
      body: JSON.stringify({ properties }),
    });
    if (!upd.ok) throw new Error(`HubSpot update ${upd.status}: ${await upd.text()}`);
    return { action: "updated", id };
  }

  const crt = await fetch("https://api.hubapi.com/crm/v3/objects/contacts", {
    method: "POST",
    headers,
    body: JSON.stringify({ properties }),
  });
  if (!crt.ok) throw new Error(`HubSpot create ${crt.status}: ${await crt.text()}`);
  const created = await crt.json();
  return { action: "created", id: created.id };
}

async function sendPhotoEmail(env, { email, firstName, photo }) {
  const base64 = photo.replace(/^data:image\/jpeg;base64,/, "");
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
      subject: "Your Sage Oak Back to School photo is here! \uD83D\uDCF8",
      attachments: [{ filename: "sage-oak-btsc-2026.jpg", content: base64 }],
      html: `
        <div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto;background:#F7F4EC;padding:32px;border-radius:16px;">
          <img src="https://sage-oak-booth.pages.dev/logo.png" alt="A+ Tutoring" width="110" style="display:block;margin:0 0 18px;">
          <p style="font-size:13px;letter-spacing:2px;color:#46603F;font-weight:bold;margin:0 0 12px;">SAGE OAK \u00B7 BACK TO SCHOOL 2026</p>
          <h1 style="color:#2E4030;font-size:26px;margin:0 0 16px;">Hi ${escapeHtml(name)}, your photo is attached!</h1>
          <p style="color:#1E281C;font-size:16px;line-height:1.6;">Thanks for stopping by the A+ Tutoring booth. Here's to an amazing school year ahead.</p>
          <p style="color:#1E281C;font-size:16px;line-height:1.6;">A+ Tutoring partners with Sage Oak to provide one-on-one virtual tutoring for your students &mdash; often at no cost to families through enrichment funds.</p>
          <p style="margin:28px 0;">
            <a href="https://wetutorathome.com" style="background:#E2A33B;color:#1E281C;font-weight:bold;text-decoration:none;padding:14px 28px;border-radius:999px;display:inline-block;">Learn how it works</a>
          </p>
          <p style="color:#46603F;font-size:13px;">A+ Tutoring \u00B7 Supporting Sage Oak families since day one</p>
        </div>`,
    }),
  });
  if (!res.ok) throw new Error(`Resend ${res.status}: ${await res.text()}`);
  return { sent: true };
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
