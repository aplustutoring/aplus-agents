/**
 * EO LA Valley "Build Your First AI Agent" booth — Cloudflare Worker
 * Agent persona: "Minion #23" 🤖. NOTHING attendee-facing may read as A+.
 *
 * EVENT-TEMP. Sunset 2026-08-22: disable both crons, disable the inbound
 * webhook, delete the eo_lav_agents_2026 contacts, archive the six eo_*
 * properties via the properties.yml retire process.
 *
 * Routes
 *   POST /capture     booth submission (see booth/eo/index.html)
 *   GET  /photo/<key> public image host — MMS media_url + hero images
 *   POST /sms         JustCall inbound webhook (idea capture + STOP)
 *
 * Crons (see wrangler.toml — UTC, and PT is UTC-7 in August)
 *   17 1 * * *  → 6:17 PM PT — Payload #1 (triple text + brief email)
 *   0  3 * * *  → 8:00 PM PT — Payload #2 (hero MMS + composed email)
 *
 * Secrets (wrangler secret put ...)
 *   HUBSPOT_TOKEN  RESEND_API_KEY  JUSTCALL_API_KEY  JUSTCALL_API_SECRET
 *   ANTHROPIC_API_KEY  GEMINI_API_KEY  ZAPIER_IDEAS_HOOK
 *
 * Nothing prints at the booth. Attendees receive the framed EO card by email
 * and MMS, and both images land in the shared Drive folder — prints are pulled
 * from Drive afterwards, so no one is standing at a printer mid-event.
 */

const EVENT_TAG = "eo_lav_agents_2026";

// Claude model: locked by Roman's brief. claude-opus-5 is the current
// flagship and writes a better brief; sonnet-4-6 is faster and cheaper, and
// supports the same web_search_20260209 tool. Swap the constant to change.
const CLAUDE_MODEL = "claude-sonnet-4-6";

// Gemini for the hero image — the same model + reference-image face-lock
// technique the case-study comic engine uses. NOT Higgsfield: Higgsfield is
// a connected app in this stack, has no API key here, and cannot be reached
// from a Worker (see marketing/scripts/b2c/build-case-study-comic.py:18).
const GEMINI_MODEL = "gemini-3-pro-image";

// Locked copy — do not paraphrase. Every attendee-facing string signs M23.
const HERO_PROMPT =
  "Cinematic superhero portrait of this exact person, preserving their exact " +
  "face and likeness, wearing a sleek dark suit with a glowing AI " +
  "circuit-shield badge on the chest, electric blue energy aura, dramatic " +
  "rim lighting, dark city skyline at night, hyper-detailed, movie-poster " +
  "quality.";

const PHOTO_SMS =
  "📸 Great seeing you tonight! Here's your photo from the EO LA Valley " +
  "workshop. Reply STOP to opt out.";

const PAYLOAD1_TEXTS = [
  (c) => `Hi ${c.firstname || "there"} — while you were finding your seat, I researched ${c.company || "your company"}. Full notes in your email. — Minion #23 🤖`,
  () => "Seriously, check your email. I stayed up all 11 minutes of my life working on this.",
  (c) => `${c.firstname || "Hey"}. The email. I can see Roman stalling up there. You have time.`,
];

const PAYLOAD2_TEXT_WITH_HERO =
  "Look at you — building a minion of your own. That superhero? That's you " +
  "now. Wrap it up, he's about to talk again. — Minion #23 🤖";

// Same copy minus the superhero sentence. No apology, no "image failed".
const PAYLOAD2_TEXT_NO_HERO =
  "Look at you — building a minion of your own. Wrap it up, he's about to " +
  "talk again. — Minion #23 🤖";

const IDEA_AUTOREPLY = "Logged. Roman sees everything. Build it well tonight. — M23";

// ── Deliverable ③ was not supplied. These two system prompts are DRAFTS
// written to match the Minion #23 voice; Roman approves or replaces them
// before go-live. Everything else in this file is per spec.
const RESEARCH_SYSTEM = `You are Minion #23, an AI agent working a photo booth at an Entrepreneurs' Organization chapter event in Los Angeles. You have about two minutes and one job: find out who this person actually is, professionally, and write it up so it lands when they read it on their phone twenty minutes later.

Search the web for the company you are given. Look for what it does, roughly how big it is, who runs it, and — most importantly — anything recent and specific: a new location, a hire, an award, an acquisition, a press mention, a product launch, a milestone. Specific and recent beats comprehensive.

Then write a brief of 150-220 words, in plain paragraphs. No headers, no bullet points, no markdown — this is going in the body of an email and it should read like a person wrote it, not like a report.

Rules that matter:
- Open with the single most specific true thing you found. Not "Acme Corp is a leading provider of..." — that is what every AI writes and it will kill the effect. Something they would be surprised you knew.
- Be accurate above all else. This person knows their own company better than you do, and one wrong fact destroys the whole trick. If the search turns up little, say less rather than padding. Never invent a detail, a number, or a quote.
- If you genuinely cannot identify the company, write about the industry and what is happening in it right now, and say plainly that you could not find much on them specifically. Honest and short beats confident and wrong.
- No flattery, no "impressive work you're doing." Observant, dry, a little amused at itself. You are a robot who did homework.
- Do not mention tutoring, education, or any company other than theirs. Do not pitch anything. Do not sign off — the email template adds the signature.

Return only the brief text.`;

const PAYLOAD2_SYSTEM = `You are Minion #23, an AI agent at an Entrepreneurs' Organization event in Los Angeles. Earlier tonight you took someone's photo, researched their company, and texted them about it. The workshop is now ending — they have just spent two hours building their first AI agent.

You will be given the research brief you wrote earlier. Write the closing email.

Length: 120-180 words, plain paragraphs, no headers or bullets or markdown.

What it needs to do:
- Call back to one specific detail from your earlier brief, so it is obvious this is the same agent that has been paying attention all night rather than a template blast.
- Land the actual point: a few hours ago an agent doing this to them was a magic trick, and they just built one themselves. They can do this. It is closer than it looked.
- Be warm here. You have been dry and a little smug all evening; this is the one place you drop it slightly. Do not become sentimental or start giving a speech.
- No pitch, no call to action, no links, no ask. Nothing to buy or book. The whole point is that you want nothing from them.
- Do not mention tutoring, education, or any company other than theirs.
- Do not sign off — the template adds the signature.

Return only the email body text.`;

// ────────────────────────────────────────────────────────────── HTTP

const cors = (env) => ({
  "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
});

export default {
  async fetch(request, env, ctx) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: cors(env) });
    }
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname.startsWith("/photo/")) {
      const key = url.pathname.slice("/photo/".length);
      const img = await env.PHOTOS.get(key, "arrayBuffer");
      if (!img) return new Response("Gone", { status: 404 });
      return new Response(img, {
        headers: { "Content-Type": "image/jpeg", "Cache-Control": "public, max-age=604800" },
      });
    }

    if (request.method === "POST" && url.pathname === "/sms") {
      return handleInboundSms(request, env, ctx);
    }

    if (request.method === "POST" && url.pathname === "/capture") {
      return handleCapture(request, env, ctx, url);
    }

    return json({ error: "Not found" }, 404, env);
  },

  // Cron A and cron B share this handler; event.cron says which fired.
  async scheduled(event, env, ctx) {
    if (event.cron === "17 1 * * *") {
      ctx.waitUntil(runPayload1(env));
    } else if (event.cron === "0 3 * * *") {
      ctx.waitUntil(runPayload2(env));
    } else {
      log(env, { at: "scheduled", warn: "unrecognized cron", cron: event.cron });
    }
  },
};

// ─────────────────────────────────────────────────────────── /capture

async function handleCapture(request, env, ctx, url) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Invalid JSON" }, 400, env);
  }

  const { firstName, lastName, email, phone, company, demoConsent, photo, face } = body;
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return json({ error: "Valid email required" }, 400, env);
  }
  const to = normalizePhone(phone);
  if (!to) return json({ error: "Valid phone required" }, 400, env);

  const results = {};

  // ---- 1. HubSpot upsert (tag + company + demo consent) ----
  let contactId = null;
  try {
    const up = await upsertContact(env, {
      email,
      firstname: firstName || "",
      lastname: lastName || "",
      phone: to,
      aplus_event_tag: EVENT_TAG,
      eo_company_name: company || "",
      eo_demo_consent: demoConsent ? "true" : "false",
    });
    contactId = up.id;
    results.hubspot = up;
  } catch (e) {
    results.hubspot = { error: String(e) };
  }

  // ---- 1b. Archive the booth photo; it doubles as the MMS media_url ----
  let photoUrl = null;
  if (photo) {
    try {
      const key = `eo/${crypto.randomUUID()}.jpg`;
      await env.PHOTOS.put(key, dataUrlToBytes(photo));
      photoUrl = `${url.origin}/photo/${key}`;
      results.photo = { url: photoUrl };
    } catch (e) {
      results.photo = { error: String(e) };
    }
  }

  // ---- 2. INSTANT beat. Never blocked by the async work below. ----
  try {
    results.email = await sendEmail(env, {
      to: email,
      subject: "Your photo from tonight 📸",
      html: photoEmailHtml(firstName, photoUrl),
    });
  } catch (e) {
    results.email = { error: String(e) };
  }

  // The ONLY message carrying the opt-out line.
  try {
    results.text = await sendSms(env, {
      to,
      body: PHOTO_SMS,
      mediaUrl: photoUrl,
      contactId,
      payload: "photo",
      // The photo is theirs regardless of demo consent, and this message is
      // where the opt-out lives, so it is not gated on eo_demo_consent.
      ignoreConsent: true,
    });
  } catch (e) {
    results.text = { error: String(e) };
  }

  // ---- 3. ASYNC: research → hero → Drive → clock check ----
  if (contactId) {
    ctx.waitUntil(afterCapture(env, url, {
      contactId, firstName, lastName, email, to, company, face, photoUrl,
      demoConsent: !!demoConsent,
    }));
  }

  return json({ ok: true, results }, 200, env);
}

// Sequential by design: the clock check at the end must see the stored brief.
async function afterCapture(env, url, c) {
  // (a) research brief — retry once, then a graceful generic brief
  let brief = null;
  try {
    brief = await researchBrief(env, c.company);
  } catch (e) {
    log(env, { at: "research", contactId: c.contactId, error: String(e), attempt: 1 });
    try {
      brief = await researchBrief(env, c.company);
    } catch (e2) {
      log(env, { at: "research", contactId: c.contactId, error: String(e2), attempt: 2 });
      brief = genericBrief(c.company);
    }
  }
  try {
    await patchContact(env, c.contactId, { eo_research_brief: brief });
  } catch (e) {
    log(env, { at: "research.store", contactId: c.contactId, error: String(e) });
  }

  // (b) hero image — retry once, then leave empty (Payload #2 degrades)
  let heroUrl = "";
  if (c.face) {
    for (let attempt = 1; attempt <= 2 && !heroUrl; attempt++) {
      try {
        const bytes = await heroImage(env, c.face);
        const key = `eo/hero-${crypto.randomUUID()}.jpg`;
        await env.PHOTOS.put(key, bytes);
        heroUrl = `${url.origin}/photo/${key}`;
      } catch (e) {
        log(env, { at: "hero", contactId: c.contactId, error: String(e), attempt });
      }
    }
    if (heroUrl) {
      try {
        await patchContact(env, c.contactId, { eo_hero_image_url: heroUrl });
      } catch (e) {
        log(env, { at: "hero.store", contactId: c.contactId, error: String(e) });
      }
    }
  }

  // (c) Drive upload for Crystal (comms chair). Since the booth no longer
  // prints, Drive is where prints are pulled from afterwards — so a silent
  // failure here costs someone their print. It still must not block or
  // surface, so instead we leave a recovery path: both URLs go on the
  // contact's timeline, and the images live in KV with no TTL. Nothing is
  // lost if the Drive hook is down, it just has to be re-run.
  try {
    await logPhotoNote(env, c.contactId, c.photoUrl, heroUrl);
  } catch (e) {
    log(env, { at: "photo.note", contactId: c.contactId, error: String(e) });
  }
  try {
    await uploadToDrive(env, {
      lastName: c.lastName, firstName: c.firstName, photoUrl: c.photoUrl, heroUrl,
    });
  } catch (e) {
    log(env, { at: "drive", contactId: c.contactId, error: String(e) });
  }

  // (d) clock check — captured after 6:17 PM PT? send Payload #1 now.
  // Before 6:17, do nothing: cron A batches this contact with everyone else.
  if (nowPT() >= 18 * 60 + 17) {   // 6:17 PM PT
    try {
      const fresh = await getContact(env, c.contactId, ["eo_payload1_sent"]);
      if (!fresh?.properties?.eo_payload1_sent) {
        await sendPayload1(env, {
          id: c.contactId,
          firstname: c.firstName,
          email: c.email,
          phone: c.to,
          company: c.company,
          brief,
          demoConsent: c.demoConsent,
        });
      }
    } catch (e) {
      log(env, { at: "instant.payload1", contactId: c.contactId, error: String(e) });
    }
  }
}

// ─────────────────────────────────────────────────────── inbound SMS

// Scoped to the booth number only — never touches main-line routing.
async function handleInboundSms(request, env, ctx) {
  let body;
  try {
    body = await request.json();
  } catch {
    return new Response("ok", { status: 200 });
  }

  // JustCall's inbound payload shape varies by webhook version; read the
  // common field names defensively rather than assuming one. VERIFY against
  // a real delivery before go-live.
  const d = body.data || body;
  const from = normalizePhone(d.contact_number || d.from || d.contact_phone || "");
  const text = String(d.body || d.message || d.text || d.sms_body || "").trim();
  const toNumber = normalizePhone(d.justcall_number || d.to || "");

  // Hard scope guard: ignore anything that did not land on the booth line.
  const booth = normalizePhone(env.JUSTCALL_FROM || "");
  if (booth && toNumber && toNumber !== booth) {
    return new Response("ok", { status: 200 });
  }
  if (!from) return new Response("ok", { status: 200 });

  if (/^(stop|unsubscribe|stopall|quit|cancel|end)\b/i.test(text)) {
    await env.PHOTOS.put(`optout:${from}`, "1");
    log(env, { at: "sms.optout", from });
    return new Response("ok", { status: 200 });
  }

  if (!text) return new Response("ok", { status: 200 });

  // Resolve a name if we can, so Crystal's sheet is readable.
  let name = "";
  try {
    const c = await searchByPhone(env, from);
    if (c) name = `${c.properties.firstname || ""} ${c.properties.lastname || ""}`.trim();
  } catch (e) {
    log(env, { at: "sms.resolve", from, error: String(e) });
  }

  ctx.waitUntil((async () => {
    try {
      if (env.MODE === "send" && env.ZAPIER_IDEAS_HOOK) {
        const res = await fetch(env.ZAPIER_IDEAS_HOOK, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            timestamp: new Date().toISOString(), phone: from, name, idea: text,
          }),
        });
        if (!res.ok) throw new Error(`Zapier ${res.status}`);
      }
      log(env, { at: "sms.idea", from, name, chars: text.length });
    } catch (e) {
      log(env, { at: "sms.idea", from, error: String(e) });
    }
    try {
      await sendSms(env, { to: from, body: IDEA_AUTOREPLY, payload: "idea-ack", ignoreConsent: true });
    } catch (e) {
      log(env, { at: "sms.ack", from, error: String(e) });
    }
  })());

  return new Response("ok", { status: 200 });
}

// ──────────────────────────────────────────────────────────── payloads

// Cron A. Everyone's phone buzzes together — that is the effect on stage.
async function runPayload1(env) {
  const contacts = (await listTagged(env, [
    "firstname", "lastname", "email", "phone",
    "eo_company_name", "eo_research_brief", "eo_payload1_sent", "eo_demo_consent",
  ])).filter((c) => !c.properties.eo_payload1_sent);

  log(env, { at: "payload1", found: contacts.length });
  if (!contacts.length) return;

  // Claim BEFORE sending. A contact captured mid-cron takes the instant
  // path, sees the stamp, and stands down — one send per human.
  const claimed = [];
  for (const c of contacts) {
    const p = c.properties;
    try {
      await patchContact(env, c.id, { eo_payload1_sent: new Date().toISOString() });
      claimed.push({
        id: c.id,
        firstname: p.firstname,
        email: p.email,
        phone: normalizePhone(p.phone),
        company: p.eo_company_name,
        brief: p.eo_research_brief || genericBrief(p.eo_company_name),
        demoConsent: p.eo_demo_consent === "true",
      });
    } catch (e) {
      log(env, { at: "payload1.claim", contactId: c.id, error: String(e) });
    }
  }

  // Texts in three waves, ~30s apart. Sleeping is wall clock, not CPU, so
  // this stays well inside the scheduled-handler budget.
  for (let i = 0; i < PAYLOAD1_TEXTS.length; i++) {
    if (i > 0) await sleep(30000);
    await Promise.all(claimed.map((c) =>
      sendSms(env, {
        to: c.phone,
        body: PAYLOAD1_TEXTS[i](c),
        contactId: c.id,
        payload: `payload1-text${i + 1}`,
        requireConsent: !c.demoConsent,
      }).catch((e) => log(env, { at: `payload1.text${i + 1}`, contactId: c.id, error: String(e) }))
    ));
  }

  await Promise.all(claimed.map((c) =>
    sendEmail(env, {
      to: c.email,
      subject: `I did some homework on ${c.company || "your company"}`,
      html: briefEmailHtml(c.brief),
    }).catch((e) => log(env, { at: "payload1.email", contactId: c.id, error: String(e) }))
  ));
}

// Instant-path variant: one contact, same copy, same stagger.
async function sendPayload1(env, c) {
  await patchContact(env, c.id, { eo_payload1_sent: new Date().toISOString() });
  for (let i = 0; i < PAYLOAD1_TEXTS.length; i++) {
    if (i > 0) await sleep(30000);
    await sendSms(env, {
      to: c.phone,
      body: PAYLOAD1_TEXTS[i](c),
      contactId: c.id,
      payload: `payload1-text${i + 1}`,
      requireConsent: !c.demoConsent,
    }).catch((e) => log(env, { at: `payload1.text${i + 1}`, contactId: c.id, error: String(e) }));
  }
  await sendEmail(env, {
    to: c.email,
    subject: `I did some homework on ${c.company || "your company"}`,
    html: briefEmailHtml(c.brief),
  });
}

// Cron B. ALL tagged contacts, regardless of payload-1 status.
async function runPayload2(env) {
  const contacts = (await listTagged(env, [
    "firstname", "lastname", "email", "phone",
    "eo_company_name", "eo_research_brief", "eo_hero_image_url",
    "eo_payload2_sent", "eo_demo_consent",
  ])).filter((c) => !c.properties.eo_payload2_sent);

  log(env, { at: "payload2", found: contacts.length });

  for (const c of contacts) {
    const p = c.properties;
    const phone = normalizePhone(p.phone);
    const hero = p.eo_hero_image_url || "";
    const consented = p.eo_demo_consent === "true";

    try {
      await patchContact(env, c.id, { eo_payload2_sent: new Date().toISOString() });
    } catch (e) {
      log(env, { at: "payload2.claim", contactId: c.id, error: String(e) });
      continue;
    }

    // Static template, NOT Claude-generated. Missing hero → text-only,
    // same copy minus the superhero sentence. Seamless, no apology.
    await sendSms(env, {
      to: phone,
      body: hero ? PAYLOAD2_TEXT_WITH_HERO : PAYLOAD2_TEXT_NO_HERO,
      mediaUrl: hero || null,
      contactId: c.id,
      payload: hero ? "payload2-mms" : "payload2-text",
      requireConsent: !consented,
    }).catch((e) => log(env, { at: "payload2.text", contactId: c.id, error: String(e) }));

    let bodyText;
    try {
      bodyText = await composePayload2Email(env, p.eo_research_brief || genericBrief(p.eo_company_name));
    } catch (e) {
      log(env, { at: "payload2.compose", contactId: c.id, error: String(e) });
      bodyText = fallbackPayload2Body();
    }

    await sendEmail(env, {
      to: p.email,
      subject: "Two of us on your team now",
      html: briefEmailHtml(bodyText),
    }).catch((e) => log(env, { at: "payload2.email", contactId: c.id, error: String(e) }));
  }
}

// ─────────────────────────────────────────────────────────── Claude

async function researchBrief(env, company) {
  const name = (company || "").trim();
  if (!name) throw new Error("no company");

  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": env.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: CLAUDE_MODEL,
      max_tokens: 2000,
      system: RESEARCH_SYSTEM,
      // Dynamic filtering is built into this tool version — do NOT also
      // declare code_execution; a second execution environment confuses
      // the model.
      tools: [{ type: "web_search_20260209", name: "web_search" }],
      messages: [{
        role: "user",
        content: `Company: ${name}\n\nResearch them and write the brief.`,
      }],
    }),
  });
  if (!res.ok) throw new Error(`Anthropic ${res.status}: ${await res.text()}`);
  const data = await res.json();

  // Safety classifiers can decline with a 200 — check before reading content.
  if (data.stop_reason === "refusal") throw new Error("refusal");

  // A server-side tool loop that hits its iteration cap returns pause_turn
  // with a partial answer. Resend to let the server pick up where it left
  // off; do NOT append a "continue" user message.
  if (data.stop_reason === "pause_turn") {
    const resumed = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "x-api-key": env.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: CLAUDE_MODEL,
        max_tokens: 2000,
        system: RESEARCH_SYSTEM,
        tools: [{ type: "web_search_20260209", name: "web_search" }],
        messages: [
          { role: "user", content: `Company: ${name}\n\nResearch them and write the brief.` },
          { role: "assistant", content: data.content },
        ],
      }),
    });
    if (!resumed.ok) throw new Error(`Anthropic resume ${resumed.status}`);
    const rdata = await resumed.json();
    const rtext = extractText(rdata);
    if (rtext) return rtext;
  }

  const text = extractText(data);
  if (!text) throw new Error("empty brief");
  return text;
}

async function composePayload2Email(env, brief) {
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": env.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: CLAUDE_MODEL,
      max_tokens: 1200,
      system: PAYLOAD2_SYSTEM,
      messages: [{
        role: "user",
        content: `Here is the brief you wrote earlier tonight:\n\n${brief}\n\nWrite the closing email.`,
      }],
    }),
  });
  if (!res.ok) throw new Error(`Anthropic ${res.status}: ${await res.text()}`);
  const data = await res.json();
  if (data.stop_reason === "refusal") throw new Error("refusal");
  const text = extractText(data);
  if (!text) throw new Error("empty email");
  return text;
}

// Response content is a list of blocks — text, server_tool_use,
// web_search_tool_result. Only the text blocks are the answer.
function extractText(data) {
  return (data.content || [])
    .filter((b) => b.type === "text")
    .map((b) => b.text)
    .join("\n")
    .trim();
}

function genericBrief(company) {
  const name = (company || "your company").trim();
  return `I went looking for ${name} and came back with less than I wanted — which, honestly, is its own kind of finding. The businesses that are heads-down building tend to leave a thinner trail than the ones optimizing their trail.

So instead of pretending I know your quarter, here is what I actually know: you are in a room tonight full of people who run things, learning to build an agent like me. Twenty minutes ago you were having your photo taken. Now you are reading a piece of email that assembled itself around your name.

That is the whole demo. Whatever I would have found about ${name}, the interesting part was never the research — it was that nobody asked me to do it.`;
}

function fallbackPayload2Body() {
  return `A few hours ago, an agent texting you about your own company was a party trick. You have spent the evening building one.

That is the entire distance between those two things: an evening. Not a degree, not a team, not a budget cycle. Whatever you sketched out in that exercise tonight is closer than it looked when you walked in.

Go build it.`;
}

// ─────────────────────────────────────────────────────────── Gemini

// Face-lock via reference image — the same technique the case-study comic
// engine uses for character consistency, pointed at the attendee's selfie.
async function heroImage(env, faceDataUrl) {
  const b64 = faceDataUrl.replace(/^data:image\/\w+;base64,/, "");
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent?key=${env.GEMINI_API_KEY}`;

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contents: [{
        parts: [
          { inline_data: { mime_type: "image/jpeg", data: b64 } },
          { text: HERO_PROMPT + " Use the EXACT SAME person shown in the reference image: identical face, hair, skin tone, age and build. CRITICAL: absolutely no text, letters, words, logos or watermarks anywhere in the image." },
        ],
      }],
      generationConfig: { responseModalities: ["IMAGE"] },
    }),
  });
  if (!res.ok) throw new Error(`Gemini ${res.status}: ${(await res.text()).slice(0, 300)}`);

  const data = await res.json();
  const parts = data?.candidates?.[0]?.content?.parts || [];
  const img = parts.find((p) => p.inline_data?.data || p.inlineData?.data);
  const out = img?.inline_data?.data || img?.inlineData?.data;
  if (!out) throw new Error("no image in Gemini response");
  return Uint8Array.from(atob(out), (ch) => ch.charCodeAt(0));
}

// ──────────────────────────────────────────────────────────── Drive

// Crystal's shared folder — and, now that the booth does not print, the
// source everyone's prints get pulled from after the event. Failure is
// logged and never surfaced: the photo flow is sacred and must not block on
// a Drive write, and the recovery path above means nothing is unrecoverable.
async function uploadToDrive(env, { lastName, firstName, photoUrl, heroUrl }) {
  if (!env.DRIVE_UPLOAD_HOOK) return;
  const slug = (s) => String(s || "guest").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const base = `${slug(lastName)}-${slug(firstName)}`;
  const files = [];
  if (photoUrl) files.push({ filename: `${base}-photo.jpg`, url: photoUrl });
  if (heroUrl) files.push({ filename: `${base}-hero.jpg`, url: heroUrl });
  if (!files.length) return;

  if (env.MODE !== "send") {
    log(env, { at: "drive", dry_run: true, files: files.map((f) => f.filename) });
    return;
  }
  const res = await fetch(env.DRIVE_UPLOAD_HOOK, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder: env.DRIVE_FOLDER_ID || "", files }),
  });
  if (!res.ok) throw new Error(`Drive hook ${res.status}`);
}

// ─────────────────────────────────────────────────────────── HubSpot

const hsHeaders = (env) => ({
  Authorization: `Bearer ${env.HUBSPOT_TOKEN}`,
  "Content-Type": "application/json",
});

async function upsertContact(env, properties) {
  const search = await fetch("https://api.hubapi.com/crm/v3/objects/contacts/search", {
    method: "POST",
    headers: hsHeaders(env),
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
      method: "PATCH", headers: hsHeaders(env), body: JSON.stringify({ properties }),
    });
    if (!upd.ok) throw new Error(`HubSpot update ${upd.status}: ${await upd.text()}`);
    return { action: "updated", id };
  }

  const crt = await fetch("https://api.hubapi.com/crm/v3/objects/contacts", {
    method: "POST", headers: hsHeaders(env), body: JSON.stringify({ properties }),
  });
  if (!crt.ok) throw new Error(`HubSpot create ${crt.status}: ${await crt.text()}`);
  return { action: "created", id: (await crt.json()).id };
}

async function patchContact(env, id, properties) {
  const res = await fetch(`https://api.hubapi.com/crm/v3/objects/contacts/${id}`, {
    method: "PATCH", headers: hsHeaders(env), body: JSON.stringify({ properties }),
  });
  if (!res.ok) throw new Error(`HubSpot patch ${res.status}: ${await res.text()}`);
}

async function getContact(env, id, props) {
  const res = await fetch(
    `https://api.hubapi.com/crm/v3/objects/contacts/${id}?properties=${props.join(",")}`,
    { headers: hsHeaders(env) },
  );
  if (!res.ok) throw new Error(`HubSpot get ${res.status}`);
  return res.json();
}

// Recovery breadcrumb on the contact timeline (note→contact assoc 202), so
// any photo can be re-fetched or re-uploaded to Drive later without digging
// through KV keys. Same pattern the Sage Oak booth uses.
async function logPhotoNote(env, contactId, photoUrl, heroUrl) {
  if (!photoUrl && !heroUrl) return;
  const lines = [
    photoUrl ? `📸 Booth photo: ${photoUrl}` : null,
    heroUrl ? `🦸 Hero image: ${heroUrl}` : null,
    "EO LA Valley · Build Your First AI Agent · 2026-08-20",
  ].filter(Boolean);

  const res = await fetch("https://api.hubapi.com/crm/v3/objects/notes", {
    method: "POST",
    headers: hsHeaders(env),
    body: JSON.stringify({
      properties: { hs_timestamp: new Date().toISOString(), hs_note_body: lines.join("\n") },
      associations: [{
        to: { id: contactId },
        types: [{ associationCategory: "HUBSPOT_DEFINED", associationTypeId: 202 }],
      }],
    }),
  });
  if (!res.ok) throw new Error(`HubSpot note ${res.status}: ${await res.text()}`);
}

async function searchByPhone(env, phone) {
  const res = await fetch("https://api.hubapi.com/crm/v3/objects/contacts/search", {
    method: "POST",
    headers: hsHeaders(env),
    body: JSON.stringify({
      filterGroups: [{ filters: [{ propertyName: "phone", operator: "EQ", value: phone }] }],
      properties: ["firstname", "lastname"],
      limit: 1,
    }),
  });
  if (!res.ok) throw new Error(`HubSpot phone search ${res.status}`);
  const data = await res.json();
  return data.total > 0 ? data.results[0] : null;
}

// aplus_event_tag is a multi-checkbox, so the operator is CONTAINS_TOKEN.
async function listTagged(env, properties) {
  const out = [];
  let after;
  do {
    const res = await fetch("https://api.hubapi.com/crm/v3/objects/contacts/search", {
      method: "POST",
      headers: hsHeaders(env),
      body: JSON.stringify({
        filterGroups: [{ filters: [{ propertyName: "aplus_event_tag", operator: "CONTAINS_TOKEN", value: EVENT_TAG }] }],
        properties,
        limit: 100,
        ...(after ? { after } : {}),
      }),
    });
    if (!res.ok) throw new Error(`HubSpot list ${res.status}: ${await res.text()}`);
    const data = await res.json();
    out.push(...(data.results || []));
    after = data.paging?.next?.after;
  } while (after);
  return out;
}

// ────────────────────────────────────────────────────── send channels

async function sendSms(env, { to, body, mediaUrl, contactId, payload, requireConsent, ignoreConsent }) {
  if (!to) throw new Error("no phone");

  // STOP excludes a contact from ALL further SMS/MMS. Email still sends.
  if (await env.PHOTOS.get(`optout:${to}`)) {
    log(env, { at: "sms", payload, contactId, to, skipped: "opted-out" });
    return { skipped: "opted-out" };
  }
  if (requireConsent && !ignoreConsent) {
    log(env, { at: "sms", payload, contactId, to, skipped: "no-demo-consent" });
    return { skipped: "no-demo-consent" };
  }

  if (env.MODE !== "send") {
    log(env, { at: "sms", payload, contactId, to, dry_run: true, media: !!mediaUrl, body });
    return { dry_run: true };
  }

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
      body,
      ...(mediaUrl ? { media_url: mediaUrl } : {}),
    }),
  });
  if (!res.ok) throw new Error(`JustCall ${res.status}: ${await res.text()}`);
  log(env, { at: "sms", payload, contactId, to, sent: true, media: !!mediaUrl });
  return { sent: true };
}

async function sendEmail(env, { to, subject, html }) {
  if (env.MODE !== "send") {
    log(env, { at: "email", to, subject, dry_run: true });
    return { dry_run: true };
  }
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({ from: env.RESEND_FROM, to: [to], subject, html }),
  });
  if (!res.ok) throw new Error(`Resend ${res.status}: ${await res.text()}`);
  log(env, { at: "email", to, subject, sent: true });
  return { sent: true };
}

// ───────────────────────────────────────────────────────── templates

// Dark + electric, signed M23. No A+ logo, no A+ colours, no A+ links.
function shell(inner) {
  return `<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:560px;margin:0 auto;background:#0B1220;color:#E2E8F0;padding:34px;border-radius:16px;">
  <p style="font-size:12px;letter-spacing:2.5px;color:#38BDF8;font-weight:700;margin:0 0 22px;">EO LA VALLEY · BUILD YOUR FIRST AI AGENT</p>
  ${inner}
  <p style="color:#64748B;font-size:12px;margin-top:30px;">You met me at the photo booth on August 20, 2026.</p>
</div>`;
}

function photoEmailHtml(firstName, photoUrl) {
  return shell(`
  <h1 style="color:#F1F5F9;font-size:23px;margin:0 0 16px;">Here's your photo, ${escapeHtml(firstName || "friend")}.</h1>
  ${photoUrl ? `<img src="${escapeHtml(photoUrl)}" alt="Your photo" style="width:100%;border-radius:12px;margin:0 0 18px;">` : ""}
  <p style="font-size:16px;line-height:1.65;color:#CBD5E1;">That's the easy part. I'm working on something else for you — give me a few minutes.</p>
  <p style="font-size:16px;line-height:1.65;color:#94A3B8;">— Minion #23 🤖</p>`);
}

function briefEmailHtml(bodyText) {
  const paras = String(bodyText).split(/\n\s*\n/).map((p) =>
    `<p style="font-size:16px;line-height:1.7;color:#CBD5E1;margin:0 0 16px;">${escapeHtml(p.trim()).replace(/\n/g, "<br>")}</p>`
  ).join("");
  return shell(`
  <p style="font-size:16px;line-height:1.7;color:#94A3B8;margin:0 0 20px;">You took a photo 20 minutes ago. I've been busy since.</p>
  ${paras}
  <p style="font-size:16px;line-height:1.7;color:#38BDF8;margin-top:22px;">— Minion #23 🤖 <span style="color:#64748B;">(I'm not done yet.)</span></p>`);
}

// ─────────────────────────────────────────────────────────── helpers

function json(obj, status, env) {
  return new Response(JSON.stringify(obj), {
    status, headers: { "Content-Type": "application/json", ...cors(env) },
  });
}

function normalizePhone(raw) {
  const d = String(raw || "").replace(/\D/g, "");
  if (d.length === 10) return `+1${d}`;
  if (d.length === 11 && d.startsWith("1")) return `+${d}`;
  return null;
}

function dataUrlToBytes(dataUrl) {
  const b64 = String(dataUrl).replace(/^data:image\/\w+;base64,/, "");
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

// Minutes since midnight, America/Los_Angeles. PT is UTC-7 in August, but
// derive it rather than hardcoding so a post-DST re-run can't be wrong.
function nowPT() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles", hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(new Date());
  const h = Number(parts.find((p) => p.type === "hour").value);
  const m = Number(parts.find((p) => p.type === "minute").value);
  return h * 60 + m;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Every send is logged: contact id, payload type, channel, timestamp.
function log(env, fields) {
  console.log(JSON.stringify({ ts: new Date().toISOString(), mode: env.MODE || "dry_run", ...fields }));
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
