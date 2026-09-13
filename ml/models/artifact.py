"""Registry artifact that bundles a directional model with an optional calibrator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CalibratedArtifact:
    model: Any
    calibrator: Any | None = None
    calibration_method: str = "identity"

    def predict_probability(self, features: Any) -> float:
        from ml.calibration import calibrate_probability

        raw = float(self.model.predict_probability(features))
        return calibrate_probability(
            raw,
            method=self.calibration_method,
            calibrator=self.calibrator,
        )
