"""Education seed contract (spec §8) — parsing."""

from pathlib import Path

import pytest

from scripts.education_seed_contract import Bundle, SeedContractError, load_bundle


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
