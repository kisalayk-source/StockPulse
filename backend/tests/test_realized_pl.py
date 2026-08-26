from app.config import Settings
from app.services.providers import AlpacaService, fifo_realized_pl


def test_fifo_long_partial_close() -> None:
    fills = [
        {"symbol": "AAPL", "side": "buy", "qty": 10, "price": 100},
        {"symbol": "AAPL", "side": "sell", "qty": 4, "price": 110},
    ]
    # (110 - 100) * 4 = 40; 6 shares still open
    assert fifo_realized_pl(fills) == 40.0


def test_fifo_multiple_lots() -> None:
    fills = [
        {"symbol": "NVDA", "side": "buy", "qty": 2, "price": 100},
        {"symbol": "NVDA", "side": "buy", "qty": 3, "price": 120},
        {"symbol": "NVDA", "side": "sell", "qty": 4, "price": 150},
    ]
    # Close 2 @100 and 2 @120: (150-100)*2 + (150-120)*2 = 100 + 60 = 160
    assert fifo_realized_pl(fills) == 160.0


def test_fifo_short_then_cover() -> None:
    fills = [
        {"symbol": "TSLA", "side": "sell", "qty": 5, "price": 200},
        {"symbol": "TSLA", "side": "buy", "qty": 5, "price": 180},
    ]
    # Cover short: (200 - 180) * 5 = 100
    assert fifo_realized_pl(fills) == 100.0


def test_fifo_open_only_is_zero() -> None:
    fills = [
        {"symbol": "MSFT", "side": "buy", "qty": 8, "price": 300},
    ]
    assert fifo_realized_pl(fills) == 0.0


def test_realized_pl_service_paginates_and_sorts() -> None:
    pages = [
        [
            {
                "id": "2",
                "activity_type": "FILL",
                "symbol": "AAPL",
                "side": "sell",
                "qty": "2",
                "price": "110",
                "transaction_time": "2024-02-01T15:00:00Z",
            },
            {
                "id": "1",
                "activity_type": "FILL",
                "symbol": "AAPL",
                "side": "buy",
                "qty": "2",
                "price": "100",
                "transaction_time": "2024-01-01T15:00:00Z",
            },
        ],
        [],
    ]

    class TradingClient:
        def get(self, path: str, data=None, **kwargs):
            assert path == "/account/activities"
            return pages.pop(0)

    service = AlpacaService(Settings(_env_file=None))
    service._trading = lambda mode: TradingClient()
    result = service.realized_pl("paper")
    assert result["realized_pl"] == 20.0
    assert result["fill_count"] == 2
    assert result["as_of"]
