# Nine-Month Pre-Breakout Indicator Research Blueprint

**Status:** Research specification; no production signals or model training enabled.  
**Target window:** 2026-02-14 through 2026-11-14 (inclusive, subject to data availability).  
**Branch:** `research/nine-month-indicator-blueprint-v1`

## 1. Objective

Discover repeatable, point-in-time conditions that precede meaningful upward moves in small, liquid crypto assets. The goal is early detection before the move begins, not explaining a pump after it has happened.

This research is separate from live execution. No automatic orders are in scope.

## 2. Initial repository data audit (2026-11-14)

The current `MY CSV` export contains:

| File | Observed content |
|---|---|
| `events.csv` | 324 event rows, 224 unique symbols, venues: Binance 179, Bithumb 97, Upbit 48; observe dates 2026-06-04 to 2026-11-12 |
| `summary.csv` | Score-bucket counts and subsequent pump rates |
| `sell_signals.csv` | 10 exit/weakening signals |
| `sell_states.csv` | Sell and continuation state summaries |
| `sell_signal_events.csv` | Event-level exit signal outcomes |
| `upbit_events.csv` | Listing, warning, and delisting notices |
| `upbit_summary.csv` | Aggregated Upbit notice outcomes |
| `all_observations.csv` | Returned empty during this audit |
| `sell_timeline.csv` | Returned empty during this audit |

Important data-quality findings:
- The populated `events.csv` currently spans about five months, not nine.
- In the 324 `events.csv` rows, `oi_change7` is missing in 300, `netflow_K` in 324, `mcap_M` in 110, `funding` in 140, and `spot_taker_K` in 145.
- Event-level pump records are not a substitute for a complete, timestamped candle/market-observation panel. The latter is required for unbiased pre-breakout research.
- Existing sell/continuation results are useful hypotheses for the Position & Exit stage; they must not be reused as proof of pre-breakout predictive power.

These counts describe the fetched CSV snapshot only. Re-audit after the source exports are repaired or refreshed.

## 3. Nine-month data acquisition requirements

Build a timestamped panel for every eligible symbol, including non-pump periods and symbols that never pump.

### Required market data
- Spot OHLCV candles at 1m where available, plus 5m, 15m, 1h, and 4h derived/resampled bars.
- Trade-level or aggregated taker buy/sell volume where supported.
- Symbol metadata and listing/delisting timestamps.
- Quote volume, trade count, spread, and order-book depth/imbalance snapshots where available.
- Futures open interest, funding, basis, taker flow, and liquidations where the instrument exists.
- On-chain transfer and exchange-flow observations only for chains/assets with reliable coverage.

Store raw payloads, source, venue, symbol, event time, collection time, and ingestion status. Never silently fill missing provider data with zero.

### Coverage and survivorship controls
- Preserve delisted and renamed assets with stable identifiers and symbol history.
- Record when each symbol became eligible for the universe.
- Keep Binance spot universe as the primary comparable cohort; analyze other venues separately until cross-venue mappings are validated.
- Do not assume current listings existed throughout the historical window.
- Mark provider outages and gaps explicitly.

## 4. Feature families to investigate

All features must be computed using information available at or before their timestamp.

### A. Price structure and technical momentum
- Returns over 5m, 15m, 1h, 4h, 24h, and 7d.
- RSI (multiple horizons), MACD histogram/slope, moving-average distance and crossovers.
- ATR and realized volatility; volatility contraction/expansion.
- Bollinger-band width, distance to range highs/lows, Donchian position.
- VWAP deviation, candle body/wick ratios, close location within candle.
- Higher-high / higher-low structure and range compression.

### B. Volume and participation
- Relative volume against symbol-specific time-of-day and rolling baselines.
- Quote-volume acceleration and trade-count acceleration.
- Taker buy/sell imbalance and its persistence.
- OBV, CMF, volume-weighted price pressure.
- Price movement per unit of volume; detect volume absorption.
- Liquidity-adjusted volume rather than raw volume alone.

### C. Liquidity and order book
- Bid/ask spread and its change.
- Depth within fixed basis-point bands on both sides.
- Order-book imbalance and persistence.
- Liquidity withdrawal/refill, depth concentration, and slippage estimates.
- Flag thin books and abnormal spreads as risk, not bullish evidence.

### D. Derivatives positioning
- Open-interest change and price/OI divergence.
- Funding level and change; perp/spot basis.
- Taker long/short flow and liquidation bursts.
- Separate new leveraged positioning from spot-led demand.

### E. On-chain and whale flow
- Large transfers normalized by circulating supply and normal transfer activity.
- Exchange inflow/outflow estimates, with address-label confidence.
- Repeated entity-level accumulation/distribution only where entity attribution is defensible.
- Treat a transfer as movement, not proof of buying or selling.
- Include coverage/confidence flags; missing chain data is unknown, not neutral.

### F. Cross-market context
- BTC/ETH market regime and broad market returns/volatility.
- Sector and peer-group relative strength.
- Venue-specific premium/volume share, only where timestamps and units align.
- Listing, announcement, unlock, and exchange-notice events as separate event features.

## 5. Target labels

Use multiple horizons rather than one vague "pump" label. Initial research labels:
- `up_10pct_24h`: future maximum price reaches +10% within the next 24 hours.
- `up_20pct_48h`: future maximum price reaches +20% within the next 48 hours.
- `up_30pct_72h`: future maximum price reaches +30% within the next 72 hours.

These are candidate labels for analysis, not final trading rules. Also record:
- time to first threshold;
- maximum favorable excursion;
- maximum adverse excursion before threshold;
- return at fixed horizons;
- whether the move was already underway at feature time;
- fees, spread, slippage, and executable-liquidity constraints.

A candidate pre-breakout sample must not already have crossed its target threshold before the observation time. Build separate labels for early continuation and downside/failure risk.

## 6. Feature timing and leakage prevention

- Every feature row is keyed by `(venue, instrument_id, event_time)`.
- Use only candles/trades/metadata whose event time is no later than the feature timestamp and whose availability time is known.
- Labels may look forward; features may not.
- Apply a purge/embargo around overlapping label windows when splitting samples.
- Never use future peak, future drawdown, post-event summaries, or future exchange notices as predictors.
- Fit scalers, imputers, feature selection, and thresholds on training data only.
- Missing values remain missing with explicit availability indicators; do not replace them with zero by default.

## 7. Validation design

Use chronological walk-forward validation, not random row splitting. Proposed initial folds:
1. Train on the earliest available six months; validate on the next month; test on the final two months.
2. Roll the cutoffs forward and repeat when sufficient history exists.

Report:
- precision, recall, PR-AUC, ROC-AUC, and calibration;
- precision at a fixed alert budget per day;
- median lead time before the first threshold;
- false alerts per symbol-day;
- performance by liquidity, market-cap/volume cohort, venue, and market regime;
- net outcomes after conservative fees, spread, and slippage;
- comparison to simple baselines (relative volume only, momentum only, and random/time-matched alerts).

Do not optimize only for accuracy because pump labels are rare. The primary operating metric should reflect useful early alerts at a manageable false-alert rate.

## 8. Indicator construction strategy

Do not begin by assigning hand-picked weights to RSI, MACD, or other familiar indicators.

1. Audit raw coverage and timestamp quality.
2. Create simple, interpretable feature families.
3. Measure each feature's conditional lift versus a matched baseline.
4. Check stability across symbols, months, venues, and market regimes.
5. Remove redundant features and test interactions.
6. Build a small interpretable composite score only from features with repeatable out-of-sample value.
7. Compare the composite with a calibrated model and simple baselines.
8. Freeze the version and evaluate it on untouched future data.

The final discovery score must be distinct from the Entry confirmation score and Position/Exit score.

## 9. Immediate implementation sequence

1. Repair/export the complete `all_observations.csv` source or replace it with normalized candle/observation tables.
2. Create a data coverage report for the full nine-month window and each provider/feature family.
3. Implement a canonical market-observation schema and point-in-time candle collector.
4. Add label generation with explicit look-ahead tests.
5. Implement the first price/volume feature set, then add derivatives, order-book, and on-chain features as coverage permits.
6. Add walk-forward evaluation and leakage tests before model training.

## 10. Acceptance criteria before any live alert

- At least nine months of usable timestamped data, or an explicit report of the shorter actual coverage.
- Broad symbol coverage including non-pump observations and delisted assets where retrievable.
- No unresolved future-data leakage tests.
- Reproducible walk-forward results with fees/slippage and baseline comparisons.
- Stable performance across more than one time period and liquidity cohort.
- Research/paper alerts only until prospective performance is independently demonstrated.
