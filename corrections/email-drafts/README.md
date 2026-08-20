# corrections/email-drafts/

Automatic feedback from the team's edits to agent-written email drafts
(charter@ PO inbox). Every draft the agent creates is registered with its exact
text; when it leaves Gmail Drafts the agent compares it to what was actually
sent:

- **sent as-is** → good (no record here)
- **edited / rewritten** → one file per draft with the diff, plus a distilled
  line in `STYLE-RULES.md`
- **discarded** → one file noting no message went out

`STYLE-RULES.md` is loaded into BOTH drafting prompts (charter PO inbox and the
admin-inbox classifier) at runtime — the agent writes tomorrow's drafts the way
the team sent yesterday's. Weekly one-liner to the visionary seat (Fri 4 PM PT).

People can also add rules the human way: reply to the aplus bot in
#agent-feedback ("PO drafts: stop saying 'we'll take it from there'") — the
feedback agent files it here through the standard corrections PR.
