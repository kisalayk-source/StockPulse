from __future__ import annotations

from datetime import date, datetime
from typing import Any


def parse_sec_date(value: str | None) -> date | None:
    if not value:
        return None
    raw = value.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(raw[:10], fmt).date()
        except ValueError:
            continue
    return None


def normalize_cik(cik: str | int) -> str:
    return str(int(cik)).zfill(10)


def accession_from_filename(name: str) -> str | None:
    """Extract accession from SEC filename if present."""
    if not name:
        return None
    parts = name.replace(".txt", "").split("-")
    if len(parts) >= 3 and parts[0].isdigit():
        return f"{parts[0]}-{parts[1]}-{parts[2]}"
    return None


def is_amendment(form_type: str) -> bool:
    upper = form_type.upper()
    return "/A" in upper or upper.endswith("A")


def form_family(form_type: str) -> str:
    upper = form_type.upper().replace("/A", "")
    if upper.startswith("13F"):
        return "13F"
    if upper in {"SC 13D", "13D"}:
        return "13D"
    if upper in {"SC 13G", "13G"}:
        return "13G"
    if upper == "4":
        return "4"
    return upper


def edgar_filing_url(cik: str, accession_number: str) -> str:
    cik_int = str(int(cik))
    accession_path = accession_number.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_path}"


def iter_recent_filings(submissions: dict[str, Any], form_families: set[str] | None = None) -> list[dict[str, Any]]:
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    primary_docs = recent.get("primaryDocument", [])
    results: list[dict[str, Any]] = []
    for idx, form in enumerate(forms):
        family = form_family(str(form))
        if form_families and family not in form_families:
            continue
        accession = accessions[idx] if idx < len(accessions) else None
        if not accession:
            continue
        results.append(
            {
                "form_type": str(form),
                "accession_number": str(accession),
                "filing_date": parse_sec_date(filing_dates[idx] if idx < len(filing_dates) else None),
                "report_period": parse_sec_date(report_dates[idx] if idx < len(report_dates) else None),
                "primary_document": primary_docs[idx] if idx < len(primary_docs) else None,
                "is_amendment": is_amendment(str(form)),
                "form_family": family,
            }
        )
    return results
