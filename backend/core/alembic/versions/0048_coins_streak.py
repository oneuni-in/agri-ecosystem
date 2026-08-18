"""A-U4 W2: the 7-day streak bonus rule.

Revision ID: 0048
Revises: 0047
Create Date: 2026-08-17

Adds ONE row to coins.rules: `daily_visit_streak`, the "📅 Daily price check
— 7-day streak bonus" card the A1 reference shows on the home.

WHY 15, AND WHY THAT IS NOT WHAT THE MOCKUP SAYS IT IS.

The A1 reference prints `+15` beside that card, and this rule is seeded at
15 — but the agreement is coincidental and must not be read as "the mockup
sets the amounts". The mockup also prints `+5` for a review (the engine pays
20), `+25` for a referral (the engine pays 250) and `+10` for a webinar
(there is no such rule). Those are illustrative figures in a design file.
`coins.rules` is the data, and A-U4 W2 adds `GET /coins/rules` so the cards
render the configured amount instead of a placeholder — which is the A-U1
"never invent amounts" deviation being paid off.

WHAT IS DELIBERATELY NOT HERE: a `webinar_attend` rule. The A1 reference
shows that card, but events and webinars are a Stage D surface and the home
renders them as honest Soon cards today. A rule that no code path can ever
fire would advertise a reward nobody can earn — worse than an empty slot.
It lands with events, not before them.

STREAK SEMANTICS. The bonus is awarded when a user completes seven
consecutive days carrying a `daily_visit` entry. The idempotency key is
`daily_visit_streak:{user_id}:{completion_day}`, so:
  - replaying the event that completed a streak credits once (UNIQUE key);
  - a user who keeps visiting can earn it again seven days later, because
    the completion day differs;
  - a broken streak simply never reaches seven and awards nothing.
No numeric cap is set: the deterministic key already bounds it to at most
one award per calendar day, and a per-day bound on a seven-day requirement
is the tightest cap that can matter.
"""

# -- THREAT/NOTES:
# - One INSERT into coins.rules. No schema change, no table rewrite, no lock
#   on live data.
# - downgrade deletes the rule row. Ledger entries already awarded under it
#   are NOT removed: the ledger is append-only by trigger (D13) and deleting
#   history to undo a config change would be the exact thing that guarantee
#   exists to prevent. A downgraded deployment simply stops awarding it.
# - Money path: this is a rules-table row, and every award still routes
#   through service.award -> rules.load_active_rule + check_numeric_caps.
#   There is no new award path and no cap bypass; the rule is data.
# - AgriCoins are NOT money (module CLAUDE.md) and no real-money interplay
#   is touched here.
# - PII: none. A rule row is a code, an amount and caps.
# - GRANTs: coins.rules already carries its app_rt grants from 0013; a row
#   insert needs none.

from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # coins.rules carries no description column — the rule's meaning lives
    # in this file's docstring and in reason_codes.py's i18n key, which is
    # what the UI actually renders.
    op.execute(
        "INSERT INTO coins.rules (code, amount, active) "
        "VALUES ('daily_visit_streak', 15, true) "
        "ON CONFLICT (code) DO NOTHING"
    )


def downgrade() -> None:
    # Rule row only. Awarded ledger entries stay — see THREAT/NOTES.
    op.execute("DELETE FROM coins.rules WHERE code = 'daily_visit_streak'")
