"""
The channel's pinned how-to-use post must not be filed as a report.

On 2026-08-20 Roman posted "How this channel works" into #agent-feedback and
the classifier filed it as an IDEA against the feedback agent itself
(thread 1787258667.896529). The guard runs against the SHIPPED config.yml
markers — and the real reports below are the false-positive floor: every one
of them must still file.
"""

import feedback_agent as fa

CFG = fa.load_config()


# The pinned post, verbatim from the thread (Slack markup and all).
PINNED = """:pushpin: *How this channel works* — read once, then just use it.

*What it's for:* anything one of our agents got wrong, missed, or did annoyingly. The blog builder, the spotlight builder, the inbox agent, the call agent, the PO agent — all of them. If it felt broken, it belongs here.

*How to report:* just say it in plain English, as a new message in the channel. No format, no ticket number, no tagging anyone.

&gt; _the spotlight for Amelia is missing the superhero reel_
&gt; _Danielle's op-ed got cut off again on the Visions post_
*Screenshots are welcome.*

*What happens next, usually within two minutes:*
1. The agent replies in a thread confirming what it understood
*Then you decide. Reply in that thread with one word:*

• `approve` — build the fix. A pull request comes back into the thread.
• `merge` — ship it. That's the fix live.
• `no` — leave it filed, don't fix it now.

Every Friday there's a digest of what was reported, grouped by agent, never by person. *Sent using* <@U0AKFN28V1U>"""


# Reports that actually came through the channel — the guard must stay off.
REAL_REPORTS = [
    "Content build graphics keep cutting off text mid-sentence, the LinkedIn "
    "carousel especially. Fix the overflow so text always fits the frame. "
    "*Sent using* <@U0AKFN28V1U>",
    "The call agent can fail every single call in a run and still come back green "
    "in GitHub — nothing alerts us, because the retry sweeper only reacts to a "
    "non-zero exit. *Sent using* <@U0AKFN28V1U>",
    "the spotlight for Amelia is missing the superhero reel",
    "status *Sent using* <@U0AKFN28V1U>",
]


def test_pinned_post_is_meta():
    assert fa.meta_post_reason(PINNED, CFG)


def test_real_reports_are_not_meta():
    for text in REAL_REPORTS:
        assert fa.meta_post_reason(text, CFG) is None, text


def test_one_quoted_line_still_files():
    """Quoting the pinned post while reporting a real problem is a report."""
    text = ("The pinned post says *How to report:* just say it in plain English, "
            "but the blog agent never replied to mine yesterday.")
    assert fa.meta_post_reason(text, CFG) is None


def test_sender_app_ids_ship_empty():
    """U0AKFN28V1U is Roman's client attribution, not a workflow bot: listing it
    would swallow every report he files (see config.yml)."""
    assert (CFG["intake"]["ignore"]["sender_app_ids"] or []) == []


def test_sender_app_id_ignore_list_works_when_populated():
    cfg = {"intake": {"ignore": {"sender_app_ids": ["U0WORKFLOW1"], "meta_markers": []}}}
    assert fa.meta_post_reason("Weekly notice *Sent using* <@U0WORKFLOW1>", cfg)
    assert fa.meta_post_reason("Weekly notice *Sent using* <@U0AKFN28V1U>", cfg) is None


def test_curly_apostrophes_and_wrapped_lines_still_match():
    text = ("*How this channel works*\n\n*What it’s\nfor:* telling us what broke.")
    assert fa.meta_post_reason(text, CFG)


def test_no_config_section_means_no_guard():
    assert fa.meta_post_reason(PINNED, {}) is None
