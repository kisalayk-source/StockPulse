from __future__ import annotations

import xml.etree.ElementTree as ET

from app.sec.edgar import parse_sec_date
from app.sec.models import ParsedInsiderTransaction


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
        return float(value.replace(",", "").replace("$", ""))
    except ValueError:
        return None


def parse_form4(xml_text: str) -> list[ParsedInsiderTransaction]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    insider_name = None
    insider_title = None
    issuer_ticker = None
    transactions: list[ParsedInsiderTransaction] = []

    for element in root.iter():
        tag = _local(element.tag)
        text = _text(element)
        if tag == "rptOwnerName" and text:
            insider_name = text
        if tag in {"officerTitle", "relationshipOfficerTitle"} and text:
            insider_title = text
        if tag == "issuerTradingSymbol" and text:
            issuer_ticker = text.upper()

    for txn in root.iter():
        if _local(txn.tag) not in {"nonDerivativeTransaction", "derivativeTransaction"}:
            continue
        is_derivative = _local(txn.tag) == "derivativeTransaction"
        code = ""
        shares = 0.0
        price = None
        value = None
        txn_date = None
        shares_after = None
        ownership = None
        for child in txn.iter():
            tag = _local(child.tag)
            text = _text(child)
            if tag == "transactionCode" and text:
                code = text
            if tag == "transactionShares" and text:
                shares = _float(text) or 0.0
            if tag == "transactionPricePerShare" and text:
                price = _float(text)
            if tag == "transactionValue" and text:
                value = _float(text)
            if tag == "transactionDate" and text:
                txn_date = parse_sec_date(text)
            if tag == "sharesOwnedFollowingTransaction" and text:
                shares_after = _float(text)
            if tag == "directOrIndirectOwnership" and text:
                ownership = text
        if not code:
            continue
        if value is None and price is not None:
            value = abs(shares * price)
        transactions.append(
            ParsedInsiderTransaction(
                insider_name=insider_name or "Unknown",
                insider_title=insider_title,
                issuer_ticker=issuer_ticker,
                transaction_date=txn_date,
                filing_date=None,
                transaction_code=code.upper()[:1],
                shares=abs(shares),
                price=price,
                value=value,
                shares_owned_after=shares_after,
                ownership_type=ownership or None,
                is_derivative=is_derivative,
            )
        )
    return transactions
