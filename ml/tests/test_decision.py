"""Decision engine tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.decision import decide_signal


def test_decide_signal_thresholds() -> None:
    assert decide_signal(0.81)["signal"] == "STRONG BUY"
    assert decide_signal(0.70)["signal"] == "BUY"
    assert decide_signal(0.50)["signal"] == "HOLD"
    assert decide_signal(0.30)["signal"] == "SELL"
    assert decide_signal(0.10)["signal"] == "STRONG SELL"


def test_model_agreement_can_force_hold() -> None:
    result = decide_signal(0.90, model_agreement=0.2)
    assert result["signal"] == "HOLD"
