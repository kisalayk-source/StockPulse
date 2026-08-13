# Production historical backtesting

This package (`kronos_backtest`) is the recommended Kronos backtester.
`examples/run_backtest_kronos.py` and `finetune/qlib_test.py` remain as
**demo-grade** illustrations. They are not used for realistic evaluation.

## Event loop

For each bar `T` (index `i`):

1. **Market data is available** for bar `T` (OHLCV is known).
2. **Pending orders fill** if `created_bar_index + delay_bars <= i`. The
   fill reference is **this bar's open**, never this bar's close and never
   the originating bar's close.
3. **Portfolio is marked to market** at bar `T` close.
4. **Context** is `data.get_history(T)`: every timestamp is `<= T`.
5. **Predictor** (Kronos or a stub) sees only that context. Future rows
   raise `LookAheadBiasError`.
6. **Strategy** emits BUY / SELL / HOLD after subtracting estimated costs.
7. **Risk manager** sizes and may reject the order. Daily-loss and
   drawdown limits stop *new* positions; they do not auto-flatten unless
   configured to.
8. **Order is queued.** It cannot fill until a later bar.

```text
Prediction at T
        ↓
ONLY data <= T
        ↓
Signal
        ↓
Order
        ↓
Execution at T+1 open
        ↓
Spread + slippage + fees
        ↓
Portfolio update
```

## Spread assumption

If `bid` and `ask` columns exist, those quotes are used. Otherwise a
synthetic spread is applied around the next-bar open:

```text
buy  = mid * (1 + spread_rate / 2)
sell = mid * (1 - spread_rate / 2)
```

That is a modeling assumption, not observed microstructure.

## Fine-tuning

`model.mode: pretrained` freezes the supplied predictor after validating
the training window. `model.mode: fine_tune` calls a user-supplied
`FineTuner.fit(train_data, train_end, test_start)`. Test-period rows are
never passed into `fit`. Plug in the existing `finetune/` or
`finetune_csv/` trainers behind that callback; this engine does not
reimplement GPU training.

## Command

```bash
pip install -r requirements.txt
python -m kronos_backtest --config configs/backtest.yaml --predictor dummy --output backtest_results
```

Use `--predictor kronos` to wrap `model.KronosPredictor` (downloads weights).
Use `--data path/to/ohlcv.csv` for a real series.

```bash
pytest tests/backtest -q
```

## Outputs

```text
backtest_results/
    summary.json
    metrics.json
    trades.csv
    equity_curve.csv
    daily_returns.csv
    drawdown.csv
    report.html
```

## Limitations

- Market impact beyond proportional slippage is not modeled.
- Only MARKET orders are executed; LIMIT/STOP types are reserved.
- Multi-asset books are supported in data/portfolio objects, but the
  default event loop trades one symbol per run.
- Fine-tuning quality depends on the callback you provide.
- Synthetic spread is used when bid/ask is missing.
