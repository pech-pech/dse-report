"""Reader-facing names for the engine's shortened sector names, applied to the finished report."""
from __future__ import annotations

import re
from typing import Any

SECTOR_NAMES = {
    "FuelPower": "Fuel & Power", "FoodAllied": "Food & Allied", "PharmaChem": "Pharma & Chemicals",
    "ServRealEst": "Services & Real Estate", "TravelLeisur": "Travel & Leisure", "PaperPrint": "Paper & Printing",
    "Financial In": "Financial Institutions", "Misc": "Miscellaneous",
}
_PATTERN = re.compile(r"(?<![\w&])(" + "|".join(re.escape(k) for k in sorted(SECTOR_NAMES, key=len, reverse=True)) + r")(?![\w])")


def sector_name(name: str) -> str:
    return SECTOR_NAMES.get(name, name)


def relabel(value: Any) -> Any:
    """A copy of ``value`` with every engine sector name, in keys and in text, replaced by its display name."""
    if isinstance(value, str):
        return _PATTERN.sub(lambda m: SECTOR_NAMES[m.group(1)], value)
    if isinstance(value, dict):
        return {relabel(k): relabel(v) for k, v in value.items()}
    if isinstance(value, list):
        return [relabel(v) for v in value]
    return value
