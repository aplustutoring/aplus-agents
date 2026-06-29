"""Run aplus-research 3 times with different lens weights and time windows.

Decisions:
  #9  — 3 topics from 3 independent runs (take #1 from each)
  #10 — different lens weights per run for structural diversity
  #11 — different time windows per run for data diversity

The aplus-research SKILL.md (categories A-E, Tier 1/2 keywords, ranking criteria)
stays cached as the system prompt across all 3 runs. The user message steers
weights and the time window per run.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from skills_runner import SkillsRunner, SkillResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Lens:
    name: str
    description: str
    time_window_days: int
    category_emphasis: tuple[str, ...]
    ranking_emphasis: tuple[str, ...]


# 3 lenses for structural and data diversity. Order is deterministic — Lens A
# always runs first so its output sits at index 0 in the resulting candidate list.
LENSES: tuple[Lens, ...] = (
    Lens(
        name="policy_funding_hawk",
        description="Federal/state funding flows and academic research releases",
        time_window_days=14,
        category_emphasis=("A", "E"),  # funding + research
        ranking_emphasis=("evidence strength", "recency"),
    ),
    Lens(
        name="target_school_radar",
        description="HOT 13 charter/district news and acute K-12 problem stories",
        time_window_days=7,
        category_emphasis=("C", "B"),  # target schools + problem stories
        ranking_emphasis=("A+ positioning fit", "audience relevance"),
    ),
    Lens(
        name="competitive_intel",
        description="Industry/competitor moves and emerging intervention models",
        time_window_days=30,
        category_emphasis=("D", "B"),  # competitor + problem stories
        ranking_emphasis=("differentiation potential", "A+ positioning fit"),
    ),
)


@dataclass
class Topic:
    headline: str
    category: str
    sources: list[str] = field(default_factory=list)
    why_matters: str = ""
    angle: str = ""
    roman_take: str = ""
    danielle_take: str = ""
    source_lens: str = ""
    raw_markdown_excerpt: str = ""


def _build_user_prompt(lens: Lens, context: str) -> str:
    cats = ", ".join(lens.category_emphasis)
    rank = ", then ".join(lens.ranking_emphasis)
    return f"""Run a research brief NOW for the A+ Tutoring LinkedIn content engine, using the steering below.

LENS NAME: {lens.name}
LENS DESCRIPTION: {lens.description}

STEERING for this run (overrides defaults from the skill):
- TIME WINDOW: prefer findings from the past {lens.time_window_days} days (not the default 7)
- CATEGORY EMPHASIS: weight categories {cats} above the others when ranking topics
- RANKING EMPHASIS: rank by {rank} above the standard ordering

Output exactly the markdown format the skill specifies. Top 3 topics required.
Topic 1 must be the strongest candidate FROM THIS LENS — do not hedge across lenses.

CONTEXT for this run:
{context}
""".strip()


# Tolerant Topic-1 capture: accept `### Topic 1:`, `### **Topic 1:**`, `### Topic 1.`,
# `### Topic #1:`, `### 1.`, etc. Headline may be bold-wrapped.
_TOPIC_1_BLOCK = re.compile(
    r"###\s+\*{0,2}\s*(?:Topic\s*#?\s*)?1\s*\*{0,2}\s*[:.—\-]+\s*\*{0,2}\s*(?P<headline>[^\n]+?)\*{0,2}\s*\n(?P<body>.*?)(?=\n###\s|\n##\s|\Z)",
    re.DOTALL | re.IGNORECASE,
)
# Field rows like `- **Category:** B` or `- **Source(s) to verify ⚠:**`
_FIELD_RE = re.compile(
    r"^-\s+\*\*(?P<key>[^:*]+?):?\*\*\s*(?P<value>.+?)(?=\n-\s+\*\*|\Z)",
    re.MULTILINE | re.DOTALL,
)
_URL_RE = re.compile(r"https?://[^\s\)\]>,]+")


def _build_topic(headline: str, body: str, source_lens: str, raw: str) -> Topic:
    """Build a Topic from a parsed block's headline + body markdown."""
    fields_raw = {
        m.group("key").strip().lower(): m.group("value").strip()
        for m in _FIELD_RE.finditer(body)
    }

    def f(*keys: str) -> str:
        for k in keys:
            if k in fields_raw:
                return re.sub(r"\s+", " ", fields_raw[k]).strip()
        return ""

    sources_field = f("source(s)", "sources", "source")
    sources = _URL_RE.findall(sources_field) if sources_field else []

    return Topic(
        headline=headline.strip(),
        category=f("category"),
        sources=sources,
        why_matters=f("why this matters for a+", "why this matters"),
        angle=f("suggested angle for company post", "suggested angle"),
        roman_take=f("roman take suggestion", "roman take"),
        danielle_take=f("danielle take suggestion", "danielle take"),
        source_lens=source_lens,
        raw_markdown_excerpt=raw.strip(),
    )


def parse_topic_1(markdown: str, source_lens: str) -> Optional[Topic]:
    """Extract Topic 1 from an aplus-research markdown brief."""
    block_match = _TOPIC_1_BLOCK.search(markdown)
    if not block_match:
        return None
    return _build_topic(
        block_match.group("headline"), block_match.group("body"), source_lens, block_match.group(0)
    )


# Tolerant capture of ANY numbered topic block (1-9). Used to pull the full
# 3-candidate slate from a single lens call for the REDO flow.
_TOPIC_ANY_BLOCK = re.compile(
    r"###\s+\*{0,2}\s*(?:Topic\s*#?\s*)?(?P<num>[1-9])\s*\*{0,2}\s*[:.—\-]+\s*\*{0,2}\s*(?P<headline>[^\n]+?)\*{0,2}\s*\n(?P<body>.*?)(?=\n###\s|\n##\s|\Z)",
    re.DOTALL | re.IGNORECASE,
)


def parse_topics(markdown: str, source_lens: str, max_n: int = 3) -> list[Topic]:
    """Extract up to max_n numbered topics (1..max_n) from a research brief."""
    out: list[Topic] = []
    seen: set[int] = set()
    for m in _TOPIC_ANY_BLOCK.finditer(markdown):
        num = int(m.group("num"))
        if num in seen or num > max_n:
            continue
        seen.add(num)
        out.append(_build_topic(m.group("headline"), m.group("body"), source_lens, m.group(0)))
    return out[:max_n]


@dataclass
class LensRunResult:
    lens: Lens
    topic: Optional[Topic]
    skill_result: SkillResult
    parse_failed: bool = False


def run_lens(lens: Lens, runner: SkillsRunner, context: str) -> LensRunResult:
    """Execute aplus-research with one lens. Returns the parsed Topic 1 or None."""
    prompt = _build_user_prompt(lens, context)
    logger.info("lens_start name=%s window=%dd", lens.name, lens.time_window_days)
    skill_result = runner.run_skill("aplus-research", prompt, web_search=True)
    topic = parse_topic_1(skill_result.text, source_lens=lens.name)
    if topic is None:
        # Dump the start of the skill output so future failures are debuggable
        preview = skill_result.text[:600].replace("\n", " | ")
        logger.warning(
            "lens_parse_failed name=%s — Topic 1 block not found. Output preview: %s",
            lens.name, preview,
        )
        return LensRunResult(lens=lens, topic=None, skill_result=skill_result, parse_failed=True)
    logger.info("lens_ok name=%s topic=%r", lens.name, topic.headline[:60])
    return LensRunResult(lens=lens, topic=topic, skill_result=skill_result)


def run_all_lenses(runner: SkillsRunner, context: str) -> list[LensRunResult]:
    """Run all 3 lenses sequentially. Returns 3 LensRunResults in LENSES order."""
    return [run_lens(lens, runner, context) for lens in LENSES]


LENS_BY_NAME: dict[str, Lens] = {lens.name: lens for lens in LENSES}


def lens_for_slot(slot: int, lens_name: Optional[str] = None) -> Lens:
    """Resolve the Lens for a 1-based slot, preferring an explicit lens name."""
    if lens_name and lens_name in LENS_BY_NAME:
        return LENS_BY_NAME[lens_name]
    return LENSES[(slot - 1) % len(LENSES)]


def generate_slot_candidates(
    lens: Lens, runner: SkillsRunner, context: str, n: int = 3
) -> list[Topic]:
    """Re-run one lens and return up to n candidate topics (for the REDO flow).

    The aplus-research skill already emits a Top-3, so a single web-searched call
    yields all n candidates — no need for n separate API calls.
    """
    prompt = _build_user_prompt(lens, context)
    logger.info("slot_candidates_start lens=%s n=%d", lens.name, n)
    skill_result = runner.run_skill("aplus-research", prompt, web_search=True)
    topics = parse_topics(skill_result.text, source_lens=lens.name, max_n=n)
    logger.info("slot_candidates_done lens=%s got=%d", lens.name, len(topics))
    return topics


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # Round-trip a synthetic markdown brief through the parser without touching the API.
    sample = """# A+ Research Brief . 2026-05-21

## Summary
Two big signals this week.

## Top 3 recommended topics for next week's content

### Topic 1: California releases LTEL reclassification data showing 47% improvement under HIT programs
- **Category:** B
- **Source(s):** https://example.com/cde-ltel-2026 https://example.com/edsource-followup
- **Why this matters for A+:** Direct validation of HIT model with state-level data.
- **Suggested angle for company post:** Lead with the 47% number, anchor to iLEAD case study.
- **Roman take suggestion:** What CDE is finally measuring is what A+ has been doing for 3 years.
- **Danielle take suggestion:** Here is what reclassification timelines look like inside the classroom.

### Topic 2: Title III deadline pushed to June 30
- **Category:** A
- **Source(s):** https://example.com/title-iii
- **Why this matters for A+:** More runway for charter funding asks.

### Topic 3: Sylvan announces AI tutor product
- **Category:** D
- **Source(s):** https://example.com/sylvan
- **Why this matters for A+:** Validates the market.
"""
    parsed = parse_topic_1(sample, source_lens="test_lens")
    assert parsed is not None, "parser failed to extract Topic 1"
    print(f"headline: {parsed.headline!r}")
    print(f"category: {parsed.category!r}")
    print(f"sources:  {parsed.sources}")
    print(f"why_matters: {parsed.why_matters!r}")
    print(f"angle: {parsed.angle!r}")
    print(f"roman_take: {parsed.roman_take!r}")
    print(f"danielle_take: {parsed.danielle_take!r}")
    print(f"source_lens: {parsed.source_lens!r}")

    assert parsed.category == "B"
    assert len(parsed.sources) == 2
    assert "47%" in parsed.headline
    assert parsed.roman_take.startswith("What CDE")
    assert parsed.danielle_take.startswith("Here is what")

    # Variant formats the model might use
    variants = [
        "### **Topic 1: Bold-wrapped headline lives here**\n- **Category:** A\n",
        "### Topic 1. Period instead of colon\n- **Category:** B\n",
        "### Topic #1: Hash mark variant\n- **Category:** C\n",
        "### Topic 1 — Em-dash variant\n- **Category:** D\n",
        "### 1. Just numbered no Topic word\n- **Category:** E\n",
    ]
    for v in variants:
        p = parse_topic_1(v, source_lens="v")
        assert p is not None, f"variant failed: {v[:50]!r}"
        assert p.category in {"A", "B", "C", "D", "E"}, f"category bad in {v[:50]!r}"
    print("\nALL ASSERTIONS PASSED (including 5 format variants)")
