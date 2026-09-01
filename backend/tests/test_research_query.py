from datetime import date

from app.services.research_query import parse_research_query


def test_parse_energy_institutional_query() -> None:
    parsed = parse_research_query("Which energy stocks have strong institutional accumulation?")
    assert parsed["sector"] == "Energy"
    assert parsed["filters"]["institutional_accumulation"] == "strong"


def test_parse_insider_and_institutional() -> None:
    parsed = parse_research_query("Show me energy stocks where insiders and institutions are both accumulating")
    assert parsed["sector"] == "Energy"
    assert parsed["filters"].get("institutional_accumulation") == "strong"
    assert parsed["filters"].get("insider_accumulation") == "positive"


def test_parse_top_accumulation_query() -> None:
    parsed = parse_research_query("Show me the top hot accumulation stocks")
    assert parsed["filters"].get("ranking") == "top"
    assert parsed["filters"].get("signal") == "ACCUMULATION"
