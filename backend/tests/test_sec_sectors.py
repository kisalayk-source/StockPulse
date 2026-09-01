from app.sec.sectors import normalize_sector, sector_matches


def test_normalize_financial_services():
    assert normalize_sector("Financial Services") == "Financials"


def test_normalize_information_technology():
    assert normalize_sector("Information Technology") == "Technology"


def test_sector_matches_normalized():
    assert sector_matches("Financial Services", "Financials")
    assert not sector_matches("Energy", "Technology")


def test_normalize_unknown_passthrough():
    assert normalize_sector("Custom Sector") == "Custom Sector"
