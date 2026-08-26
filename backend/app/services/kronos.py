from __future__ import annotations

import sys
import threading
import json
import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from cachetools import TTLCache

from app.config import ROOT_DIR, Settings
from app.services.providers import AlpacaService, jsonable
from app.services.research import (
    classify_regime,
    edge_is_reliable,
    net_expected_change,
    round_trip_cost,
    score_journal,
    walk_forward_evaluate,
)


PRESETS = {
    "short": {"timeframe": "5Min", "context": 256, "horizon": 12},
    "long": {"timeframe": "1Day", "context": 256, "horizon": 20},
    "scan_intraday": {"timeframe": "5Min", "context": 64, "horizon": 8},
    "scan_daily": {"timeframe": "1Day", "context": 64, "horizon": 5},
}

SCAN_LIMIT = 50
SCAN_UNIVERSE_CAP = 100
SCAN_CACHE_TTL = 600
# IEX prints a fraction of consolidated volume; SIP uses the full tape.
MIN_SCAN_VOLUME_IEX = 250_000
MIN_SCAN_VOLUME_SIP = 5_000_000
MIN_SCAN_VOLUME = MIN_SCAN_VOLUME_IEX  # default / backward-compatible alias
logger = logging.getLogger("app.kronos")
# Large-cap US equities only (no ETFs, no speculative small/mid growth).
BLUE_CHIP_UNIVERSE = (
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "TSLA", "AVGO", "BRK.B",
    "JPM", "V", "UNH", "XOM", "LLY", "MA", "COST", "PG", "HD", "ORCL",
    "NFLX", "ABBV", "KO", "MRK", "BAC", "PEP", "CRM", "AMD", "CSCO", "WMT",
    "DIS", "INTC", "QCOM", "TXN", "AMAT", "INTU", "IBM", "CAT", "GS", "BA",
    "AXP", "AMGN", "HON", "NKE", "MCD", "ADBE", "ACN", "TMO", "DHR", "PM",
    "UPS", "RTX", "GE", "CVX", "WFC", "MS", "BLK", "SCHW", "C", "PFE",
    "T", "VZ", "CMCSA", "LOW", "SBUX", "BKNG", "ISRG", "NOW", "SPGI",
)


def _ranked_change(item: dict[str, Any]) -> float:
    value = item.get("net_forecast_change")
    if value is None:
        value = item.get("forecast_change")
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def path_segments(
    closes: list[float],
    timestamps: list[str] | None = None,
    *,
    threshold: float = 0.002,
) -> list[dict[str, Any]]:
    """Split a close path into direction segments at flat ±threshold turns."""
    if len(closes) < 2:
        return []
    segments: list[dict[str, Any]] = []
    start_index = 0
    start_close = closes[0]

    def direction_of(change: float) -> str:
        if change > threshold:
            return "up"
        if change < -threshold:
            return "down"
        return "flat"

    current = direction_of(closes[1] / start_close - 1.0) if start_close else "flat"
    for index in range(2, len(closes)):
        if not start_close:
            break
        change = closes[index] / start_close - 1.0
        direction = direction_of(change)
        if direction == "flat" or direction == current:
            continue
        end_close = closes[index - 1]
        segment_change = (end_close / start_close - 1.0) if start_close else 0.0
        segment: dict[str, Any] = {
            "direction": current,
            "start_index": start_index,
            "end_index": index - 1,
            "start_close": start_close,
            "end_close": end_close,
            "change": segment_change,
        }
        if timestamps and len(timestamps) > index - 1:
            segment["start_timestamp"] = timestamps[start_index]
            segment["end_timestamp"] = timestamps[index - 1]
        segments.append(segment)
        start_index = index - 1
        start_close = end_close
        current = direction_of(closes[index] / start_close - 1.0) if start_close else "flat"
    end_close = closes[-1]
    segment_change = (end_close / start_close - 1.0) if start_close else 0.0
    segment = {
        "direction": current if abs(segment_change) > threshold else "flat",
        "start_index": start_index,
        "end_index": len(closes) - 1,
        "start_close": start_close,
        "end_close": end_close,
        "change": segment_change,
    }
    if timestamps and timestamps:
        segment["start_timestamp"] = timestamps[start_index]
        segment["end_timestamp"] = timestamps[-1]
    segments.append(segment)
    return segments


class KronosService:
    def __init__(self, settings: Settings, alpaca: AlpacaService):
        self.settings = settings
        self.alpaca = alpaca
        self._predictor: Any = None
        self._predictor_load_error: str | None = None
        self._load_lock = threading.Lock()
        self._inference_lock = threading.Lock()
        self._forecast_cache: TTLCache[tuple[Any, ...], dict[str, Any]] = TTLCache(
            maxsize=128, ttl=300
        )
        self._scan_lock = threading.Lock()
        self._scan_cache: TTLCache[str, dict[str, Any]] = TTLCache(
            maxsize=4, ttl=SCAN_CACHE_TTL
        )
        self._scan_progress_lock = threading.Lock()
        self._scan_progress: dict[str, Any] | None = None
        self._scan_thread: threading.Thread | None = None
        self._journal: deque[dict[str, Any]] = deque(maxlen=256)
        self._journal_lock = threading.Lock()
        self._journal_path = self._resolve_journal_path()
        self._load_journal()

    def _resolve_journal_path(self) -> Path | None:
        configured = self.settings.kronos_journal_path
        if not configured:
            return None
        path = Path(configured)
        return path if path.is_absolute() else ROOT_DIR / path

    def _load_journal(self) -> None:
        if self._journal_path is None or not self._journal_path.exists():
            return
        try:
            lines = self._journal_path.read_text(encoding="utf-8").splitlines()[-256:]
            for line in lines:
                payload = json.loads(line)
                if isinstance(payload, dict):
                    self._journal.append(payload)
        except (OSError, json.JSONDecodeError):
            logger.warning("forecast_journal_load_failed", exc_info=True)

    def _append_journal(self, entry: dict[str, Any]) -> None:
        with self._journal_lock:
            self._journal.append(entry)
            if self._journal_path is None:
                return
            try:
                self._journal_path.parent.mkdir(parents=True, exist_ok=True)
                with self._journal_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry, separators=(",", ":")) + "\n")
            except OSError:
                logger.warning("forecast_journal_write_failed", exc_info=True)

    @property
    def loaded(self) -> bool:
        return self._predictor is not None

    def _device(self) -> str | None:
        return None if self.settings.kronos_device == "auto" else self.settings.kronos_device

    def _get_predictor(self) -> Any:
        if self._predictor is not None:
            return self._predictor
        if self._predictor_load_error is not None:
            raise RuntimeError(self._predictor_load_error)
        with self._load_lock:
            if self._predictor is not None:
                return self._predictor
            if self._predictor_load_error is not None:
                raise RuntimeError(self._predictor_load_error)
            try:
                root = str(ROOT_DIR)
                if root not in sys.path:
                    sys.path.insert(0, root)
                from model import Kronos, KronosPredictor, KronosTokenizer

                tokenizer = KronosTokenizer.from_pretrained(
                    self.settings.kronos_tokenizer_id
                )
                model = Kronos.from_pretrained(self.settings.kronos_model_id)
                tokenizer.eval()
                model.eval()
                self._predictor = KronosPredictor(
                    model,
                    tokenizer,
                    device=self._device(),
                    max_context=self.settings.kronos_max_context,
                )
                self._predictor_load_error = None
            except Exception as exc:
                # Common on locked-down Windows hosts: WDAC blocks torch DLLs.
                message = (
                    f"Kronos model unavailable ({type(exc).__name__}: {exc}). "
                    "Using baseline drift forecast until PyTorch can load."
                )
                self._predictor_load_error = message
                logger.error(
                    "kronos_predictor_load_failed",
                    extra={"error_type": type(exc).__name__},
                    exc_info=True,
                )
                raise RuntimeError(message) from exc
        return self._predictor

    @staticmethod
    def _baseline_predict(frame: pd.DataFrame, horizon: int) -> pd.DataFrame:
        """Drift path from recent close returns when Kronos/torch cannot load."""
        closes = frame["close"].astype(float)
        last = float(closes.iloc[-1])
        rets = closes.pct_change().dropna()
        step = float(rets.tail(min(20, len(rets))).mean()) if len(rets) else 0.0
        step = max(-0.02, min(0.02, step))
        rows: list[dict[str, float]] = []
        price = last
        for _ in range(horizon):
            price = price * (1.0 + step)
            rows.append(
                {
                    "open": price,
                    "high": price * 1.002,
                    "low": price * 0.998,
                    "close": price,
                    "volume": 0.0,
                    "amount": 0.0,
                }
            )
        return pd.DataFrame(rows)

    def _predict_frame(
        self,
        frame: pd.DataFrame,
        timestamps: pd.DatetimeIndex,
        future: pd.DatetimeIndex,
        horizon: int,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        """Run Kronos when available; otherwise a labeled baseline path."""
        model_meta = {
            "id": self.settings.kronos_model_id,
            "tokenizer_id": self.settings.kronos_tokenizer_id,
            "device": self.settings.kronos_device,
            "context": len(frame),
            "horizon": horizon,
            "fallback": False,
            "engine": "kronos",
            "temperature": float(self.settings.kronos_temperature),
            "sample_count": int(self.settings.kronos_sample_count),
            "top_p": float(self.settings.kronos_top_p),
        }
        try:
            predictor = self._get_predictor()
            with self._inference_lock:
                predicted = predictor.predict(
                    frame,
                    pd.Series(timestamps, name="timestamps"),
                    pd.Series(future, name="timestamps"),
                    pred_len=horizon,
                    T=float(self.settings.kronos_temperature),
                    top_p=float(self.settings.kronos_top_p),
                    sample_count=int(self.settings.kronos_sample_count),
                    verbose=False,
                )
            model_meta["device"] = getattr(predictor, "device", model_meta["device"])
            return predicted, model_meta
        except Exception as exc:
            logger.warning(
                "kronos_using_baseline_forecast",
                extra={"error_type": type(exc).__name__},
            )
            predicted = self._baseline_predict(frame, horizon)
            model_meta.update(
                {
                    "id": "baseline-drift",
                    "tokenizer_id": "none",
                    "device": "cpu",
                    "fallback": True,
                    "fallback_reason": str(exc),
                }
            )
            return predicted, model_meta

    @staticmethod
    def _future_timestamps(last: datetime, timeframe: str, count: int) -> pd.DatetimeIndex:
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        eastern = last.astimezone(ZoneInfo("America/New_York"))
        result: list[datetime] = []
        if timeframe == "1Day":
            cursor = eastern
            while len(result) < count:
                cursor += timedelta(days=1)
                if cursor.weekday() < 5:
                    result.append(cursor)
        else:
            minutes = {"1Min": 1, "5Min": 5, "15Min": 15, "1Hour": 60}[timeframe]
            cursor = eastern
            while len(result) < count:
                cursor += timedelta(minutes=minutes)
                if cursor.weekday() >= 5 or cursor.time() >= datetime.strptime("16:00", "%H:%M").time():
                    cursor = (cursor + timedelta(days=1)).replace(
                        hour=9, minute=30, second=0, microsecond=0
                    )
                    while cursor.weekday() >= 5:
                        cursor += timedelta(days=1)
                if cursor.time() >= datetime.strptime("09:30", "%H:%M").time():
                    result.append(cursor)
        return pd.DatetimeIndex(result)

    def _window_frame(self, bars: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
        history = pd.DataFrame(bars)
        timestamps = pd.DatetimeIndex(pd.to_datetime(history.pop("timestamp"), utc=True))
        frame = history[["open", "high", "low", "close", "volume"]].astype(float)
        frame["amount"] = frame["volume"] * frame[["open", "high", "low", "close"]].mean(axis=1)
        return frame, timestamps

    def _ensure_repo_path(self) -> None:
        root = str(ROOT_DIR)
        if root not in sys.path:
            sys.path.insert(0, root)

    def _locked_predictor(self, predictor: Any) -> Any:
        """Wrap a shared KronosPredictor so every predict() holds the inference lock."""
        lock = self._inference_lock

        class _LockedPredictor:
            def __getattr__(self, name: str) -> Any:
                return getattr(predictor, name)

            def predict(self, *args: Any, **kwargs: Any) -> Any:
                with lock:
                    return predictor.predict(*args, **kwargs)

        return _LockedPredictor()

    @staticmethod
    def _ensemble_is_persistence_only(models_used: list[str]) -> bool:
        learned = {name for name in models_used if name not in {"persistence"}}
        return bool(models_used) and not learned

    def _ensemble_predict_frame(
        self,
        symbol: str,
        bars: list[dict[str, Any]],
        timeframe: str,
        horizon: int,
        context: int,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        """Run forecasting/ ensemble and return a predicted OHLCV frame + meta."""
        self._ensure_repo_path()
        try:
            from forecasting.core.registry import (
                get_active_models,
                get_ensemble_settings,
                get_model_weights,
            )
            from forecasting.core.schema import ForecastInput
            from forecasting.data.loader import bars_to_ohlcv
            from forecasting.ensemble.combine import forecast_ensemble
        except ImportError as exc:
            raise RuntimeError(
                f"Ensemble forecasting package unavailable ({type(exc).__name__}: {exc})"
            ) from exc

        ohlcv = bars_to_ohlcv(bars, ticker=symbol.upper())
        context_len = min(int(context), len(ohlcv))
        models = get_active_models()
        # Reuse the StockPulse Kronos predictor when available to avoid a second load.
        try:
            predictor = self._get_predictor()
        except Exception:
            predictor = None
        if predictor is not None:
            locked = self._locked_predictor(predictor)
            for model in models:
                if getattr(model, "name", None) == "kronos":
                    if getattr(model, "_predictor", None) is None:
                        model._predictor = locked
                        model._loaded = True
                    model.temperature = float(self.settings.kronos_temperature)
                    model.sample_count = int(self.settings.kronos_sample_count)
                    model.top_p = float(self.settings.kronos_top_p)
                    break
        else:
            for model in models:
                if getattr(model, "name", None) == "kronos":
                    model.temperature = float(self.settings.kronos_temperature)
                    model.sample_count = int(self.settings.kronos_sample_count)
                    model.top_p = float(self.settings.kronos_top_p)
                    break

        weights = get_model_weights()
        ensemble_cfg = get_ensemble_settings()
        strategy = str(ensemble_cfg.get("strategy") or "weighted_average")
        if strategy == "inverse_error":
            strategy = "weighted_average"

        inp = ForecastInput(
            ticker=symbol.upper(),
            ohlcv=ohlcv,
            horizon=horizon,
            context_len=context_len,
            timeframe=timeframe,
        )
        per_model, ensemble = forecast_ensemble(
            models,
            inp,
            strategy=strategy,
            weights=weights,
        )
        models_used = [str(r.model_name) for r in per_model]
        if ensemble is None or not per_model or self._ensemble_is_persistence_only(models_used):
            # Persistence-only (or empty) is a flat last-close path — use Kronos/Prediction fallback.
            frame, timestamps = self._window_frame(bars)
            future = self._future_timestamps(timestamps[-1].to_pydatetime(), timeframe, horizon)
            predicted, model_meta = self._predict_frame(frame, timestamps, future, horizon)
            model_meta = {
                **model_meta,
                "engine": "ensemble",
                "ensemble_degraded": True,
                "fallback_from": "ensemble",
                "models_used": models_used or ["persistence"],
                "strategy": strategy,
            }
            return predicted, model_meta

        predicted = ensemble.predicted.reset_index(drop=True).copy()
        if "close" not in predicted.columns:
            raise RuntimeError("Ensemble forecast missing close column")
        close = predicted["close"].astype(float)
        for col in ("open", "high", "low"):
            if col not in predicted.columns:
                predicted[col] = close
        if "volume" not in predicted.columns:
            predicted["volume"] = 0.0
        if "amount" not in predicted.columns:
            predicted["amount"] = 0.0

        model_meta = {
            "id": "ensemble",
            "tokenizer_id": "none",
            "device": self.settings.kronos_device,
            "context": context_len,
            "horizon": horizon,
            "fallback": False,
            "engine": "ensemble",
            "strategy": strategy,
            "models_used": models_used,
            "weights": {name: float(weights.get(name, 1.0)) for name in models_used},
        }
        return predicted, model_meta

    def _predict_change(self, bars: list[dict[str, Any]], timeframe: str, horizon: int) -> float:
        frame, timestamps = self._window_frame(bars)
        future = self._future_timestamps(timestamps[-1].to_pydatetime(), timeframe, horizon)
        predicted, _meta = self._predict_frame(frame, timestamps, future, horizon)
        first_close = float(frame.iloc[-1]["close"])
        last_close = float(predicted.iloc[-1]["close"])
        return (last_close / first_close - 1.0) if first_close else 0.0

    def _annotate(self, result: dict[str, Any], bars: list[dict[str, Any]], *, evaluate: bool) -> dict[str, Any]:
        horizon = int((result.get("model") or {}).get("horizon") or 1)
        eval_horizon = min(horizon, 20)
        timeframe = str(result.get("timeframe") or "1Day")
        costs = round_trip_cost(bars)
        change = float((result.get("trend") or {}).get("forecast_change") or 0.0)
        net = net_expected_change(change, costs["round_trip_bps"])
        regime = classify_regime(bars)
        evaluation = {
            "folds": 0,
            "hit_rate": None,
            "mean_gross_return": None,
            "mean_net_return": None,
            "ic": None,
            "by_regime": {},
            "fill": "next_open",
        }
        if evaluate and self.settings.kronos_eval_folds > 0:
            eval_context = min(
                int(self.settings.kronos_eval_context),
                max(16, len(bars) - eval_horizon - 1),
            )
            evaluation = walk_forward_evaluate(
                bars,
                lambda window, tf=timeframe, hz=eval_horizon: self._predict_change(window, tf, hz),
                horizon=eval_horizon,
                context=eval_context,
                max_folds=int(self.settings.kronos_eval_folds),
            )
            if eval_horizon != horizon:
                evaluation["eval_horizon"] = eval_horizon
        live_oos = score_journal(
            list(self._journal),
            bars,
            symbol=str(result.get("symbol") or ""),
            timeframe=timeframe,
            horizon=horizon,
        )
        evaluation["live_oos"] = live_oos
        evaluation["edge_reliable"] = edge_is_reliable(evaluation, regime)
        trend = dict(result.get("trend") or {})
        trend["net_forecast_change"] = net
        result = {
            **result,
            "trend": trend,
            "costs": costs,
            "regime": regime,
            "evaluation": evaluation,
        }
        self._append_journal({
            "symbol": result.get("symbol"),
            "timeframe": timeframe,
            "horizon": horizon,
            "as_of": result.get("as_of"),
            "forecast_change": change,
            "round_trip_bps": costs["round_trip_bps"],
            "regime": regime.get("label"),
        })
        return result

    def forecast(
        self,
        symbol: str,
        preset: str,
        timeframe: str | None = None,
        context: int | None = None,
        horizon: int | None = None,
        bars: list[dict[str, Any]] | None = None,
        use_cache: bool = True,
        evaluate: bool = True,
        engine: str = "kronos",
    ) -> dict[str, Any]:
        engine = "ensemble" if str(engine).lower() == "ensemble" else "kronos"
        defaults = PRESETS[preset]
        timeframe = timeframe or str(defaults["timeframe"])
        context = min(context or int(defaults["context"]), self.settings.kronos_max_context, 512)
        horizon = horizon or int(defaults["horizon"])
        # Ensemble OOS folds are too expensive (N models × folds); skip by default.
        if engine == "ensemble":
            evaluate = False
        cache_key = (symbol.upper(), preset, timeframe, context, horizon, engine)
        if use_cache:
            cached = self._forecast_cache.get(cache_key)
            if cached is not None:
                return cached

        end = datetime.now(timezone.utc)
        if timeframe == "1Day":
            start = end - timedelta(days=max(90, context * 2))
        else:
            start = end - timedelta(days=max(7, context // 12))
        if bars is None:
            bars = self.alpaca.bars(symbol, timeframe, start, end, context)
        if len(bars) < 32:
            raise ValueError("At least 32 historical bars are required for a forecast")
        bars = bars[-context:]
        frame, timestamps = self._window_frame(bars)
        future = self._future_timestamps(timestamps[-1].to_pydatetime(), timeframe, horizon)
        if engine == "ensemble":
            predicted, model_meta = self._ensemble_predict_frame(
                symbol, bars, timeframe, horizon, context
            )
        else:
            predicted, model_meta = self._predict_frame(frame, timestamps, future, horizon)
        historical = [
            {"timestamp": timestamp.isoformat(), **row}
            for timestamp, row in zip(timestamps, bars, strict=True)
        ]
        forecast = [
            {"timestamp": timestamp.isoformat(), **jsonable(row.to_dict())}
            for timestamp, (_, row) in zip(future, predicted.iterrows(), strict=True)
        ]
        first_close = float(frame.iloc[-1]["close"])
        last_close = float(predicted.iloc[-1]["close"])
        change = (last_close / first_close - 1.0) if first_close else 0.0
        trend = "up" if change > 0.002 else "down" if change < -0.002 else "flat"
        segment_closes = [first_close] + [float(row["close"]) for row in forecast]
        segment_timestamps = [timestamps[-1].isoformat()] + [row["timestamp"] for row in forecast]
        result = {
            "symbol": symbol.upper(),
            "preset": preset,
            "timeframe": timeframe,
            "as_of": timestamps[-1].isoformat(),
            "model": model_meta,
            "trend": {"direction": trend, "forecast_change": change},
            "historical": historical,
            "forecast": forecast,
            "path_segments": path_segments(segment_closes, segment_timestamps),
        }
        result = self._annotate(result, bars, evaluate=evaluate)
        if use_cache:
            self._forecast_cache[cache_key] = result
        return result

    def _scan_preset(self) -> tuple[str, dict[str, Any]]:
        try:
            clock = self.alpaca.market_clock("paper")
        except Exception:
            clock = {"is_open": False, "session": "closed"}
        session = str(clock.get("session") or "closed")
        intraday = bool(clock.get("is_open")) or session in {"regular", "pre_market", "after_hours"}
        preset = "scan_intraday" if intraday else "scan_daily"
        return preset, clock

    def _scan_universe(self) -> list[str]:
        unique = list(dict.fromkeys(symbol.upper() for symbol in BLUE_CHIP_UNIVERSE if symbol))
        return unique[:SCAN_UNIVERSE_CAP]

    def _min_scan_volume(self) -> int:
        feed = str(getattr(self.settings, "alpaca_data_feed", "iex") or "iex").lower()
        return MIN_SCAN_VOLUME_SIP if feed == "sip" else MIN_SCAN_VOLUME_IEX

    @staticmethod
    def _snapshot_volume(snapshot: dict[str, Any] | None) -> float | None:
        """Best available full-day volume for liquidity checks.

        Prefer the larger of today's and the prior session's volume so after-hours
        / overnight partial session prints do not false-fail liquid blue chips.
        """
        if not snapshot:
            return None
        volumes: list[float] = []
        for key in ("previous_daily", "daily"):
            bar = snapshot.get(key)
            if not isinstance(bar, dict):
                continue
            raw = bar.get("volume")
            if raw is None:
                continue
            try:
                volumes.append(float(raw))
            except (TypeError, ValueError):
                continue
        return max(volumes) if volumes else None

    @staticmethod
    def _day_change(snapshot: dict[str, Any] | None) -> float | None:
        if not snapshot:
            return None
        daily = snapshot.get("daily") or {}
        previous = snapshot.get("previous_daily") or {}
        last = snapshot.get("current_price")
        close = daily.get("close") if isinstance(daily, dict) else None
        previous_close = previous.get("close") if isinstance(previous, dict) else None
        price = last if last is not None else close
        try:
            if price is None or previous_close in (None, 0):
                return None
            return float(price) / float(previous_close) - 1.0
        except (TypeError, ValueError, ZeroDivisionError):
            return None

    def scan_movers(self, limit: int = SCAN_LIMIT, refresh: bool = False) -> dict[str, Any]:
        limit = max(1, min(int(limit), SCAN_LIMIT))
        if not refresh:
            cached = self._scan_cache.get("movers")
            if cached is not None:
                return {**cached, "movers": cached["movers"][:limit], "cached": True}
        with self._scan_lock:
            if not refresh:
                cached = self._scan_cache.get("movers")
                if cached is not None:
                    return {**cached, "movers": cached["movers"][:limit], "cached": True}
            result = self._run_scan(limit)
            self._scan_cache["movers"] = result
            return result

    def start_movers_scan(self, limit: int = SCAN_LIMIT, refresh: bool = False) -> dict[str, Any]:
        """Return cached data immediately or launch a progressive background scan."""
        limit = max(1, min(int(limit), SCAN_LIMIT))
        if not refresh:
            cached = self._scan_cache.get("movers")
            if cached is not None:
                return {**cached, "cached": True, "status": "ready"}
        with self._scan_progress_lock:
            if self._scan_thread is not None and self._scan_thread.is_alive():
                return dict(self._scan_progress or {"status": "pending", "movers": []})
            self._scan_progress = {
                "status": "pending",
                "as_of": datetime.now(timezone.utc).isoformat(),
                "scanned": 0,
                "total": 0,
                "movers": [],
                "gainers": [],
                "losers": [],
                "cached": False,
            }
            self._scan_thread = threading.Thread(
                target=self._background_scan,
                args=(limit,),
                name="kronos-movers-scan",
                daemon=True,
            )
            self._scan_thread.start()
            return dict(self._scan_progress)

    def movers_scan_status(self) -> dict[str, Any]:
        cached = self._scan_cache.get("movers")
        with self._scan_progress_lock:
            if self._scan_thread is not None and self._scan_thread.is_alive():
                return dict(self._scan_progress or {"status": "pending", "movers": []})
        if cached is not None:
            return {**cached, "cached": True, "status": "ready"}
        return {"status": "idle", "movers": [], "gainers": [], "losers": [], "scanned": 0}

    def _background_scan(self, limit: int) -> None:
        try:
            with self._scan_lock:
                result = self._run_scan(limit)
                self._scan_cache["movers"] = result
            with self._scan_progress_lock:
                self._scan_progress = {**result, "status": "ready"}
        except Exception:
            logger.exception("movers_scan_failed")
            with self._scan_progress_lock:
                self._scan_progress = {
                    **(self._scan_progress or {}),
                    "status": "error",
                    "error": "Mover scan failed; check server logs",
                }

    def _run_scan(self, limit: int) -> dict[str, Any]:
        preset, clock = self._scan_preset()
        defaults = PRESETS[preset]
        timeframe = str(defaults["timeframe"])
        context = int(defaults["context"])
        horizon = int(defaults["horizon"])
        symbols = self._scan_universe()
        snapshots: dict[str, dict[str, Any]] = {}
        bars_by_symbol: dict[str, list[dict[str, Any]]] = {}
        try:
            snapshots = self.alpaca.snapshots_many(symbols)
        except Exception:
            snapshots = {}
        try:
            end = datetime.now(timezone.utc)
            if timeframe == "1Day":
                start = end - timedelta(days=max(90, context * 2))
            else:
                start = end - timedelta(days=max(7, context // 12))
            bars_by_symbol = self.alpaca.bars_many(symbols, timeframe, start, end, context)
        except Exception:
            bars_by_symbol = {}

        movers: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        with self._scan_progress_lock:
            self._scan_progress = {
                **(self._scan_progress or {}),
                "status": "pending",
                "total": len(symbols),
                "timeframe": timeframe,
                "session": clock.get("session"),
            }
        for symbol in symbols:
            volume = self._snapshot_volume(snapshots.get(symbol))
            min_volume = self._min_scan_volume()
            if volume is not None and volume < min_volume:
                skipped.append(
                    {
                        "symbol": symbol,
                        "message": f"Liquidity volume {int(volume):,} below {min_volume:,} floor",
                    }
                )
                self._publish_scan_progress(movers, skipped, len(symbols), timeframe, clock)
                continue
            try:
                forecast = self.forecast(
                    symbol,
                    preset,
                    timeframe,
                    context,
                    horizon,
                    bars=bars_by_symbol.get(symbol) or None,
                    use_cache=False,
                    evaluate=False,
                )
            except Exception as exc:
                logger.warning(
                    "movers_symbol_skipped",
                    extra={"symbol": symbol, "error_type": type(exc).__name__},
                )
                skipped.append({"symbol": symbol, "message": "Forecast unavailable"})
                self._publish_scan_progress(movers, skipped, len(symbols), timeframe, clock)
                continue
            snapshot = snapshots.get(symbol) or {}
            daily = snapshot.get("daily") if isinstance(snapshot.get("daily"), dict) else {}
            trend = forecast.get("trend") or {}
            last_price = snapshot.get("current_price")
            if last_price is None:
                historical = forecast.get("historical") or []
                last_price = historical[-1]["close"] if historical else None
            forecast_bars = forecast.get("forecast") or []
            last_forecast = forecast_bars[-1] if forecast_bars else {}
            predicted = last_forecast.get("close")
            prediction_end = last_forecast.get("timestamp")
            volume = daily.get("volume") if daily else None
            movers.append(
                {
                    "symbol": symbol,
                    "last_price": last_price,
                    "predicted_price": predicted,
                    "forecast_change": trend.get("forecast_change"),
                    "net_forecast_change": trend.get("net_forecast_change"),
                    "direction": trend.get("direction"),
                    "day_change": self._day_change(snapshot),
                    "volume": volume,
                    "as_of": forecast.get("as_of"),
                    "prediction_end": prediction_end,
                    "horizon": (forecast.get("model") or {}).get("horizon")
                    or (forecast.get("horizon")),
                    "regime": (forecast.get("regime") or {}).get("label"),
                    "edge_reliable": (forecast.get("evaluation") or {}).get("edge_reliable"),
                    "round_trip_bps": (forecast.get("costs") or {}).get("round_trip_bps"),
                }
            )
            self._publish_scan_progress(movers, skipped, len(symbols), timeframe, clock)

        movers.sort(key=lambda item: abs(_ranked_change(item)), reverse=True)
        gainers = sorted(
            (item for item in movers if _ranked_change(item) >= 0),
            key=_ranked_change,
            reverse=True,
        )[:limit]
        losers = sorted(
            (item for item in movers if _ranked_change(item) < 0),
            key=_ranked_change,
        )[:limit]
        generated = datetime.now(timezone.utc).isoformat()
        return {
            "status": "ready",
            "as_of": generated,
            "session": clock.get("session"),
            "market_open": bool(clock.get("is_open")),
            "preset": preset,
            "timeframe": timeframe,
            "scanned": len(movers) + len(skipped),
            "cached": False,
            "movers": movers[:limit],
            "gainers": gainers,
            "losers": losers,
            "skipped": skipped[:12],
        }

    def _publish_scan_progress(
        self,
        movers: list[dict[str, Any]],
        skipped: list[dict[str, str]],
        total: int,
        timeframe: str,
        clock: dict[str, Any],
    ) -> None:
        ranked = sorted(
            movers,
            key=lambda item: abs(_ranked_change(item)),
            reverse=True,
        )
        gainers = sorted(
            (item for item in ranked if _ranked_change(item) >= 0),
            key=_ranked_change,
            reverse=True,
        )[:SCAN_LIMIT]
        losers = sorted(
            (item for item in ranked if _ranked_change(item) < 0),
            key=_ranked_change,
        )[:SCAN_LIMIT]
        with self._scan_progress_lock:
            self._scan_progress = {
                "status": "pending",
                "as_of": datetime.now(timezone.utc).isoformat(),
                "session": clock.get("session"),
                "market_open": bool(clock.get("is_open")),
                "timeframe": timeframe,
                "scanned": len(movers) + len(skipped),
                "total": total,
                "cached": False,
                "movers": ranked[:SCAN_LIMIT],
                "gainers": gainers,
                "losers": losers,
                "skipped": skipped[:12],
            }
