from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date

from app.sec.edgar import parse_sec_date
from app.sec.models import ParsedHolding


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


def parse_13f_infotable(xml_text: str, manager_name: str = "", manager_cik: str | None = None) -> list[ParsedHolding]:
    root = ET.fromstring(xml_text)
    holdings: list[ParsedHolding] = []
    for info in root.iter():
        if _local(info.tag) != "infoTable":
            continue
        child_map = {_local(child.tag): child for child in info}
        shares = _float(_text(child_map.get("sshPrnamt"))) or 0.0
        value = _float(_text(child_map.get("value")))
        cusip = _text(child_map.get("cusip")) or None
        issuer = _text(child_map.get("nameOfIssuer")) or "Unknown"
        title = _text(child_map.get("titleOfClass")) or None
        put_call = _text(child_map.get("putCall")) or None
        holdings.append(
            ParsedHolding(
                manager_name=manager_name,
                manager_cik=manager_cik,
                issuer_name=issuer,
                issuer_ticker=None,
                issuer_cusip=cusip,
                report_period=None,
                shares=shares,
                market_value=value,
                security_type=title,
                put_call=put_call if put_call else None,
            )
        )
    return holdings


def parse_13f_primary(xml_text: str) -> tuple[str | None, date | None]:
    root = ET.fromstring(xml_text)
    manager_name = None
    report_period = None
    for element in root.iter():
        tag = _local(element.tag)
        if tag in {"reportCalendarOrQuarter", "reportCalendarOrQuarterEndDate"} and element.text:
            report_period = parse_sec_date(element.text)
        if tag in {"name", "filingManagerName"} and element.text and not manager_name:
            manager_name = element.text.strip()
    return manager_name, report_period


def issuer_matches_target(issuer_name: str, ticker: str, company_name: str | None = None) -> bool:
    issuer_upper = issuer_name.upper().strip()
    ticker_upper = ticker.upper().strip()
    if re.search(rf"\b{re.escape(ticker_upper)}\b", issuer_upper):
        return True
    if company_name:
        company_upper = company_name.upper().strip()
        if company_upper and (company_upper in issuer_upper or issuer_upper in company_upper):
            return True
        company_words = [word for word in re.split(r"[^A-Z0-9]+", company_upper) if len(word) > 2]
        issuer_words = set(re.split(r"[^A-Z0-9]+", issuer_upper))
        if company_words and all(word in issuer_words for word in company_words[:2]):
            return True
    return False


def match_ticker_from_issuer(issuer_name: str, ticker_hint: str | None = None) -> str | None:
    tokens = re.findall(r"\b[A-Z]{1,5}\b", issuer_name.upper())
    guessed = tokens[0] if tokens else None
    if ticker_hint:
        return ticker_hint.upper() if issuer_matches_target(issuer_name, ticker_hint) else None
    return guessed
