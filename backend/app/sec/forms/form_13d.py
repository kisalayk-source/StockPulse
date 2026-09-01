from __future__ import annotations

import xml.etree.ElementTree as ET

from app.sec.edgar import parse_sec_date
from app.sec.models import ParsedBeneficialOwnership


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _text(element: ET.Element | None) -> str:
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def _float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def parse_13d(xml_text: str, form_type: str = "SC 13D", is_amendment: bool = False) -> ParsedBeneficialOwnership | None:
    root = ET.fromstring(xml_text)
    reporter = None
    issuer = None
    shares = None
    pct = None
    purpose_parts: list[str] = []
    passive = False
    for element in root.iter():
        tag = _local(element.tag)
        text = _text(element)
        if tag in {"rptOwnerName", "reportingPersonName"} and text:
            reporter = text
        if tag in {"issuerName", "subjectCompanyName"} and text:
            issuer = text
        if tag in {"sshPrnamt", "amountBeneficiallyOwned"} and text:
            shares = _float(text)
        if tag in {"pctOwnership", "percentOfClass"} and text:
            pct = _float(text.replace("%", ""))
            if pct is not None and pct > 1:
                pct = pct / 100.0
        if tag in {"purposeOfTransaction", "purposeText"} and text:
            purpose_parts.append(text)
        if tag == "passiveInvestor" and text.lower() in {"y", "yes", "true", "1"}:
            passive = True
    if not reporter and not issuer:
        return None
    purpose = " ".join(purpose_parts) if purpose_parts else None
    activist_keywords = ("activist", "change control", "board", "proxy", "management regarding")
    activist = bool(purpose and any(k in purpose.lower() for k in activist_keywords))
    return ParsedBeneficialOwnership(
        reporter_name=reporter or "Unknown",
        reporter_cik=None,
        issuer_name=issuer or "Unknown",
        issuer_ticker=None,
        shares=shares,
        ownership_pct=pct,
        form_type=form_type,
        filing_date=None,
        purpose=purpose,
        passive_flag=passive or not activist,
        is_amendment=is_amendment,
    )
