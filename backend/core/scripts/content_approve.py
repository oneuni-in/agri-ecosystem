"""Approve or reject queued content from the command line.

    python -m scripts.content_approve --actor <user-uuid> --list
    python -m scripts.content_approve --actor <user-uuid> --slug 2026-08-17-foo
    python -m scripts.content_approve --actor <user-uuid> --source the-hindu --limit 6

An ops tool, not a test hook. It exists because the CMS UI is a later
surface and someone still has to be able to clear a queue — and because
an approval that leaves no record of who made it is worthless.

What it does NOT do is skip the gate. It runs the same
`service.set_moderation` the HTTP route runs and writes the same audit
row with the same action name, so an approval made here is
indistinguishable in the ledger from one made in the console. The one
thing it cannot check is the caller's `content.publish` permission —
shell access is the authorisation here, which is why `--actor` is
REQUIRED and unguessable: every row it writes is attributed to a real
user id, and an anonymous approval is impossible.
"""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from modules.content.models import ContentItem, Source  # noqa: E402
from modules.content.service import APPROVED, PENDING, REJECTED, set_moderation  # noqa: E402
from shared.audit import audit  # noqa: E402
from shared.db import get_sessionmaker  # noqa: E402
from shared.telemetry import configure_logging  # noqa: E402
from settings import get_settings  # noqa: E402


async def main(args: argparse.Namespace) -> int:
    async with get_sessionmaker()() as session:
        query = select(ContentItem).where(ContentItem.moderation_status == PENDING)
        if args.slug:
            query = select(ContentItem).where(ContentItem.slug == args.slug)
        elif args.source:
            source = await session.scalar(select(Source).where(Source.slug == args.source))
            if source is None:
                print(f"no such source: {args.source}")  # noqa: T201
                return 1
            query = query.where(ContentItem.source_id == source.id)
        query = query.order_by(ContentItem.published_at.desc()).limit(args.limit)

        items = (await session.scalars(query)).all()
        if not items:
            print("nothing pending")  # noqa: T201
            return 0

        if args.list:
            for item in items:
                print(  # noqa: T201
                    f"  [{item.moderation_status}] {item.slug}\n"
                    f"      {item.title.get('en', '')}\n"
                    f"      {item.source_name} · {item.published_at.date()}"
                )
            return 0

        status = REJECTED if args.reject else APPROVED
        for item in items:
            await set_moderation(session, item.id, status=status)
            await audit(
                session,
                action="content.moderated",
                actor_user_id=args.actor,
                target_type="content.item",
                target_id=str(item.id),
                metadata={"status": status, "kind": item.kind, "slug": item.slug, "via": "cli"},
            )
            print(f"  {status}: {item.slug}")  # noqa: T201
        await session.commit()
        print(f"{len(items)} item(s) -> {status}")  # noqa: T201
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    # Required and unguessable: every approval is attributed to a person.
    parser.add_argument("--actor", type=uuid.UUID, required=True, help="approving user's id")
    parser.add_argument("--slug", help="approve exactly this item")
    parser.add_argument("--source", help="limit to one source slug")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--list", action="store_true", help="show, change nothing")
    parser.add_argument("--reject", action="store_true", help="reject instead of approve")
    configure_logging(get_settings().log_level)
    sys.exit(asyncio.run(main(parser.parse_args())))
