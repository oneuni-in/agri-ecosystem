"""Generate the AG-A24 vernacular review sheet from the source of truth.

Parses the AST rather than pattern-matching text: `_t(en, ta, hi)` calls
carry implicit concatenation and f-strings, and a regex over those is how
you silently drop half the corpus.
"""

import ast
import io
import pathlib
import sys

SRC = pathlib.Path("backend/core/modules/market_data/weather.py")
OUT = pathlib.Path("docs/qa/agri-vernacular-review.md")


def literal(node: ast.AST) -> str:
    """Flatten a string arg: plain literal, implicit concatenation, or an
    f-string whose placeholders we keep as {name} so a reviewer sees them."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                parts.append("{" + ast.unparse(value.value) + "}")
        return "".join(parts)
    return ""


tree = ast.parse(SRC.read_text(encoding="utf-8"))
rows: list[tuple[str, str, str]] = []
for node in ast.walk(tree):
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_t"
        and len(node.args) == 3
    ):
        en, ta, hi = (literal(a).strip() for a in node.args)
        if en and ta and hi:
            rows.append((en, ta, hi))

body = io.StringIO()
body.write("""# A-U2 vernacular review sheet (AG-A24)

Generated from `backend/core/modules/market_data/weather.py` by
`scripts/gen_vernacular_review.py`. Regenerate rather than hand-edit, so it
cannot drift from the code it is reviewing.

**What needs a native speaker, and why these first.** A-U2 authored roughly 57
Tamil and 57 Hindi strings, and they are not equal risk:

- The pairs below **carry ADVICE** — when to spray, when to hold off urea, when
  to irrigate, what disease to scout for, and severe-weather warnings. A wrong
  nuance changes what a farmer *does*. These are worth a careful read.
- The other ~38 are weather-condition labels and weekday abbreviations in
  `wmo.py` ("Overcast", "Light drizzle", "Mon"). An awkward word there is
  cosmetic. Review them second, or not at all.

`{day.ta}`, `{end.ta}`, `{wet.ta}` and `{hours}` are placeholders filled at
render time with a weekday abbreviation or a number.

The English column is the source of truth: the Tamil and Hindi should say the
same thing to a farmer, not match word for word.

## Advice strings — please check

| # | English | Tamil | Hindi | OK? |
|---|---|---|---|---|
""")
for index, (en, ta, hi) in enumerate(rows, 1):
    cells = [c.replace("|", "\\|").replace("\n", " ") for c in (en, ta, hi)]
    body.write(f"| {index} | {cells[0]} | {cells[1]} | {cells[2]} | |\n")

body.write("""
## Recording the outcome

Tick the OK column, or replace the cell with the wording you want. Anything
changed here has to go back into `weather.py` — this file is a review surface,
not the source.

Least certain, flagged by the author:

- **தெளிப்பு** for spraying — correct for pesticide application, but confirm it is
  what a farmer in the Coimbatore belt would say rather than a textbook term.
- **மூடாக்கு** (mulch) and **பூஞ்சை இலைப்புள்ளி** (fungal leaf spot) are agronomic
  terms; a field-accurate synonym may read better.
- The Hindi severe-weather headlines deliberately mirror IMD's own phrasing
  (**भारी बारिश की चेतावनी**). Keep that alignment if you reword them — people
  recognise the official form.
- Numbers, units and crop names stay in the English column's form on purpose;
  the UI formats them.
""")

OUT.write_text(body.getvalue(), encoding="utf-8", newline="\n")
print(f"wrote {OUT} with {len(rows)} advice pairs", file=sys.stderr)
