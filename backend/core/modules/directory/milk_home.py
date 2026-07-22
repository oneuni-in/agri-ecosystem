"""Milk homepage blend (D23): compose covers() + milk products + geo into a
single pincode response with a 3-way scope discriminator, schema-driven
filter keys, and a price banner parsed from free-text price_display.

Milk-specific glue only — reuses covers/catalog/geo, rebuilds nothing.
The directory module must not import notify/audit/search (import-linter)."""

import re
import uuid
from dataclasses import dataclass
from typing import Protocol

_RUPEE_RE = re.compile(r"₹\s*(\d+)")


class ProductLike(Protocol):
    business_id: uuid.UUID
    specs: dict[str, object]
    price_display: str | None


@dataclass(frozen=True, slots=True)
class PriceBand:
    milk_type: str
    low: int
    high: int
    unit: str | None


def _rupees(text: str | None) -> list[int]:
    if not text:
        return []
    return [int(n) for n in _RUPEE_RE.findall(text)]


def compute_price_banner(products: list[ProductLike]) -> tuple[list[PriceBand], int]:
    """Group parseable ₹ prices by milk_type → (low, high) band per type.
    unit = the shared pack_size when uniform for that type, else None.
    seller_count = distinct businesses among the passed products.
    Products with no milk_type or no parseable ₹ number are skipped from
    bands (best-effort — price_display is free text)."""
    prices: dict[str, list[int]] = {}
    packs: dict[str, set[str]] = {}
    for p in products:
        milk_type = p.specs.get("milk_type")
        nums = _rupees(p.price_display)
        if not isinstance(milk_type, str) or not milk_type or not nums:
            continue
        prices.setdefault(milk_type, []).extend(nums)
        pack = p.specs.get("pack_size")
        if isinstance(pack, str):
            packs.setdefault(milk_type, set()).add(pack)

    bands: list[PriceBand] = []
    for milk_type, nums in prices.items():
        pack_set = packs.get(milk_type, set())
        unit = next(iter(pack_set)) if len(pack_set) == 1 else None
        bands.append(PriceBand(milk_type=milk_type, low=min(nums), high=max(nums), unit=unit))

    seller_count = len({p.business_id for p in products})
    return bands, seller_count
