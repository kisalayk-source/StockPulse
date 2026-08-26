"""Registry + config tests."""

from __future__ import annotations

from pathlib import Path

import yaml

from forecasting.adapters.kronos_adapter import KronosAdapter
from forecasting.core.base import ForecastModel
from forecasting.core.registry import get_active_models, get_model_weights, load_config
from forecasting.core.schema import ForecastInput, ForecastResult
import pandas as pd


class _StubA(ForecastModel):
    name = "stub_a"

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def load(self) -> None:
        return None

    def supports(self, inp: ForecastInput) -> bool:
        return True

    def predict(self, inp: ForecastInput) -> ForecastResult:
        return ForecastResult(
            model_name=self.name,
            ticker=inp.ticker,
            predicted=pd.DataFrame({"close": [1.0] * inp.horizon}),
        )


class _StubB(ForecastModel):
    name = "stub_b"

    def __init__(self, **kwargs) -> None:
        pass

    def load(self) -> None:
        return None

    def supports(self, inp: ForecastInput) -> bool:
        return True

    def predict(self, inp: ForecastInput) -> ForecastResult:
        return ForecastResult(
            model_name=self.name,
            ticker=inp.ticker,
            predicted=pd.DataFrame({"close": [2.0] * inp.horizon}),
        )


def test_load_default_config():
    cfg = load_config()
    assert "models" in cfg
    assert "kronos" in cfg["models"]


def test_get_active_models_respects_enabled(tmp_path: Path):
    # Register stubs via a temp module path using dotted builtins — use inline config
    # pointing at classes defined in this test module.
    mod = "forecasting.tests.test_registry"
    cfg = {
        "models": {
            "stub_a": {
                "enabled": True,
                "adapter": f"{mod}._StubA",
                "weight": 1.0,
                "params": {"x": 1},
            },
            "stub_b": {
                "enabled": False,
                "adapter": f"{mod}._StubB",
                "weight": 0.5,
                "params": {},
            },
        }
    }
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    active = get_active_models(path)
    assert len(active) == 1
    assert active[0].name == "stub_a"
    weights = get_model_weights(path)
    assert weights == {"stub_a": 1.0}


def test_default_registry_instantiates_kronos():
    cfg = load_config()
    # Force only kronos enabled for this assertion
    models_cfg = {
        "kronos": {
            **cfg["models"]["kronos"],
            "enabled": True,
        },
        "chronos": {**cfg["models"]["chronos"], "enabled": False},
        "timesfm": {**cfg["models"]["timesfm"], "enabled": False},
        "lag_llama": {**cfg["models"]["lag_llama"], "enabled": False},
    }
    active = get_active_models(config={"models": models_cfg})
    assert len(active) == 1
    assert isinstance(active[0], KronosAdapter)
    assert active[0].name == "kronos"
