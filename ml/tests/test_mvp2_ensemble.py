"""MVP-2 ensemble + calibration unit tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.calibration import calibrate_probability, fit_calibrator
from ml.ensemble import combine_probabilities, model_agreement
from ml.models.kronos import KronosModel, probability_from_path
from ml.models.lightgbm_model import LightGBMModel
from ml.registry import ModelRegistry
from ml.service import PredictionEngine


ROOT = Path(__file__).resolve().parents[2]


def _synthetic_dataset(n: int = 120, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    logits = 1.2 * x1 - 0.8 * x2
    prob = 1.0 / (1.0 + np.exp(-logits))
    target = (rng.random(n) < prob).astype(int)
    # Ensure both classes
    target[0] = 0
    target[1] = 1
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"f1": x1, "f2": x2, "target": target, "forward_return": logits}, index=idx)


def test_kronos_path_probability_bounds_and_ordering():
    up = probability_from_path({"trend": {"forecast_change": 0.05}}, volatility=0.02)
    down = probability_from_path({"trend": {"forecast_change": -0.05}}, volatility=0.02)
    flat = probability_from_path({"trend": {"forecast_change": 0.0}}, volatility=0.02)
    assert 0.0 < down < flat < up < 1.0
    adapter = KronosModel()
    assert adapter.set_path({"trend": {"net_forecast_change": 0.03}}, volatility=0.02) > 0.5


def test_ensemble_weights_with_multiple_members():
    members = {"xgboost": 0.8, "lightgbm": 0.4, "kronos": 0.6}
    equal = combine_probabilities(members, strategy="equal_weight")
    assert abs(equal - (0.8 + 0.4 + 0.6) / 3) < 1e-9
    weighted = combine_probabilities(
        members,
        weights={"xgboost": 1.0, "lightgbm": 0.5, "kronos": 0.5},
        strategy="performance_weighted",
    )
    expected = (0.8 * 1.0 + 0.4 * 0.5 + 0.6 * 0.5) / 2.0
    assert abs(weighted - expected) < 1e-9
    # lightgbm 0.4 is "down"; majority still up → 2/3 agreement
    assert model_agreement(members) == pytest.approx(2 / 3)
    assert model_agreement({"a": 0.2, "b": 0.3, "c": 0.9}) == pytest.approx(2 / 3)


def test_identity_calibration_passthrough():
    assert calibrate_probability(0.73, method="identity") == pytest.approx(0.73)
    assert calibrate_probability(1.5, method="identity") == 1.0


def test_platt_and_isotonic_change_probabilities():
    # Overconfident raw probs vs softer labels → calibrator should pull extremes inward.
    y_true = [0, 0, 0, 0, 1, 1, 1, 1, 0, 1, 0, 1]
    y_prob = [0.9, 0.85, 0.8, 0.75, 0.2, 0.15, 0.1, 0.25, 0.7, 0.3, 0.65, 0.35]
    platt = fit_calibrator(y_true, y_prob, "platt")
    iso = fit_calibrator(y_true, y_prob, "isotonic")
    assert platt is not None
    assert iso is not None
    raw = 0.9
    platt_p = calibrate_probability(raw, method="platt", calibrator=platt)
    iso_p = calibrate_probability(raw, method="isotonic", calibrator=iso)
    assert platt_p != pytest.approx(raw, abs=1e-6) or iso_p != pytest.approx(raw, abs=1e-6)
    assert 0.0 <= platt_p <= 1.0
    assert 0.0 <= iso_p <= 1.0


def test_lightgbm_train_predict_smoke():
    pytest.importorskip("lightgbm")
    model = LightGBMModel(params={"n_estimators": 20, "max_depth": 3, "verbosity": -1})
    ds = _synthetic_dataset(100)
    model.train(ds)
    p = model.predict_probability({"f1": 0.5, "f2": -0.2})
    assert 0.0 <= p <= 1.0


def _bars(n: int = 320) -> list[dict]:
    rng = np.random.default_rng(1)
    price = 100.0
    out = []
    start = pd.Timestamp("2022-01-03", tz="UTC")
    for i in range(n):
        ret = float(rng.normal(0.0005, 0.015))
        open_p = price
        close = price * (1 + ret)
        high = max(open_p, close) * (1 + abs(float(rng.normal(0, 0.004))))
        low = min(open_p, close) * (1 - abs(float(rng.normal(0, 0.004))))
        out.append(
            {
                "timestamp": (start + pd.Timedelta(days=i)).isoformat(),
                "open": open_p,
                "high": high,
                "low": low,
                "close": close,
                "volume": float(rng.integers(1_000_000, 5_000_000)),
            }
        )
        price = close
    return out


def test_engine_multi_model_with_fake_kronos(tmp_path: Path):
    pytest.importorskip("xgboost")

    def fake_path(symbol: str, horizon: str, ohlcv: pd.DataFrame):
        _ = symbol, horizon, ohlcv
        return {
            "trend": {"forecast_change": 0.04, "net_forecast_change": 0.04},
            "historical": [{"close": 100.0 + i} for i in range(30)],
        }

    lightgbm_enabled = False
    try:
        import lightgbm  # noqa: F401

        lightgbm_enabled = True
    except ImportError:
        pass

    engine = PredictionEngine(
        config={
            "prediction": {
                "horizons": ["1d", "5d", "20d"],
                "return_threshold": 0.0,
                "lookback_bars": 400,
                "min_train_rows": 60,
                "feature_version": "1.0.0",
            },
            "models": {
                "xgboost": {
                    "enabled": True,
                    "weight": 1.0,
                    "params": {"n_estimators": 20, "max_depth": 3, "n_jobs": 1, "random_state": 0},
                },
                "kronos": {"enabled": True, "weight": 0.5},
                "lightgbm": {
                    "enabled": lightgbm_enabled,
                    "weight": 0.4,
                    "params": {"n_estimators": 20, "max_depth": 3, "verbosity": -1},
                },
            },
            "ensemble": {"strategy": "performance_weighted"},
            "calibration": {"method": "identity"},
            "decision": {
                "buy_probability": 0.65,
                "strong_buy_probability": 0.80,
                "sell_probability": 0.35,
                "strong_sell_probability": 0.20,
                "minimum_model_agreement": 0.60,
            },
            "risk": {"enabled": False},
            "llm": {"enabled": False},
            "registry": {"store_dir": str(tmp_path / "registry")},
        },
        registry=ModelRegistry(tmp_path / "registry"),
        root_dir=ROOT,
        path_forecast_fn=fake_path,
    )
    result = engine.predict_from_bars("AAPL", _bars(320), horizon="5d", retrain=True)
    assert "xgboost" in result["model_predictions"]
    assert "kronos" in result["model_predictions"]
    if lightgbm_enabled:
        assert "lightgbm" in result["model_predictions"]
    assert 0.0 <= result["probability"] <= 1.0
    assert result["model_agreement"] <= 1.0


def test_engine_xgb_only_fallback(tmp_path: Path):
    pytest.importorskip("xgboost")
    engine = PredictionEngine(
        config={
            "prediction": {
                "horizons": ["5d"],
                "return_threshold": 0.0,
                "lookback_bars": 400,
                "min_train_rows": 60,
                "feature_version": "1.0.0",
            },
            "models": {
                "xgboost": {
                    "enabled": True,
                    "weight": 1.0,
                    "params": {"n_estimators": 15, "max_depth": 3, "n_jobs": 1, "random_state": 1},
                },
                "kronos": {"enabled": False},
                "lightgbm": {"enabled": False},
            },
            "ensemble": {"strategy": "equal_weight"},
            "calibration": {"method": "platt"},
            "decision": {
                "buy_probability": 0.65,
                "strong_buy_probability": 0.80,
                "sell_probability": 0.35,
                "strong_sell_probability": 0.20,
                "minimum_model_agreement": 0.60,
            },
            "risk": {"enabled": False},
            "llm": {"enabled": False},
            "registry": {"store_dir": str(tmp_path / "registry2")},
        },
        registry=ModelRegistry(tmp_path / "registry2"),
        root_dir=ROOT,
    )
    result = engine.predict_from_bars("MSFT", _bars(300), horizon="5d", retrain=True)
    assert list(result["model_predictions"].keys()) == ["xgboost"]
    assert result["calibration_method"] == "platt"
