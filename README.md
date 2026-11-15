# Global Crypto Intelligence Engine

An independent research platform for discovering small-cap crypto assets before major moves, detecting early breakout conditions, and managing signal lifecycle through evidence-based market and on-chain intelligence.

## Mission

Build a research-first intelligence engine with three operational stages:

1. **Discovery** — screen liquid, actively traded smaller assets and rank pre-breakout / accumulation evidence.
2. **Entry** — monitor discovered assets and identify early, confirmed breakout conditions.
3. **Position & Exit** — evaluate continuation, weakening momentum, distribution, and exit risk.

Historical research studies the complete lifecycle: pre-explosion, early breakout, expansion, distribution, decline, and post-event behavior.

## Core principles

- Evidence fusion, not single-indicator triggers.
- Strict point-in-time data: no look-ahead leakage in features, labels, or backtests.
- Separate models and thresholds for discovery, entry, holding, and exit.
- Preserve raw observations and provenance; normalize only in derived datasets.
- Treat whale transfers as flows, not proof of buying or selling.
- Paper/research signals first. No automatic order execution in the initial releases.
- Secrets stay in environment variables / GitHub Secrets; never commit credentials.

## Planned intelligence domains

- Spot markets across supported exchanges.
- Futures: open interest, funding, long/short positioning, taker flow, liquidations.
- Order books: depth, spread, imbalance, liquidity changes.
- On-chain: large transfers, exchange inflows/outflows, accumulation/distribution hypotheses.
- Technical and microstructure features.
- Lifecycle research, calibrated ML models, risk controls, Telegram notifications.

## Initial architecture

```
src/gcie/
  config/          # environment-backed configuration
  collectors/      # exchange and on-chain ingestion
  exchanges/       # exchange adapters
  features/        # point-in-time feature engineering
  lifecycle/       # historical event research
  discovery/       # candidate screening and ranking
  entry/           # early-breakout confirmation
  position/        # hold / reduce / exit decisions
  risk/            # exposure and signal safeguards
  models/           # training, validation, inference
  storage/          # persistence interfaces
  notifications/   # Telegram delivery
tests/
research/
reports/
.github/workflows/
```

## Operating model

- **GitHub Actions:** CI, unit tests, scheduled low-frequency research jobs, and deployment automation.
- **cron-job.org:** optional external scheduler that calls a secured, fast-responding trigger endpoint. It should not host long-running collectors or expose secrets in URLs.
- **Workers:** long-running or high-frequency collectors should run on a dedicated worker service. A trigger should enqueue work and return quickly.
- **Supabase/PostgreSQL:** planned persistence layer, isolated from the older research project.

## Development status

The repository now includes public market-data collectors and a local SQLite persistence foundation. It is not yet a complete multi-exchange intelligence engine, and production discovery/entry signals or automated trading are not enabled.

## Local setup

Requires Python 3.11 or newer.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
python -m gcie.health
```

Copy `.env.example` to `.env` for local configuration. Never commit the real `.env` file.

## Configuration

See [`.env.example`](.env.example). The initial application intentionally requires no API keys to run its health check and test suite.

## Public market-data collectors

The current public collectors support Binance spot OHLCV and USDⓈ-M funding history, OKX historical candles and perpetual funding history, Bybit linear/inverse funding history and historical open interest, plus current Binance USDⓈ-M and OKX SWAP/FUTURES/OPTION open-interest snapshots. OKX instruments are classified from their instId (`BTC-USDT` spot, `BTC-USDT-SWAP` perpetual, `BTC-USD-261225` dated future, `BTC-USD-261225-60000-C` option). These public endpoints do not require API keys.

Install the project:

```bash
python -m pip install -e ".[dev]"
```

Example (replace timestamps with the exact UTC epoch-millisecond window required):

```bash
gcie-backfill binance-spot --instrument ABCUSDT --interval 1m --start-ms 1771027200000 --end-ms 1771113600000 --output data/raw/binance_ABCUSDT_1m.jsonl
gcie-backfill binance-funding --instrument ABCUSDT --start-ms 1771027200000 --end-ms 1771113600000 --output data/raw/binance_ABCUSDT_funding.jsonl
gcie-backfill okx-candles --instrument ABC-USDT --bar 1m --start-ms 1771027200000 --end-ms 1771113600000 --output data/raw/okx_ABC-USDT_1m.jsonl
gcie-backfill okx-funding --instrument ABC-USDT-SWAP --start-ms 1771027200000 --end-ms 1771113600000 --output data/raw/okx_ABC-USDT-SWAP_funding.jsonl
gcie-backfill bybit-funding --instrument ABCUSDT --category linear --start-ms 1771027200000 --end-ms 1771113600000 --output data/raw/bybit_ABCUSDT_funding.jsonl
gcie-backfill bybit-open-interest --instrument ABCUSDT --category linear --interval 1h --start-ms 1771027200000 --end-ms 1771113600000 --output data/raw/bybit_ABCUSDT_oi_1h.jsonl
gcie-backfill binance-open-interest-snapshot --instrument ABCUSDT --output data/raw/binance_ABCUSDT_oi_snapshot.jsonl
gcie-backfill okx-open-interest-snapshot --instrument ABC-USDT-SWAP --output data/raw/okx_ABC-USDT-SWAP_oi_snapshot.jsonl
```

Output is JSON Lines. Decimal values remain strings to avoid floating-point precision loss. Candles that are still open are dropped, so every exported candle is final. In CLI output the `metric` field names the stream, including the interval where there is one (`ohlcv_1m`, `open_interest_linear_1h`, `funding_rate`), whether or not `--db` is used. Time-range commands use a half-open range [start_ms, end_ms); the end timestamp is exclusive. These commands collect one instrument at a time. Use bounded batches; do not launch an unbounded nine-month, one-minute backfill for every symbol.

## Local SQLite storage and resumable backfills

Range collectors accept --db to persist collection results in a local SQLite database. The store creates:

- raw_pages: raw provider response payloads and request-window metadata.
- observations: normalized observations keyed by venue, market type, instrument, metric, and event timestamp.
- checkpoints: completion state for each time partition.

Each **time partition** is currently collected as a unit. Its raw response pages, normalized observations, and checkpoint are committed in one SQLite transaction. Replaying a stable partition key is idempotent. Completed partitions are skipped on a rerun; partitions reaching into the future remain running and are collected again. SQLite WAL mode is enabled.

Example:

```bash
gcie-backfill binance-spot --instrument ABCUSDT --interval 1m \
  --start-ms 1771027200000 --end-ms 1771113600000 \
  --db data/raw/research.sqlite \
  --output data/processed/binance_ABCUSDT_1m.jsonl
```

- Default partition sizes are 1 day for candles, 7 days for open interest, and 30 days for funding. Override with --chunk-ms.
- HTTP 429/5xx and network errors use bounded exponential backoff and respect Retry-After. HTTP 418 stops the run.
- When --db and --output are both supplied, the JSONL file is rebuilt from **all stored observations in the requested range**, including partitions skipped during resume. Without --db, JSONL contains rows fetched during that run. The export is streamed from SQLite in batches, so memory use stays flat for long 1-minute ranges.
- JSONL files are written atomically: output goes to a temporary file that replaces the target only when complete, so a failed run leaves the previous file untouched instead of a truncated one.
- If a run is interrupted, rerun the same command and database path to skip completed partitions and fetch unfinished partitions.

**Important current limitation:** resume is at the time-partition level, not at the individual API-page level. The collector holds a partition's fetched rows and recorded raw responses until that partition finishes, then commits them together. A failure within a partition can therefore require fetching that partition again. The next persistence improvement is page-level commits and cursor checkpoints, followed by explicit gap/coverage validation. The SQLite store is local only; distributed locking, Supabase/PostgreSQL storage, automated gap detection, and a coverage manifest are not yet implemented.

## Current data limitations

Binance and OKX open-interest commands are current snapshots, not historical OI backfills. Bybit OI is interval-based history (5m through 1d). Wallet transfers, liquidation history, borrow/lending rates, historical order-book depth, and the full Korean premium inputs are not yet implemented. Historical retention and availability differ by endpoint, so coverage must be measured separately for each venue and metric before attempting the nine-month research dataset.

## Roadmap

1. Complete resilient collection: page-level persistence, cursor resume, retries, and gap/coverage checks.
2. Build and maintain exchange instrument universes and bounded collection schedules.
3. Expand futures, order-book, on-chain, and regional market intelligence.
4. Build the historical explosion lifecycle dataset and point-in-time labels.
5. Implement feature engineering and leakage audits.
6. Validate Discovery with walk-forward and out-of-sample tests.
7. Research Entry confirmation.
8. Research holding, reduction, and exit decisions.
9. Add Telegram alerts, monitoring, paper trading, and operational hardening.

## Disclaimer

This is a research and decision-support project, not financial advice. Any future signal must be evaluated with fees, slippage, liquidity, and out-of-sample testing.
