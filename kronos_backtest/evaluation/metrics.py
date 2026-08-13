"""Performance metrics for equity curves and trade blotters."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _periods_per_year(index: pd.DatetimeIndex) -> float:
    if len(index) < 2:
        return 252.0
    delta = pd.Series(index).diff().median()
    if pd.isna(delta) or delta <= pd.Timedelta(0):
        return 252.0
    seconds = float(delta.total_seconds())
    year = 365.25 * 24 * 3600
    return year / seconds


def _drawdown(equity: pd.Series) -> pd.Series:
    peak = equity.cummax()
    peak = peak.replace(0, np.nan)
    return equity / peak - 1.0


def _trade_pnls(trades: pd.DataFrame) -> list[float]:
    if trades.empty:
        return []
    ordered = trades.sort_values("timestamp")
    pnls: list[float] = []
    open_qty = 0.0
    avg = 0.0
    for _, row in ordered.iterrows():
        qty = float(row["quantity"])
        price = float(row["fill_price"])
        costs = float(row.get("commission", 0.0) or 0.0) + float(row.get("exchange_fees", 0.0) or 0.0)
        side = str(row["side"]).upper()
        if side == "BUY":
            new_qty = open_qty + qty
            if open_qty >= 0:
                avg = (avg * open_qty + price * qty) / new_qty if new_qty else 0.0
                open_qty = new_qty
            else:
                closing = min(qty, abs(open_qty))
                pnls.append((avg - price) * closing - costs * (closing / qty))
                leftover = qty - abs(open_qty)
                open_qty = leftover
                avg = price if leftover > 0 else 0.0
        else:
            if open_qty > 0:
                closing = min(qty, open_qty)
                pnls.append((price - avg) * closing - costs * (closing / qty))
                open_qty -= qty
                if open_qty <= 1e-12:
                    open_qty = 0.0
                    avg = 0.0
            else:
                open_qty -= qty
                avg = price
    return pnls


def _holding_periods(trades: pd.DataFrame) -> list[float]:
    if trades.empty:
        return []
    ordered = trades.sort_values("timestamp")
    holds: list[float] = []
    entry: pd.Timestamp | None = None
    for _, row in ordered.iterrows():
        stamp = pd.Timestamp(row["timestamp"])
        if str(row["side"]).upper() == "BUY" and entry is None:
            entry = stamp
        elif str(row["side"]).upper() == "SELL" and entry is not None:
            holds.append((stamp - entry).total_seconds() / 86400.0)
            entry = None
    return holds


def compute_metrics(
    equity_curve: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    initial_capital: float,
    portfolio: Any | None = None,
) -> dict[str, Any]:
    if equity_curve.empty:
        return {
            "total_return": 0.0,
            "cagr": 0.0,
            "annual_return": 0.0,
            "monthly_return": 0.0,
            "volatility": 0.0,
            "max_drawdown": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "calmar": 0.0,
            "number_of_trades": 0,
            "win_rate": 0.0,
            "average_win": 0.0,
            "average_loss": 0.0,
            "profit_factor": 0.0,
            "average_holding_period": 0.0,
            "turnover": 0.0,
            "total_commission": 0.0,
            "total_fees": 0.0,
            "total_slippage": 0.0,
            "total_spread_cost": 0.0,
            "total_transaction_costs": 0.0,
            "final_equity": initial_capital,
        }

    curve = equity_curve.copy()
    curve["timestamp"] = pd.to_datetime(curve["timestamp"])
    curve = curve.sort_values("timestamp")
    equity = curve["equity"].astype(float)
    returns = equity.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    total_return = float(equity.iloc[-1] / initial_capital - 1.0)
    ppy = _periods_per_year(pd.DatetimeIndex(curve["timestamp"]))
    n = max(len(returns), 1)
    years = n / ppy if ppy else n / 252.0
    cagr = float((1.0 + total_return) ** (1.0 / years) - 1.0) if years > 0 and total_return > -1 else 0.0
    vol = float(returns.std(ddof=1) * np.sqrt(ppy)) if len(returns) > 1 else 0.0
    dd = _drawdown(equity)
    max_dd = float(dd.min()) if len(dd) else 0.0
    excess = returns.mean() * ppy
    sharpe = float(excess / vol) if vol > 0 else 0.0
    downside = returns[returns < 0]
    downside_std = float(downside.std(ddof=1) * np.sqrt(ppy)) if len(downside) > 1 else 0.0
    sortino = float(excess / downside_std) if downside_std > 0 else 0.0
    calmar = float(cagr / abs(max_dd)) if max_dd < 0 else 0.0
    monthly = curve.set_index("timestamp")["equity"].resample("ME").last().pct_change().dropna()
    monthly_return = float(monthly.mean()) if len(monthly) else 0.0

    pnls = _trade_pnls(trades)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    win_rate = (len(wins) / len(pnls)) if pnls else 0.0
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(np.mean(losses)) if losses else 0.0
    gross_profit = float(sum(wins))
    gross_loss = float(abs(sum(losses)))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    holds = _holding_periods(trades)
    turnover = 0.0
    if not trades.empty and initial_capital:
        turnover = float(trades["gross_value"].sum() / initial_capital)

    cost_totals = {
        "total_commission": float(trades["commission"].sum()) if not trades.empty else 0.0,
        "total_fees": float((trades["exchange_fees"] + trades.get("regulatory_fees", 0)).sum())
        if not trades.empty
        else 0.0,
        "total_slippage": float(trades["slippage"].sum()) if not trades.empty else 0.0,
        "total_spread_cost": float(trades["spread"].sum()) if not trades.empty else 0.0,
        "total_transaction_costs": float(trades["total_cost"].sum()) if not trades.empty else 0.0,
    }
    if portfolio is not None:
        cost_totals = {
            "total_commission": float(portfolio.total_commission),
            "total_fees": float(portfolio.total_fees),
            "total_slippage": float(portfolio.total_slippage_cost),
            "total_spread_cost": float(portfolio.total_spread_cost),
            "total_transaction_costs": float(portfolio.total_transaction_costs),
        }

    return {
        "total_return": total_return,
        "cagr": cagr,
        "annual_return": cagr,
        "monthly_return": monthly_return,
        "volatility": vol,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "number_of_trades": int(len(trades)),
        "win_rate": win_rate,
        "average_win": avg_win,
        "average_loss": avg_loss,
        "profit_factor": profit_factor if profit_factor != float("inf") else None,
        "average_holding_period": float(np.mean(holds)) if holds else 0.0,
        "turnover": turnover,
        "final_equity": float(equity.iloc[-1]),
        **cost_totals,
    }


def daily_returns(equity_curve: pd.DataFrame) -> pd.DataFrame:
    if equity_curve.empty:
        return pd.DataFrame(columns=["timestamp", "return"])
    curve = equity_curve.copy()
    curve["timestamp"] = pd.to_datetime(curve["timestamp"])
    daily = curve.set_index("timestamp")["equity"].resample("D").last().dropna()
    out = daily.pct_change().fillna(0.0).rename("return").reset_index()
    return out


def drawdown_series(equity_curve: pd.DataFrame) -> pd.DataFrame:
    if equity_curve.empty:
        return pd.DataFrame(columns=["timestamp", "drawdown"])
    curve = equity_curve.copy()
    curve["timestamp"] = pd.to_datetime(curve["timestamp"])
    dd = _drawdown(curve["equity"].astype(float))
    return pd.DataFrame({"timestamp": curve["timestamp"], "drawdown": dd})
