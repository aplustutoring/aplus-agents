/**
 * A+ Tutoring Spotlight Watcher — Google Apps Script
 *
 * Polls the Drive intake folder where Paola drops case-study source
 * material. For each subfolder that:
 *   (a) has the three required source files (parent-call*, lesson-notes
 *       /report*, paola-brief*), and
 *   (b) has not yet been dispatched (no `.spotlight-dispatched` sentinel),
 * fires the GitHub Actions workflow via the repository_dispatch API and
 * drops the sentinel so the same folder doesn't get re-dispatched on
 * the next poll.
 *
 * Trigger: time-driven, every 5 minutes (configure in the Apps Script
 * Triggers UI after deploying).
 *
 * Configuration lives in Script Properties (Project Settings ->
 * Script Properties), not hardcoded — so the same script can be redeployed
 * against a different intake folder, GitHub repo, or PAT without code
 * edits:
 *
 *   PIPELINE_ROOT_ID         — the Drive folder ID Paola drops into
 *   GITHUB_REPO              — full "owner/repo" string, e.g. "aplustutoring/aplus-marketing-skills"
 *   GITHUB_TOKEN             — fine-grained PAT with "Actions: write" permission
 *   SLACK_WEBHOOK_URL        — Slack incoming webhook for notifications (optional)
 *   PAOLA_SLACK_USER_ID      — Paola's Slack user ID for mentions (optional)
 *
 * Deployment: see scripts/watcher/README.md.
 */

const SENTINEL_NAME = '.spotlight-dispatched';
const INCOMPLETE_SENTINEL_NAME = '.spotlight-incomplete';
const DISPATCH_EVENT_TYPE = 'spotlight-folder-dropped';

/** Required-file matchers, mirrored from the orchestrator's source classifier.
 *  The watcher should fire only when a transcript/call and a lesson file are present.
 *  A Paola brief is preferred but optional for dispatch. */
const TRANSCRIPT_PATTERN = /\b(transcription|transcript|call)\b/i;
const LESSON_PATTERN = /\blesson\b/i;
const BRIEF_PATTERN = /\b(survey|brief|handoff|spotlight)\b/i;


/** Main entry point. Wire a 5-minute time trigger to this function. */
function pollIntakeFolder() {
  const props = PropertiesService.getScriptProperties();
  const config = readConfig_(props);
  if (!config) return;  // readConfig_ already logged the missing keys

  const intake = DriveApp.getFolderById(config.intakeFolderId);
  const subfolders = intake.getFolders();

  let dispatched = 0;
  let skipped = 0;
  let errors = [];

  while (subfolders.hasNext()) {
    const folder = subfolders.next();
    const result = processFolder_(folder, config);
    if (result.status === 'dispatched') dispatched++;
    else if (result.status === 'error') errors.push(result);
    else skipped++;
  }

  Logger.log(
    `Poll complete: ${dispatched} dispatched, ${skipped} skipped, ` +
    `${errors.length} errored.`
  );
  if (errors.length && config.errorNotifyEmail) {
    notifyErrors_(config.errorNotifyEmail, errors);
  }
}


function processFolder_(folder, config) {
  const name = folder.getName();

  if (hasSentinel_(folder)) {
    return { status: 'skipped', reason: 'already dispatched', name };
  }

  const missing = missingRequiredFiles_(folder);
  if (missing.length > 0) {
    if (!hasIncompleteSentinel_(folder)) {
      Logger.log(`INCOMPLETE: ${name} — missing ${missing.join(', ')}`);
      notifyIncompleteFolder_(folder, missing, config);
      dropIncompleteSentinel_(folder, missing);
    } else {
      Logger.log(`SKIP: ${name} — still missing ${missing.join(', ')}`);
    }
    return { status: 'skipped', reason: 'incomplete', name, missing };
  }

  Logger.log(`DISPATCH: ${name} (id=${folder.getId()})`);
  try {
    dispatchWorkflow_(folder.getId(), name, config);
    removeIncompleteSentinel_(folder);
    dropSentinel_(folder, /*payload=*/ {
      dispatched_at: new Date().toISOString(),
      folder_name: name,
      github_repo: config.githubRepo,
    });
    return { status: 'dispatched', name };
  } catch (exc) {
    Logger.log(`ERROR dispatching ${name}: ${exc}`);
    return { status: 'error', name, error: String(exc) };
  }
}


function hasSentinel_(folder) {
  const it = folder.getFilesByName(SENTINEL_NAME);
  return it.hasNext();
}


function dropSentinel_(folder, payload) {
  // Sentinel content is just human-readable JSON so anyone clicking
  // through can see when and why the folder got dispatched.
  folder.createFile(
    SENTINEL_NAME,
    JSON.stringify(payload, null, 2),
    MimeType.PLAIN_TEXT,
  );
}

function hasIncompleteSentinel_(folder) {
  return folder.getFilesByName(INCOMPLETE_SENTINEL_NAME).hasNext();
}

function dropIncompleteSentinel_(folder, missing) {
  folder.createFile(
    INCOMPLETE_SENTINEL_NAME,
    JSON.stringify(
      {
        created_at: new Date().toISOString(),
        missing_required_files: missing,
      },
      null,
      2,
    ),
    MimeType.PLAIN_TEXT,
  );
}

function removeIncompleteSentinel_(folder) {
  const sentinels = folder.getFilesByName(INCOMPLETE_SENTINEL_NAME);
  while (sentinels.hasNext()) {
    sentinels.next().setTrashed(true);
  }
}


function missingRequiredFiles_(folder) {
  let hasTranscript = false;
  let hasLesson = false;
  let hasBrief = false;
  const files = folder.getFiles();
  while (files.hasNext()) {
    const name = files.next().getName();
    if (TRANSCRIPT_PATTERN.test(name)) hasTranscript = true;
    if (LESSON_PATTERN.test(name)) hasLesson = true;
    if (BRIEF_PATTERN.test(name)) hasBrief = true;
  }

  const missing = [];
  if (!hasTranscript) missing.push('transcript/call file');
  if (!hasLesson) missing.push('lesson file');
  if (!hasBrief) Logger.log(
    `NOTE: ${folder.getName()} has no brief-like source file; proceeding because briefs are optional.`
  );
  return missing;
}


function dispatchWorkflow_(folderId, folderName, config) {
  const url = `https://api.github.com/repos/${config.githubRepo}/dispatches`;
  const payload = {
    event_type: DISPATCH_EVENT_TYPE,
    client_payload: {
      drive_folder_id: folderId,
      folder_name: folderName,
      dispatched_at: new Date().toISOString(),
    },
  };
  const response = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    headers: {
      Authorization: `Bearer ${config.githubToken}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
  });
  const code = response.getResponseCode();
  if (code !== 204) {
    throw new Error(
      `GitHub dispatch returned HTTP ${code}: ${response.getContentText()}`,
    );
  }
}


function readConfig_(props) {
  const required = [
    'PIPELINE_ROOT_ID',
    'GITHUB_REPO',
    'GITHUB_TOKEN',
  ];
  const missing = required.filter((k) => !props.getProperty(k));
  if (missing.length) {
    Logger.log(
      `ERROR: missing Script Properties: ${missing.join(', ')}. ` +
      `Set them in Project Settings > Script properties.`,
    );
    return null;
  }
  return {
    intakeFolderId: props.getProperty('PIPELINE_ROOT_ID'),
    githubRepo: props.getProperty('GITHUB_REPO'),
    githubToken: props.getProperty('GITHUB_TOKEN'),
    errorNotifyEmail: props.getProperty('ERROR_NOTIFY_EMAIL') || '',
    slackWebhookUrl: props.getProperty('SLACK_WEBHOOK_URL') || '',
    paolaSlackUserId: props.getProperty('PAOLA_SLACK_USER_ID') || '',
  };
}


/* -------------------------------------------------------------------------
 * One-shot helpers for setup + manual ops (run from the Apps Script editor)
 * ------------------------------------------------------------------------- */

/** Print whether every Script Property is set. Run after deploying. */
function checkConfig() {
  const required = ['PIPELINE_ROOT_ID', 'GITHUB_REPO', 'GITHUB_TOKEN'];
  const optional = ['ERROR_NOTIFY_EMAIL', 'SLACK_WEBHOOK_URL', 'PAOLA_SLACK_USER_ID'];
  const props = PropertiesService.getScriptProperties();
  required.forEach((k) => {
    const v = props.getProperty(k);
    Logger.log(`${k}: ${v ? 'set (' + String(v).length + ' chars)' : 'MISSING'}`);
  });
  optional.forEach((k) => {
    const v = props.getProperty(k);
    Logger.log(`${k}: ${v ? v : '(unset, optional)'}`);
  });
}


/** List subfolders of the intake area + their dispatch state. Dry-run. */
function listIntakeFolders() {
  const props = PropertiesService.getScriptProperties();
  const config = readConfig_(props);
  if (!config) return;
  const intake = DriveApp.getFolderById(config.intakeFolderId);
  Logger.log(`Intake: ${intake.getName()} (${intake.getId()})`);
  const it = intake.getFolders();
  while (it.hasNext()) {
    const f = it.next();
    const missing = missingRequiredFiles_(f);
    const state = hasSentinel_(f)
      ? 'DISPATCHED'
      : missing.length
        ? `INCOMPLETE (missing ${missing.join(', ')})`
        : 'READY';
    Logger.log(`  - ${f.getName()} (${f.getId()}) — ${state}`);
  }
}


/** Manual reset: remove the sentinel from one folder so the next
 *  poll re-dispatches it. Useful after fixing a bad run.
 *
 *  Usage: edit FOLDER_NAME below, save, and run resetSentinel from
 *  the Apps Script editor. */
function notifyErrors_(email, errors) {
  const subject = `Spotlight watcher failure: ${errors.length} folder(s) could not be dispatched`;
  const body = errors
    .map((error) => `- ${error.name}: ${error.error}`)
    .join('\n');
  MailApp.sendEmail(email, subject, body);
}

function notifyIncompleteFolder_(folder, missing, config) {
  const name = folder.getName();
  const subject = `Spotlight watcher: folder ${name} missing required files`;
  const body = `Folder ${name} is missing required files: ${missing.join(', ')}.`;
  if (config.errorNotifyEmail) {
    MailApp.sendEmail(config.errorNotifyEmail, subject, body);
  }
}

function resetSentinel() {
  const FOLDER_NAME = '__PASTE_FOLDER_NAME_HERE__';
  const props = PropertiesService.getScriptProperties();
  const config = readConfig_(props);
  if (!config) return;
  const intake = DriveApp.getFolderById(config.intakeFolderId);
  const matches = intake.getFoldersByName(FOLDER_NAME);
  if (!matches.hasNext()) {
    Logger.log(`No folder named "${FOLDER_NAME}" under intake.`);
    return;
  }
  const folder = matches.next();
  const sentinels = folder.getFilesByName(SENTINEL_NAME);
  if (!sentinels.hasNext()) {
    Logger.log(`No sentinel to remove in ${FOLDER_NAME}.`);
    return;
  }
  sentinels.next().setTrashed(true);
  Logger.log(`Removed sentinel from ${FOLDER_NAME}; next poll will re-dispatch.`);
}
