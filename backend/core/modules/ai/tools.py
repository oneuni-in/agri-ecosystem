"""A-U4 W1 — the assistant's tool surface. Read-only, allowlisted, no writes.

Three rules, and each is enforced structurally rather than by convention:

1. NO TOOL CAN WRITE. Every entry declares `method` and the allowlist contains
   only GET. `test_ai_redteam.py::test_no_tool_can_write` walks this table, so
   a future tool that mutates state fails CI instead of shipping. A
   write-capable tool behind an LLM is a different risk class and the build
   prompt puts it explicitly out of bounds.

2. NO PRIVILEGED DATA PATH. Tools call the SAME public HTTP endpoints the
   pages call — `/market/today/{pincode}` and `/market/commodities` — over
   loopback, unauthenticated. The assistant therefore cannot see anything a
   visitor could not fetch themselves. This is also why it is HTTP and not a
   Python import: `modules.ai` is forbidden from importing `modules.market_data`
   (import-linter independence contract), and going through the public surface
   makes "no privileged path" a property of the architecture rather than a
   promise in a comment.

3. THE MODEL NEVER SUPPLIES A URL. It supplies a tool NAME and typed
   arguments; the path is built here from a template. `resolve_tool` returns
   None for anything not in the table, so a hallucinated or traversal-shaped
   name (`../../admin/users`) dies before any request is made.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from settings import get_settings

__all__ = ["ToolSpec", "TOOL_ALLOWLIST", "resolve_tool", "anthropic_tool_schemas", "call_tool"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    #: Always "GET". Declared as data so the invariant is testable.
    method: str
    #: Path template filled from validated args only — never from raw model text.
    path: str
    #: JSON Schema the model sees. Kept tight: a narrow schema is a narrower
    #: attack surface than a free-text argument.
    input_schema: dict[str, Any]


#: Pincode: exactly six digits, first digit non-zero (India). Validating here
#: rather than trusting the model is what stops `641001/../../admin` reaching
#: the path template.
_PINCODE_RE = re.compile(r"^[1-9][0-9]{5}$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,48}[a-z0-9]$")


TOOL_ALLOWLIST: dict[str, ToolSpec] = {
    "mandi_and_weather_today": ToolSpec(
        name="mandi_and_weather_today",
        description=(
            "Today's mandi prices, weather and scheme deadlines for one Indian "
            "pincode. Use when the question depends on current local prices or "
            "current weather. Returns the same data the agri.in home page shows."
        ),
        method="GET",
        path="/market/today/{pincode}",
        input_schema={
            "type": "object",
            "properties": {
                "pincode": {
                    "type": "string",
                    "description": "Six-digit Indian pincode, e.g. 641001",
                }
            },
            "required": ["pincode"],
            "additionalProperties": False,
        },
    ),
    "mandi_prices": ToolSpec(
        name="mandi_prices",
        description=(
            "The list of commodities agri.in tracks mandi prices for. Use to "
            "check whether a crop is covered before promising a price."
        ),
        method="GET",
        path="/market/commodities",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    ),
    "commodity_price_detail": ToolSpec(
        name="commodity_price_detail",
        description=(
            "Recent price history and market detail for one commodity slug, e.g. "
            "'paddy'. Call mandi_prices first to get valid slugs."
        ),
        method="GET",
        path="/market/commodities/{slug}",
        input_schema={
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Commodity slug from mandi_prices, e.g. 'paddy'",
                }
            },
            "required": ["slug"],
            "additionalProperties": False,
        },
    ),
}


def resolve_tool(name: str) -> ToolSpec | None:
    """Exact-match lookup. Anything not in the table is not a tool."""
    return TOOL_ALLOWLIST.get(name)


def anthropic_tool_schemas() -> list[dict[str, Any]]:
    """The `tools` array for the Messages API, built from the same table the
    executor uses — the model cannot be shown a tool the executor won't run,
    and vice versa."""
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in TOOL_ALLOWLIST.values()
    ]


def _safe_path(spec: ToolSpec, args: dict[str, Any]) -> str | None:
    """Build the request path from VALIDATED arguments.

    Returns None (rather than raising) on anything unexpected, so the caller
    reports a tool error to the model and the turn continues — a malformed
    tool call should cost the model a retry, not 500 the request.
    """
    if "{pincode}" in spec.path:
        pincode = str(args.get("pincode", ""))
        if not _PINCODE_RE.match(pincode):
            return None
        return spec.path.replace("{pincode}", pincode)
    if "{slug}" in spec.path:
        slug = str(args.get("slug", "")).lower()
        if not _SLUG_RE.match(slug):
            return None
        return spec.path.replace("{slug}", slug)
    return spec.path


async def call_tool(name: str, args: dict[str, Any]) -> tuple[bool, str]:
    """Execute one allowlisted read. Returns (ok, payload-or-error-text).

    Failures are returned as text for the model to read, never raised: an
    upstream hiccup should degrade the answer, not break the conversation.
    """
    spec = resolve_tool(name)
    if spec is None:
        return False, f"Unknown tool: {name}"
    path = _safe_path(spec, args or {})
    if path is None:
        return False, f"Invalid arguments for {name}"

    settings = get_settings()
    base = settings.internal_api_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # No auth header, by design — see rule 2 in the module docstring.
            res = await client.get(f"{base}{path}")
        if res.status_code != 200:
            return False, f"{name} returned {res.status_code}"
        # Truncated: a tool result is evidence for one answer, not a payload
        # to blow the context window open with.
        return True, res.text[:8000]
    except Exception:  # noqa: BLE001 - upstream shape is not ours to trust
        return False, f"{name} is unavailable right now"
