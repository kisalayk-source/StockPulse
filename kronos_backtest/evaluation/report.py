"""Write backtest artifacts: JSON, CSV, and a standalone HTML report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from kronos_backtest.engine import BacktestResult
from kronos_backtest.evaluation.metrics import compute_metrics, daily_returns, drawdown_series


def _json_default(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def write_report(
    result: BacktestResult,
    output_dir: str | Path,
    *,
    metrics: dict[str, Any] | None = None,
    benchmarks: dict[str, dict[str, Any]] | None = None,
    stress: dict[str, dict[str, Any]] | None = None,
) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    metrics = metrics or compute_metrics(
        result.equity_curve,
        result.trades,
        initial_capital=result.config.initial_capital,
        portfolio=result.portfolio,
    )
    equity = result.equity_curve.copy()
    trades = result.trades.copy()
    daily = daily_returns(equity)
    drawdown = drawdown_series(equity)

    (output / "metrics.json").write_text(json.dumps(metrics, indent=2, default=_json_default), encoding="utf-8")
    summary = {
        "final_equity": metrics.get("final_equity"),
        "total_return": metrics.get("total_return"),
        "sharpe": metrics.get("sharpe"),
        "max_drawdown": metrics.get("max_drawdown"),
        "number_of_trades": metrics.get("number_of_trades"),
        "total_transaction_costs": metrics.get("total_transaction_costs"),
        "benchmarks": benchmarks or {},
        "stress": stress or {},
        "reproducibility": result.metadata,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, default=_json_default), encoding="utf-8")
    if not trades.empty:
        trades.to_csv(output / "trades.csv", index=False)
    else:
        pd.DataFrame().to_csv(output / "trades.csv", index=False)
    equity.to_csv(output / "equity_curve.csv", index=False)
    daily.to_csv(output / "daily_returns.csv", index=False)
    drawdown.to_csv(output / "drawdown.csv", index=False)
    html = _render_html(metrics, summary, equity, trades)
    (output / "report.html").write_text(html, encoding="utf-8")
    return output / "report.html"


def _render_html(
    metrics: dict[str, Any],
    summary: dict[str, Any],
    equity: pd.DataFrame,
    trades: pd.DataFrame,
) -> str:
    metric_rows = "".join(
        f"<tr><th>{key}</th><td>{_fmt(value)}</td></tr>" for key, value in metrics.items()
    )
    bench_rows = "".join(
        f"<tr><th>{name}</th><td>{_fmt(vals.get('total_return'))}</td>"
        f"<td>{_fmt(vals.get('sharpe'))}</td><td>{_fmt(vals.get('max_drawdown'))}</td></tr>"
        for name, vals in (summary.get("benchmarks") or {}).items()
    )
    stress_rows = "".join(
        f"<tr><th>{name}</th><td>{_fmt(vals.get('total_return'))}</td>"
        f"<td>{_fmt(vals.get('sharpe'))}</td><td>{_fmt(vals.get('final_equity'))}</td></tr>"
        for name, vals in (summary.get("stress") or {}).items()
    )
    trade_preview = trades.head(25).to_html(index=False) if not trades.empty else "<p>No trades.</p>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Kronos Backtest Report</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; color: #111; }}
    table {{ border-collapse: collapse; margin-bottom: 2rem; }}
    th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.7rem; text-align: left; }}
    th {{ background: #f4f4f4; }}
    .note {{ background: #fff8e1; padding: 1rem; }}
  </style>
</head>
<body>
  <h1>Kronos production backtest</h1>
  <p class="note">
    Event loop: bar T closes → predict on data ≤ T → signal → order → fill at T+delay open
    with spread, slippage, and fees. Same-bar close execution is disabled.
  </p>
  <h2>Metrics</h2>
  <table>{metric_rows}</table>
  <h2>Benchmarks</h2>
  <table>
    <tr><th>Name</th><th>Total return</th><th>Sharpe</th><th>Max drawdown</th></tr>
    {bench_rows or "<tr><td colspan='4'>None</td></tr>"}
  </table>
  <h2>Stress scenarios</h2>
  <table>
    <tr><th>Scenario</th><th>Total return</th><th>Sharpe</th><th>Final equity</th></tr>
    {stress_rows or "<tr><td colspan='4'>None</td></tr>"}
  </table>
  <h2>Trades (preview)</h2>
  {trade_preview}
  <h2>Reproducibility</h2>
  <pre>{json.dumps(summary.get("reproducibility") or {{}}, indent=2, default=_json_default)}</pre>
</body>
</html>
"""


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)
