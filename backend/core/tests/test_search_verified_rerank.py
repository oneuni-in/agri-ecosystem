"""M1 spec C, search half: verified hits lead each returned page. A stable
partition applied AFTER Meili returns - the index is untouched (no
sortableAttributes change, no reindex), so Meili's relevance order is
preserved exactly within each partition."""

from modules.search.service import _verified_first


def _hit(name: str, verified: bool | None) -> dict[str, object]:
    return {"id": name, "name": name, "verified": verified}


def test_verified_hits_lead() -> None:
    hits = [_hit("a", False), _hit("b", True), _hit("c", False), _hit("d", True)]
    assert [h["name"] for h in _verified_first(hits)] == ["b", "d", "a", "c"]


def test_relevance_order_is_preserved_within_each_partition() -> None:
    hits = [_hit(n, n in {"b", "d"}) for n in "abcdef"]
    result = [h["name"] for h in _verified_first(hits)]
    assert result[:2] == ["b", "d"]  # verified, in Meili's order
    assert result[2:] == ["a", "c", "e", "f"]  # unverified, in Meili's order


def test_missing_verified_field_sorts_with_unverified() -> None:
    """A doc indexed before `verified` existed must not rank up."""
    hits = [_hit("legacy", None), _hit("ver", True)]
    assert [h["name"] for h in _verified_first(hits)] == ["ver", "legacy"]


def test_empty_page_is_handled() -> None:
    assert _verified_first([]) == []
