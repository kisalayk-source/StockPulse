"""Generate StockPulse technical architecture and finance glossary PDFs."""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PURPLE = (44, 33, 84)
MUTED = (91, 101, 115)
ACCENT = (93, 67, 163)
RULE = (217, 211, 234)
INK = (27, 36, 48)
DATE = "24 August 2026"


class GuidePDF(FPDF):
    doc_label = "StockPulse guide"

    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*MUTED)
        self.cell(0, 8, self.doc_label, align="L")
        self.cell(0, 8, "Personal tooling", align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*RULE)
        self.line(self.l_margin, 16, self.w - self.r_margin, 16)
        self.ln(6)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 8, f"Page {self.page_no()}  |  Not investment advice", align="C")

    def cover(self, eyebrow: str, title: str, subtitle: str) -> None:
        self.add_page()
        self.set_fill_color(*PURPLE)
        self.rect(0, 0, self.w, 18, "F")
        self.ln(42)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*ACCENT)
        self.cell(0, 8, eyebrow, new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "B", 28)
        self.set_text_color(*PURPLE)
        self.multi_cell(0, 12, title)
        self.ln(4)
        self.set_font("Helvetica", "", 12)
        self.set_text_color(*INK)
        self.multi_cell(0, 7, subtitle)
        self.ln(10)
        self.set_font("Helvetica", "", 11)
        self.set_text_color(*MUTED)
        for line in (
            f"Date: {DATE}",
            "Product: StockPulse (Kronos monorepo)",
            "Local UI: http://localhost:5173",
            "LAN UI: http://192.168.86.197:5173",
        ):
            self.cell(0, 7, line, new_x="LMARGIN", new_y="NEXT")
        self.ln(14)
        self.set_fill_color(253, 244, 244)
        self.set_draw_color(181, 45, 57)
        self.set_text_color(90, 28, 34)
        self.set_font("Helvetica", "", 10)
        self.multi_cell(
            0,
            6,
            "Not investment advice. Forecasts are research outputs. Broker acceptance "
            "does not guarantee execution. Prefer paper mode until you understand the "
            "risk controls.",
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

    def term(self, name: str, definition: str) -> None:
        # Keep term blocks from splitting into a zero-width remnant after page breaks.
        needed = 22
        if self.get_y() > self.h - self.b_margin - needed:
            self.add_page()
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*PURPLE)
        self.multi_cell(0, 6, name, new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 11)
        self.set_text_color(*INK)
        self.multi_cell(0, 6, definition, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def body(self, text: str) -> None:
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "", 11)
        self.set_text_color(*INK)
        self.multi_cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def bullets(self, items: list[str]) -> None:
        self.set_font("Helvetica", "", 11)
        self.set_text_color(*INK)
        for item in items:
            self.set_x(self.l_margin)
            self.multi_cell(0, 6, f"  -  {item}", new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def code(self, text: str) -> None:
        self.set_x(self.l_margin)
        self.set_fill_color(243, 241, 248)
        self.set_draw_color(*RULE)
        self.set_text_color(*INK)
        self.set_font("Courier", "", 9)
        self.multi_cell(0, 5, text, border=1, fill=True, padding=3, new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def add_table(self, headers: list[str], rows: list[list[str]], widths: list[float] | None = None) -> None:
        self.set_x(self.l_margin)
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


def build_architecture() -> Path:
    pdf = GuidePDF(format="Letter", unit="mm")
    pdf.doc_label = "StockPulse technical architecture"
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_title("StockPulse Technical Architecture")
    pdf.set_author("StockPulse")
    pdf.cover(
        "TECHNICAL ARCHITECTURE",
        "StockPulse Web App",
        "How the dashboard, API, market providers, and Kronos forecast path fit together "
        "for local and LAN hosting - including which model is used and how predictions "
        "are produced from OHLCV through to the chart.",
    )

    pdf.add_page()
    pdf.heading("1. Purpose")
    pdf.body(
        "StockPulse is a paper-first trading workstation in the Kronos monorepo. The UI "
        "shows quotes, charts, news, sentiment, predicted movers, and open positions. "
        "Orders are always manual. Forecasts never place trades."
    )
    pdf.body(
        "This document describes the web application architecture only. The research "
        "multi-model package under forecasting/ and the portfolio engine under "
        "kronos_backtest/ are adjacent systems, noted where they touch StockPulse."
    )

    pdf.heading("2. Runtime topology")
    pdf.add_table(
        ["Process", "Bind", "Role"],
        [
            ["Vite preview (frontend)", "0.0.0.0:5173", "Static UI + reverse proxy for /api"],
            ["Uvicorn (backend)", "127.0.0.1:8000", "FastAPI. Loopback only."],
            ["Research forecast API", "optional :8001", "forecasting.api.serve (not StockPulse)"],
        ],
        [48, 36, 106],
    )
    pdf.body(
        "LAN clients open the frontend URL. They never talk to :8000 directly. The Vite "
        "preview server proxies /api/v1/* to the loopback API. That keeps broker keys and "
        "model weights off the public interface."
    )
    pdf.subhead("Request path")
    pdf.code(
        "Browser (localhost or LAN)\n"
        "  -> http://<host>:5173\n"
        "       -> React dashboard (static build)\n"
        "       -> /api/v1/*  --proxy-->  FastAPI 127.0.0.1:8000\n"
        "            -> Alpaca (bars, quotes, trading)\n"
        "            -> Finnhub (news, public sentiment)\n"
        "            -> KronosService (forecast / movers)"
    )

    pdf.heading("3. Repository layers")
    pdf.add_table(
        ["Layer", "Path", "Responsibility"],
        [
            ["UI", "frontend/", "React + TypeScript + Vite. Chart, ticket, movers, portfolio."],
            ["API", "backend/app/", "Routes, schemas, DI, rate limits, risk checks."],
            ["Providers", "backend/app/services/providers.py", "Alpaca + Finnhub clients."],
            ["Forecast", "backend/app/services/kronos.py", "Bars windowing, Kronos/baseline predict, annotate."],
            ["Research", "backend/app/services/research.py", "Costs, regime, walk-forward, edge score."],
            ["Model", "model/", "Kronos tokenizer + predictor (HF weights)."],
            ["Publish", "scripts/publish-kronos-lan.ps1", "Build UI, start API + preview, print LAN URL."],
        ],
        [28, 52, 110],
    )

    pdf.heading("4. Frontend composition")
    pdf.bullets(
        [
            "App.tsx owns symbol, short/long horizon, forecast bar count, paper/live mode.",
            "MarketChart draws historical candles and the forecast close path.",
            "DecisionPanel summarizes path turns, net change, regime, and news context.",
            "MoversPanel polls a background scan for top predicted gainers/losers.",
            "PortfolioPanel lists open positions; clicking a symbol reloads the market pane.",
            "api.ts maps snake_case API payloads to camelCase UI types; coalesces in-flight forecasts.",
        ]
    )
    pdf.body(
        "Partial-data banners appear when overview succeeds but chart or forecast fails "
        "(including rate limits). Forecast failures now surface the API error text when present."
    )

    pdf.heading("5. Which model StockPulse uses")
    pdf.body(
        "The chart toggle is Kronos (single Kronos model, engine=kronos) or Forecast "
        "(weighted ensemble from forecasting/, engine=ensemble). Chronos, TimesFM, and "
        "Lag-Llama participate only when installed and enabled; missing adapters are skipped. "
        "The optional research API on port 8001 is separate and not used by the dashboard."
    )
    pdf.subhead("Default checkpoint")
    pdf.add_table(
        ["Setting", "Default", "Meaning"],
        [
            ["KRONOS_MODEL_ID", "NeoQuasar/Kronos-small", "Candlestick foundation model (~24.7M params)."],
            ["KRONOS_TOKENIZER_ID", "NeoQuasar/Kronos-Tokenizer-base", "Must match the model family."],
            ["KRONOS_DEVICE", "auto", "cuda / MPS / cpu chosen at load time."],
            ["KRONOS_MAX_CONTEXT", "512", "Hard cap for Kronos-small context window."],
        ],
        [48, 62, 80],
    )
    pdf.body(
        "Weights download from Hugging Face on the first successful forecast that needs them. "
        "Tokenizer and model are loaded once, kept in memory, and protected by an inference lock. "
        "Override IDs in backend/.env if you switch to Kronos-mini (longer context) or another "
        "compatible checkpoint - keep tokenizer and model sizes matched."
    )
    pdf.subhead("What Kronos is")
    pdf.bullets(
        [
            "Candlestick-native: consumes OHLCV (plus a synthetic amount = volume x mean price).",
            "Tokenizer encodes continuous bars into discrete tokens (binary spherical quantization).",
            "Autoregressive decoder predicts future tokens, then decodes them back to OHLCV.",
            "StockPulse calls KronosPredictor.predict with sample_count=1 (single path, not a Monte Carlo cloud).",
            "Sampling defaults inside the predictor: temperature T=1.0, top_k=0, top_p=0.9.",
        ]
    )
    pdf.subhead("When Kronos cannot load")
    pdf.body(
        "If PyTorch fails (for example Windows Application Control blocking torch DLLs), "
        "KronosService switches to baseline-drift: average of the last up to 20 close returns, "
        "clamped to +/-2% per bar, applied repeatedly for the horizon. Response model.id is "
        "baseline-drift and model.fallback is true. Real Kronos resumes once Torch loads."
    )

    pdf.heading("6. How a prediction is produced")
    pdf.subhead("End-to-end data flow")
    pdf.code(
        "UI: Short|Long + bar count (1/10/20/30/60)\n"
        "  POST /api/v1/forecast { symbol, preset, horizon, engine }\n"
        "\n"
        "1. Resolve preset\n"
        "     short -> 5Min bars, context default 256\n"
        "     long  -> 1Day bars, context default 256\n"
        "     horizon from request or preset default (12 / 20)\n"
        "     context capped at min(requested, kronos_max_context, 512)\n"
        "\n"
        "2. Fetch history (Alpaca)\n"
        "     Need at least 32 bars; keep the last `context` bars\n"
        "     Columns: open, high, low, close, volume\n"
        "     amount synthesized for the model\n"
        "\n"
        "3. Build time axes\n"
        "     x_timestamp = historical bar times (UTC)\n"
        "     y_timestamp = future session times (ET calendar):\n"
        "       daily: next weekdays\n"
        "       intraday: step 5/15/... min, roll to next 09:30 after 16:00\n"
        "\n"
        "4. Infer path\n"
        "     try KronosPredictor.predict(df, x_ts, y_ts, pred_len=horizon)\n"
        "     else baseline-drift on close returns\n"
        "\n"
        "5. Annotate for the UI\n"
        "     gross change = last_pred_close / last_hist_close - 1\n"
        "     net change   = gross - round_trip_cost_bps/10000\n"
        "     regime from recent vol/trend\n"
        "     optional walk-forward folds (next-open fill)\n"
        "     path_segments for DecisionPanel\n"
        "\n"
        "6. Cache key (symbol, preset, timeframe, context, horizon) TTL 300s"
    )
    pdf.subhead("Presets vs UI bar picker")
    pdf.add_table(
        ["Control", "Effect"],
        [
            ["Short / Long toggle", "Chooses bar timeframe (5Min vs 1Day) and default horizon."],
            ["Bar count buttons", "Overrides horizon only (how many future bars to draw)."],
            ["Context", "How many past bars Kronos may see; not user-editable in the UI."],
        ],
        [48, 142],
    )
    pdf.subhead("Inputs the model actually sees")
    pdf.bullets(
        [
            "A float DataFrame of open/high/low/close/volume/amount for the context window.",
            "Aligned historical timestamps and synthesized future timestamps (no future OHLCV).",
            "pred_len = horizon; StockPulse does not pass true future prices into the model.",
        ]
    )
    pdf.subhead("Outputs the UI plots")
    pdf.bullets(
        [
            "forecast[]: timestamped predicted OHLCV rows (chart uses close).",
            "trend.direction / forecast_change / net_forecast_change after cost haircut.",
            "model.id, device, context, horizon, and fallback flag.",
            "evaluation: walk-forward hit rate / IC-style stats when folds are enabled.",
            "Investors sentiment badge follows forecast direction; dimmed if edge is not reliable.",
        ]
    )
    pdf.subhead("Movers scan (same model path)")
    pdf.body(
        "POST /forecast/movers runs the same KronosService.forecast path over a universe "
        "(Alpaca actives/movers, capped), with evaluate=False for speed, then ranks by absolute "
        "net forecast change. Separate rate-limit bucket from per-ticker chart forecasts."
    )

    pdf.heading("7. Backend services")
    pdf.subhead("Dependency injection")
    pdf.body(
        "On startup, main.py builds Settings from backend/.env, constructs AlpacaService, "
        "FinnhubService, and KronosService, and stores them on app.state. Routes receive a "
        "Services object via FastAPI Depends."
    )

    pdf.heading("8. External providers")
    pdf.add_table(
        ["Provider", "Used for", "Failure mode"],
        [
            ["Alpaca", "Bars, quotes, clock, paper/live trading, news", "502/503; UI partial data"],
            ["Finnhub", "Symbol search assist, news, public sentiment", "Optional; overview still returns"],
            ["Hugging Face", "Kronos-small + tokenizer weights", "Falls back to baseline-drift"],
        ],
        [32, 78, 80],
    )

    pdf.heading("9. Security and hosting")
    pdf.bullets(
        [
            "API binds loopback only; secrets stay on the host.",
            "Optional API_KEY requires X-API-Key on all routes except /health.",
            "Live trading requires ALLOW_LIVE_TRADING plus typed LIVE confirmation.",
            "CORS is restricted; LAN access is via the frontend origin on :5173.",
            "Rate limits: forecasts, movers scans, and orders use separate buckets.",
            "Publish with scripts/publish-kronos-lan.ps1 after app changes (checks then build).",
        ]
    )

    pdf.heading("10. Related packages (out of StockPulse hot path)")
    pdf.add_table(
        ["Package", "Role vs webapp"],
        [
            ["forecasting/", "Model-agnostic research layer (registry, ensemble, eval). Separate :8001 API."],
            ["kronos_backtest/", "Look-ahead-safe portfolio backtester. Not called by the dashboard."],
            ["webui/", "Legacy Flask demo. Not required for StockPulse."],
        ],
        [40, 150],
    )

    pdf.heading("11. Key endpoints")
    pdf.add_table(
        ["Method", "Path", "UI use"],
        [
            ["GET", "/health", "Liveness / publish check"],
            ["GET", "/stocks/{sym}/overview", "Quote, news, public sentiment"],
            ["GET", "/stocks/{sym}/bars", "Chart candles"],
            ["POST", "/forecast", "Kronos (kronos) or Forecast (ensemble)"],
            ["POST", "/forecast/movers", "Start movers scan"],
            ["GET", "/forecast/movers/status", "Poll gainers/losers"],
            ["GET", "/positions", "Open positions table"],
            ["POST", "/orders/equity", "Manual equity order (after review)"],
        ],
        [22, 55, 113],
    )

    out = DOCS / "StockPulse-Architecture.pdf"
    pdf.output(out)
    return out


def build_finance_glossary() -> Path:
    pdf = GuidePDF(format="Letter", unit="mm")
    pdf.doc_label = "StockPulse finance glossary"
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_title("StockPulse Finance Glossary")
    pdf.set_author("StockPulse")
    pdf.cover(
        "FINANCE AND MARKET TERMS",
        "StockPulse Glossary",
        "How StockPulse calculates costs, forecast edge, portfolio weights, and "
        "order risk. Definitions match the live dashboard and API - not a textbook. "
        "Nothing here is investment advice.",
    )

    pdf.add_page()
    pdf.heading("1. How to use this glossary")
    pdf.body(
        "Terms are grouped by product surface. Formulas mirror backend/app/services/"
        "research.py (forecast annotations) and backend/app/services/risk.py (order "
        "preview). Defaults come from backend/app/config.py and can be overridden in "
        "backend/.env. Forecasts never auto-trade."
    )

    pdf.heading("2. Market data")
    pdf.term(
        "OHLCV",
        "Open, High, Low, Close, Volume for one bar (candle). The chart and Kronos "
        "context window are built from these fields.",
    )
    pdf.term(
        "Bar / candle",
        "One OHLCV sample over a fixed interval. Short horizon uses 5-minute bars; "
        "long horizon uses daily bars.",
    )
    pdf.term(
        "Session / RTH",
        "Regular trading hours for US equities (roughly 09:30-16:00 America/New_York). "
        "Forecast timestamps skip weekends and stay inside RTH for intraday bars.",
    )
    pdf.term(
        "Pre-market / after-hours",
        "Extended sessions outside RTH. The market clock badge reflects Alpaca session "
        "state. Intraday forecast synthesis still anchors to RTH open/close rules.",
    )
    pdf.term(
        "Quote",
        "Latest tradeable snapshot for a symbol: last price, day change, OHLC, volume, "
        "and optional fundamentals (market cap, P/E, EPS, dividend yield).",
    )
    pdf.term(
        "ADV (average daily volume)",
        "Typical share volume from the quote snapshot. Risk checks require ADV >= "
        "RISK_MIN_ADV_SHARES (default 200,000) before allowing a buy. Cost helpers also "
        "use dollar ADV = mean(volume * close) when estimating slippage.",
    )
    pdf.term(
        "Bid / ask / mid",
        "Best buy and sell quotes. Quoted spread in bps = (ask - bid) / mid * 10,000 "
        "when both sides exist. Used for live risk checks on buys.",
    )

    pdf.heading("3. Forecast engines and horizons")
    pdf.term(
        "Kronos mode",
        "Chart engine toggle (engine=kronos). Single NeoQuasar Kronos path (or labeled "
        "baseline-drift if Torch cannot load). Movers scans always use this path.",
    )
    pdf.term(
        "Forecast mode",
        "Chart engine toggle (engine=ensemble). Weighted blend of enabled models from "
        "forecasting/ (persistence, Kronos, Chronos, TimesFM, ...). If only persistence "
        "survives, StockPulse falls back to the Kronos/baseline path and marks the "
        "response as ensemble_degraded.",
    )
    pdf.term(
        "Short horizon",
        "Preset on 5-minute bars. Default context 256, default horizon 12 bars; UI can "
        "override horizon to 1 / 10 / 20 / 30 / 60.",
    )
    pdf.term(
        "Long horizon",
        "Preset on daily bars. Default context 256, default horizon 20 trading days; "
        "UI can override to 1 / 10 / 20 / 30 / 60.",
    )
    pdf.term(
        "Context",
        "Historical bars the model may see. StockPulse caps context at "
        "min(requested, KRONOS_MAX_CONTEXT, 512) for Kronos-small.",
    )
    pdf.term(
        "Forecast path",
        "Sequence of predicted closes (Kronos usually returns full OHLCV) plotted after "
        "the last historical candle.",
    )
    pdf.term(
        "Path segments",
        "UI breakdown of the forecast into up / down / flat stretches for decision context.",
    )
    pdf.term(
        "Direction noise band",
        "Trend is flat when |forecast_change| < 0.002 (0.2%). Same band is used when "
        "scoring walk-forward direction hits.",
    )
    pdf.term(
        "Baseline-drift",
        "Fallback when Kronos/PyTorch cannot load: last close grown by the mean of the "
        "last ~20 bar returns, each step clamped to +/- 2%. Labeled in model.id so it "
        "is not mistaken for a neural forecast.",
    )

    pdf.heading("4. Cost and edge calculations")
    pdf.subhead("Round-trip cost (research.py)")
    pdf.body(
        "For each forecast annotation StockPulse estimates friction from the same OHLCV "
        "window used as context (default notional assumption $10,000):"
    )
    pdf.code(
        "range_i     = (high_i - low_i) / close_i\n"
        "spread_bps  = clamp(mean(range) * 10000, floor=2, cap=80)\n"
        "realized    = stdev(close returns over last ~21 bars)\n"
        "dollar_ADV  = mean(volume_i * close_i)\n"
        "particip.   = min(1, notional / dollar_ADV)   # else 0.05\n"
        "slip_bps    = clamp(10000 * realized * sqrt(particip.) * 0.5, 0.5, 40)\n"
        "fee_bps     = 0.5\n"
        "round_trip  = 2 * (spread_bps + slip_bps) + fee_bps"
    )
    pdf.body(
        "If fewer than 5 valid bars exist, a conservative default is used: "
        "2 * 2bp spread floor + 2bp slip + 0.5bp fee."
    )
    pdf.term(
        "Basis point (bp / bps)",
        "One hundredth of one percent. 100 bps = 1%. Dividing bps by 10,000 converts to "
        "a decimal return haircut.",
    )
    pdf.subhead("Gross and net forecast change")
    pdf.code(
        "gross = last_predicted_close / last_historical_close - 1\n"
        "net   = sign(gross) * (|gross| - round_trip_bps/10000)\n"
        "      = -round_trip_bps/10000   when gross == 0"
    )
    pdf.body(
        "Net change is what the chart meta line and movers ranking use after the cost "
        "haircut. A positive net means the predicted move still exceeds estimated friction."
    )
    pdf.term(
        "Quoted spread (risk path)",
        "Separate from the bar-range spread proxy: (ask - bid) / mid * 10,000 from the "
        "live snapshot. Used only in order risk checks.",
    )

    pdf.heading("5. Regime, walk-forward, and edge reliability")
    pdf.subhead("Regime label (classify_regime)")
    pdf.body(
        "Needs >= 21 closes. realized_vol = stdev of last 20 bar returns. Compare short "
        "vol to longer (up to 60) vol; trend compares 20-bar vs 60-bar mean price "
        "(+/- 0.5% band = sideways). Label form: {low|normal|high}_vol_{up|down|sideways}."
    )
    pdf.subhead("Walk-forward evaluation")
    pdf.body(
        "Kronos mode (not ensemble) may run purged walk-forward folds "
        "(KRONOS_EVAL_FOLDS, default 3; context KRONOS_EVAL_CONTEXT, default 32). "
        "Eval horizon is min(path_horizon, 20). For each fold:"
    )
    pdf.code(
        "signal at bar t using only bars [t-context, t)\n"
        "fill at next bar open (or close if open missing)\n"
        "exit at close of bar t+horizon-1\n"
        "traded_return = predicted_dir * realized_return   # 0 if flat signal\n"
        "net_fold = traded_return - round_trip_bps/10000   # 0 if no trade"
    )
    pdf.term(
        "Hit rate",
        "Share of folds where predicted_dir matches realized_dir (both non-flat).",
    )
    pdf.term(
        "Mean net return / IC",
        "Average net_fold across folds; IC is Spearman rank correlation of predicted "
        "gross vs realized when enough folds exist.",
    )
    pdf.term(
        "Edge reliable",
        "True only if folds >= 2, mean_net_return > 0, hit_rate >= 0.5, and (when the "
        "current regime bucket has >= 2 folds) that bucket's mean_net_return is also "
        "> 0. Dims the Investors sentiment badge when false.",
    )
    pdf.term(
        "Live OOS journal",
        "StockPulse appends forecast_change snapshots to an in-memory / optional file "
        "journal and scores them later against realized bars (live_oos in evaluation).",
    )

    pdf.heading("6. Portfolio and open positions")
    pdf.term(
        "Equity",
        "Broker-reported account equity for the selected paper/live mode. Shown in the "
        "account card and Open positions summary.",
    )
    pdf.term(
        "Buying power / cash",
        "Broker capacity for new buys and settled cash. Buys that exceed buying power "
        "are blocked at preview.",
    )
    pdf.term(
        "Market value",
        "Alpaca position market_value for the holding (signed; UI sorts by absolute size).",
    )
    pdf.term(
        "% of equity (Open positions)",
        "portfolio_weight = position.market_value / account.equity. Displayed as a "
        "percent (for example 1.20%). Shows em dash if equity is missing or zero.",
    )
    pdf.term(
        "Unrealized P/L",
        "Broker unrealized dollar P/L and optional percent vs average entry. Separate "
        "from portfolio weight.",
    )
    pdf.term(
        "Gross exposure",
        "Sum of abs(market_value) across open positions. Used in risk: after a buy, "
        "(gross_exposure + order_cost) / equity must stay <= RISK_MAX_GROSS_PCT.",
    )
    pdf.term(
        "Daily P/L percent",
        "daily_pnl_pct = equity / last_equity - 1. If this is at or below "
        "-RISK_MAX_DAILY_LOSS_PCT, new buys are halted (new_buys_halted).",
    )

    pdf.heading("7. Order sizing and review preview")
    pdf.subhead("Estimated notional")
    pdf.code(
        "equity:  notional field, else qty * (limit|stop|last|ask)\n"
        "option:  same, then * 100 (contract multiplier)"
    )
    pdf.term(
        "position_pct (preview)",
        "For buys: (current_position_value + estimated_cost) / equity. For sells: "
        "current_position_value / equity. Shown in the review dialog as "
        "\"X% of equity\".",
    )
    pdf.term(
        "Review-before-send",
        "Every equity/option order opens a confirmation dialog with estimated cost, "
        "position %, spread bps, daily P/L %, and warnings. Nothing routes from the "
        "forecast engine automatically.",
    )
    pdf.term(
        "Large market-order warning",
        "Soft warning (does not hard-block) when type=market and estimated cost >= $5,000.",
    )

    pdf.heading("8. Risk portfolio controls (defaults)")
    pdf.body(
        "Hard limits live in check_order_risk. Breaches raise ValueError and become "
        "422/preview failures. Defaults (override via env):"
    )
    pdf.add_table(
        ["Setting", "Default", "Rule"],
        [
            ["RISK_MAX_POSITION_PCT", "10%", "Buy: (pos + cost)/equity <= limit"],
            ["RISK_MAX_OPTION_DEBIT_PCT", "5%", "Same for option buys (debit)"],
            ["RISK_MAX_GROSS_PCT", "150%", "(gross + cost)/equity <= limit"],
            ["RISK_MAX_DAILY_LOSS_PCT", "3%", "Buy blocked if daily P/L <= -limit"],
            ["RISK_MAX_SPREAD_BPS", "80", "Buy blocked if quoted spread > limit"],
            ["RISK_MIN_ADV_SHARES", "200,000", "Buy blocked if ADV below floor"],
            ["ALLOW_SHORT_SELLING", "false", "Equity sell qty/notional <= long"],
            ["ALLOW_UNCOVERED_OPTIONS", "false", "Blocks sell_to_open by default"],
        ],
        [52, 28, 100],
    )
    pdf.term(
        "Sell-to-close / buy-to-close",
        "Option closes cannot exceed the held long/short contract quantity.",
    )
    pdf.term(
        "Live confirmation",
        "Live mode requires ALLOW_LIVE_TRADING on the server plus typing LIVE "
        "(and matching live_confirmation_token on the order).",
    )

    pdf.heading("9. Sentiment badges")
    pdf.term(
        "Public sentiment",
        "News-derived bullish / bearish / neutral (Finnhub-oriented).",
    )
    pdf.term(
        "Investors sentiment",
        "Mapped from forecast trend direction (up->bullish, down->bearish, flat->neutral). "
        "Dimmed when edge_reliable is false.",
    )

    pdf.heading("10. Movers scan")
    pdf.term(
        "Movers ranking",
        "Background Kronos forecasts over a liquid universe (Alpaca actives/movers + "
        "fallback list). Ranked by absolute net_forecast_change after the cost haircut. "
        "UI shows top predicted gainers and losers (cap 50).",
    )
    pdf.term(
        "Scan rate limit",
        "Separate throttle from per-ticker forecasts so a universe scan does not starve "
        "the chart (defaults: ~10 scan req/min vs ~30 ticker forecasts/min).",
    )
    pdf.term(
        "Evaluate=False on scan",
        "Movers forecasts skip walk-forward folds for speed; chart Kronos mode still "
        "may run OOS folds.",
    )

    pdf.heading("11. Trading account vocabulary")
    pdf.term(
        "Paper / live",
        "Simulated vs real Alpaca account. Default UI mode is paper.",
    )
    pdf.term(
        "Notional vs qty",
        "Dollar size vs share/contract count. Exactly one is required for equity orders.",
    )
    pdf.term(
        "Market / limit / stop",
        "Market seeks immediate fill; limit at your price or better; stop/stop-limit "
        "need stop_price (and limit_price for stop-limit).",
    )
    pdf.term(
        "Time in force",
        "Day cancels at session end; GTC may persist (broker rules apply).",
    )

    pdf.heading("12. Options (single-leg)")
    pdf.term(
        "Contract symbol",
        "OCC-style option identifier (underlying + expiry + call/put + strike).",
    )
    pdf.term(
        "Buy to open / sell to close",
        "Open a long option / close an existing long.",
    )
    pdf.term(
        "Sell to open / buy to close",
        "Open a short option / cover it. Sell-to-open requires "
        "ALLOW_UNCOVERED_OPTIONS=true.",
    )

    pdf.heading("13. Research extras")
    pdf.body(
        "Visible mainly in forecasting/ and kronos_backtest/, and sometimes in logs."
    )
    pdf.term(
        "Look-ahead bias",
        "Using information unknowable at decision time. The production backtester "
        "refuses predictors that see future bars.",
    )
    pdf.term(
        "RankIC",
        "Spearman correlation of predicted scores vs realized outcomes across names.",
    )
    pdf.term(
        "Ensemble disagreement",
        "Cross-model std of final closes / path. Wide disagreement is a low-confidence "
        "signal even if the blend looks calm.",
    )
    pdf.term(
        "Weighted average ensemble",
        "Default Forecast-mode blend: sum(w_i * close_i) / sum(w_i) using weights from "
        "forecasting/config/models.yaml.",
    )

    out = DOCS / "StockPulse-Finance-Glossary.pdf"
    pdf.output(out)
    return out


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    arch = build_architecture()
    gloss = build_finance_glossary()
    print(f"Wrote {arch} ({arch.stat().st_size / 1024:.1f} KB)")
    print(f"Wrote {gloss} ({gloss.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
