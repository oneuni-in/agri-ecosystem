"""Education seed contract (spec §8) — parsing and validation."""

from datetime import date
from pathlib import Path

import pytest

from scripts.education_seed_contract import (
    Bundle,
    GeoReference,
    SeedContractError,
    load_bundle,
    validate,
)
from scripts.validate_education_seed import _main


def _write(seed_dir: Path, name: str, header: str, *rows: str) -> None:
    (seed_dir / name).write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")


def test_load_bundle_reads_all_five_files(tmp_path: Path) -> None:
    _write(tmp_path, "institutions.csv", "slug,name_en", "tnau,Tamil Nadu Agricultural University")
    _write(tmp_path, "programmes.csv", "slug,name_en", "bsc-agriculture,B.Sc (Hons) Agriculture")
    _write(
        tmp_path,
        "institution_programmes.csv",
        "institution_slug,programme_slug",
        "tnau,bsc-agriculture",
    )
    _write(tmp_path, "student_resources.csv", "slug,name_en", "icar-jrf,ICAR JRF")
    _write(tmp_path, "guides.csv", "slug,title_en", "icar-counselling,ICAR counselling")

    bundle = load_bundle(tmp_path)

    assert isinstance(bundle, Bundle)
    assert bundle.institutions[0]["slug"] == "tnau"
    assert bundle.programmes[0]["name_en"] == "B.Sc (Hons) Agriculture"
    assert bundle.institution_programmes[0]["programme_slug"] == "bsc-agriculture"
    assert bundle.student_resources[0]["slug"] == "icar-jrf"
    assert bundle.guides[0]["title_en"] == "ICAR counselling"


def test_load_bundle_reports_every_missing_file_at_once(tmp_path: Path) -> None:
    _write(tmp_path, "institutions.csv", "slug,name_en", "tnau,TNAU")

    with pytest.raises(SeedContractError) as excinfo:
        load_bundle(tmp_path)

    joined = "\n".join(excinfo.value.violations)
    assert "programmes.csv" in joined
    assert "guides.csv" in joined
    # All four missing files reported in one pass, not one-at-a-time.
    assert len(excinfo.value.violations) == 4


def _write_valid_bundle(seed_dir: Path) -> None:
    _write(seed_dir, "institutions.csv", "slug,name_en", "tnau,Tamil Nadu Agricultural University")
    _write(seed_dir, "programmes.csv", "slug,name_en", "bsc-agriculture,B.Sc (Hons) Agriculture")
    _write(
        seed_dir,
        "institution_programmes.csv",
        "institution_slug,programme_slug",
        "tnau,bsc-agriculture",
    )
    _write(seed_dir, "student_resources.csv", "slug,name_en", "icar-jrf,ICAR JRF")
    _write(seed_dir, "guides.csv", "slug,title_en", "icar-counselling,ICAR counselling")


def test_load_bundle_reports_too_long_row_as_structural_violation(tmp_path: Path) -> None:
    _write_valid_bundle(tmp_path)
    # Row 2 has an extra, unheaded column — a stray comma.
    _write(
        tmp_path,
        "institutions.csv",
        "slug,name_en",
        "tnau,Tamil Nadu Agricultural University,extra",
    )

    with pytest.raises(SeedContractError) as excinfo:
        load_bundle(tmp_path)

    joined = "\n".join(excinfo.value.violations)
    assert "structure ·" in joined
    assert "institutions.csv" in joined
    assert "row 2" in joined
    # Must not be misreported as one of the numbered spec rules.
    assert not any(v.startswith("rule ") for v in excinfo.value.violations)


def test_load_bundle_reports_too_short_row_as_structural_violation(tmp_path: Path) -> None:
    _write_valid_bundle(tmp_path)
    # Row 2 is missing a trailing column — a dropped comma.
    _write(
        tmp_path, "institutions.csv", "slug,name_en,kind", "tnau,Tamil Nadu Agricultural University"
    )

    with pytest.raises(SeedContractError) as excinfo:
        load_bundle(tmp_path)

    joined = "\n".join(excinfo.value.violations)
    assert "structure ·" in joined
    assert "institutions.csv" in joined
    assert "row 2" in joined
    assert not any(v.startswith("rule ") for v in excinfo.value.violations)


TODAY = date(2026, 8, 16)
GEO = GeoReference(
    states={"tamil nadu", "punjab"},
    districts={"tamil nadu": {"coimbatore", "chennai"}},
)


def _institution(**overrides: str) -> dict[str, str]:
    row = {
        "slug": "tnau",
        "name_en": "Tamil Nadu Agricultural University",
        "kind": "state_agri_university",
        "is_government": "true",
        "parent_slug": "",
        "country_code": "IN",
        "state": "Tamil Nadu",
        "district": "Coimbatore",
        "trust": "verified",
        "status": "active",
        "merged_into_slug": "",
        "source_url": "https://tnau.ac.in/",
        "last_verified_at": "2026-08-10",
    }
    row.update(overrides)
    return row


def _guide(**overrides: str) -> dict[str, str]:
    """A guides row carrying EXACTLY the columns of the spec §8 header.

    Critically this has no `source_url` / `official_url` — guides cite their
    sources through `official_links_json`. A helper that invented one would
    test a row shape `load_bundle` can never produce.
    """
    row = {
        "slug": "icar-counselling",
        "title_en": "ICAR UG counselling",
        "title_ta": "",
        "title_hi": "",
        "kind": "counselling",
        "country_code": "IN",
        "state": "",
        "summary_en": "How ICAR AIEEA UG counselling runs, round by round.",
        "summary_ta": "",
        "summary_hi": "",
        "steps_json": '[{"title": "Register", "body": "x", "links": []}]',
        "official_links_json": '["https://icar.org.in/"]',
        "last_verified_at": "2026-08-10",
        "status": "published",
    }
    row.update(overrides)
    return row


def _violations(bundle: Bundle) -> list[str]:
    try:
        validate(bundle, GEO, today=TODAY)
    except SeedContractError as exc:
        return exc.violations
    return []


def test_valid_bundle_raises_nothing() -> None:
    assert _violations(Bundle(institutions=[_institution()])) == []


def test_rule_1_missing_source_url() -> None:
    found = _violations(Bundle(institutions=[_institution(source_url="")]))
    assert any("rule 1" in v for v in found)


def test_rule_2_verified_without_stamp_is_caught_by_rule_1() -> None:
    # Spec rule 2 (verified needs both stamps) is a strict subset of rule 1
    # (every row needs both stamps), because `listed` rows must also cite the
    # bulk list they came from. One check enforces both; rule 2 keeps its spec
    # number for traceability but has no separate branch.
    found = _violations(Bundle(institutions=[_institution(last_verified_at="")]))
    assert any("rule 1" in v for v in found)


def test_rule_3_future_stamp_rejected() -> None:
    found = _violations(Bundle(institutions=[_institution(last_verified_at="2027-01-01")]))
    assert any("rule 3" in v for v in found)


def test_rule_4_unknown_state_rejected() -> None:
    found = _violations(Bundle(institutions=[_institution(state="Atlantis", district="")]))
    assert any("rule 4" in v for v in found)


def test_rule_4_district_for_unloaded_state_rejected() -> None:
    # Punjab is a known state, but its districts have not loaded (TN-only, D8).
    found = _violations(Bundle(institutions=[_institution(state="Punjab", district="Ludhiana")]))
    assert any("rule 4" in v for v in found)


def test_rule_4_state_without_district_is_fine() -> None:
    assert _violations(Bundle(institutions=[_institution(state="Punjab", district="")])) == []


def test_rule_5_indian_row_without_state() -> None:
    found = _violations(Bundle(institutions=[_institution(state="", district="")]))
    assert any("rule 5" in v for v in found)


def test_rule_6_reserved_slug_rejected() -> None:
    found = _violations(Bundle(institutions=[_institution(slug="abroad")]))
    assert any("rule 6" in v for v in found)


def test_rule_7_duplicate_slug_rejected() -> None:
    found = _violations(Bundle(institutions=[_institution(), _institution()]))
    assert any("rule 7" in v for v in found)


def test_rule_8_dangling_parent_slug() -> None:
    found = _violations(Bundle(institutions=[_institution(parent_slug="nowhere")]))
    assert any("rule 8" in v for v in found)


def test_rule_9_merged_without_target() -> None:
    found = _violations(Bundle(institutions=[_institution(status="merged")]))
    assert any("rule 9" in v for v in found)


def test_rule_10_listed_institution_cannot_carry_numbers() -> None:
    bundle = Bundle(
        institutions=[_institution(trust="listed")],
        programmes=[
            {
                "slug": "bsc-agriculture",
                "name_en": "B.Sc (Hons) Agriculture",
                "level": "ug",
                "discipline": "agriculture",
                "duration_months": "48",
            }
        ],
        institution_programmes=[
            {
                "institution_slug": "tnau",
                "programme_slug": "bsc-agriculture",
                "intake_seats": "120",
                "annual_fees_inr": "",
                "fee_note": "",
                "admission_route": "",
                "source_url": "https://tnau.ac.in/admissions",
                "last_verified_at": "2026-08-10",
            }
        ],
    )
    found = _violations(bundle)
    assert any("rule 10" in v for v in found)


def test_rule_11_unknown_enum_rejected() -> None:
    found = _violations(Bundle(institutions=[_institution(kind="Agricultural University")]))
    assert any("rule 11" in v for v in found)


def test_rule_12_foreign_country_needs_foreign_kind() -> None:
    found = _violations(
        Bundle(
            institutions=[
                _institution(
                    slug="wageningen",
                    country_code="NL",
                    state="",
                    district="",
                    kind="state_agri_university",
                )
            ]
        )
    )
    assert any("rule 12" in v for v in found)


def test_every_violation_reported_in_one_pass() -> None:
    found = _violations(
        Bundle(institutions=[_institution(slug="abroad", source_url="", kind="nonsense")])
    )
    assert len(found) >= 3


def test_rule_8_dangling_institution_slug_in_institution_programmes() -> None:
    bundle = Bundle(
        institutions=[_institution()],
        programmes=[
            {
                "slug": "bsc-agriculture",
                "name_en": "B.Sc (Hons) Agriculture",
                "level": "ug",
                "discipline": "agriculture",
                "duration_months": "48",
            }
        ],
        institution_programmes=[
            {
                "institution_slug": "nowhere",
                "programme_slug": "bsc-agriculture",
                "intake_seats": "",
                "annual_fees_inr": "",
                "fee_note": "",
                "admission_route": "",
                "source_url": "https://tnau.ac.in/admissions",
                "last_verified_at": "2026-08-10",
            }
        ],
    )
    found = _violations(bundle)
    assert any("rule 8" in v and "institution_slug" in v for v in found)


def test_rule_8_dangling_programme_slug_in_institution_programmes() -> None:
    bundle = Bundle(
        institutions=[_institution()],
        institution_programmes=[
            {
                "institution_slug": "tnau",
                "programme_slug": "nowhere",
                "intake_seats": "",
                "annual_fees_inr": "",
                "fee_note": "",
                "admission_route": "",
                "source_url": "https://tnau.ac.in/admissions",
                "last_verified_at": "2026-08-10",
            }
        ],
    )
    found = _violations(bundle)
    assert any("rule 8" in v and "programme_slug" in v for v in found)


def test_rule_1_guide_cites_through_official_links_json() -> None:
    # guides.csv has no source_url/official_url column (spec §8) — a guide's
    # citation IS official_links_json. A real, complete guide row must pass.
    assert _violations(Bundle(guides=[_guide()])) == []


def test_rule_1_guide_without_official_links_rejected() -> None:
    found = _violations(Bundle(guides=[_guide(official_links_json="[]")]))
    assert any("rule 1" in v for v in found)


def test_rule_1_guide_with_blank_official_links_rejected() -> None:
    found = _violations(Bundle(guides=[_guide(official_links_json="")]))
    assert any("rule 1" in v for v in found)


def test_rule_3_still_applies_to_guides() -> None:
    # The official_links_json branch must not skip the date checks.
    found = _violations(Bundle(guides=[_guide(last_verified_at="2027-01-01")]))
    assert any("rule 3" in v for v in found)


def test_guide_with_unparseable_official_links_is_a_structural_violation() -> None:
    found = _violations(Bundle(guides=[_guide(official_links_json="[not json")]))
    assert any("official_links_json" in v for v in found)


def test_valid_bundle_across_all_five_collections_raises_nothing() -> None:
    # test_valid_bundle_raises_nothing only ever exercises institutions; this
    # covers the happy path of every other loop (programmes,
    # institution_programmes, student_resources, guides) so a regression in
    # any of them is caught here instead of silently passing CI.
    bundle = Bundle(
        institutions=[_institution()],
        programmes=[
            {
                "slug": "bsc-agriculture",
                "name_en": "B.Sc (Hons) Agriculture",
                "level": "ug",
                "discipline": "agriculture",
                "duration_months": "48",
            }
        ],
        institution_programmes=[
            {
                "institution_slug": "tnau",
                "programme_slug": "bsc-agriculture",
                "intake_seats": "120",
                "annual_fees_inr": "50000",
                "fee_note": "",
                "admission_route": "TNEA counselling",
                "source_url": "https://tnau.ac.in/admissions",
                "last_verified_at": "2026-08-10",
            }
        ],
        student_resources=[
            {
                "slug": "icar-jrf",
                "name_en": "ICAR JRF",
                "kind": "scholarship",
                "category": "entrance",
                "scope": "india",
                "provider": "ICAR",
                "levels": "ug,pg",
                "benefit": "Monthly stipend",
                "official_url": "https://icar.gov.in/jrf",
                "last_verified_at": "2026-08-10",
                "status": "active",
            }
        ],
        guides=[_guide()],
    )
    assert _violations(bundle) == []


def test_cli_passes_on_the_committed_bundle() -> None:
    # The committed seed bundle must ALWAYS validate — this is the gate every
    # data PR has to pass.
    assert _main([]) == 0


def test_cli_reports_violations_and_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in (
        "institutions.csv",
        "programmes.csv",
        "institution_programmes.csv",
        "student_resources.csv",
        "guides.csv",
    ):
        (tmp_path / name).write_text("slug\n", encoding="utf-8")
    (tmp_path / "institutions.csv").write_text(
        "slug,name_en,kind,country_code,state,trust,status,source_url,last_verified_at\n"
        "abroad,Nowhere,nonsense,IN,Atlantis,verified,active,,\n",
        encoding="utf-8",
    )

    assert _main(["--seed-dir", str(tmp_path)]) == 1
    printed = capsys.readouterr().out
    assert "rule 6" in printed
    assert "rule 4" in printed
