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
DEFAULT_MAX_TOKENS = int(os.environ.get("SAPBUDDY_CLAUDE_MAX_TOKENS", "12000"))
WEB_SEARCH_MAX_USES = int(os.environ.get("SAPBUDDY_WEB_SEARCH_MAX_USES", "5"))

# Anthropic-hosted web search - runs server-side inside a single API call
# (Claude issues its own queries and reads results; no client-side loop
# needed). See enrichment/enrich_company.py for how this is used.
WEB_SEARCH_TOOL = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": WEB_SEARCH_MAX_USES,
}


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
    tools: list[dict] | None = None,
) -> dict:
    """Call Claude and return a dict validated against json_schema.

    If `tools` includes a server-side tool (e.g. WEB_SEARCH_TOOL), Claude
    runs it automatically within this same call - the response's content
    ends with a text block matching json_schema, preceded by whatever
    server_tool_use/tool_result blocks it took to get there.

    Raises ClaudeNotConfiguredError if no API key is set, and ValueError if
    Claude's response cannot be parsed as JSON (should not happen with
    output_config.format, but we guard defensively).
    """
    client = _client()
    kwargs = {}
    if tools:
        kwargs["tools"] = tools

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
        **kwargs,
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
