from __future__ import annotations

from typing import Any


def score_price_volume(bars: list[dict[str, Any]], spy_bars: list[dict[str, Any]] | None = None) -> tuple[float, list[str]]:
    if len(bars) < 20:
        return 50.0, []
    closes = [float(bar["close"]) for bar in bars[-50:] if bar.get("close") is not None]
    volumes = [float(bar.get("volume") or 0) for bar in bars[-20:]]
    if len(closes) < 20:
        return 50.0, []
    sma20 = sum(closes[-20:]) / 20
    sma50 = sum(closes[-50:]) / len(closes[-50:]) if len(closes) >= 50 else sma20
    trend = (closes[-1] - sma20) / sma20 if sma20 else 0.0
    avg_vol = sum(volumes) / len(volumes) if volumes else 0.0
    recent_vol = volumes[-1] if volumes else 0.0
    vol_expansion = (recent_vol / avg_vol - 1.0) if avg_vol else 0.0
    rel_strength = 0.0
    if spy_bars and len(spy_bars) >= 20:
        spy_closes = [float(b["close"]) for b in spy_bars[-20:] if b.get("close")]
        if len(spy_closes) >= 2 and spy_closes[0]:
            stock_ret = (closes[-1] - closes[-20]) / closes[-20]
            spy_ret = (spy_closes[-1] - spy_closes[0]) / spy_closes[0]
            rel_strength = stock_ret - spy_ret
    score = 50.0 + trend * 200.0 + rel_strength * 100.0 + min(vol_expansion, 1.0) * 10.0
    evidence: list[str] = []
    if trend > 0.02:
        evidence.append("+ Price trend confirms accumulation")
    elif trend < -0.02:
        evidence.append("- Price trend weak vs recent average")
    if rel_strength > 0.03:
        evidence.append("+ Relative strength vs SPY")
    if vol_expansion > 0.2:
        evidence.append("+ Volume expansion vs 20-day average")
    return max(0.0, min(100.0, score)), evidence


def score_fundamentals(metrics: dict[str, float | None]) -> tuple[float, list[str]]:
    if not metrics:
        return 50.0, []
    score = 50.0
    evidence: list[str] = []
    rev_growth = metrics.get("revenue_growth")
    eps_growth = metrics.get("eps_growth")
    roic = metrics.get("roic")
    pe = metrics.get("pe_ratio")
    if rev_growth is not None:
        if rev_growth > 0.05:
            score += 10.0
            evidence.append("+ Revenue growth positive")
        elif rev_growth < 0:
            score -= 10.0
            evidence.append("- Revenue growth negative")
    if eps_growth is not None:
        if eps_growth > 0.05:
            score += 10.0
            evidence.append("+ EPS growth positive")
        elif eps_growth < 0:
            score -= 10.0
            evidence.append("- EPS growth negative")
    if roic is not None and roic > 0.1:
        score += 5.0
        evidence.append("+ ROIC above 10%")
    if pe is not None and pe > 35:
        score -= 8.0
        evidence.append("- Valuation above historical average (high P/E)")
    return max(0.0, min(100.0, score)), evidence
