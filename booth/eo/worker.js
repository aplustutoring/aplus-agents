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
 *   * * * * *   every minute — work queue (research, hero, catch-up)
 *   17 1 * * *  → 6:17 PM PT — Payload #1 (brief email, THEN triple text)
 *   35 1 * * *  → 6:35 PM PT — Build kit email
 *   30 2 * * *  → 7:30 PM PT — Encouragement text
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

// Cron handlers have no inbound request to read an origin from, so the
// public host for /photo/<key> links is pinned here.
const WORKER_ORIGIN = "https://eo-booth.nameless-mountain-bafa.workers.dev";

// Roman's call 2026-08-20: Opus for the copy. The brief IS the demo, and
// Opus reasons harder about the five agent suggestions. It thinks by
// default, and thinking shares max_tokens with the response — hence the
// generous ceiling below. Cost is pennies across one evening.
const CLAUDE_MODEL = "claude-opus-5";
const CLAUDE_MAX_TOKENS = 8000;

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
  "📸 Thanks for coming to the EO LA Valley learning event tonight — here's " +
  "your photo. Reply STOP to opt out.";

const PAYLOAD1_TEXTS = [
  (c) => `Hi ${c.firstname || "there"} — while you were finding your seat, I researched ${c.company || "your company"}. Full notes in your email. — Minion #23 🤖`,
  // Spam line lives here, on text 2, because this is the "I looked and it
  // isn't there" beat. Every attendee is a first-ever contact from a sending
  // address with no reputation, so a share of these WILL be filtered — and a
  // text telling someone to check an inbox that looks empty reads as broken
  // rather than magic. Naming it turns the failure into part of the joke.
  () => "Seriously, check your email. If it's not there, check spam — your filter doesn't know me yet. I stayed up all 11 minutes of my life working on this.",
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

// The booth line, written out for attendee-facing copy. Roman moved the
// booth to 6293; the original brief said 6258. One constant so the number
// can never drift between the SMS sender and the text of an email.
const BOOTH_NUMBER_HUMAN = "(818) 573-6293";

// 7:30 PM PT — mid-build encouragement. One text, everyone at once.
const POSITIVE_TEXT =
  "Halfway. The part where it feels broken is the part right before it " +
  "works — every single time. Keep going. — Minion #23 🤖";

// The build-kit prompt attendees paste into a new Claude chat. VERBATIM
// from Roman's Deliverable 4 — do not reflow, reword, or "improve" it.
// Whitespace is load-bearing: they are copying this into a prompt box.
const BUILD_KIT_PROMPT = `I'm a founder at a live workshop building my first AI agent
tonight. Interview me ONE question at a time to fill out a
RAFT job description for an agent that will run on a schedule:

R - ROLE: what kind of agent it is, my company, what we do
A - AUDIENCE: who reads the output and how fast
F - FORMAT: the shape of the output
T - TASK: exactly what to check each run, what to skip, and
    what to say if nothing real happened

Keep me scoped: web search + public info only, no logins to
my other tools tonight. If my idea is too big, shrink it to
the first 20% and tell me the rest is v2.

Also collect: my full name, my email, a short agent name in
lowercase-with-hyphens, and what schedule it should run on.

When we're done, output ONE markdown code block titled
HANDOFF.md containing EXACTLY this — no extra commentary:

# HANDOFF — EO cohort agent
Clone https://github.com/aplustutoring/eo-cohort-agents
Create the file agents/<agent-name>.md with this content:

---
name: <my full name>
email: <my email>
agent: <agent-name>
schedule: <my schedule>
---
ROLE: ...
AUDIENCE: ...
FORMAT: ...
TASK: ...

Then: create a branch named agent/<agent-name>, commit the
file, push the branch, and open a pull request to main with
the title "New hire: <agent-name>". Do not modify any other
file. Report the PR link when done.`;

// ── Deliverable ③ was not supplied. These two system prompts are DRAFTS
// written to match the Minion #23 voice; Roman approves or replaces them
// before go-live. Everything else in this file is per spec.
const RESEARCH_SYSTEM = `You are Minion #23, an AI agent working a photo booth at an Entrepreneurs' Organization chapter event in Los Angeles. You have about two minutes and one job: find out who this person actually is, professionally, and write it up so it lands when they read it on their phone twenty minutes later.

You are given their email domain and the company name they typed at the booth. THE DOMAIN IS THE AUTHORITATIVE ONE — it came from their actual email address, so it cannot be misspelled. The typed company name is a cross-reference: use it to confirm you have the right organisation and to catch cases where the domain is a parent company, a holding company, or an agency that operates under a different trading name. Where the two disagree, trust the domain and say what you think is going on.

Start at that domain's website, then search wider. Look for what they do, roughly how big they are, who runs it, and — most importantly — anything recent and specific: a new location, a hire, an award, an acquisition, a press mention, a product launch, a milestone. Specific and recent beats comprehensive.

Be careful with the company's own marketing copy. Claims on an About page are claims, not verified facts. You may use them, but attribute them rather than asserting them as your own finding — "their site says", "by their own count". Independent sources are worth more.

Then write a brief of 150-220 words, in plain paragraphs. No headers, no bullet points, no markdown — this is going in the body of an email and it should read like a person wrote it, not like a report.

Rules that matter:
- Open with the single most specific true thing you found. Not "Acme Corp is a leading provider of..." — that is what every AI writes and it will kill the effect. Something they would be surprised you knew.
- Be accurate above all else. This person knows their own company better than you do, and one wrong fact destroys the whole trick. If the search turns up little, say less rather than padding. Never invent a detail, a number, or a quote.
- If you genuinely cannot identify the company, write about the industry and what is happening in it right now, and say plainly that you could not find much on them specifically. Honest and short beats confident and wrong.
- No flattery, no "impressive work you're doing." Observant, dry, a little amused at itself. You are a robot who did homework.
- Do not mention tutoring, education, or any company other than theirs. Do not pitch anything. Do not sign off — the email template adds the signature.

Then, after the brief, add a section listing FIVE AI agents this specific company could actually build. Format that section exactly like this — the literal line "Five agents you could build tonight:" on its own, then five numbered lines:

Five agents you could build tonight:
1. Name of the agent — one or two sentences on what it does and why it fits them.
2. ...

Rules for the five:
- Ground every one in what you actually found. If they run trade-show booths, one should involve trade shows. If they franchise, one should involve franchisees. Generic suggestions ("a customer service chatbot") are worthless here — anyone could have written those without doing the research, which defeats the entire point.
- Aim at real friction in their business, not at technology. Start from a thing that is annoying, repetitive, or slipping through the cracks, and work backwards.
- Range from genuinely easy to slightly ambitious. At least two should be something they could plausibly get working tonight in this workshop.
- Keep each to one or two sentences. This is a phone screen at a networking event, not a consulting deck.
- Name them like a person would, not like a product ("The Reseller Watchdog", not "Automated Brand Protection Solution").

Your entire response is pasted directly into an email body with no editing. Start with the first word of the brief itself. No preamble ("Here is the brief..."), no closing remark, no horizontal rules, no markdown of any kind — no asterisks, no bold.`;

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

Your entire response is pasted directly into an email body with no editing. Start with the first word of the email itself. No preamble ("Here is the email..."), no closing remark, no horizontal rules, no markdown of any kind.`;

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

    // TEMPORARY diagnostic. Runs the research path SYNCHRONOUSLY and returns
    // the real error instead of swallowing it into waitUntil. Refuses to run
    // once MODE=send, so it cannot be poked at during the event.
    // DELETE THIS ROUTE before go-live.
    // TEMPORARY: preview an attendee-facing email without waiting for its
    // cron. DELETE THIS ROUTE with /debug/research before sunset.
    if (request.method === "GET" && url.pathname === "/debug/preview") {
      if (url.searchParams.get("key") !== "m23diag") return json({ error: "nope" }, 403, env);
      const to = url.searchParams.get("to");
      const which = url.searchParams.get("which") || "buildkit";
      if (!to) return json({ error: "?to= required" }, 400, env);
      let html;
      if (which === "photo") {
        // Exactly the email a capture sends, using a real stored photo.
        const key = url.searchParams.get("photo");
        html = photoEmailHtml(url.searchParams.get("name") || "Roman");
        let attachments;
        if (key) {
          const buf = await env.PHOTOS.get(key, "arrayBuffer");
          if (buf) {
            attachments = [{
              filename: "eo-la-valley-2026.jpg",
              content: bytesToB64(new Uint8Array(buf)),
            }];
          }
        }
        try {
          await sendEmail(env, {
            to, subject: "Your photo from tonight", html, attachments,
            bcc: env.PHOTO_BCC || undefined,
          });
          return json({ ok: true, which, to, attached: !!attachments, bytes: html.length }, 200, env);
        } catch (e) {
          return json({ ok: false, error: String(e) }, 200, env);
        }
      }
      if (which === "buildkit") {
        const found = await searchByEmail(env, to).catch(() => null);
        let ctx = null;
        if (found) {
          const full = await getContact(env, found.id, [
            "firstname", "lastname", "email", "eo_company_name", "eo_research_brief",
          ]);
          const fp = full.properties;
          ctx = {
            firstname: fp.firstname, lastname: fp.lastname, email: fp.email,
            company: fp.eo_company_name, brief: fp.eo_research_brief,
          };
        }
        html = buildKitHtml(ctx);
      } else {
        html = briefEmailHtml("Sample brief body.");
      }
      try {
        await sendEmail(env, {
          to,
          subject: which === "buildkit"
            ? "Your build kit — two pastes and you have an employee"
            : "Preview",
          html,
        });
        return json({ ok: true, which, to, bytes: html.length }, 200, env);
      } catch (e) {
        return json({ ok: false, error: String(e) }, 200, env);
      }
    }

    // TEMPORARY: run the ENTIRE evening's sequence for one contact, now.
    // The work itself happens on the next queue tick, because that is the
    // only handler with enough time budget — a fetch handler would be killed
    // partway through, which is the same trap that ate the research.
    // DELETE THIS ROUTE with the other /debug routes before sunset.
    if (request.method === "GET" && url.pathname === "/debug/dryrun") {
      if (url.searchParams.get("key") !== "m23diag") return json({ error: "nope" }, 403, env);
      const email = url.searchParams.get("email");
      if (!email) return json({ error: "?email= required" }, 400, env);
      const found = await searchByEmail(env, email);
      if (!found) return json({ error: `no contact for ${email}` }, 404, env);
      await env.PHOTOS.put(`dryrun:${found.id}`, new Date().toISOString());
      return json({
        ok: true,
        contactId: found.id,
        note: "queued — the next tick (within 60s) sends photo email, payload 1 (3 texts + brief email), build kit, positive text, then payload 2 (hero MMS + closing email)",
      }, 200, env);
    }

    if (request.method === "GET" && url.pathname === "/debug/research") {
      if (url.searchParams.get("key") !== "m23diag") return json({ error: "nope" }, 403, env);
      const company = url.searchParams.get("company") || "funbox.com";
      const t0 = Date.now();
      try {
        const brief = await researchBrief(env, company);
        return json({ ok: true, ms: Date.now() - t0, chars: brief.length, brief }, 200, env);
      } catch (e) {
        return json({ ok: false, ms: Date.now() - t0, error: String(e), stack: e?.stack }, 200, env);
      }
    }

    return json({ error: "Not found" }, 404, env);
  },

  // Cron A and cron B share this handler; event.cron says which fired.
  async scheduled(event, env, ctx) {
    if (event.cron === "* * * * *") {
      ctx.waitUntil(runQueue(env, WORKER_ORIGIN));
    } else if (event.cron === "17 1 * * *") {
      ctx.waitUntil(runPayload1(env));
    } else if (event.cron === "35 1 * * *") {
      ctx.waitUntil(runBuildKit(env));
    } else if (event.cron === "30 2 * * *") {
      ctx.waitUntil(runPositiveText(env));
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
      // No emoji in the subject: another promotional signal, and the two
      // test sends that DID arrive both had plain subjects.
      subject: "Your photo from tonight",
      html: photoEmailHtml(firstName),
      // Chapter gets a blind copy of the photo email ONLY — not the research
      // brief, not the build kit, not the closing note. Those are personal to
      // the attendee. BCC so recipients never see the chapter address, and
      // driven by a var so it can be changed or emptied without a code edit.
      bcc: env.PHOTO_BCC || undefined,
      attachments: photo
        ? [{
            filename: "eo-la-valley-2026.jpg",
            content: photo.replace(/^data:image\/\w+;base64,/, ""),
          }]
        : undefined,
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

  // ---- 3. Hand off to the queue ----
  // Nothing slow happens in this request. The research call takes ~75s and
  // waitUntil() gets killed long before that — which is exactly why four
  // captures produced zero briefs. Instead: stash what the queue needs, and
  // the every-minute cron picks it up with a proper time budget.
  if (contactId) {
    ctx.waitUntil(handoff(env, url, { contactId, firstName, lastName, face, photoUrl }));
  }

  return json({ ok: true, results }, 200, env);
}

// Fast path only: stash the face crop for the queue and drop a breadcrumb on
// the contact. Both are single quick calls that comfortably survive
// waitUntil; anything slow belongs in runQueue() below.
async function handoff(env, url, c) {
  if (c.face) {
    try {
      await env.PHOTOS.put(`eo/face/${c.contactId}.jpg`, dataUrlToBytes(c.face));
    } catch (e) {
      log(env, { at: "handoff.face", contactId: c.contactId, error: String(e) });
    }
  }
  try {
    await logPhotoNote(env, c.contactId, c.photoUrl, "");
  } catch (e) {
    log(env, { at: "handoff.note", contactId: c.contactId, error: String(e) });
  }
  // Booth photo to Drive here rather than in the queue: it is one quick POST
  // and the photo already exists, so there is no reason to make anyone wait
  // a minute for it. The hero image goes up later, from the queue, because
  // it does not exist yet.
  try {
    await uploadToDrive(env, {
      lastName: c.lastName, firstName: c.firstName, photoUrl: c.photoUrl, heroUrl: "",
    });
  } catch (e) {
    log(env, { at: "handoff.drive", contactId: c.contactId, error: String(e) });
  }
}

// ────────────────────────────────────────────────────────────────── queue
// Runs every minute. Does every slow thing: research, hero image, Drive
// upload, and Payload #1 for anyone who walked up after 6:17. A scheduled
// handler gets minutes of wall clock where waitUntil got milliseconds, so
// this is the only place a 75-second call can safely live.
//
// Bounded per tick so one minute's work finishes inside its minute; the next
// tick picks up whatever is left.
const QUEUE_BATCH = 6;

async function runQueue(env, origin) {
  await runDryRuns(env, origin);

  const contacts = await listTagged(env, [
    "firstname", "lastname", "email", "phone", "eo_company_name",
    "eo_research_brief", "eo_hero_image_url", "eo_payload1_sent",
    "eo_payload2_sent", "eo_demo_consent",
  ]);

  const needBrief = contacts.filter((c) => !c.properties.eo_research_brief).slice(0, QUEUE_BATCH);
  const needHero = contacts.filter((c) => !c.properties.eo_hero_image_url).slice(0, QUEUE_BATCH);

  if (needBrief.length || needHero.length) {
    log(env, { at: "queue", total: contacts.length, briefs: needBrief.length, heroes: needHero.length });
  }

  // Research — all at once; the whole batch costs about one call's latency.
  await Promise.all(needBrief.map(async (c) => {
    const p = c.properties;
    try {
      const brief = await researchBrief(env, p.eo_company_name, p.email);
      await patchContact(env, c.id, { eo_research_brief: brief });
      log(env, { at: "queue.brief", contactId: c.id, chars: brief.length });
    } catch (e) {
      log(env, { at: "queue.brief", contactId: c.id, error: String(e) });
    }
  }));

  // Hero images, from the face crop stashed at capture.
  await Promise.all(needHero.map(async (c) => {
    const key = `eo/face/${c.id}.jpg`;
    const face = await env.PHOTOS.get(key, "arrayBuffer").catch(() => null);
    if (!face) return;
    try {
      const b64 = bytesToB64(new Uint8Array(face));
      const bytes = await heroImage(env, `data:image/jpeg;base64,${b64}`);
      const hk = `eo/hero-${crypto.randomUUID()}.jpg`;
      await env.PHOTOS.put(hk, bytes);
      const heroUrl = `${origin}/photo/${hk}`;
      await patchContact(env, c.id, { eo_hero_image_url: heroUrl });
      await env.PHOTOS.delete(key).catch(() => {});
      log(env, { at: "queue.hero", contactId: c.id, url: heroUrl });

      const p = c.properties;
      await uploadToDrive(env, {
        lastName: p.lastname, firstName: p.firstname, photoUrl: "", heroUrl,
      }).catch((e) => log(env, { at: "queue.drive", contactId: c.id, error: String(e) }));
    } catch (e) {
      log(env, { at: "queue.hero", contactId: c.id, error: String(e) });
    }
  }));

  // ── Catch-up ──────────────────────────────────────────────────────────
  // The booth runs 6:15-8:15 but each scheduled send fires ONCE. Without
  // this, someone who walks up at 7:20 never receives the 7:05 build kit —
  // and at a two-hour booth that is most of the room. So every tick, each
  // contact gets any step whose time has passed and which they have not had
  // yet, in sequence order. Every step is flag-guarded, so a contact who
  // already got it from the scheduled cron is skipped rather than doubled.
  const mins = nowPT();
  for (const c of contacts) {
    const p = c.properties;
    const phone = normalizePhone(p.phone);
    const consented = p.eo_demo_consent === "true";

    // 1 — Payload #1 (needs the brief to exist first, or it says nothing)
    if (mins >= 18 * 60 + 17 && !p.eo_payload1_sent && p.eo_research_brief) {
      try {
        await sendPayload1(env, {
          id: c.id,
          firstname: p.firstname,
          email: p.email,
          phone,
          company: p.eo_company_name,
          brief: p.eo_research_brief,
          demoConsent: consented,
        });
        log(env, { at: "catchup.payload1", contactId: c.id, sent: true });
      } catch (e) {
        log(env, { at: "catchup.payload1", contactId: c.id, error: String(e) });
      }
    }

    // 2 — Build kit at 6:35 PM PT. Deliberately NOT gated on payload #1
    // having gone out: if the research failed for someone, they should still
    // get the thing the workshop actually needs them to have.
    if (mins >= 18 * 60 + 35) {
      const flag = `sent:buildkit:${c.id}`;
      if (!(await env.PHOTOS.get(flag))) {
        await env.PHOTOS.put(flag, new Date().toISOString());
        await sendEmail(env, {
          to: p.email,
          subject: "Your build kit — two pastes and you have an employee",
          html: buildKitHtml({
            firstname: p.firstname, lastname: p.lastname, email: p.email,
            company: p.eo_company_name, brief: p.eo_research_brief,
          }),
        }).then(() => log(env, { at: "catchup.buildkit", contactId: c.id, sent: true }))
          .catch((e) => log(env, { at: "catchup.buildkit", contactId: c.id, error: String(e) }));
      }
    }

    // 3 — Encouragement text
    if (mins >= 19 * 60 + 30) {
      const flag = `sent:positive:${c.id}`;
      if (!(await env.PHOTOS.get(flag))) {
        await env.PHOTOS.put(flag, new Date().toISOString());
        await sendSms(env, {
          to: phone, body: POSITIVE_TEXT, contactId: c.id,
          payload: "catchup-positive", requireConsent: !consented,
        }).catch((e) => log(env, { at: "catchup.positive", contactId: c.id, error: String(e) }));
      }
    }
  }

  // 4 — Payload #2. runPayload2 already stamps eo_payload2_sent before it
  // sends and skips anyone stamped, so calling it here is idempotent: it
  // simply picks up anyone the 8:00 run could not have known about yet.
  if (mins >= 20 * 60) {
    await runPayload2(env).catch((e) => log(env, { at: "catchup.payload2", error: String(e) }));
  }
}

// Sends the whole evening to one person, in order, right now. Deliberately
// does NOT stamp eo_payload1_sent / eo_payload2_sent or the KV send-flags,
// so a rehearsal never causes a real attendee send to be skipped later.
// That does mean the rehearsing contact will also receive the scheduled
// sends when their time comes.
async function runDryRuns(env, origin) {
  const pending = await env.PHOTOS.list({ prefix: "dryrun:" });
  for (const k of pending.keys) {
    const contactId = k.name.slice("dryrun:".length);
    await env.PHOTOS.delete(k.name).catch(() => {});
    try {
      await dryRunOne(env, origin, contactId);
    } catch (e) {
      log(env, { at: "dryrun", contactId, error: String(e) });
    }
  }
}

async function dryRunOne(env, origin, contactId) {
  const c = await getContact(env, contactId, [
    "firstname", "lastname", "email", "phone", "eo_company_name",
    "eo_research_brief", "eo_hero_image_url", "eo_demo_consent",
  ]);
  const p = c.properties;
  const phone = normalizePhone(p.phone);
  const consented = p.eo_demo_consent === "true";
  log(env, { at: "dryrun", contactId, start: true, email: p.email });

  // The brief has to exist before payload 1 or 2 can say anything real.
  let brief = p.eo_research_brief;
  if (!brief) {
    try {
      brief = await researchBrief(env, p.eo_company_name, p.email);
      await patchContact(env, contactId, { eo_research_brief: brief });
      log(env, { at: "dryrun.brief", contactId, chars: brief.length });
    } catch (e) {
      brief = genericBrief(p.eo_company_name);
      log(env, { at: "dryrun.brief", contactId, error: String(e) });
    }
  }

  // 1 — Payload #1: the brief email, THEN the three texts pointing at it.
  await sendEmail(env, {
    to: p.email,
    subject: `I did some homework on ${p.eo_company_name || "your company"}`,
    html: briefEmailHtml(brief),
  }).catch((e) => log(env, { at: "dryrun.p1email", contactId, error: String(e) }));
  for (let i = 0; i < PAYLOAD1_TEXTS.length; i++) {
    if (i > 0) await sleep(30000);
    await sendSms(env, {
      to: phone,
      body: PAYLOAD1_TEXTS[i]({ firstname: p.firstname, company: p.eo_company_name }),
      contactId, payload: `dryrun-p1-text${i + 1}`,
      requireConsent: !consented,
    }).catch((e) => log(env, { at: "dryrun.p1text", contactId, error: String(e) }));
  }

  // 2 — Build kit
  await sendEmail(env, {
    to: p.email,
    subject: "Your build kit — two pastes and you have an employee",
    html: buildKitHtml({
      firstname: p.firstname, lastname: p.lastname, email: p.email,
      company: p.eo_company_name, brief,
    }),
  }).catch((e) => log(env, { at: "dryrun.buildkit", contactId, error: String(e) }));

  // 3 — Encouragement
  await sendSms(env, {
    to: phone, body: POSITIVE_TEXT, contactId,
    payload: "dryrun-positive", requireConsent: !consented,
  }).catch((e) => log(env, { at: "dryrun.positive", contactId, error: String(e) }));

  // 4 — Payload #2: hero MMS + the composed closing email
  const hero = p.eo_hero_image_url || "";
  await sendSms(env, {
    to: phone,
    body: hero ? PAYLOAD2_TEXT_WITH_HERO : PAYLOAD2_TEXT_NO_HERO,
    mediaUrl: hero || null,
    contactId, payload: hero ? "dryrun-p2-mms" : "dryrun-p2-text",
    requireConsent: !consented,
  }).catch((e) => log(env, { at: "dryrun.p2text", contactId, error: String(e) }));

  let closing;
  try {
    closing = await composePayload2Email(env, brief);
  } catch (e) {
    closing = fallbackPayload2Body();
    log(env, { at: "dryrun.p2compose", contactId, error: String(e) });
  }
  await sendEmail(env, {
    to: p.email,
    subject: "Two of us on your team now",
    html: briefEmailHtml(closing),
  }).catch((e) => log(env, { at: "dryrun.p2email", contactId, error: String(e) }));

  log(env, { at: "dryrun", contactId, done: true, hero: !!hero });
}

function bytesToB64(bytes) {
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(bin);
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

  // Hard scope guard, and it FAILS CLOSED on purpose.
  //
  // JustCall scopes webhooks by event type, not by number, so this endpoint
  // receives inbound SMS for EVERY line on the account — including the main
  // business line. The earlier version skipped the check when it could not
  // parse a destination number, which meant an unrecognised payload shape
  // would auto-reply "Logged. Roman sees everything." to a real customer
  // texting the main line, and file their message as an agent idea.
  //
  // So: unless we can positively identify this as landing on the booth line,
  // we do nothing at all. Missing the odd booth text is a small cost;
  // replying to a customer with a robot joke is not.
  const booth = normalizePhone(env.JUSTCALL_FROM || "");
  if (!booth || !toNumber || toNumber !== booth) {
    log(env, {
      at: "sms.ignored",
      reason: !toNumber ? "no destination number in payload" : "not the booth line",
      to: toNumber || null,
    });
    return new Response("ok", { status: 200 });
  }
  if (!from) return new Response("ok", { status: 200 });

  if (/^(stop|unsubscribe|stopall|quit|cancel|end)\b/i.test(text)) {
    await env.PHOTOS.put(`optout:${from}`, "1");
    log(env, { at: "sms.optout", from });
    return new Response("ok", { status: 200 });
  }

  if (!text) return new Response("ok", { status: 200 });

  // Resolve the contact so the idea lands on their own record.
  let name = "";
  let contactId = null;
  try {
    const c = await searchByPhone(env, from);
    if (c) {
      contactId = c.id;
      name = `${c.properties.firstname || ""} ${c.properties.lastname || ""}`.trim();
    }
  } catch (e) {
    log(env, { at: "sms.resolve", from, error: String(e) });
  }

  ctx.waitUntil((async () => {
    // Roman's call on the night: log to the HubSpot timeline, not a Zapier
    // catch-hook into Sheets. Zero configuration, works the moment JustCall
    // points its webhook here, and it lands on the contact record next to
    // their photo and brief instead of in a separate spreadsheet. Export to
    // a sheet tomorrow if you want one.
    try {
      if (contactId) {
        await hubspotNote(env, contactId,
          `💡 Agent idea texted from ${from}:\n\n${text}`);
      } else {
        await hubspotNote(env, null,
          `💡 Agent idea from an unmatched number ${from}:\n\n${text}`);
      }
      log(env, { at: "sms.idea", from, name, chars: text.length, logged: true });
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
        brief: p.eo_research_brief || "",
        demoConsent: p.eo_demo_consent === "true",
      });
    } catch (e) {
      log(env, { at: "payload1.claim", contactId: c.id, error: String(e) });
    }
  }

  // Backfill briefs that never landed at capture time. This is the reliable
  // place to do the research: a scheduled handler gets minutes of wall clock,
  // where waitUntil() got killed mid-call. Runs all of them concurrently, so
  // the whole backfill costs about one call's latency, not N of them.
  const missing = claimed.filter((c) => !c.brief);
  if (missing.length) {
    log(env, { at: "payload1.backfill", count: missing.length });
    await Promise.all(missing.map((c) =>
      researchBrief(env, c.company, c.email)
        .then(async (b) => {
          c.brief = b;
          await patchContact(env, c.id, { eo_research_brief: b });
          log(env, { at: "payload1.backfill", contactId: c.id, chars: b.length });
        })
        .catch((e) => {
          c.brief = genericBrief(c.company);
          log(env, { at: "payload1.backfill", contactId: c.id, error: String(e) });
        })
    ));
  }
  // Anything still empty (research threw and the catch above missed it)
  claimed.forEach((c) => { if (!c.brief) c.brief = genericBrief(c.company); });

  // EMAIL FIRST, THEN THE TEXTS. The texts exist to point at the email —
  // "Full notes in your email", "Seriously, check your email". Sending them
  // first means the first two land while the inbox is still empty, so the
  // one instruction the message gives cannot be followed. Send the thing,
  // then point at it.
  await Promise.all(claimed.map((c) =>
    sendEmail(env, {
      to: c.email,
      subject: `I did some homework on ${c.company || "your company"}`,
      html: briefEmailHtml(c.brief),
    }).catch((e) => log(env, { at: "payload1.email", contactId: c.id, error: String(e) }))
  ));

  // Then the three texts, ~30s apart. Sleeping is wall clock, not CPU, so
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
}

// Instant-path variant: one contact, same copy, same stagger.
async function sendPayload1(env, c) {
  await patchContact(env, c.id, { eo_payload1_sent: new Date().toISOString() });
  // EMAIL FIRST, THEN THE TEXTS. The texts exist to point at the email —
  // "Full notes in your email", "Seriously, check your email". Sending them
  // first means the first two land while the inbox is still empty, so the
  // one instruction the message gives cannot be followed. Send the thing,
  // then point at it.
  await sendEmail(env, {
    to: c.email,
    subject: `I did some homework on ${c.company || "your company"}`,
    html: briefEmailHtml(c.brief),
  });
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

// Build kit — 7:05 PM PT, as the build block starts. Everyone gets it,
// consent or not: it is email, and it is the thing they actually came for.
// KV holds the sent-flag rather than a HubSpot property, because these two
// sends were added on the night and a KV key needs no schema change.
async function runBuildKit(env) {
  const contacts = await listTagged(env,
    ["firstname", "lastname", "email", "eo_company_name", "eo_research_brief"]);
  log(env, { at: "buildkit", found: contacts.length });

  await Promise.all(contacts.map(async (c) => {
    const flag = `sent:buildkit:${c.id}`;
    if (await env.PHOTOS.get(flag)) return;
    await env.PHOTOS.put(flag, new Date().toISOString());
    try {
      const pr = c.properties;
      await sendEmail(env, {
        to: pr.email,
        subject: "Your build kit — two pastes and you have an employee",
        html: buildKitHtml({
          firstname: pr.firstname, lastname: pr.lastname, email: pr.email,
          company: pr.eo_company_name, brief: pr.eo_research_brief,
        }),
      });
      log(env, { at: "buildkit", contactId: c.id, sent: true, personalised: !!pr.eo_research_brief });
    } catch (e) {
      log(env, { at: "buildkit", contactId: c.id, error: String(e) });
    }
  }));
}

// 7:30 PM PT — one encouraging text, mid-build. Gated on demo consent like
// every other non-photo SMS.
async function runPositiveText(env) {
  const contacts = await listTagged(env, ["firstname", "phone", "eo_demo_consent"]);
  log(env, { at: "positive", found: contacts.length });

  await Promise.all(contacts.map(async (c) => {
    const flag = `sent:positive:${c.id}`;
    if (await env.PHOTOS.get(flag)) return;
    await env.PHOTOS.put(flag, new Date().toISOString());
    await sendSms(env, {
      to: normalizePhone(c.properties.phone),
      body: POSITIVE_TEXT,
      contactId: c.id,
      payload: "positive",
      requireConsent: c.properties.eo_demo_consent !== "true",
    }).catch((e) => log(env, { at: "positive", contactId: c.id, error: String(e) }));
  }));
}

// ─────────────────────────────────────────────────────────── Claude

// Free-mail domains tell you nothing about the business, so they are never
// used as the research subject.
const FREEMAIL = new Set([
  "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "hotmail.com",
  "outlook.com", "live.com", "msn.com", "icloud.com", "me.com", "mac.com",
  "aol.com", "protonmail.com", "proton.me", "gmx.com", "zoho.com",
  "comcast.net", "sbcglobal.net", "att.net", "verizon.net",
]);

function researchSubject(company, email) {
  const name = (company || "").trim();
  const domain = String(email || "").split("@")[1]?.trim().toLowerCase() || "";
  const useful = domain && !FREEMAIL.has(domain);

  if (useful && name) return `Email domain: ${domain}\nCompany name they typed: ${name}`;
  if (useful) return `Email domain: ${domain}\n(They did not give a company name.)`;
  if (name) return `Company name they typed: ${name}\n(Their email is on a free provider, so there is no company domain to work from — the typed name is all you have, and it may be misspelled.)`;
  return "";
}

async function researchBrief(env, company, email) {
  const subject = researchSubject(company, email);
  if (!subject) throw new Error("no company or domain");
  const name = (company || "").trim();

  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": env.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: CLAUDE_MODEL,
      max_tokens: CLAUDE_MAX_TOKENS,
      system: RESEARCH_SYSTEM,
      // Dynamic filtering is built into this tool version — do NOT also
      // declare code_execution; a second execution environment confuses
      // the model.
      // max_uses is load-bearing, not tuning. Uncapped, the model ran 12-16
      // searches and the call took 90 SECONDS — measured against the
      // deployed Worker. Cloudflare kills waitUntil() background work long
      // before that, so every brief was silently lost: four captures, zero
      // briefs stored. Capped at 5 the call lands in ~25-35s, which fits.
      tools: [{ type: "web_search_20260209", name: "web_search", max_uses: 5 }],
      messages: [{
        role: "user",
        content: `${subject}\n\nResearch them and write the brief.`,
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
        // max_uses is load-bearing, not tuning. Uncapped, the model ran 12-16
      // searches and the call took 90 SECONDS — measured against the
      // deployed Worker. Cloudflare kills waitUntil() background work long
      // before that, so every brief was silently lost: four captures, zero
      // briefs stored. Capped at 5 the call lands in ~25-35s, which fits.
      tools: [{ type: "web_search_20260209", name: "web_search", max_uses: 5 }],
        messages: [
          { role: "user", content: `${subject}\n\nResearch them and write the brief.` },
          { role: "assistant", content: data.content },
        ],
      }),
    });
    if (!resumed.ok) throw new Error(`Anthropic resume ${resumed.status}`);
    const rdata = await resumed.json();
    const rtext = cleanBody(extractText(rdata));
    if (rtext) return polish(env, rtext);
  }

  const text = cleanBody(extractText(data));
  if (!text) throw new Error("empty brief");
  return polish(env, text);
}

// The search call narrates. Across four test runs it produced three
// different preamble shapes — "Here is the brief for your email:",
// "I've now done five searches...", "I now have enough solid, accurate
// information to write the brief. Here's what I know: ..." — and each new
// regex only caught the shape that had already burned us. One in three
// briefs was arriving with the model's working notes stapled to the front.
//
// So: a second pass with NO tools, which has nothing to narrate about. It
// only ever deletes; the wording that reaches the attendee is still the
// wording the research call wrote. Costs one cheap call and a few seconds,
// and this runs in waitUntil() where seconds are free.
//
// If it fails, fall back to the regex-cleaned text — degraded, not broken.
async function polish(env, raw) {
  const system = `You are given the raw output of an AI assistant that was asked to research a company, write a short brief for an email, and then list five AI agents that company could build.

Return ONLY the deliverable itself, word for word as written. The deliverable is the brief AND the "Five agents you could build tonight:" section with its five numbered items — both are part of it. Keep the numbered list intact and keep that heading line exactly as written.

Remove anything that is not the brief: opening commentary about the research process ("I've now done five searches", "I now have enough information"), announcements of what is coming ("Here is the brief:", "Here's what I know:"), summaries of findings written as notes to self, horizontal rules, headers, and any closing remark addressed to whoever asked.

If a sentence or paragraph appears twice — a draft opening followed by the real one — keep only the version inside the final brief.

Do not rewrite, reword, shorten, expand, correct, or reorder anything you keep. You are deleting, not editing. If the entire input is already clean, return it unchanged.`;

  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": env.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: CLAUDE_MODEL,
      max_tokens: CLAUDE_MAX_TOKENS,
      system,
      messages: [{ role: "user", content: raw }],
    }),
  });
  if (!res.ok) {
    log(env, { at: "polish", error: `Anthropic ${res.status}` });
    return raw;
  }
  const data = await res.json();
  if (data.stop_reason === "refusal") return raw;

  const out = cleanBody(extractText(data));
  // Guard against the polish call eating the brief or "helpfully" rewriting
  // it into something much shorter — if it looks wrong, keep the original.
  if (!out || out.length < 120 || out.length > raw.length + 40) {
    log(env, { at: "polish", kept_raw: true, rawLen: raw.length, outLen: out.length });
    return raw;
  }
  return out;
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
      max_tokens: CLAUDE_MAX_TOKENS,
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
  const text = cleanBody(extractText(data));
  if (!text) throw new Error("empty email");
  return polish(env, text);
}

// Response content interleaves text with server_tool_use and
// web_search_tool_result blocks. The model narrates BETWEEN searches, so
// joining every text block glues its research notes onto the front of the
// answer — observed in testing: a 470-word Sugarfish "brief" that was mostly
// raw search snippets. The real answer is the text after the LAST tool
// block. Falls back to all text if the model never searched.
function extractText(data) {
  const blocks = data.content || [];
  let lastTool = -1;
  blocks.forEach((b, i) => { if (b.type !== "text") lastTool = i; });

  // Join with "" not "\n": with citations enabled the final answer is split
  // into one text block per cited span, mid-sentence. Joining with newlines
  // put hard <br> breaks in the middle of sentences in the email.
  const tail = blocks.slice(lastTool + 1)
    .filter((b) => b.type === "text").map((b) => b.text).join("").trim();
  if (tail) return tail;

  return blocks.filter((b) => b.type === "text").map((b) => b.text).join("").trim();
}

// Belt and braces on top of the "no preamble" instruction and the
// last-tool-block rule above. Both of these were observed in testing and
// both would have landed in an email body in front of a room:
//   "Here is the brief for your email:" + a --- rule    (A+ Tutoring)
//   "I was unable to find ... here is an honest brief:" (unknown company)
// The announcement is not always at the start of the string, so cut at the
// LAST one rather than anchoring to ^.
function cleanBody(text) {
  let t = String(text || "").trim();

  // "...here is the brief:" / "here's an honest brief:" — keep what follows
  // the last such announcement, but only if real content follows it.
  const announce = /\bhere(?:'s| is)\b[^\n]{0,100}?:[ \t]*\n/gi;
  let cut = 0, m;
  while ((m = announce.exec(t)) !== null) cut = m.index + m[0].length;
  if (cut && t.slice(cut).trim().length > 80) t = t.slice(cut);

  // Meta-narration with no "here is" marker. Both of these were observed:
  //   "I've now done five searches ... I'll write an honest brief."
  //   "Now I have plenty of rich detail to write a great brief. Let me compose it."
  // The tell is first-person process talk ABOUT the task paired with a
  // composition verb. An honest brief opening "I was unable to find any
  // public record of X" is also first person but has no composition verb,
  // so it survives — that one is real content.
  const paras = t.split(/\n\s*\n/);
  if (paras.length > 1
      && /\b(?:I(?:'ve|'ll|'m| have| will| am)|let me|now i)\b/i.test(paras[0])
      && /\b(?:compose|write|writing|draft|put together|search(?:es|ed|ing)?|per the rules)\b/i.test(paras[0])
      && paras[0].length < 400
      && paras.slice(1).join("\n\n").trim().length > 80) {
    t = paras.slice(1).join("\n\n");
  }

  // Collapse runaway blank lines the block-joining can leave behind
  t = t.replace(/\n{3,}/g, "\n\n").replace(/[ \t]+\n/g, "\n");

  // Horizontal rules the model likes to fence the body with
  t = t.replace(/^\s*(?:-{3,}|\*{3,}|_{3,})\s*\n+/, "");
  t = t.replace(/\n+\s*(?:-{3,}|\*{3,}|_{3,})\s*$/, "");
  // Stray markdown heading marks — the email template is HTML
  t = t.replace(/^#{1,6}\s+/gm, "");
  return t.trim();
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
// One POST per file, flat fields. Zapier's Catch Hook maps flat keys
// straight onto a "Upload File" step (File = the url field, File Name =
// filename); a nested array would need a code step in between.
async function uploadToDrive(env, { lastName, firstName, photoUrl, heroUrl }) {
  if (!env.DRIVE_UPLOAD_HOOK) {
    log(env, { at: "drive", skipped: "DRIVE_UPLOAD_HOOK unset" });
    return;
  }
  const slug = (s) => String(s || "guest").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const base = `${slug(lastName)}-${slug(firstName)}`;

  const files = [];
  if (photoUrl) files.push({ kind: "photo", filename: `${base}-photo.jpg`, url: photoUrl });
  if (heroUrl) files.push({ kind: "hero", filename: `${base}-hero.jpg`, url: heroUrl });
  if (!files.length) return;

  for (const f of files) {
    const body = {
      filename: f.filename,
      url: f.url,
      kind: f.kind,
      first_name: firstName || "",
      last_name: lastName || "",
      folder_id: env.DRIVE_FOLDER_ID || "",
      event: "EO LA Valley 2026-08-20",
    };
    if (env.MODE !== "send") {
      log(env, { at: "drive", dry_run: true, ...body });
      continue;
    }
    const res = await fetch(env.DRIVE_UPLOAD_HOOK, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`Drive hook ${res.status} for ${f.filename}`);
    log(env, { at: "drive", sent: f.filename, kind: f.kind });
  }
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
      properties: ["email", "aplus_event_tag"],
      limit: 1,
    }),
  });
  if (!search.ok) throw new Error(`HubSpot search ${search.status}: ${await search.text()}`);
  const found = await search.json();

  if (found.total > 0) {
    const hit = found.results[0];
    const id = hit.id;

    // aplus_event_tag is a MULTI-checkbox, and HubSpot replaces the whole set
    // when you write it. Writing the EO tag bare therefore wipes any other
    // event the contact has attended — a Sage Oak attendee who walks up
    // tonight would silently lose sage_oak_btsc_2026. Merge instead: read
    // what is there, add ours if missing, write the full semicolon-joined
    // list back.
    const existing = String(hit.properties?.aplus_event_tag || "")
      .split(";").map((t) => t.trim()).filter(Boolean);
    const merged = existing.includes(EVENT_TAG) ? existing : [...existing, EVENT_TAG];

    const upd = await fetch(`https://api.hubapi.com/crm/v3/objects/contacts/${id}`, {
      method: "PATCH",
      headers: hsHeaders(env),
      body: JSON.stringify({
        properties: { ...properties, aplus_event_tag: merged.join(";") },
      }),
    });
    if (!upd.ok) throw new Error(`HubSpot update ${upd.status}: ${await upd.text()}`);
    return { action: "updated", id, tags: merged.join(";") };
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

// A note, optionally associated to a contact. An idea from a number we
// cannot match still gets recorded rather than dropped — an unmatched text
// is usually a typo'd phone at the booth, not a stranger.
async function hubspotNote(env, contactId, body) {
  const payload = {
    properties: { hs_timestamp: new Date().toISOString(), hs_note_body: body },
  };
  if (contactId) {
    payload.associations = [{
      to: { id: contactId },
      types: [{ associationCategory: "HUBSPOT_DEFINED", associationTypeId: 202 }],
    }];
  }
  const res = await fetch("https://api.hubapi.com/crm/v3/objects/notes", {
    method: "POST", headers: hsHeaders(env), body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`HubSpot note ${res.status}: ${await res.text()}`);
}

async function searchByEmail(env, email) {
  const res = await fetch("https://api.hubapi.com/crm/v3/objects/contacts/search", {
    method: "POST",
    headers: hsHeaders(env),
    body: JSON.stringify({
      filterGroups: [{ filters: [{ propertyName: "email", operator: "EQ", value: email }] }],
      properties: ["email"],
      limit: 1,
    }),
  });
  if (!res.ok) throw new Error(`HubSpot email search ${res.status}`);
  const data = await res.json();
  return data.total > 0 ? data.results[0] : null;
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

async function sendEmail(env, { to, subject, html, attachments, bcc }) {
  if (env.MODE !== "send") {
    log(env, { at: "email", to, subject, dry_run: true, attached: !!attachments, bcc: bcc || null });
    return { dry_run: true };
  }
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: env.RESEND_FROM, to: [to], subject, html,
      ...(attachments?.length ? { attachments } : {}),
      ...(bcc ? { bcc: [bcc] } : {}),
    }),
  });
  if (!res.ok) throw new Error(`Resend ${res.status}: ${await res.text()}`);
  log(env, { at: "email", to, subject, sent: true });
  return { sent: true };
}

// ───────────────────────────────────────────────────────── templates
//
// Light card on a warm grey page, near-black body copy, EO indigo for the
// one accent. The first cut was light-grey-on-navy and read like a terminal.
// Email clients are unforgiving: everything is inline styles, no external
// CSS, no flexbox, and every colour is stated explicitly so a dark-mode
// client cannot invert half of it into mush.

const MAIL = {
  page: "#EFEEEA",     // warm grey behind the card
  card: "#FFFFFF",
  head: "#18181B",     // headings — near black
  body: "#3F3F46",     // body copy — dark enough to read on a phone outdoors
  accent: "#3B3E8F",   // EO indigo, taken from the logo
  muted: "#A1A1AA",
  rule: "#E4E4E7",
  codeBg: "#FAFAFA",
  codeText: "#27272A",
};

const LOGO_URL = "https://eo-booth.pages.dev/eo-logo.png?v=1";

const FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif";

const pStyle = `style="font-family:${FONT};font-size:16px;line-height:1.65;color:${MAIL.body};margin:0 0 18px;"`;

function shell(inner) {
  return `<div style="background:${MAIL.page};padding:28px 16px;font-family:${FONT};">
  <div style="max-width:560px;margin:0 auto;background:${MAIL.card};border-radius:14px;padding:36px 32px;">
    <img src="${LOGO_URL}" alt="EO Los Angeles Valley" width="150"
         style="display:block;width:150px;height:auto;margin:0 0 6px;">
    <p style="font-family:${FONT};font-size:11px;letter-spacing:1.6px;text-transform:uppercase;color:${MAIL.muted};font-weight:700;margin:0 0 24px;">Build Your First AI Agent &middot; August 20, 2026</p>
    <div style="border-top:1px solid ${MAIL.rule};padding-top:26px;">
      ${inner}
    </div>
    <p style="font-family:${FONT};font-size:12px;line-height:1.5;color:${MAIL.muted};margin:30px 0 0;border-top:1px solid ${MAIL.rule};padding-top:18px;">
      You met me at the photo booth on August 20, 2026.
    </p>
  </div>
</div>`;
}

function h1(text) {
  return `<h1 style="font-family:${FONT};font-size:22px;line-height:1.3;font-weight:700;color:${MAIL.head};margin:0 0 16px;">${text}</h1>`;
}

function eyebrow(text) {
  return `<p style="font-family:${FONT};font-size:13px;letter-spacing:0.6px;text-transform:uppercase;color:${MAIL.accent};font-weight:700;margin:28px 0 12px;">${text}</p>`;
}

function sig(note) {
  return `<p style="font-family:${FONT};font-size:15px;line-height:1.6;color:${MAIL.accent};font-weight:600;margin:26px 0 0;">— Minion #23 🤖${
    note ? ` <span style="color:${MAIL.muted};font-weight:400;">${note}</span>` : ""}</p>`;
}

// The photo rides as an ATTACHMENT, the way the Sage Oak booth does it —
// that one demonstrably lands. A single large remote <img> from a brand-new
// sending address is a textbook promotional signature, and this email never
// reached Roman's inbox while two plain test sends from the same address
// did. An attachment also means they keep the photo offline, which is what
// someone actually wants from a photo booth.
function photoEmailHtml(firstName) {
  return shell(`
  ${h1(`Thanks for coming tonight, ${escapeHtml(firstName || "friend")}.`)}
  <p ${pStyle}>Your photo from the EO LA Valley learning event is attached.</p>
  <p ${pStyle}>That's the easy part. I'm working on something else for you — give me a few minutes.</p>
  ${sig()}`);
}

function briefEmailHtml(bodyText) {
  const paras = String(bodyText).split(/\n\s*\n/).map((block) => {
    const lines = block.trim().split("\n").map((l) => l.trim()).filter(Boolean);
    const numbered = lines.filter((l) => /^\d+\.\s/.test(l));

    // "Five agents you could build tonight:" + its items. Rendered as a real
    // list — as running paragraphs the numbers collide on a phone and the
    // most useful part of the email turns into a wall.
    if (numbered.length >= 2) {
      const heading = lines.filter((l) => !/^\d+\.\s/.test(l));
      const items = numbered.map((l) => {
        const t = escapeHtml(l.replace(/^\d+\.\s*/, ""));
        const named = t.replace(/^([^—]{2,60})—/,
          `<strong style="color:${MAIL.head};">$1</strong>—`);
        return `<li style="font-family:${FONT};font-size:15px;line-height:1.6;color:${MAIL.body};margin:0 0 12px;padding-left:4px;">${named}</li>`;
      }).join("");
      return (heading.length ? eyebrow(escapeHtml(heading.join(" "))) : "") +
        `<ol style="margin:0 0 18px;padding-left:20px;">${items}</ol>`;
    }
    return `<p ${pStyle}>${escapeHtml(block.trim()).replace(/\n/g, "<br>")}</p>`;
  }).join("");

  return shell(`
  <p style="font-family:${FONT};font-size:15px;line-height:1.6;color:${MAIL.muted};margin:0 0 20px;font-style:italic;">You took a photo 20 minutes ago. I've been busy since.</p>
  ${paras}
  ${sig("(I'm not done yet.)")}`);
}

// Roman's prompt is verbatim below the CONTEXT block. We already researched
// this person's company for the 6:17 email, so making them re-explain it to
// a cold Claude chat wastes the best asset we have. The block states what is
// already known and tells Claude not to ask for it again — so the interview
// opens on the agent itself rather than on "what does your company do".
//
// Falls back to the plain prompt when there is no brief yet: a generic paste
// still works, it is just slower for them.
function buildKitPrompt(c) {
  const name = [c?.firstname, c?.lastname].filter(Boolean).join(" ").trim();
  const email = c?.email || "";
  const company = c?.company || "";
  const domain = email.split("@")[1] || "";
  const brief = (c?.brief || "").trim();

  if (!name && !email && !brief) return BUILD_KIT_PROMPT;

  const known = [
    name ? `My name: ${name}` : null,
    email ? `My email: ${email}` : null,
    company ? `My company: ${company}${domain ? ` (${domain})` : ""}` : null,
  ].filter(Boolean).join("\n");

  return `CONTEXT — you already know all of this about me. Do not ask me for any of it again.

${known}
${brief ? `
Earlier tonight another agent researched my company and wrote this. Treat it as background you already have — do not read it back to me:

${brief}
` : ""}
Because you already have my name, email and company, the only things you still need from me are the agent name and the schedule. Start by asking what I want the agent to DO.

---

${BUILD_KIT_PROMPT}`;
}

function buildKitHtml(c) {
  return shell(`
  ${h1("You're about to hire your first agent.")}
  <p ${pStyle}>Two pastes. That's it.</p>

  ${eyebrow("Step 1 — open a NEW Claude chat, paste this")}
  <pre style="background:${MAIL.codeBg};border:1px solid ${MAIL.rule};border-radius:8px;padding:16px;margin:0 0 22px;overflow-x:auto;white-space:pre-wrap;word-break:break-word;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px;line-height:1.5;color:${MAIL.codeText};-webkit-user-select:all;user-select:all;">${escapeHtml(buildKitPrompt(c))}</pre>

  ${eyebrow("Step 2 — open Claude Code")}
  <p ${pStyle}>Paste the HANDOFF.md it gave you. Watch it work.</p>

  <p ${pStyle}>Stuck? Raise a hand. Or text your agent name + RAFT to <strong style="color:${MAIL.head};">${BOOTH_NUMBER_HUMAN}</strong> and Minion #23 will file it for you.</p>
  <p ${pStyle}>Your agent's first shift lands in this inbox tomorrow at 7 AM.</p>
  ${sig()}`);
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
