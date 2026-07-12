"""Append-only, tamper-evident audit log (D12).

Entries hash-chain per UTC day; the first entry of a day chains from
sha256("genesis:<day>"). audit() writes in the CALLER's transaction, so the
record commits or rolls back atomically with the action it describes. Same-day
appends serialize on a pg advisory xact lock: the chain cannot fork under
concurrency and the schema needs no UPDATE grant anywhere (the app role
physically cannot rewrite history; verify_chain() proves nobody else did).

PII rule: metadata carries agri_ids and hashes - never phone numbers, message
bodies, or addresses. Deleting the newest entry of a day is the one mutation
the chain alone cannot see; the grant matrix (app_rt: INSERT+SELECT only) is
what closes that hole for the application role.
"""

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from typing import Any

import uuid6
from sqlalchemy import TIMESTAMP, Date, Integer, Text, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class AuditEntry(Base):
    """audit.entries. Deliberately no TimestampMixin: immutable rows have no
    updated_at, and created_at is set client-side because it is hashed."""

    __tablename__ = "entries"
    __table_args__ = {"schema": "audit"}

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # attribute is `meta`: `metadata` collides with DeclarativeBase.metadata
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata", postgresql.JSONB, nullable=False, default=dict
    )
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    chain_day: Mapped[date] = mapped_column(Date, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    prev_hash: Mapped[str] = mapped_column(Text, nullable=False)
    entry_hash: Mapped[str] = mapped_column(Text, nullable=False)


def genesis_hash(day: date) -> str:
    return hashlib.sha256(f"genesis:{day.isoformat()}".encode()).hexdigest()


def _canonical(entry: AuditEntry) -> str:
    """Deterministic serialization of every hashed field; any drift here is a
    chain-format change and needs a re-anchor plan."""
    return json.dumps(
        {
            "id": str(entry.id),
            "created_at": entry.created_at.isoformat(),
            "actor_user_id": str(entry.actor_user_id) if entry.actor_user_id else None,
            "action": entry.action,
            "target_type": entry.target_type,
            "target_id": entry.target_id,
            "metadata": entry.meta,
            "ip": entry.ip,
            "chain_day": entry.chain_day.isoformat(),
            "seq": entry.seq,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def compute_entry_hash(entry: AuditEntry) -> str:
    return hashlib.sha256((entry.prev_hash + _canonical(entry)).encode()).hexdigest()


async def audit(
    session: AsyncSession,
    *,
    action: str,
    actor_user_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    ip: str | None = None,
    now: datetime | None = None,
) -> AuditEntry:
    """Append one entry in the caller's transaction. `now` is injectable for
    tests only; production callers never pass it."""
    now = now or datetime.now(UTC)
    day = now.date()
    # serialize same-day appends; xact lock releases with the transaction
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))").bindparams(key=f"audit:{day}")
    )
    last = await session.scalar(
        select(AuditEntry)
        .where(AuditEntry.chain_day == day)
        .order_by(AuditEntry.seq.desc())
        .limit(1)
    )
    entry = AuditEntry(
        id=uuid6.uuid7(),
        created_at=now,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        meta=metadata or {},
        ip=ip,
        chain_day=day,
        seq=(last.seq + 1) if last is not None else 1,
        prev_hash=last.entry_hash if last is not None else genesis_hash(day),
    )
    entry.entry_hash = compute_entry_hash(entry)
    session.add(entry)
    await session.flush()
    return entry
