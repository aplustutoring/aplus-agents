/**
 * A+ Tutoring Feedback Agent relay — Google Apps Script
 *
 * The doorbell. Slack Events API -> repository_dispatch. Deployed as a Web
 * App (Execute as: me · Access: anyone) whose URL is the Slack app's Event
 * Subscriptions Request URL. Every message event in #agent-feedback is
 * forwarded to GitHub Actions as a `feedback-report` dispatch; ALL logic
 * (classify, ack, correction PR, demote) lives in git — this script only
 * rings the bell. Same pattern as the spotlight Drive watcher
 * (marketing/scripts/watcher/apps-script.gs).
 *
 * Forwarded events (filtering the rest here keeps Actions minutes flat):
 *   - top-level channel messages (new reports)
 *   - thread replies (the agent ignores all except answers to its own
 *     clarifying questions — it tracks which threads it started)
 * Dropped here: bot messages (incl. the fleet bot itself), edits/deletes/
 * joins (subtype present), and anything outside CHANNEL_ID.
 *
 * NOTE: #agent-feedback is a PRIVATE channel, so the Slack app must
 * subscribe to the bot event `message.groups` (private-channel messages),
 * not just `message.channels` — and the bot must be a member (/invite).
 *
 * Configuration lives in Script Properties (Project Settings ->
 * Script Properties), not hardcoded:
 *
 *   CHANNEL_ID           — the #agent-feedback channel ID (C…)
 *   GITHUB_REPO          — "owner/repo", e.g. "aplustutoring/aplus-agents"
 *   GITHUB_TOKEN         — fine-grained PAT with "Contents: read & write"
 *                          (repository_dispatch rides the contents scope)
 *   SLACK_VERIFICATION_TOKEN — from the Slack app's Basic Information page.
 *                          Apps Script can't read request headers, so Slack's
 *                          signing-secret scheme is unavailable; the legacy
 *                          verification token is the best available check.
 *
 * Slack retries (it retries any response slower than 3s) are deduped by the
 * agent via event_id — this script forwards them without caring.
 *
 * Deployment: see ../README.md ("Wiring the doorbell").
 */

const DISPATCH_EVENT_TYPE = 'feedback-report';

function doPost(e) {
  let body;
  try {
    body = JSON.parse(e.postData.contents);
  } catch (err) {
    return textOut_('bad request');
  }

  // One-time URL verification handshake when the Request URL is saved.
  if (body.type === 'url_verification') {
    return textOut_(body.challenge);
  }

  const props = PropertiesService.getScriptProperties();
  const expectedToken = props.getProperty('SLACK_VERIFICATION_TOKEN');
  if (expectedToken && body.token !== expectedToken) {
    Logger.log('verification token mismatch — dropping event');
    return textOut_('ok');
  }

  if (body.type !== 'event_callback') return textOut_('ok');
  const ev = body.event || {};

  // Only human messages in the feedback channel ring the bell.
  if (ev.type !== 'message') return textOut_('ok');
  if (ev.subtype) return textOut_('ok');            // edits, deletes, joins, bot_message
  if (ev.bot_id) return textOut_('ok');             // @Fleet must not hear itself
  if (ev.channel !== props.getProperty('CHANNEL_ID')) return textOut_('ok');
  if (!ev.text || !ev.user) return textOut_('ok');

  dispatch_(props, {
    channel: ev.channel,
    user: ev.user,
    text: ev.text,
    ts: ev.ts,
    thread_ts: ev.thread_ts || '',
    event_id: body.event_id || '',
    event_time: body.event_time || 0,
  });
  return textOut_('ok');
}

function dispatch_(props, clientPayload) {
  const repo = props.getProperty('GITHUB_REPO');
  const token = props.getProperty('GITHUB_TOKEN');
  if (!repo || !token) {
    Logger.log('GITHUB_REPO / GITHUB_TOKEN not configured — dropping event');
    return;
  }
  const resp = UrlFetchApp.fetch(`https://api.github.com/repos/${repo}/dispatches`, {
    method: 'post',
    contentType: 'application/json',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
    },
    payload: JSON.stringify({
      event_type: DISPATCH_EVENT_TYPE,
      client_payload: clientPayload,
    }),
    muteHttpExceptions: true,
  });
  const code = resp.getResponseCode();
  if (code >= 300) {
    Logger.log(`repository_dispatch failed (${code}): ${resp.getContentText()}`);
  }
}

function textOut_(s) {
  return ContentService.createTextOutput(s).setMimeType(ContentService.MimeType.TEXT);
}
