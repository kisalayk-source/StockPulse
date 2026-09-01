from __future__ import annotations

SECTOR_ALIASES: dict[str, str] = {
    "energy": "Energy",
    "technology": "Technology",
    "information technology": "Technology",
    "tech": "Technology",
    "healthcare": "Healthcare",
    "health care": "Healthcare",
    "financials": "Financials",
    "financial services": "Financials",
    "financial": "Financials",
    "consumer cyclical": "Consumer Cyclical",
    "consumer defensive": "Consumer Defensive",
    "consumer staples": "Consumer Defensive",
    "consumer discretionary": "Consumer Cyclical",
    "industrials": "Industrials",
    "industrial": "Industrials",
    "utilities": "Utilities",
    "materials": "Materials",
    "basic materials": "Materials",
    "real estate": "Real Estate",
    "communication services": "Communication Services",
    "telecommunication services": "Communication Services",
}

DEFAULT_SECTOR_BUCKETS = (
    "Energy",
    "Technology",
    "Healthcare",
    "Financials",
    "Industrials",
    "Consumer Cyclical",
    "Consumer Defensive",
    "Utilities",
    "Materials",
    "Real Estate",
    "Communication Services",
)


def normalize_sector(sector: str | None) -> str | None:
    if sector is None:
        return None
    cleaned = str(sector).strip()
    if not cleaned:
        return None
    key = cleaned.lower()
    if key in SECTOR_ALIASES:
        return SECTOR_ALIASES[key]
    for alias, bucket in SECTOR_ALIASES.items():
        if alias in key or key.startswith(alias):
            return bucket
    return cleaned


def sector_matches(stored: str | None, requested: str) -> bool:
    if not stored:
        return False
    normalized = normalize_sector(stored)
    target = normalize_sector(requested) or requested
    if not normalized:
        return False
    return normalized.lower() == target.lower()
