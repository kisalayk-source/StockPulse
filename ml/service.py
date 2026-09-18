"""End-to-end hybrid prediction orchestration (MVP-2 ensemble + calibration)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

import numpy as np
import pandas as pd

from ml import FEATURE_VERSION
from ml.backtesting.metrics import classification_metrics, summarize_metrics
from ml.calibration import fit_calibrator
from ml.config import get_prediction_config, horizon_to_bars, load_prediction_config
from ml.data.loaders import bars_to_ohlcv, filter_bars_as_of
from ml.decision import decide_signal
from ml.ensemble import combine_probabilities, model_agreement
from ml.explanation import explain_prediction
from ml.features.feature_pipeline import build_feature_snapshot, compute_technical_frame
from ml.features.government import compute_government_features
from ml.models.artifact import CalibratedArtifact
from ml.models.kronos import KronosModel
from ml.models.lightgbm_model import LightGBMModel
from ml.models.targets import add_forward_return_target
from ml.models.xgboost_model import XGBoostModel
from ml.observability import log_prediction
from ml.regime import classify_market_regime
from ml.registry import ModelRegistry, ModelRecord
from ml.risk import apply_risk_gate, assess_risk

PathForecastFn = Callable[[str, str, pd.DataFrame], dict[str, Any] | None]


class PredictionEngine:
    """Train/cache directional models, ensemble, calibrate, and emit signals."""

    def __init__(
        self,
        *,
        config: dict[str, Any] | None = None,
        config_path: Path | str | None = None,
        registry: ModelRegistry | None = None,
        root_dir: Path | str | None = None,
        path_forecast_fn: PathForecastFn | None = None,
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
        self.path_forecast_fn = path_forecast_fn

    def set_path_forecast_fn(self, fn: PathForecastFn | None) -> None:
        self.path_forecast_fn = fn

    def predict_from_bars(
        self,
        ticker: str,
        bars: list[dict[str, Any]],
        *,
        horizon: str = "5d",
        as_of: datetime | str | None = None,
        retrain: bool = False,
        sec_events: list[dict[str, Any]] | None = None,
        fundamentals_metrics: dict[str, Any] | None = None,
        government_events: list[dict[str, Any]] | None = None,
        annual_revenue: float | None = None,
        government_config: dict[str, Any] | None = None,
        position_concentration: float | None = None,
    ) -> dict[str, Any]:
        started = perf_counter()
        pred_cfg = self.config.get("prediction", {})
        feature_flags = self.config.get("features") or {}
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

        snapshot = build_feature_snapshot(
            ticker,
            ohlcv,
            as_of=ohlcv.index.max(),
            feature_version=feature_version,
            sec_events=sec_events if feature_flags.get("sec", False) else None,
            fundamentals_metrics=fundamentals_metrics if feature_flags.get("fundamentals", False) else None,
            government_events=government_events if feature_flags.get("government", False) else None,
            annual_revenue=annual_revenue,
            government_config=government_config,
        )
        regime = classify_market_regime(ohlcv)
        snapshot.market_regime = regime

        model_features = _merge_model_features(snapshot, feature_flags)
        gov_events_for_train = government_events if feature_flags.get("government", False) else None

        model_probs: dict[str, float] = {}
        model_versions: dict[str, str] = {}
        training_cutoff = snapshot.data_cutoff
        cal_method = str(self.config.get("calibration", {}).get("method", "identity")).lower()

        if self.config.get("models", {}).get("xgboost", {}).get("enabled", True):
            xgb_prob, xgb_meta = self._tree_probability(
                model_type="xgboost",
                model_cls=XGBoostModel,
                ticker=ticker.upper(),
                ohlcv=ohlcv,
                horizon=horizon_key,
                horizon_bars=horizon_bars,
                feature_version=feature_version,
                snapshot_features=model_features,
                retrain=retrain,
                calibration_method=cal_method,
                government_events=gov_events_for_train,
                annual_revenue=annual_revenue,
                government_config=government_config,
            )
            model_probs["xgboost"] = xgb_prob
            model_versions["xgboost"] = xgb_meta["model_version"]
            training_cutoff = xgb_meta["training_cutoff"]

        if self.config.get("models", {}).get("lightgbm", {}).get("enabled", False):
            lgb_prob, lgb_meta = self._tree_probability(
                model_type="lightgbm",
                model_cls=LightGBMModel,
                ticker=ticker.upper(),
                ohlcv=ohlcv,
                horizon=horizon_key,
                horizon_bars=horizon_bars,
                feature_version=feature_version,
                snapshot_features=model_features,
                retrain=retrain,
                calibration_method=cal_method,
                government_events=gov_events_for_train,
                annual_revenue=annual_revenue,
                government_config=government_config,
            )
            model_probs["lightgbm"] = lgb_prob
            model_versions["lightgbm"] = lgb_meta["model_version"]
            training_cutoff = lgb_meta["training_cutoff"]

        if self.config.get("models", {}).get("kronos", {}).get("enabled", False):
            kronos_prob, kronos_meta = self._kronos_probability(
                ticker=ticker.upper(),
                ohlcv=ohlcv,
                horizon=horizon_key,
                volatility=snapshot.technical.get("rolling_volatility"),
            )
            if kronos_prob is not None:
                model_probs["kronos"] = kronos_prob
                model_versions["kronos"] = kronos_meta["model_version"]

        if not model_probs:
            raise RuntimeError("no enabled prediction models")

        strategy = self.config.get("ensemble", {}).get("strategy", "equal_weight")
        weights = {
            name: float(self.config.get("models", {}).get(name, {}).get("weight", 1.0))
            for name in model_probs
        }
        raw_probability = combine_probabilities(model_probs, weights=weights, strategy=strategy)
        # Tree members are already calibrated; ensemble raw is the final P(up).
        probability = float(np.clip(raw_probability, 0.0, 1.0))
        agreement = model_agreement(model_probs)

        decision = decide_signal(
            probability,
            config=self.config.get("decision"),
            model_agreement=agreement if len(model_probs) > 1 else 1.0,
        )

        tech = snapshot.technical
        risk_cfg = self.config.get("risk") or {}
        last_close = float(ohlcv["close"].iloc[-1]) if "close" in ohlcv.columns else None
        price_ref = tech.get("sma_20") or tech.get("sma_50") or last_close
        risk = assess_risk(
            predicted_probability=probability,
            expected_return=None,
            volatility=tech.get("rolling_volatility"),
            atr=tech.get("atr"),
            price=float(price_ref) if price_ref is not None else last_close,
            drawdown=tech.get("drawdown"),
            market_regime=regime.get("regime"),
            model_agreement=agreement,
            data_quality=1.0 if len(tech) >= 10 else 0.5,
            position_concentration=position_concentration,
            config=risk_cfg,
        )
        gate = apply_risk_gate(
            decision["signal"],
            risk,
            volatility=tech.get("rolling_volatility"),
            drawdown=tech.get("drawdown"),
            position_concentration=position_concentration,
            config=risk_cfg,
        )
        decision = {
            **decision,
            "signal": gate["signal"],
            "risk_gate": {
                "action": gate["action"],
                "original_signal": gate["original_signal"],
                "reasons": gate["reasons"],
                "gated": gate["gated"],
            },
        }
        risk = {
            **risk,
            "gate": {
                "action": gate["action"],
                "original_signal": gate["original_signal"],
                "reasons": gate["reasons"],
                "gated": gate["gated"],
            },
        }

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
            "institutional_score": _institutional_score(snapshot.sec),
            "fundamental_score": _fundamental_score(snapshot.fundamentals),
            "government_score": snapshot.government.get("government_score"),
            "calibration_method": cal_method,
            "risk_gate": decision.get("risk_gate"),
        }
        explanation = explain_prediction(structured)

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
            "calibration_method": cal_method,
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
        sec_events: list[dict[str, Any]] | None = None,
        fundamentals_metrics: dict[str, Any] | None = None,
        government_events: list[dict[str, Any]] | None = None,
        annual_revenue: float | None = None,
        government_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        feature_flags = self.config.get("features") or {}
        ohlcv = bars_to_ohlcv(bars)
        snapshot = build_feature_snapshot(
            ticker,
            ohlcv,
            as_of=as_of,
            sec_events=sec_events if feature_flags.get("sec", False) else None,
            fundamentals_metrics=fundamentals_metrics if feature_flags.get("fundamentals", False) else None,
            government_events=government_events if feature_flags.get("government", False) else None,
            annual_revenue=annual_revenue,
            government_config=government_config,
        )
        return snapshot.to_dict()

    def _kronos_probability(
        self,
        *,
        ticker: str,
        ohlcv: pd.DataFrame,
        horizon: str,
        volatility: float | None,
    ) -> tuple[float | None, dict[str, Any]]:
        if self.path_forecast_fn is None:
            return None, {"model_version": KronosModel.version}
        try:
            path_payload = self.path_forecast_fn(ticker, horizon, ohlcv)
        except Exception:
            return None, {"model_version": KronosModel.version}
        if not path_payload:
            return None, {"model_version": KronosModel.version}
        adapter = KronosModel()
        probability = adapter.set_path(path_payload, volatility=volatility)
        return probability, {"model_version": adapter.version, "model_id": f"kronos:{ticker}:{horizon}"}

    def _tree_probability(
        self,
        *,
        model_type: str,
        model_cls: type,
        ticker: str,
        ohlcv: pd.DataFrame,
        horizon: str,
        horizon_bars: int,
        feature_version: str,
        snapshot_features: dict[str, float],
        retrain: bool,
        calibration_method: str,
        government_events: list[dict[str, Any]] | None = None,
        annual_revenue: float | None = None,
        government_config: dict[str, Any] | None = None,
    ) -> tuple[float, dict[str, Any]]:
        key = self.registry.key(ticker, horizon, feature_version, model_type)
        artifact: CalibratedArtifact | None = None
        training_cutoff = ohlcv.index.max().to_pydatetime()
        if training_cutoff.tzinfo is None:
            training_cutoff = training_cutoff.replace(tzinfo=timezone.utc)

        if not retrain:
            cached = self.registry.load_artifact(key)
            artifact = _coerce_artifact(cached, calibration_method=calibration_method)

        if artifact is None:
            feature_frame = compute_technical_frame(ohlcv)
            if government_events is not None:
                feature_frame = _attach_government_features(
                    feature_frame,
                    government_events,
                    annual_revenue=annual_revenue,
                    government_config=government_config,
                )
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
            params = self.config.get("models", {}).get(model_type, {}).get("params") or {}
            model = model_cls(params=params)
            artifact, holdout_metrics = _train_with_holdout_calibration(
                model, dataset, method=calibration_method
            )
            training_cutoff = dataset.index.max().to_pydatetime()
            if training_cutoff.tzinfo is None:
                training_cutoff = training_cutoff.replace(tzinfo=timezone.utc)
            validation_metrics = {
                "train_rows": float(getattr(model, "training_rows", 0) or 0),
                "calibration": 1.0 if artifact.calibrator is not None else 0.0,
            }
            validation_metrics.update(summarize_metrics(holdout_metrics))
            record = ModelRecord(
                model_id=key,
                model_type=model_type,
                version=getattr(model, "version", "1.0"),
                feature_version=feature_version,
                prediction_horizon=horizon,
                training_period=f"{dataset.index.min().date()}→{dataset.index.max().date()}",
                training_timestamp=ModelRegistry.utc_now_iso(),
                training_cutoff=training_cutoff.isoformat(),
                validation_metrics=validation_metrics,
                test_metrics={},
                status="active",
            )
            self.registry.save(key, model=artifact, record=record)

        probability = artifact.predict_probability(snapshot_features)
        return probability, {
            "model_version": getattr(artifact.model, "version", "1.0"),
            "training_cutoff": training_cutoff,
            "model_id": key,
        }


def _coerce_artifact(cached: Any, *, calibration_method: str) -> CalibratedArtifact | None:
    if isinstance(cached, CalibratedArtifact):
        return cached
    if isinstance(cached, (XGBoostModel, LightGBMModel)):
        # Legacy pickle from MVP-1 — wrap without calibrator.
        return CalibratedArtifact(model=cached, calibrator=None, calibration_method="identity")
    return None


def _train_with_holdout_calibration(
    model: Any,
    dataset: pd.DataFrame,
    *,
    method: str,
) -> tuple[CalibratedArtifact, dict[str, float]]:
    method = str(method or "identity").lower()
    n = len(dataset)
    empty_metrics: dict[str, float] = {}
    if method == "identity" or n < 40:
        model.train(dataset)
        return CalibratedArtifact(model=model, calibrator=None, calibration_method="identity"), empty_metrics

    split = max(int(n * 0.8), n - max(12, int(n * 0.2)))
    split = min(split, n - 8)
    if split < 20:
        model.train(dataset)
        return CalibratedArtifact(model=model, calibrator=None, calibration_method="identity"), empty_metrics

    train_ds = dataset.iloc[:split]
    hold_ds = dataset.iloc[split:]
    model.train(train_ds)

    probs: list[float] = []
    labels: list[float] = []
    feature_cols = [c for c in hold_ds.columns if c not in {"target", "forward_return"}]
    for _, row in hold_ds.iterrows():
        feats = {c: float(row[c]) for c in feature_cols if pd.notna(row[c])}
        try:
            probs.append(float(model.predict_probability(feats)))
            labels.append(float(row["target"]))
        except Exception:
            continue

    calibrator = fit_calibrator(labels, probs, method)
    applied = method if calibrator is not None else "identity"
    holdout_metrics = classification_metrics(labels, y_prob=probs) if labels else empty_metrics
    return (
        CalibratedArtifact(model=model, calibrator=calibrator, calibration_method=applied),
        holdout_metrics,
    )


def _technical_score(technical: dict[str, float]) -> float | None:
    keys = ("distance_from_sma50", "rsi", "macd_histogram", "volume_ratio")
    present = [technical[k] for k in keys if k in technical]
    if not present:
        return None
    rsi = technical.get("rsi")
    dist = technical.get("distance_from_sma50")
    score = 0.5
    if rsi is not None:
        score += (rsi - 50.0) / 200.0
    if dist is not None:
        score += max(-0.2, min(0.2, dist))
    return round(max(0.0, min(1.0, score)), 4)


def _institutional_score(sec: dict[str, float]) -> float | None:
    """Map SEC flow component scores (0–100) to a 0–1 institutional score."""
    keys = ("inst_flow_score", "insider_flow_score", "ownership_flow_score")
    present = [sec[k] for k in keys if k in sec]
    if not present:
        return None
    return round(max(0.0, min(1.0, (sum(present) / len(present)) / 100.0)), 4)


def _fundamental_score(fundamentals: dict[str, float]) -> float | None:
    """Map Finnhub metrics to a 0–1 confirmation-style fundamental score."""
    if not fundamentals:
        return None
    score = 50.0
    rev_growth = fundamentals.get("revenue_growth")
    eps_growth = fundamentals.get("eps_growth")
    roic = fundamentals.get("roic")
    pe = fundamentals.get("pe_ratio")
    if rev_growth is not None:
        if rev_growth > 0.05:
            score += 10.0
        elif rev_growth < 0:
            score -= 10.0
    if eps_growth is not None:
        if eps_growth > 0.05:
            score += 10.0
        elif eps_growth < 0:
            score -= 10.0
    if roic is not None and roic > 0.1:
        score += 5.0
    if pe is not None and pe > 35:
        score -= 8.0
    return round(max(0.0, min(1.0, max(0.0, min(100.0, score)) / 100.0)), 4)


def _merge_model_features(snapshot: Any, feature_flags: dict[str, Any]) -> dict[str, float]:
    """Combine enabled feature categories into the tree-model input vector."""
    merged = dict(snapshot.technical or {})
    if feature_flags.get("sec", False):
        merged.update(snapshot.sec or {})
    if feature_flags.get("fundamentals", False):
        merged.update(snapshot.fundamentals or {})
    if feature_flags.get("government", False):
        merged.update(snapshot.government or {})
    return merged


def _attach_government_features(
    feature_frame: pd.DataFrame,
    government_events: list[dict[str, Any]],
    *,
    annual_revenue: float | None = None,
    government_config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Attach PIT government feature columns aligned to each training row timestamp."""
    if feature_frame.empty:
        return feature_frame
    rows: list[dict[str, float]] = []
    index = []
    for ts in feature_frame.index:
        as_of = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
        if getattr(as_of, "tzinfo", None) is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        feats = compute_government_features(
            government_events,
            as_of=as_of,
            annual_revenue=annual_revenue,
            config=government_config,
        )
        rows.append(feats)
        index.append(ts)
    if not rows:
        return feature_frame
    gov_frame = pd.DataFrame(rows, index=index)
    return feature_frame.join(gov_frame, how="left")


__all__ = ["PredictionEngine"]
