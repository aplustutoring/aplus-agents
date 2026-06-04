"""Execute A+ skills (skills/<name>/SKILL.md) via the Anthropic API.

Each skill is a self-contained set of instructions designed to be loaded as a
system prompt. This module loads a skill, calls Claude with the SKILL.md cached
as a system prompt, and returns the parsed output.

Used by topic_gen.py, blog_publish.py, and other Phase 3 entry points.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import anthropic
from dotenv import load_dotenv

load_dotenv(override=True)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = REPO_ROOT / "skills"

DEFAULT_MODEL = "claude-opus-4-7"
DEFAULT_MAX_TOKENS = 16000
DEFAULT_EFFORT = "high"
DEFAULT_MAX_RETRIES = 5

logger = logging.getLogger(__name__)


class SkillNotFound(FileNotFoundError):
    """Raised when skills/<name>/SKILL.md does not exist."""


@dataclass
class SkillResult:
    text: str
    thinking: str
    skill_name: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    stop_reason: Optional[str]
    request_id: Optional[str]

    @property
    def total_input_tokens(self) -> int:
        return (
            self.input_tokens
            + self.cache_read_input_tokens
            + self.cache_creation_input_tokens
        )

    @property
    def cache_read_ratio(self) -> float:
        total = self.total_input_tokens
        return self.cache_read_input_tokens / total if total else 0.0


def load_skill(skill_name: str) -> str:
    path = SKILLS_DIR / skill_name / "SKILL.md"
    if not path.is_file():
        raise SkillNotFound(f"skill not found: {path}")
    return path.read_text(encoding="utf-8")


class SkillsRunner:
    def __init__(
        self,
        *,
        client: Optional[anthropic.Anthropic] = None,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        effort: str = DEFAULT_EFFORT,
        thinking: bool = True,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        if client is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise RuntimeError(
                    "ANTHROPIC_API_KEY not set. Add to .env or pass an explicit client."
                )
            client = anthropic.Anthropic(max_retries=max_retries)
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        self.thinking = thinking

    def run_skill(
        self,
        skill_name: str,
        user_input: str,
        *,
        max_tokens: Optional[int] = None,
        effort: Optional[str] = None,
        thinking: Optional[bool] = None,
    ) -> SkillResult:
        """Execute a skill end-to-end and return the parsed result."""
        skill_md = load_skill(skill_name)

        system = [
            {
                "type": "text",
                "text": skill_md,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        use_thinking = self.thinking if thinking is None else thinking

        params = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user_input}],
            "output_config": {"effort": effort or self.effort},
        }
        if use_thinking:
            params["thinking"] = {"type": "adaptive", "display": "summarized"}

        try:
            with self.client.messages.stream(**params) as stream:
                for _ in stream.text_stream:
                    pass
                response = stream.get_final_message()
        except anthropic.APIStatusError as e:
            request_id = (
                getattr(e.response, "headers", {}).get("request-id")
                if e.response is not None
                else None
            )
            logger.exception(
                "skill_run_failed skill=%s status=%s request_id=%s",
                skill_name,
                e.status_code,
                request_id,
            )
            raise

        text_parts = [b.text for b in response.content if b.type == "text"]
        thinking_parts = [b.thinking for b in response.content if b.type == "thinking"]

        result = SkillResult(
            text="".join(text_parts),
            thinking="\n".join(thinking_parts),
            skill_name=skill_name,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read_input_tokens=response.usage.cache_read_input_tokens or 0,
            cache_creation_input_tokens=response.usage.cache_creation_input_tokens or 0,
            stop_reason=response.stop_reason,
            request_id=getattr(response, "_request_id", None),
        )

        logger.info(
            "skill_run_ok skill=%s in=%d out=%d cache_read=%d cache_create=%d stop=%s req=%s",
            skill_name,
            result.input_tokens,
            result.output_tokens,
            result.cache_read_input_tokens,
            result.cache_creation_input_tokens,
            result.stop_reason,
            result.request_id,
        )

        return result


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    runner = SkillsRunner()

    prompt = (
        "Sanity check. In ONE sentence (no more), name the five topic categories "
        "this skill watches. Do not include any other commentary."
    )

    print("=== First call (expect cache miss; cache_create > 0) ===")
    r1 = runner.run_skill("aplus-research", prompt, max_tokens=512)
    print(f"text: {r1.text.strip()}")
    print(
        f"tokens: in={r1.input_tokens} out={r1.output_tokens} "
        f"cache_read={r1.cache_read_input_tokens} "
        f"cache_create={r1.cache_creation_input_tokens}"
    )
    print(f"model={r1.model} stop={r1.stop_reason} req={r1.request_id}")

    print("\n=== Second call (expect cache hit; cache_read > 0) ===")
    r2 = runner.run_skill("aplus-research", prompt, max_tokens=512)
    print(
        f"tokens: in={r2.input_tokens} out={r2.output_tokens} "
        f"cache_read={r2.cache_read_input_tokens} "
        f"cache_create={r2.cache_creation_input_tokens}"
    )
    print(f"cache_read_ratio={r2.cache_read_ratio:.0%}")
