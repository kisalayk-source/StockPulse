"""Generate docs/StockPulse.pdf from structured sections (fpdf2)."""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "StockPulse.pdf"
PURPLE = (44, 33, 84)
MUTED = (91, 101, 115)
ACCENT = (93, 67, 163)
RULE = (217, 211, 234)
INK = (27, 36, 48)


class Manual(FPDF):
    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*MUTED)
        self.cell(0, 8, "StockPulse documentation", align="L")
        self.cell(0, 8, "Personal tooling", align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*RULE)
        self.line(self.l_margin, 16, self.w - self.r_margin, 16)
        self.ln(6)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 8, f"Page {self.page_no()}  |  Not investment advice", align="C")

    def cover(self) -> None:
        self.add_page()
        self.set_fill_color(*PURPLE)
        self.rect(0, 0, self.w, 18, "F")
        self.ln(42)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*ACCENT)
        self.cell(0, 8, "PRODUCT AND OPERATIONS GUIDE", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "B", 32)
        self.set_text_color(*PURPLE)
        self.cell(0, 16, "StockPulse", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 13)
        self.set_text_color(*INK)
        self.multi_cell(
            0,
            7,
            "Paper-first trading dashboard, Kronos forecasts, WallStreetBets research, "
            "and a look-ahead-safe historical backtester.",
        )
        self.ln(10)
        self.set_font("Helvetica", "", 11)
        self.set_text_color(*MUTED)
        for line in (
            "Version: unreleased personal build",
            "Date: 19 August 2026",
            "Local site: http://localhost:5173",
            "LAN: http://192.168.86.197:5173",
        ):
            self.cell(0, 7, line, new_x="LMARGIN", new_y="NEXT")
        self.ln(16)
        self.set_fill_color(253, 244, 244)
        self.set_draw_color(181, 45, 57)
        self.set_text_color(90, 28, 34)
        self.set_font("Helvetica", "", 10)
        self.multi_cell(
            0,
            6,
            "Not investment advice. Forecasts are research outputs. Broker acceptance "
            "does not guarantee execution. Use paper "
            "mode until you understand the risk controls.",
            border="L",
            fill=True,
            padding=4,
        )

    def heading(self, text: str) -> None:
        self.set_x(self.l_margin)
        self.ln(4)
        self.set_font("Helvetica", "B", 15)
        self.set_text_color(*PURPLE)
        self.cell(0, 10, text, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*RULE)
        y = self.get_y()
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.ln(4)

    def subhead(self, text: str) -> None:
        self.ln(2)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(61, 53, 88)
        self.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")

    def body(self, text: str) -> None:
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "", 11)
        self.set_text_color(*INK)
        self.multi_cell(0, 6, text)
        self.ln(1)

    def bullets(self, items: list[str]) -> None:
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "", 11)
        self.set_text_color(*INK)
        for item in items:
            self.set_x(self.l_margin)
            self.multi_cell(0, 6, f"  -  {item}")
        self.ln(1)

    def numbered(self, items: list[str]) -> None:
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "", 11)
        self.set_text_color(*INK)
        for i, item in enumerate(items, 1):
            self.set_x(self.l_margin)
            self.multi_cell(0, 6, f"  {i}.  {item}")
        self.ln(1)

    def code(self, text: str) -> None:
        self.set_x(self.l_margin)
        # Light snippet surface so dark printer/PDF viewers stay readable.
        self.set_fill_color(243, 241, 248)
        self.set_draw_color(*RULE)
        self.set_text_color(*INK)
        self.set_font("Courier", "", 9)
        self.multi_cell(0, 5, text, border=1, fill=True, padding=3)
        self.ln(3)

    def add_table(self, headers: list[str], rows: list[list[str]], widths: list[float] | None = None) -> None:
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*INK)
        self.set_draw_color(213, 219, 227)
        kwargs: dict[str, object] = {
            "line_height": 5.2,
            "text_align": "LEFT",
            "borders_layout": "ALL",
        }
        if widths is not None:
            kwargs["col_widths"] = widths
        with self.table(**kwargs) as table:
            head = table.row()
            self.set_font("Helvetica", "B", 9)
            for header in headers:
                head.cell(header)
            self.set_font("Helvetica", "", 9)
            for values in rows:
                row = table.row()
                for value in values:
                    row.cell(value)
        self.set_x(self.l_margin)
        self.ln(3)


def build() -> None:
    pdf = Manual(format="Letter", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_title("StockPulse documentation")
    pdf.set_author("StockPulse")
    pdf.cover()

    pdf.add_page()
    pdf.heading("1. Overview")
    pdf.body(
        "StockPulse is a personal trading workstation. It shows paper (or live) market data, "
        "Kronos probabilistic forecasts, news and public sentiment, a background scan of predicted "
        "movers, and your open broker positions. Orders are manual only. Forecasts never submit trades."
    )
    pdf.body(
        "The repository also contains Kronos itself (tokenizer, predictor, fine-tuning examples) "
        "and a separate production-grade backtester in kronos_backtest/."
    )

    pdf.heading("2. Architecture")
    pdf.add_table(
        ["Layer", "Path", "Role"],
        [
            ["Dashboard", "frontend/", "React + TypeScript + Vite. Proxies /api to the backend."],
            ["API", "backend/", "FastAPI on loopback :8000. Alpaca, Finnhub, Kronos."],
            ["Model", "model/", "Kronos predictor/tokenizer. Loaded on first forecast."],
            ["Backtester", "kronos_backtest/", "Look-ahead-safe engine, costs, walk-forward, reports."],
            ["Legacy demo", "webui/", "Unchanged Flask demo. Not required for StockPulse."],
        ],
        [28, 38, 124],
    )
    pdf.body(
        "The backend binds to 127.0.0.1:8000. LAN clients reach it only through the frontend "
        "proxy on port 5173. Do not expose the API directly on the network unless you intend to."
    )
    pdf.subhead("Request path")
    pdf.code(
        "Browser (localhost or LAN)\n"
        "  -> Vite preview :5173\n"
        "       -> static dashboard\n"
        "       -> /api/v1/* proxy -> FastAPI :8000 (loopback)\n"
        "            -> Alpaca / Finnhub / Kronos"
    )

    pdf.heading("3. Local hosting")
    pdf.body(
        "StockPulse is meant to run as a normal Windows website, not inside a Cursor terminal. "
        "Two Task Scheduler tasks start at Windows logon:"
    )
    pdf.add_table(
        ["Task", "Script", "Listens"],
        [
            ["KronosWeb", "scripts/start-kronos-web.ps1", "0.0.0.0:5173  Vite preview of the production build"],
            ["KronosAPI", "scripts/start-kronos-api.ps1", "127.0.0.1:8000  uvicorn"],
        ],
        [32, 62, 96],
    )
    pdf.body(
        "Open http://localhost:5173 in Edge or Chrome. Other devices on the same Wi-Fi can use "
        "http://192.168.86.197:5173 if the PC firewall allows inbound TCP 5173."
    )
    pdf.subhead("Manual start")
    pdf.code("powershell -ExecutionPolicy Bypass -File scripts/publish-kronos-lan.ps1 -SkipChecks")
    pdf.body(
        "That script builds the frontend if needed, starts both processes detached, and prints "
        "the local and LAN URLs. After application code changes, run backend and frontend checks "
        "first. Documentation-only changes do not need republishing."
    )
    pdf.subhead("Logs")
    pdf.bullets(
        [
            "runtime-logs/web.log  website (scheduled task)",
            "backend/logs/api.log  API (scheduled task)",
            "runtime-logs/backend.*.log  API when started via the LAN publish script",
        ]
    )

    pdf.heading("4. Dashboard")
    pdf.bullets(
        [
            "Search: symbol or company name; results stay in a scrollable list.",
            "Market light: US session pre-market, regular, after hours, or closed (America/New_York).",
            "Quote card: last, change, OHLC, volume, market cap, P/E, EPS, dividend yield.",
            "Chart: historical OHLC plus Kronos path (or ensemble Forecast). Short vs long horizon.",
            "Sentiment: Public (Finnhub news) and Investors (Kronos trend). A dimmed investor badge means no reliable out-of-sample edge.",
            "News: merged Finnhub + Alpaca coverage for the selected symbol.",
            "Portfolio / ticket: paper or live, equity or single-leg option, review-before-send.",
            "Movers: top 50 predicted gainers and losers from a background Kronos scan.",
            "Open positions: full-width holdings table under the movers scan. Click a symbol to load it.",
        ]
    )
    pdf.body(
        "Partial-data banners appear when quote data loaded but chart or forecast did not "
        "(including brief forecast throttling). Forecast retries and in-flight request coalescing "
        "reduce false unavailable states when switching symbols."
    )

    pdf.heading("5. Forecasts and movers")
    pdf.body(
        "Kronos is loaded on the first forecast, not at API startup. Device is auto unless "
        "overridden (cpu, cuda:0, MPS). Context is capped at 512. Future timestamps skip weekends "
        "and stay inside the US regular session. That is market-aware, not a full holiday calendar."
    )
    pdf.add_table(
        ["Preset", "Bars", "Context", "Horizon"],
        [
            ["short", "5-minute", "256", "12 bars"],
            ["long", "daily", "256", "20 bars"],
        ],
        [40, 40, 40, 70],
    )
    pdf.body(
        "The movers scan ranks today's active names by absolute Kronos forecast change after a "
        "spread/slippage haircut. It uses a separate rate-limit bucket from per-ticker forecasts "
        "(defaults: 10 scan requests/min vs 30 ticker forecasts/min) so a universe scan does not "
        "starve the chart. POST /forecast/movers starts a background scan. Poll "
        "GET /forecast/movers/status for progressive top-50 gainers and losers."
    )

    pdf.heading("6. Trading and safety")
    pdf.bullets(
        [
            "Default mode is paper. Live is disabled until ALLOW_LIVE_TRADING=true on the server.",
            "Enabling live in the UI requires typing LIVE. Live orders also send that confirmation token.",
            "Every order opens a review dialog. There is no scheduler or signal executor.",
            "Equity sells cannot exceed the long position unless ALLOW_SHORT_SELLING=true.",
            "Option sell_to_open requires ALLOW_UNCOVERED_OPTIONS=true.",
            "Risk preview can block buys (position size, spread, daily-loss halt).",
            "Cancel open orders from Activity. Replace is available on the API.",
        ]
    )
    pdf.subhead("Paper smoke checklist")
    pdf.numbered(
        [
            "Configure only paper Alpaca keys (and optionally Finnhub).",
            "Keep ALLOW_LIVE_TRADING=false.",
            "Confirm /health and /config/status show no secrets.",
            "Search AAPL, open overview, load daily bars.",
            "Inspect paper account, positions, and orders.",
            "View an option chain without submitting.",
            "Place a one-share or low-notional paper order; confirm in Alpaca.",
            "Cancel an open paper order from the UI or API.",
            "Run a short Kronos forecast (first call downloads weights).",
            "Confirm a live request returns 403 while live is disabled.",
        ]
    )

    pdf.heading("7. API reference")
    pdf.body(
        "All routes use the prefix /api/v1. Interactive docs: http://127.0.0.1:8000/docs "
        "(loopback only). Responses include X-Request-ID. Missing providers return generic 503; "
        "upstream failures return generic 502. If API_KEY is set, every route except /health "
        "requires header X-API-Key."
    )
    pdf.add_table(
        ["Method", "Path", "Purpose"],
        [
            ["GET", "/health", "Liveness"],
            ["GET", "/ready", "Service presence"],
            ["GET", "/config/status", "Safe config flags (no secrets)"],
            ["GET", "/market/clock", "Session / next open-close"],
            ["GET", "/symbols/search", "Symbol lookup"],
            ["GET", "/stocks/{symbol}/overview", "Quote, news, fundamentals, sentiment"],
            ["GET", "/stocks/{symbol}/bars", "OHLCV"],
            ["POST", "/forecast", "Kronos or ensemble Forecast (engine)"],
            ["POST", "/forecast/movers", "Start movers scan"],
            ["GET", "/forecast/movers/status", "Scan progress and rankings"],
            ["GET", "/account, /positions, /orders", "Broker state (mode=paper|live)"],
            ["GET", "/options/contracts, /options/chain", "Option chain"],
            ["POST", "/orders/preview", "Risk preview"],
            ["POST", "/orders/equity, /orders/option", "Submit order"],
            ["DELETE/PATCH", "/orders/{id}", "Cancel / replace"],
        ],
        [28, 78, 84],
    )
    pdf.subhead("Example paper equity order")
    pdf.code(
        '{\n'
        '  "mode": "paper",\n'
        '  "symbol": "AAPL",\n'
        '  "side": "buy",\n'
        '  "type": "limit",\n'
        '  "time_in_force": "day",\n'
        '  "qty": 1,\n'
        '  "limit_price": 190.00\n'
        "}"
    )

    pdf.heading("8. Configuration")
    pdf.body("Copy backend/.env.example to backend/.env (gitignored). Important variables:")
    pdf.add_table(
        ["Variable", "Notes"],
        [
            ["ALPACA_PAPER_KEY / _SECRET", "Paper trading and default market data"],
            ["ALPACA_LIVE_KEY / _SECRET", "Live trading only when enabled"],
            ["ALPACA_DATA_FEED", "iex (sip only with a SIP subscription)"],
            ["FINNHUB_API_KEY", "Fundamentals, company news, public sentiment"],
            ["ALLOW_LIVE_TRADING", "false"],
            ["API_KEY", "Empty = no API auth (local default)"],
            ["CORS_ORIGIN", "http://localhost:5173 plus LAN origins as needed"],
            ["FORECAST_RATE_LIMIT_PER_MINUTE", "30"],
            ["FORECAST_SCAN_RATE_LIMIT_PER_MINUTE", "10"],
            ["KRONOS_MODEL_ID", "NeoQuasar/Kronos-small"],
        ],
        [78, 112],
    )
    pdf.body(
        "Frontend optional frontend/.env.local: VITE_API_BASE_URL (default same-origin /api/v1) "
        "and VITE_API_KEY if the backend requires a key. A key in the browser is not a substitute "
        "for firewall and CORS controls."
    )

    pdf.heading("9. Historical backtester")
    pdf.body(
        "kronos_backtest is the supported engine. examples/run_backtest_kronos.py and "
        "finetune/qlib_test.py are demo-grade only."
    )
    pdf.subhead("Event loop (no look-ahead)")
    pdf.code(
        "For each bar T:\n"
        "  1. OHLCV for T is known\n"
        "  2. Pending orders fill at this bar's OPEN if delay has elapsed\n"
        "     (never this bar's close, never the signal bar's close)\n"
        "  3. Mark portfolio to T close\n"
        "  4. Context = history with timestamps <= T\n"
        "  5. Predictor sees only that context (LookAheadBiasError otherwise)\n"
        "  6. Strategy emits BUY / SELL / HOLD after estimated costs\n"
        "  7. Risk manager sizes or rejects\n"
        "  8. Order is queued; it cannot fill until a later bar"
    )
    pdf.body(
        "Default: signal at T, fill at T+1 open, plus spread, slippage, and fees. If bid/ask "
        "columns are missing, a synthetic spread is applied around the next-bar open."
    )
    pdf.code(
        "pip install -r requirements.txt\n"
        "python -m kronos_backtest --config configs/backtest.yaml --predictor dummy --output backtest_results\n"
        "pytest tests/backtest -q"
    )
    pdf.body(
        "Use --predictor kronos to wrap the real model (downloads weights). Outputs: summary.json, "
        "metrics.json, trades.csv, equity/drawdown CSVs, and report.html. Limitations: no market-impact "
        "model beyond proportional slippage; only MARKET fills; default loop is one symbol per run; "
        "fine-tune quality depends on the callback you supply (test rows are never passed to fit)."
    )

    pdf.heading("10. Development and tests")
    pdf.body(
        "Use separate virtualenvs for the core model and the StockPulse backend when dependency "
        "sets conflict. Application CI uses Python 3.12 and Node 22."
    )
    pdf.code(
        "cd backend && pytest -q\n"
        "cd frontend && npm run lint && npm run typecheck && npm test && npm run build\n"
        "pytest -q tests/backtest"
    )
    pdf.body(
        "Backend tests use fakes and HTTP mock transports. They never call Alpaca, Finnhub, "
        "Hugging Face, or place orders. Optional Docker: docker compose up --build from the repo root."
    )

    pdf.heading("11. Security and licensing")
    pdf.bullets(
        [
            "Never commit .env, credentials, account IDs, or model weights.",
            "Report vulnerabilities privately via GitHub Security, not a public issue.",
            "Financial loss, forecast accuracy, and provider outages are not software vulnerabilities.",
            "Source is MIT unless a file says otherwise. Hugging Face weights, broker data, and third-party packages keep their own terms.",
        ]
    )
    pdf.body(
        "Related files: SECURITY.md, docs/LICENSING.md, docs/DEVELOPMENT.md, docs/BACKTEST.md, "
        "backend/README.md, frontend/README.md, TRADING_APP.md."
    )
    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(
        0,
        5,
        "End of StockPulse documentation - 19 August 2026. This guide describes the personal "
        "StockPulse build in this repository and is not a broker disclosure or offer to transact.",
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    try:
        pdf.output(OUTPUT)
        target = OUTPUT
    except PermissionError:
        alt = OUTPUT.with_name("StockPulse-readable.pdf")
        pdf.output(alt)
        target = alt
        print(f"Original PDF is locked; wrote {target} instead")
    print(f"Wrote {target} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
