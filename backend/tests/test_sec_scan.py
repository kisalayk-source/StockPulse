from app.sec.scan import ETF_TICKERS, build_scan_universe
from app.sec.sectors import normalize_sector, sector_matches


class FakeKronos:
    def scan_movers(self, limit=25, refresh=False):
        return {
            "movers": [{"symbol": "NVDA"}, {"symbol": "SPY"}],
            "gainers": [{"symbol": "AMD"}],
            "losers": [],
        }


def test_build_scan_universe_merges_blue_chip_and_movers():
    universe = build_scan_universe(FakeKronos(), cap=100)
    assert "AAPL" in universe
    assert "NVDA" in universe
    assert "AMD" in universe
    assert "SPY" not in universe
    assert len(universe) == len(set(universe))


def test_build_scan_universe_respects_cap():
    universe = build_scan_universe(FakeKronos(), cap=5)
    assert len(universe) <= 5


def test_etf_tickers_exclude_spy():
    assert "SPY" in ETF_TICKERS
