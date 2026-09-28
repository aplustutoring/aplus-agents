# ops/switchboard — A+ Switchboard (calls + texts dashboard)

A private claude.ai artifact showing every call and text on every JustCall
line, per person, with IVR routing, a "waiting on a reply" list, and an Ask
box (Claude answers questions over the page's own data through page tools).

Live page: https://claude.ai/code/artifact/fff59879-8c96-4470-a729-a0885aa25dff
(owner Roman; share from the page's share menu).

## Pieces

| file | role |
|---|---|
| `refresh.py` | fetch JustCall (N days, per-day windows) → classify inbound texts → build the page |
| `template.html` | the page; `__DATA__` is replaced by the JSON payload |
| `requirements.txt` | requests, python-dotenv, anthropic |

## Refresh (daily cloud routine "Switchboard refresh")

The routine runs in the cloud on this repo, every morning, and does:

1. `Artifact read` of the live page → `prior.html` (the previous verdicts).
2. `pip install -r ops/switchboard/requirements.txt`
3. `python ops/switchboard/refresh.py --days 14 --prior prior.html --out switchboard.html`
4. `Artifact publish` of `switchboard.html` to the live URL (same link, same icon).
5. Delete both html files. They hold family names, numbers and message bodies
   and are never committed (FERPA pass 2026-09-24).

Manual refresh from a Claude Code session: same four steps, or say
"refresh the switchboard".

## Needs-reply classifier

Every inbound text gets `nr` (needs reply) and `why`. Rules first (tapback
reactions, STOP, verification codes, empty, emoji-only), then `claude-opus-5`
at low effort in batches of 40, with the last thing we sent that number as
context. Verdicts are reused from the previously published page, so a daily
run judges only new texts. The page's "Waiting on a reply", per-person reply
stats, and the Ask box's tools all use the flag; a text without a verdict
falls back to the page's word-list closer().

Why a classifier and not a word list: Roman 2026-09-24, "the thumbs up bull
shit is unnecessary". Word lists kept falling behind (see memory
word-lists-lose-to-structural-rules); the model reads the loop we opened.

## Seat facts baked into the page

- Emily and Danielle share one JustCall seat; the card reads "Emily + Danielle".
- Inbound texts are stamped to the line owner (Roman); never count them per person.
- Main line IVR: key 1 Sales rings Paola then Roman; key 2 Support = schedulers; key 3 Schools = Emily.
- `UTC_OFFSET_H` is 7 during PDT. Flip to 8 on Nov 1.

## Not in the repo on purpose

The built page, any fetched data, and classifier caches. All contain family
PII. The artifact itself is the state store: the next run reads verdicts back
out of the live page.
