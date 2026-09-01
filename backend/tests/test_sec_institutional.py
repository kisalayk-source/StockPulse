from app.sec.normalization import (
    classify_institutional_change,
    classify_insider_transaction,
    institutional_change_pct,
)


def test_institutional_new_position() -> None:
    assert classify_institutional_change(0, 1000) == "NEW_POSITION"


def test_institutional_exit() -> None:
    assert classify_institutional_change(1000, 0) == "EXITED"


def test_institutional_increase() -> None:
    assert classify_institutional_change(100, 150) == "INCREASED"


def test_institutional_decrease() -> None:
    assert classify_institutional_change(150, 100) == "DECREASED"


def test_change_pct() -> None:
    assert institutional_change_pct(100, 150) == 50.0


def test_insider_codes() -> None:
    assert classify_insider_transaction("P") == "DISCRETIONARY_BUY"
    assert classify_insider_transaction("S") == "DISCRETIONARY_SELL"
    assert classify_insider_transaction("A") == "COMPENSATION"
    assert classify_insider_transaction("F") == "TAX_WITHHOLDING"
