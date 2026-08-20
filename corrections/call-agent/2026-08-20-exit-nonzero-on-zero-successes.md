---
reporter: Roman
reporter_slack_id: U05NA7UMSSV
date: 2026-08-20
agent: call-agent
agent_label: Call agent — daily digest (~5:30 PM PT)
type: IDEA
severity: normal
channel: C0BL05MCJ4B
thread_ts: "1787256679.631249"
permalink: https://atutoringworkspace.slack.com/archives/C0BL05MCJ4B/p1787256679631249
status: open
---

## Report (Roman)

> The call agent can fail every single call in a run and still come back green in GitHub — nothing alerts us, because the retry sweeper only reacts to a non-zero exit. Skipping one bad call and carrying on is right, but if a run processes zero calls successfully it should exit non-zero so we hear about it.
> 
> (Also using this to test the fix loop end to end — the approve button has been broken since Aug 11 and was fixed today.) *Sent using* <@U0AKFN28V1U>

## Classification

Call agent returns success even when every call in a run fails, so the retry sweeper never fires; it should exit non-zero when zero calls succeed.
