"""End-to-end hybrid prediction orchestration (MVP-1)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd

from ml import FEATURE_VERSION
from ml.calibration import calibrate_probability
from ml.config import get_prediction_config, horizon_to_bars, load_prediction_config
from ml.data.loaders import bars_to_ohlcv, filter_bars_as_of
from ml.decision import decide_signal
from ml.ensemble import combine_probabilities, model_agreement
from ml.explanation import explain_prediction
from ml.features.feature_pipeline import build_feature_snapshot, compute_technical_frame
from ml.models.targets import add_forward_return_target
from ml.models.xgboost_model import XGBoostModel
from ml.observability import log_prediction
from ml.regime import classify_market_regime
from ml.registry import ModelRegistry, ModelRecord
from ml.risk import assess_risk


class PredictionEngine:
    """Train/cache XGBoost (and future plugins) and emit signals with lineage."""

    def __init__(
        self,
        *,
        config: dict[str, Any] | None = None,
        config_path: Path | str | None = None,
        registry: ModelRegistry | None = None,
        root_dir: Path | str | None = None,
    ) -> None:
        if config is not None:
            self.config = config
        elif config_path is not None:
            self.config = load_prediction_config(config_path)
        else:
            self.config = get_prediction_config()
        self.root_dir = Path(root_dir) if root_dir else Path(__file__).resolve().parents[1]
        store = self.config.get("registry", {}).get("store_dir", "backend/data/model_registry")
        store_path = Path(store)
        if not store_path.is_absolute():
            store_path = self.root_dir / store_path
        self.registry = registry or ModelRegistry(store_path)

    def predict_from_bars(
        self,
        ticker: str,
        bars: list[dict[str, Any]],
        *,
        horizon: str = "5d",
        as_of: datetime | str | None = None,
        retrain: bool = False,
    ) -> dict[str, Any]:
        started = perf_counter()
        pred_cfg = self.config.get("prediction", {})
        feature_version = str(pred_cfg.get("feature_version") or FEATURE_VERSION)
        horizon_key = horizon.strip().lower()
        horizon_bars = horizon_to_bars(horizon_key)
        ohlcv = bars_to_ohlcv(bars)
        if ohlcv.empty:
            raise ValueError("no market bars available")

        if as_of is not None:
            ohlcv = filter_bars_as_of(ohlcv, as_of)
            if ohlcv.empty:
                raise ValueError("no bars available at as_of timestamp")

        lookback = int(pred_cfg.get("lookback_bars", 400))
        if len(ohlcv) > lookback:
            ohlcv = ohlcv.iloc[-lookback:].copy()

        snapshot = build_feature_snapshot(ticker, ohlcv, as_of=ohlcv.index.max(), feature_version=feature_version)
        regime = classify_market_regime(ohlcv)
        snapshot.market_regime = regime

        model_probs: dict[str, float] = {}
        model_versions: dict[str, str] = {}
        training_cutoff = snapshot.data_cutoff

        if self.config.get("models", {}).get("xgboost", {}).get("enabled", True):
            xgb_prob, xgb_meta = self._xgboost_probability(
                ticker=ticker.upper(),
                ohlcv=ohlcv,
                horizon=horizon_key,
                horizon_bars=horizon_bars,
                feature_version=feature_version,
                snapshot_features=snapshot.technical,
                retrain=retrain,
            )
            model_probs["xgboost"] = xgb_prob
            model_versions["xgboost"] = xgb_meta["model_version"]
            training_cutoff = xgb_meta["training_cutoff"]

        if not model_probs:
            raise RuntimeError("no enabled prediction models")

        strategy = self.config.get("ensemble", {}).get("strategy", "equal_weight")
        weights = {
            name: float(self.config.get("models", {}).get(name, {}).get("weight", 1.0))
            for name in model_probs
        }
        raw_probability = combine_probabilities(model_probs, weights=weights, strategy=strategy)
        cal_method = self.config.get("calibration", {}).get("method", "identity")
        probability = calibrate_probability(raw_probability, method=cal_method)
        agreement = model_agreement(model_probs)

        decision = decide_signal(
            probability,
            config=self.config.get("decision"),
            model_agreement=agreement if len(model_probs) > 1 else 1.0,
        )

        tech = snapshot.technical
        risk = assess_risk(
            predicted_probability=probability,
            expected_return=None,
            volatility=tech.get("rolling_volatility"),
            atr=tech.get("atr"),
            drawdown=tech.get("drawdown"),
            market_regime=regime.get("regime"),
            model_agreement=agreement,
            data_quality=1.0 if len(tech) >= 10 else 0.5,
            config=self.config.get("risk"),
        )

        structured = {
            "ticker": ticker.upper(),
            "signal": decision["signal"],
            "probability": round(probability, 6),
            "raw_probability": round(raw_probability, 6),
            "risk_score": risk["risk_score"],
            "confidence": risk["confidence_score"],
            "horizon": horizon_key,
            "model_predictions": {k: round(v, 6) for k, v in model_probs.items()},
            "model_agreement": round(agreement, 6),
            "market_regime": regime,
            "technical_score": _technical_score(tech),
            "institutional_score": None,
            "fundamental_score": None,
        }
        explanation = explain_prediction(
            structured,
            llm_enabled=bool(self.config.get("llm", {}).get("enabled")),
        )

        latency_ms = round((perf_counter() - started) * 1000, 2)
        result = {
            "ticker": ticker.upper(),
            "timestamp": snapshot.timestamp.isoformat(),
            "horizon": horizon_key,
            "signal": decision["signal"],
            "probability": structured["probability"],
            "raw_probability": structured["raw_probability"],
            "expected_return": risk.get("expected_return"),
            "risk_score": risk["risk_score"],
            "confidence": risk["confidence_score"],
            "prediction_probability": structured["probability"],
            "model_confidence": round(agreement, 6),
            "data_confidence": 1.0 if len(tech) >= 10 else 0.5,
            "signal_confidence": risk["confidence_score"],
            "model_predictions": structured["model_predictions"],
            "model_versions": model_versions,
            "model_agreement": structured["model_agreement"],
            "feature_version": feature_version,
            "feature_snapshot": snapshot.to_dict(),
            "training_cutoff": training_cutoff.isoformat()
            if isinstance(training_cutoff, datetime)
            else str(training_cutoff),
            "decision": decision,
            "risk": risk,
            "market_regime": regime,
            "explanation": explanation,
            "latency_ms": latency_ms,
        }
        log_prediction(
            {
                "ticker": result["ticker"],
                "timestamp": result["timestamp"],
                "feature_version": feature_version,
                "horizon": horizon_key,
                "signal": result["signal"],
                "probability": result["probability"],
                "risk_score": result["risk_score"],
                "latency_ms": latency_ms,
                "model_versions": model_versions,
            }
        )
        return result

    def features_from_bars(
        self,
        ticker: str,
        bars: list[dict[str, Any]],
        *,
        as_of: datetime | str | None = None,
    ) -> dict[str, Any]:
        ohlcv = bars_to_ohlcv(bars)
        snapshot = build_feature_snapshot(ticker, ohlcv, as_of=as_of)
        return snapshot.to_dict()

    def _xgboost_probability(
        self,
        *,
        ticker: str,
        ohlcv: pd.DataFrame,
        horizon: str,
        horizon_bars: int,
        feature_version: str,
        snapshot_features: dict[str, float],
        retrain: bool,
    ) -> tuple[float, dict[str, Any]]:
        key = self.registry.key(ticker, horizon, feature_version, "xgboost")
        model: XGBoostModel | None = None
        training_cutoff = ohlcv.index.max().to_pydatetime()
        if training_cutoff.tzinfo is None:
            training_cutoff = training_cutoff.replace(tzinfo=timezone.utc)

        if not retrain:
            cached = self.registry.load_artifact(key)
            if isinstance(cached, XGBoostModel):
                model = cached
                record = self.registry.get(key)
                if record and record.training_cutoff:
                    training_cutoff = datetime.fromisoformat(record.training_cutoff)

        if model is None:
            feature_frame = compute_technical_frame(ohlcv)
            threshold = float(self.config.get("prediction", {}).get("return_threshold", 0.0))
            dataset = add_forward_return_target(
                ohlcv,
                feature_frame,
                horizon_bars=horizon_bars,
                threshold=threshold,
            )
            min_rows = int(self.config.get("prediction", {}).get("min_train_rows", 80))
            if len(dataset) < min_rows:
                raise ValueError(
                    f"need at least {min_rows} training rows after features/labels; got {len(dataset)}"
                )
            params = self.config.get("models", {}).get("xgboost", {}).get("params") or {}
            model = XGBoostModel(params=params)
            model.train(dataset)
            # Training cutoff is last label row timestamp (no future labels used)
            training_cutoff = dataset.index.max().to_pydatetime()
            if training_cutoff.tzinfo is None:
                training_cutoff = training_cutoff.replace(tzinfo=timezone.utc)
            record = ModelRecord(
                model_id=key,
                model_type="xgboost",
                version=model.version,
                feature_version=feature_version,
                prediction_horizon=horizon,
                training_period=f"{dataset.index.min().date()}→{dataset.index.max().date()}",
                training_timestamp=ModelRegistry.utc_now_iso(),
                training_cutoff=training_cutoff.isoformat(),
                validation_metrics={"train_rows": float(model.training_rows)},
                status="active",
            )
            self.registry.save(key, model=model, record=record)

        probability = model.predict_probability(snapshot_features)
        return probability, {
            "model_version": model.version,
            "training_cutoff": training_cutoff,
            "model_id": key,
        }


def _technical_score(technical: dict[str, float]) -> float | None:
    keys = ("distance_from_sma50", "rsi", "macd_histogram", "volume_ratio")
    present = [technical[k] for k in keys if k in technical]
    if not present:
        return None
    # Normalize a few features into a rough 0-1 research score (not a trade rule).
    rsi = technical.get("rsi")
    dist = technical.get("distance_from_sma50")
    score = 0.5
    if rsi is not None:
        score += (rsi - 50.0) / 200.0
    if dist is not None:
        score += max(-0.2, min(0.2, dist))
    return round(max(0.0, min(1.0, score)), 4)
