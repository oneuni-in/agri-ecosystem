"""{var}-only template rendering (D12).

Deliberately NOT str.format: format-spec/attribute syntax ({x.__class__},
{x!r}, {0}) stays literal, so payload values can never traverse objects.
Substitution is single-pass over the TEMPLATE only - braces inside payload
values land as literal text (injection defence, pinned by tests)."""

import html
import re
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.notify.models import Template

_VAR_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


class MissingVariableError(KeyError):
    """Template references a variable the payload does not carry."""


def render_template(
    body: str,
    payload: Mapping[str, object],
    *,
    escape_html: bool = False,
    strict: bool = True,
) -> str:
    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in payload:
            if strict:
                raise MissingVariableError(name)
            return ""
        value = str(payload[name])
        return html.escape(value) if escape_html else value

    return _VAR_RE.sub(substitute, body)


async def load_template(
    session: AsyncSession, *, key: str, channel: str, locale: str
) -> Template | None:
    """Exact locale, else English (runtime fallback; the seed-completeness CI
    gate makes this a during-deploy safety net, not a normal path)."""
    for candidate in (locale, "en"):
        template = await session.scalar(
            select(Template).where(
                Template.key == key,
                Template.channel == channel,
                Template.locale == candidate,
            )
        )
        if template is not None:
            return template
        if candidate == "en":
            break
    return None
