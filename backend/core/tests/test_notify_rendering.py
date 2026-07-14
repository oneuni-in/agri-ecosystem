"""D12 threat model: template-variable injection. Values must never alter
template structure; email values are HTML-escaped."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.notify.rendering import MissingVariableError, load_template, render_template


def test_renders_simple_variables() -> None:
    assert render_template("Hello {name}!", {"name": "Asha"}) == "Hello Asha!"


def test_missing_variable_is_a_hard_error_when_strict() -> None:
    with pytest.raises(MissingVariableError):
        render_template("Hello {name}!", {})


def test_lenient_mode_substitutes_empty_for_missing() -> None:
    assert render_template("Hello {name}!", {}, strict=False) == "Hello !"


def test_payload_values_cannot_inject_placeholders() -> None:
    # a value containing {other} must land literally, not resolve
    out = render_template("Hi {name}", {"name": "{secret}", "secret": "x"})
    assert out == "Hi {secret}"


def test_html_is_escaped_for_email() -> None:
    out = render_template("Hi {name}", {"name": "<script>alert(1)</script>"}, escape_html=True)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_format_spec_syntax_is_not_interpreted() -> None:
    # str.format would explode or leak on {name.__class__}; our renderer must
    # treat anything but a bare [a-z0-9_]+ name as literal text
    template = "Hi {name.__class__} and {name!r} and {0}"
    assert render_template(template, {"name": "x"}) == template


async def test_load_template_falls_back_to_english(db_session: AsyncSession) -> None:
    exact = await load_template(db_session, key="welcome", channel="in_app", locale="ta")
    assert exact is not None and exact.locale == "ta"
    # role_changed has no sms row at all -> None even after fallback
    missing = await load_template(db_session, key="role_changed", channel="sms", locale="ta")
    assert missing is None
