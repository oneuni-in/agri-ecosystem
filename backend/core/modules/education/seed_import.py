"""Import the committed education seed bundle into Postgres.

This module imports `scripts.education_seed_contract` **verbatim** — the same
module `validate_education_seed` runs in CI. That is the whole design: the
importer cannot hold a looser idea of "valid" than the gate does, because
there is only one idea and both call it. Duplicating any rule here, however
small, would create a second copy that drifts.

Validation runs against the WHOLE bundle before a single row is written, and
a failure raises before the first `session.add`. A partial import is worse
than no import: it leaves a corpus that looks populated and is wrong.

Idempotent by slug. Reruns update in place rather than duplicating, so the
same bundle can be re-imported after a data PR without a truncate.

Runs as the table OWNER, not `app_rt` — `education` grants app_rt SELECT and
nothing else (0049, spec section 4). That is why `scripts/import_education_seed.py`
connects with the admin URL and why the tests take `owner_session`.
"""

from __future__ import annotations

import csv
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.education_seed_contract import (
    SeedContractError,
    load_bundle,
    load_geo_reference,
    validate,
)
from shared.geo.models import State

from .models import Guide, Institution, InstitutionProgramme, Programme, StudentResource


@dataclass
class ImportReport:
    created: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    updated: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def summary(self) -> str:
        parts = []
        for table in sorted(set(self.created) | set(self.updated)):
            parts.append(f"{table}: +{self.created[table]} ~{self.updated[table]}")
        return "  ".join(parts) or "nothing to do"


def _or_none(value: str | None) -> str | None:
    """CSV has no null. An empty cell is absent, not an empty string."""
    return (value or "").strip() or None


def _bool_or_none(value: str | None) -> bool | None:
    return {"true": True, "false": False}.get((value or "").strip().lower())


def _int_or_none(value: str | None) -> int | None:
    text = (value or "").strip()
    return int(text) if text else None


def _json_or_none(value: str | None) -> Any:
    text = (value or "").strip()
    return json.loads(text) if text else None


def _decimal_or_none(value: str | None) -> Decimal | None:
    text = (value or "").strip()
    return Decimal(text) if text else None


def _date(value: str) -> date:
    return date.fromisoformat(value.strip())


async def _state_ids(session: AsyncSession) -> dict[str, uuid.UUID]:
    """State NAME (lowercased) -> geo.states.id.

    Read from the DATABASE, not from states.csv, because state_id is a real
    FK and the CSV does not carry the UUID the constraint needs. This couples
    the import to geo being loaded first — correctly so: without it every
    institution would import with a null state and the /colleges state pages
    would come up empty with nothing having failed.
    """
    rows = (await session.execute(select(State.name, State.id))).all()
    if not rows:
        raise SeedContractError(
            ["geo.states is empty — run scripts/load_geo.py before importing education"]
        )
    return {name.strip().lower(): state_id for name, state_id in rows}


def _district_lgd_codes(geo_dir: Path) -> dict[str, int]:
    """District NAME (lowercased) -> LGD code, the plain integer district_id holds.

    From the CSV, not the DB, because district_id is not an FK (see models.py).
    The file is Tamil Nadu only until D65, so a college outside TN resolves to
    None here — which is honest: we do not know its district id. 70 of the 772
    seed rows carry a district at all, and all 70 are Tamil Nadu.
    """
    with (geo_dir / "districts.csv").open(encoding="utf-8") as fh:
        return {row["name"].strip().lower(): int(row["lgd_code"]) for row in csv.DictReader(fh)}


async def import_bundle(
    session: AsyncSession, seed_dir: Path, geo_dir: Path, *, today: date
) -> ImportReport:
    bundle = load_bundle(seed_dir)
    geo = load_geo_reference(geo_dir)
    validate(bundle, geo, today=today)  # raises SeedContractError; nothing written

    report = ImportReport()
    state_ids = await _state_ids(session)
    district_ids = _district_lgd_codes(geo_dir)

    # ── institutions, pass 1: everything except the two self-references ──
    # parent_slug and merged_into_slug can point at a row further down the
    # file, so they cannot be resolved until every institution has an id.
    known = {row.slug: row for row in (await session.scalars(select(Institution))).all()}
    for row in bundle.institutions:
        institution = known.get(row["slug"])
        if institution is None:
            institution = Institution(slug=row["slug"])
            session.add(institution)
            known[row["slug"]] = institution
            report.created["institutions"] += 1
        else:
            report.updated["institutions"] += 1
        institution.name_en = row["name_en"]
        institution.name_ta = _or_none(row.get("name_ta"))
        institution.name_hi = _or_none(row.get("name_hi"))
        institution.short_name = _or_none(row.get("short_name"))
        institution.kind = row["kind"]
        institution.is_government = _bool_or_none(row.get("is_government"))
        institution.country_code = _or_none(row.get("country_code")) or "IN"
        institution.state_id = state_ids.get((row.get("state") or "").strip().lower())
        institution.district_id = district_ids.get((row.get("district") or "").strip().lower())
        institution.pincode = _or_none(row.get("pincode"))
        institution.lat = _decimal_or_none(row.get("lat"))
        institution.lng = _decimal_or_none(row.get("lng"))
        institution.address = _or_none(row.get("address"))
        institution.website = _or_none(row.get("website"))
        institution.contact_phone = _or_none(row.get("contact_phone"))
        institution.contact_email = _or_none(row.get("contact_email"))
        institution.established_year = _int_or_none(row.get("established_year"))
        institution.accreditation = _json_or_none(row.get("accreditation_json"))
        institution.trust = row["trust"]
        institution.status = row["status"]
        institution.source_url = row["source_url"]
        institution.last_verified_at = _date(row["last_verified_at"])
    await session.flush()

    # ── institutions, pass 2: the self-references ──
    for row in bundle.institutions:
        institution = known[row["slug"]]
        parent = _or_none(row.get("parent_slug"))
        merged = _or_none(row.get("merged_into_slug"))
        institution.parent_id = known[parent].id if parent else None
        institution.merged_into_id = known[merged].id if merged else None
    await session.flush()

    # ── programmes ──
    programmes = {row.slug: row for row in (await session.scalars(select(Programme))).all()}
    for row in bundle.programmes:
        programme = programmes.get(row["slug"])
        if programme is None:
            programme = Programme(slug=row["slug"])
            session.add(programme)
            programmes[row["slug"]] = programme
            report.created["programmes"] += 1
        else:
            report.updated["programmes"] += 1
        programme.name_en = row["name_en"]
        programme.name_ta = _or_none(row.get("name_ta"))
        programme.name_hi = _or_none(row.get("name_hi"))
        programme.level = row["level"]
        programme.discipline = row["discipline"]
        programme.duration_months = _int_or_none(row.get("duration_months"))
        programme.description_en = _or_none(row.get("description_en"))
        programme.description_ta = _or_none(row.get("description_ta"))
        programme.description_hi = _or_none(row.get("description_hi"))
    await session.flush()

    # ── institution_programmes, keyed on the (institution, programme) pair ──
    offerings = {
        (row.institution_id, row.programme_id): row
        for row in (await session.scalars(select(InstitutionProgramme))).all()
    }
    for row in bundle.institution_programmes:
        institution_id = known[row["institution_slug"]].id
        programme_id = programmes[row["programme_slug"]].id
        offering = offerings.get((institution_id, programme_id))
        if offering is None:
            offering = InstitutionProgramme(
                institution_id=institution_id, programme_id=programme_id
            )
            session.add(offering)
            offerings[(institution_id, programme_id)] = offering
            report.created["institution_programmes"] += 1
        else:
            report.updated["institution_programmes"] += 1
        offering.intake_seats = _int_or_none(row.get("intake_seats"))
        offering.annual_fees_inr = _int_or_none(row.get("annual_fees_inr"))
        offering.fee_note = _or_none(row.get("fee_note"))
        offering.admission_route = _or_none(row.get("admission_route"))
        offering.source_url = row["source_url"]
        offering.last_verified_at = _date(row["last_verified_at"])

    # ── student_resources ──
    resources = {row.slug: row for row in (await session.scalars(select(StudentResource))).all()}
    for row in bundle.student_resources:
        resource = resources.get(row["slug"])
        if resource is None:
            resource = StudentResource(slug=row["slug"])
            session.add(resource)
            resources[row["slug"]] = resource
            report.created["student_resources"] += 1
        else:
            report.updated["student_resources"] += 1
        resource.name_en = row["name_en"]
        resource.name_ta = _or_none(row.get("name_ta"))
        resource.name_hi = _or_none(row.get("name_hi"))
        resource.kind = row["kind"]
        resource.category = _or_none(row.get("category"))
        resource.scope = row["scope"]
        resource.provider = _or_none(row.get("provider"))
        resource.levels = _or_none(row.get("levels"))
        resource.eligibility_en = _or_none(row.get("eligibility_en"))
        resource.eligibility_ta = _or_none(row.get("eligibility_ta"))
        resource.eligibility_hi = _or_none(row.get("eligibility_hi"))
        resource.benefit = _or_none(row.get("benefit"))
        resource.applies_to = _json_or_none(row.get("applies_to_json"))
        resource.window = _json_or_none(row.get("window_json"))
        resource.official_url = row["official_url"]
        resource.last_verified_at = _date(row["last_verified_at"])
        resource.status = row["status"]

    # ── guides ──
    guides = {row.slug: row for row in (await session.scalars(select(Guide))).all()}
    for row in bundle.guides:
        guide = guides.get(row["slug"])
        if guide is None:
            guide = Guide(slug=row["slug"])
            session.add(guide)
            guides[row["slug"]] = guide
            report.created["guides"] += 1
        else:
            report.updated["guides"] += 1
        guide.title_en = row["title_en"]
        guide.title_ta = _or_none(row.get("title_ta"))
        guide.title_hi = _or_none(row.get("title_hi"))
        guide.kind = row["kind"]
        guide.country_code = _or_none(row.get("country_code"))
        guide.state_id = state_ids.get((row.get("state") or "").strip().lower())
        guide.summary_en = _or_none(row.get("summary_en"))
        guide.summary_ta = _or_none(row.get("summary_ta"))
        guide.summary_hi = _or_none(row.get("summary_hi"))
        guide.steps = _json_or_none(row.get("steps_json"))
        guide.official_links = _json_or_none(row.get("official_links_json"))
        guide.last_verified_at = _date(row["last_verified_at"])
        guide.status = row["status"]

    await session.flush()
    return report
