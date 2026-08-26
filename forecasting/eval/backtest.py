"""Walk-forward forecast backtest with optional result cache."""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from forecasting.core.base import ForecastModel
from forecasting.core.schema import ForecastInput, ForecastResult
from forecasting.eval.metrics import path_metrics, rank_ic, sharpe_of_signal

logger = logging.getLogger("forecasting.eval")

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache"


@dataclass
class FoldScore:
    as_of: str
    model_name: str
    ticker: str
    metrics: dict[str, float]
    meta: dict[str, Any] = field(default_factory=dict)


def _cache_key(
    ticker: str,
    as_of: str,
    model_name: str,
    horizon: int,
    checkpoint: str,
) -> str:
    raw = f"{ticker}|{as_of}|{model_name}|{horizon}|{checkpoint}"
    return hashlib.sha256(raw.encode()).hexdigest()


class ForecastCache:
    """Cache raw ForecastResult pickles keyed by (ticker, as_of, model, horizon, checkpoint)."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else DEFAULT_CACHE_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    def get(
        self,
        *,
        ticker: str,
        as_of: str,
        model_name: str,
        horizon: int,
        checkpoint: str,
    ) -> ForecastResult | None:
        key = _cache_key(ticker, as_of, model_name, horizon, checkpoint)
        path = self.root / f"{key}.pkl"
        if not path.exists():
            return None
        with path.open("rb") as handle:
            return pickle.load(handle)

    def put(
        self,
        result: ForecastResult,
        *,
        ticker: str,
        as_of: str,
        model_name: str,
        horizon: int,
        checkpoint: str,
    ) -> None:
        key = _cache_key(ticker, as_of, model_name, horizon, checkpoint)
        path = self.root / f"{key}.pkl"
        with path.open("wb") as handle:
            pickle.dump(result, handle)


def _checkpoint_of(model: ForecastModel, result: ForecastResult | None = None) -> str:
    if result and isinstance(result.meta, dict):
        ckpt = result.meta.get("checkpoint") or result.meta.get("model_id")
        if ckpt:
            return str(ckpt)
    return getattr(model, "checkpoint", None) or getattr(model, "model_id", None) or model.name


def walk_forward_backtest(
    ohlcv: pd.DataFrame,
    models: Sequence[ForecastModel],
    *,
    ticker: str,
    horizon: int = 5,
    context_len: int = 64,
    step: int = 5,
    timeframe: str = "1Day",
    weights: dict[str, float] | None = None,
    strategy: str = "weighted_average",
    cache: ForecastCache | None = None,
    min_history: int | None = None,
) -> dict[str, Any]:
    """Walk-forward evaluation for each model and the ensemble.

    For each as-of index ``i``, models see ``ohlcv.iloc[: i + 1]`` (tail context),
    predict ``horizon`` bars, and are scored against ``ohlcv.iloc[i + 1 : i + 1 + horizon]``.
    """
    if not isinstance(ohlcv.index, pd.DatetimeIndex):
        raise ValueError("ohlcv must have DatetimeIndex")
    need = (min_history or context_len) + horizon
    if len(ohlcv) < need:
        raise ValueError(f"need at least {need} bars, got {len(ohlcv)}")

    scores: list[FoldScore] = []
    trailing_mae: dict[str, list[float]] = defaultdict(list)
    cross_section_pred: dict[str, list[float]] = defaultdict(list)
    cross_section_act: list[float] = []

    start_i = max(context_len, min_history or context_len) - 1
    end_i = len(ohlcv) - horizon - 1
    for i in range(start_i, end_i + 1, step):
        as_of_ts = ohlcv.index[i]
        as_of = str(as_of_ts)
        history = ohlcv.iloc[: i + 1]
        actual = ohlcv.iloc[i + 1 : i + 1 + horizon]["close"].astype(float)
        last_close = float(history["close"].iloc[-1])
        inp = ForecastInput(
            ticker=ticker,
            ohlcv=history,
            horizon=horizon,
            context_len=context_len,
            timeframe=timeframe,
        )

        per_model: list[ForecastResult] = []
        for model in models:
            if not model.supports(inp):
                logger.info("skip %s at %s (unsupported)", model.name, as_of)
                continue
            ckpt = _checkpoint_of(model)
            result: ForecastResult | None = None
            if cache is not None:
                result = cache.get(
                    ticker=ticker,
                    as_of=as_of,
                    model_name=model.name,
                    horizon=horizon,
                    checkpoint=ckpt,
                )
            if result is None:
                try:
                    result = model.predict(inp)
                except Exception:
                    logger.exception("predict failed for %s at %s", model.name, as_of)
                    continue
                if cache is not None:
                    cache.put(
                        result,
                        ticker=ticker,
                        as_of=as_of,
                        model_name=model.name,
                        horizon=horizon,
                        checkpoint=_checkpoint_of(model, result),
                    )
            per_model.append(result)
            metrics = path_metrics(result.predicted["close"], actual, last_close=last_close)
            scores.append(
                FoldScore(
                    as_of=as_of,
                    model_name=model.name,
                    ticker=ticker,
                    metrics=metrics,
                    meta={"checkpoint": _checkpoint_of(model, result)},
                )
            )
            if metrics.get("mae") == metrics.get("mae"):  # not NaN
                trailing_mae[model.name].append(float(metrics["mae"]))
            if "pred_horizon_return" in metrics:
                cross_section_pred[model.name].append(float(metrics["pred_horizon_return"]))

        act_ret = float(actual.iloc[-1] / last_close - 1.0) if last_close else 0.0
        if per_model:
            cross_section_act.append(act_ret)

        if per_model:
            recent = {
                name: (sum(vals[-20:]) / len(vals[-20:]))
                for name, vals in trailing_mae.items()
                if vals
            }
            use_strategy = strategy
            if strategy == "inverse_error" and not recent:
                use_strategy = "weighted_average"
            from forecasting.ensemble.combine import combine_results

            ensemble = combine_results(
                per_model,
                strategy=use_strategy,
                weights=weights,
                recent_mae=recent if use_strategy == "inverse_error" else None,
                ticker=ticker,
            )
            em = path_metrics(ensemble.predicted["close"], actual, last_close=last_close)
            scores.append(
                FoldScore(
                    as_of=as_of,
                    model_name="ensemble",
                    ticker=ticker,
                    metrics=em,
                    meta=dict(ensemble.meta),
                )
            )

    summary = _summarize(scores, cross_section_pred, cross_section_act)
    return {"folds": [asdict(s) for s in scores], "summary": summary}


def _summarize(
    scores: list[FoldScore],
    cross_section_pred: dict[str, list[float]],
    cross_section_act: list[float],
) -> dict[str, Any]:
    by_model: dict[str, list[dict[str, float]]] = defaultdict(list)
    for score in scores:
        by_model[score.model_name].append(score.metrics)

    summary: dict[str, Any] = {}
    for name, rows in by_model.items():
        frame = pd.DataFrame(rows)
        entry: dict[str, Any] = {
            "folds": len(rows),
            "mae": float(frame["mae"].mean()) if "mae" in frame else float("nan"),
            "rmse": float(frame["rmse"].mean()) if "rmse" in frame else float("nan"),
            "directional_accuracy": float(frame["directional_accuracy"].mean())
            if "directional_accuracy" in frame
            else float("nan"),
            "horizon_dir_hit": float(frame["horizon_dir_hit"].mean())
            if "horizon_dir_hit" in frame
            else float("nan"),
        }
        preds = cross_section_pred.get(name) or []
        if len(preds) >= 2 and len(cross_section_act) >= 2:
            n = min(len(preds), len(cross_section_act))
            entry["rank_ic"] = rank_ic(preds[:n], cross_section_act[:n])
            entry["signal_sharpe"] = sharpe_of_signal(preds[:n], cross_section_act[:n])
        summary[name] = entry

    # Ensemble earns complexity only if it beats best single model on MAE
    singles = {k: v for k, v in summary.items() if k != "ensemble"}
    if "ensemble" in summary and singles:
        best_single = min(singles.items(), key=lambda kv: kv[1].get("mae", float("inf")))
        ens_mae = summary["ensemble"].get("mae", float("inf"))
        summary["ensemble"]["beats_best_single"] = bool(ens_mae < best_single[1].get("mae", float("inf")))
        summary["ensemble"]["best_single"] = best_single[0]
    return summary


def write_summary(summary: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
