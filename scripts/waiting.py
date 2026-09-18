"""Who is ACTUALLY waiting on us. Version 3.

Version 1 read only the text log, so three families who had been CALLED back
looked neglected (Annie Wolfstein was on the phone with Paola at the moment I
said she was waiting).

Version 2 fixed that by reading HubSpot's notes_last_contacted, which
aggregates channels. That was WORSE, silently: notes_last_contacted updates on
INBOUND activity too. Amanda Calof's read 04:29:51, the exact second of her own
text to us. So every message looked answered the instant it arrived, and the
checker reported "nobody is waiting" every single tick, by construction.

Version 3 asks the only question that actually means anything: did something go
OUT to this person after their message? Three channels, newest wins.

  - outbound text   JustCall
  - outbound call   JustCall (the channel version 1 was blind to)
  - outbound email  HubSpot engagements

If none of them is newer than the message, they are waiting.

The bar is ONE HOUR (Roman 2026-09-17: "all of our texts need to be
acknowledged within 1 hour"). Output splits three ways and the third matters:
WAITING, answered, and CANNOT TELL when a number does not resolve to a
contact. An unresolved number is a confident wrong answer, not a blank.

    python3 scripts/waiting.py [hours]      # default 14

Two open questions Roman has not settled, both of which change the count:
  - does a closing "thank you" need acknowledging? They are filtered out here.
  - overnight. On 2026-09-16 the line went quiet at 21:31 and reopened at
    08:50, so six people breached a flat one-hour rule by morning. The rule
    probably needs stated hours or an after-hours auto-acknowledgement.
"""
import os, re, sys, requests, warnings, datetime
warnings.filterwarnings("ignore")
from dotenv import load_dotenv
load_dotenv("/Users/romanslavinsky/code/aplus-agents/.env")
k, s = os.environ["JUSTCALL_API_KEY"], os.environ["JUSTCALL_API_SECRET"]
JH = {"Authorization": f"{k}:{s}", "Accept": "application/json"}
H = {"Authorization": f"Bearer {os.environ['HUBSPOT_PRIVATE_APP_TOKEN']}",
     "Content-Type": "application/json"}
hours = float(sys.argv[1]) if len(sys.argv) > 1 else 14
since = datetime.datetime.now() - datetime.timedelta(hours=hours)
SINCE_S = since.strftime("%Y-%m-%d %H:%M:%S")

COURTESY = re.compile(r"^\s*(thank you|thanks|ty|ok(ay)?|got it|great|perfect|"
                      r"sounds good|will do|no problem|yes|yep|you too|👍|😊|❤️|"
                      r"liked “|loved “|​👍​|​❤️​)", re.IGNORECASE)


def digits(p):
    d = re.sub(r"\D", "", str(p or ""))
    return d[-10:] if len(d) >= 10 else ""


def pull(kind):
    out, page = [], 0
    while page <= 60:
        r = requests.get(f"https://api.justcall.io/v2.1/{kind}", headers=JH, timeout=60,
                         params={"per_page": 100, "page": page, "from_datetime": SINCE_S})
        if r.status_code >= 300:
            raise SystemExit(f"JustCall {kind} HTTP {r.status_code}: {r.text[:200]}")
        j = r.json()
        rows = j.get("data") or []
        out += rows
        if not rows or not j.get("next_page_link"):
            break
        page += 1
    return out


texts, calls = pull("texts"), pull("calls")

# newest inbound text per number, and newest OUTBOUND touch per number
newest_in, newest_out = {}, {}
for t in texts:
    n = digits(t.get("contact_number"))
    if not n:
        continue
    info = t.get("sms_info") or {}
    w = f"{t.get('sms_date') or info.get('sms_date')} {t.get('sms_time') or info.get('sms_time')}"
    body = ((info.get("body")) or "").replace("\n", " ").strip()
    if str(t.get("direction", "")).lower().startswith("in"):
        if n not in newest_in or w > newest_in[n][0]:
            newest_in[n] = (w, body, t.get("contact_name") or "")
    else:
        if n not in newest_out or w > newest_out[n]:
            newest_out[n] = w
for c in calls:
    info = c.get("call_info") or {}
    if str(info.get("direction") or "").lower() != "outgoing":
        continue
    n = digits(c.get("contact_number"))
    if not n:
        continue
    w = f"{c.get('call_date')} {c.get('call_time')}"
    if n not in newest_out or w > newest_out[n]:
        newest_out[n] = w


def outbound_email_after(number, when):
    """Newest OUTBOUND email to this contact, via HubSpot engagements."""
    r = requests.post("https://api.hubapi.com/crm/v3/objects/contacts/search", headers=H,
                      timeout=30, json={"filterGroups": [
                          {"filters": [{"propertyName": "hs_searchable_calculated_phone_number",
                                        "operator": "EQ", "value": number}]},
                          {"filters": [{"propertyName": "hs_searchable_calculated_mobile_number",
                                        "operator": "EQ", "value": number}]}],
                          "properties": ["firstname", "lastname"], "limit": 1})
    hits = r.json().get("results") or []
    if not hits:
        return None, ""
    c = hits[0]
    label = f"{c['properties'].get('firstname') or ''} {c['properties'].get('lastname') or ''}".strip()
    a = requests.get(f"https://api.hubapi.com/crm/v4/objects/contacts/{c['id']}/associations/emails",
                     headers=H, timeout=30).json()
    ids = [str(x["toObjectId"]) for x in a.get("results", [])][-20:]
    if not ids:
        return False, label
    b = requests.post("https://api.hubapi.com/crm/v3/objects/emails/batch/read", headers=H,
                      timeout=30, json={"inputs": [{"id": i} for i in ids],
                                        "properties": ["hs_timestamp", "hs_email_direction"]}).json()
    for e in b.get("results", []):
        p = e["properties"]
        if p.get("hs_email_direction") == "INCOMING_EMAIL":
            continue
        ts = (p.get("hs_timestamp") or "")[:19].replace("T", " ")
        if ts >= when[:19]:
            return True, label
    return False, label


waiting, courtesy = [], 0
for n, (when, body, name) in sorted(newest_in.items(), key=lambda x: x[1][0]):
    out = newest_out.get(n, "")
    if out and out[:19] >= when[:19]:
        continue                                  # texted or called back
    if COURTESY.match(body):
        courtesy += 1
        continue
    emailed, label = outbound_email_after(n, when)
    if emailed:
        continue
    waiting.append((when, label or name or f"...{n[-4:]}", body,
                    "no contact record" if emailed is None else ""))

# Roman 2026-09-17: every text gets acknowledged within ONE HOUR.
SLA_MIN = 60
now = datetime.datetime.utcnow()
print(f"{len(newest_in)} numbers wrote in over {hours}h "
      f"({courtesy} closing courtesies ignored)\n")
breached = []
for when, label, body, note in waiting:
    try:
        age = int((now - datetime.datetime.strptime(when[:19], "%Y-%m-%d %H:%M:%S"))
                  .total_seconds() // 60)
    except ValueError:
        age = -1
    breached.append((age, when, label, body, note))
breached.sort(reverse=True)
over = [b for b in breached if b[0] >= SLA_MIN]
print(f"WAITING: {len(waiting)}   PAST THE 1-HOUR BAR: {len(over)}")
for age, when, label, body, note in breached:
    flag = "BREACH" if age >= SLA_MIN else "  ok  "
    h, m = divmod(max(age, 0), 60)
    agestr = f"{h}h {m:02d}m" if h else f"{m}m"
    print(f"  [{flag}] {agestr:>7s} | {label}{(' · ' + note) if note else ''}")
    print(f"             {body[:150]}")
