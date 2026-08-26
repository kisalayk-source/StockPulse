"""Declarative configuration for the production backtester."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from kronos_backtest.exceptions import ConfigurationError


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{name} must be a mapping")
    return dict(value)


@dataclass(frozen=True)
class ExecutionConfig:
    delay_bars: int = 1
    allow_same_bar_execution: bool = False
    fill_on: str = "open"


@dataclass(frozen=True)
class SlippageConfig:
    enabled: bool = True
    rate: float = 0.0005


@dataclass(frozen=True)
class SpreadConfig:
    enabled: bool = True
    rate: float = 0.0005
    use_bid_ask_when_available: bool = True


@dataclass(frozen=True)
class CostConfig:
    commission_rate: float = 0.0001
    exchange_fee_rate: float = 0.00005
    regulatory_fee_rate: float = 0.0


@dataclass(frozen=True)
class WalkForwardConfig:
    enabled: bool = False
    type: str = "expanding"
    training_period: str = "3y"
    test_period: str = "1m"
    embargo_bars: int = 0


@dataclass(frozen=True)
class PositionSizingConfig:
    max_position_pct: float = 0.10
    confidence_scaling: bool = True
    integer_shares: bool = False


@dataclass(frozen=True)
class RiskConfig:
    max_position_pct: float = 0.10
    max_total_exposure_pct: float = 1.0
    max_daily_loss_pct: float = 0.02
    max_drawdown_pct: float = 0.15
    max_leverage: float = 1.0
    allow_short: bool = False
    close_positions_on_drawdown: bool = False
    close_positions_on_daily_loss: bool = False


@dataclass(frozen=True)
class StrategyConfig:
    minimum_edge: float = 0.002
    name: str = "expected_return_threshold"


@dataclass(frozen=True)
class ModelConfig:
    mode: str = "pretrained"
    tokenizer_id: str = "NeoQuasar/Kronos-Tokenizer-base"
    model_id: str = "NeoQuasar/Kronos-small"
    device: str = "cpu"
    max_context: int = 512
    lookback: int = 64
    pred_len: int = 1
    sample_count: int = 1
    temperature: float = 1.0
    top_k: int = 0
    top_p: float = 0.9
    clip: float = 5.0


@dataclass(frozen=True)
class StressScenario:
    name: str
    slippage: float
    transaction_cost: float


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 100_000.0
    symbol: str = "ASSET"
    seed: int = 42
    dataset_version: str = ""
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    slippage: SlippageConfig = field(default_factory=SlippageConfig)
    spread: SpreadConfig = field(default_factory=SpreadConfig)
    costs: CostConfig = field(default_factory=CostConfig)
    walk_forward: WalkForwardConfig = field(default_factory=WalkForwardConfig)
    position_sizing: PositionSizingConfig = field(default_factory=PositionSizingConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    scenarios: tuple[StressScenario, ...] = field(
        default_factory=lambda: (
            StressScenario("optimistic", slippage=0.0001, transaction_cost=0.0002),
            StressScenario("normal", slippage=0.0005, transaction_cost=0.001),
            StressScenario("conservative", slippage=0.001, transaction_cost=0.002),
            StressScenario("severe", slippage=0.0025, transaction_cost=0.005),
        )
    )

    def __post_init__(self) -> None:
        if self.initial_capital <= 0:
            raise ConfigurationError("initial_capital must be positive")
        if self.execution.delay_bars < 1 and not self.execution.allow_same_bar_execution:
            raise ConfigurationError(
                "execution.delay_bars must be >= 1 unless allow_same_bar_execution is true"
            )
        if self.execution.fill_on not in {"open"}:
            raise ConfigurationError("Only fill_on='open' is implemented")
        if self.walk_forward.type not in {"expanding", "rolling"}:
            raise ConfigurationError("walk_forward.type must be 'expanding' or 'rolling'")
        if self.model.mode not in {"pretrained", "fine_tune"}:
            raise ConfigurationError("model.mode must be 'pretrained' or 'fine_tune'")
        if self.position_sizing.max_position_pct <= 0 or self.position_sizing.max_position_pct > 1:
            raise ConfigurationError("position_sizing.max_position_pct must be in (0, 1]")
        if self.risk.max_leverage <= 0:
            raise ConfigurationError("risk.max_leverage must be positive")

    @property
    def estimated_one_way_cost(self) -> float:
        """Conservative one-way cost rate used by the strategy, not by accounting."""
        spread = self.spread.rate / 2.0 if self.spread.enabled else 0.0
        slip = self.slippage.rate if self.slippage.enabled else 0.0
        return (
            spread
            + slip
            + self.costs.commission_rate
            + self.costs.exchange_fee_rate
            + self.costs.regulatory_fee_rate
        )

    def with_scenario(self, scenario: StressScenario) -> "BacktestConfig":
        return replace(
            self,
            slippage=replace(self.slippage, enabled=True, rate=scenario.slippage),
            costs=replace(
                self.costs,
                commission_rate=scenario.transaction_cost,
                exchange_fee_rate=0.0,
                regulatory_fee_rate=0.0,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> "BacktestConfig":
        data = dict(raw or {})
        scenarios_raw = data.pop("scenarios", None)
        kwargs: dict[str, Any] = {}
        for key, typ in (
            ("execution", ExecutionConfig),
            ("slippage", SlippageConfig),
            ("spread", SpreadConfig),
            ("costs", CostConfig),
            ("walk_forward", WalkForwardConfig),
            ("position_sizing", PositionSizingConfig),
            ("risk", RiskConfig),
            ("strategy", StrategyConfig),
            ("model", ModelConfig),
        ):
            section = _require_mapping(data.pop(key, {}), key)
            kwargs[key] = typ(**section)
        if scenarios_raw:
            if isinstance(scenarios_raw, Mapping):
                scenarios = tuple(
                    StressScenario(name=name, **_require_mapping(values, name))
                    for name, values in scenarios_raw.items()
                )
            else:
                scenarios = tuple(StressScenario(**item) for item in scenarios_raw)
            kwargs["scenarios"] = scenarios
        allowed = {field_name for field_name in cls.__dataclass_fields__}
        for key, value in data.items():
            if key in allowed:
                kwargs[key] = value
        return cls(**kwargs)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "BacktestConfig":
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - optional dependency path
            raise ConfigurationError("PyYAML is required to load YAML configs") from exc
        with Path(path).open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        if not isinstance(loaded, Mapping):
            raise ConfigurationError("YAML config root must be a mapping")
        return cls.from_dict(loaded)
