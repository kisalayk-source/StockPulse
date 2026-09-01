from datetime import date
from pathlib import Path

import pytest

from app.sec.forms.form_13d import parse_13d
from app.sec.forms.form_13f import parse_13f_infotable, parse_13f_primary
from app.sec.forms.form_4 import parse_form4
from app.sec.forms.form_13g import parse_13g

FIXTURES = Path(__file__).parent / "fixtures" / "sec"


def test_parse_13f_infotable() -> None:
    xml_text = (FIXTURES / "form_13f_infotable.xml").read_text(encoding="utf-8")
    holdings = parse_13f_infotable(xml_text, "Fund A", "0001234567")
    assert len(holdings) == 1
    assert holdings[0].shares == 150000
    assert holdings[0].issuer_name == "EXXON MOBIL CORP"


def test_parse_13f_primary() -> None:
    xml_text = (FIXTURES / "form_13f_primary.xml").read_text(encoding="utf-8")
    manager, period = parse_13f_primary(xml_text)
    assert manager == "Fund A Capital LLC"
    assert period == date(2024, 6, 30)


def test_parse_13d() -> None:
    xml_text = (FIXTURES / "form_13d.xml").read_text(encoding="utf-8")
    parsed = parse_13d(xml_text)
    assert parsed is not None
    assert parsed.ownership_pct == pytest.approx(0.052, rel=1e-3)
    assert parsed.passive_flag is False


def test_parse_13g_marks_passive() -> None:
    xml_text = (FIXTURES / "form_13d.xml").read_text(encoding="utf-8")
    parsed = parse_13g(xml_text)
    assert parsed is not None
    assert parsed.passive_flag is True


def test_parse_form4() -> None:
    xml_text = (FIXTURES / "form_4.xml").read_text(encoding="utf-8")
    txns = parse_form4(xml_text)
    assert len(txns) == 2
    purchase = next(item for item in txns if item.transaction_code == "P")
    assert purchase.insider_title == "Chief Executive Officer"
    assert purchase.shares == 10000


import pytest
