"""Thin wrapper around the Anthropic Claude API for structured-output calls.

Uses `output_config.format` (JSON Schema mode) so responses are guaranteed
to match the schema passed in - no manual JSON-in-text parsing needed.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

import anthropic

DEFAULT_MODEL = os.environ.get("SAPBUDDY_CLAUDE_MODEL", "claude-opus-5")
DEFAULT_MAX_TOKENS = int(os.environ.get("SAPBUDDY_CLAUDE_MAX_TOKENS", "8000"))


class ClaudeNotConfiguredError(RuntimeError):
    """Raised when ANTHROPIC_API_KEY is not set."""


@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ClaudeNotConfiguredError(
            "ANTHROPIC_API_KEY is not set. Export it before running enrichment."
        )
    return anthropic.Anthropic()


def call_structured(
    system: str,
    user_content: str,
    json_schema: dict,
    model: str | None = None,
    max_tokens: int | None = None,
) -> dict:
    """Call Claude and return a dict validated against json_schema.

    Raises ClaudeNotConfiguredError if no API key is set, and ValueError if
    Claude's response cannot be parsed as JSON (should not happen with
    output_config.format, but we guard defensively).
    """
    client = _client()
    response = client.messages.create(
        model=model or DEFAULT_MODEL,
        max_tokens=max_tokens or DEFAULT_MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user_content}],
        output_config={
            "format": {
                "type": "json_schema",
                "schema": json_schema,
            }
        },
    )

    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise ValueError("Claude response contained no text block to parse as JSON")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Claude response was not valid JSON: {exc}") from exc


def is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
