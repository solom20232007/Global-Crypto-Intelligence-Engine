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

**Phase 0 — foundation** is being established: repository conventions, safe configuration, health checks, and continuous integration. No live market collection or trading signals are enabled yet.

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

## Roadmap

1. Foundation, CI, configuration, and security.
2. Data-source inventory and exchange capability matrix.
3. Market universe and spot-candle collection.
4. Futures, order-book, and on-chain intelligence.
5. Historical explosion lifecycle dataset and labels.
6. Point-in-time feature engineering and leakage audits.
7. Discovery research and walk-forward validation.
8. Entry confirmation research.
9. Holding, reduction, and exit research.
10. Telegram alerts, monitoring, paper trading, and operational hardening.

## Disclaimer

This is a research and decision-support project, not financial advice. Any future signal must be evaluated with fees, slippage, liquidity, and out-of-sample testing.


## Public historical market-data backfill (research branch)

The public collectors support Binance spot OHLCV and USDⓈ-M funding, OKX historical candles and perpetual funding, Bybit linear/inverse funding and historical open interest, plus current Binance USDⓈ-M and OKX SWAP open-interest snapshots. They use public market-data endpoints and require no API keys.

Install the project:

```bash
python -m pip install -e ".[dev]"
```

Example (replace the timestamps with the exact UTC epoch-millisecond window you want):

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

Output is JSON Lines. Decimal values remain strings to avoid floating-point precision loss. The end timestamp is exclusive for candle backfills. These commands are per instrument; first discover each venue's historical instrument universe and then schedule bounded batches. Do not launch a nine-month 1-minute backfill for every symbol in one unbounded job.

**Current limitations:** these adapters write normalized JSONL only; they do not yet persist raw response pages or maintain resumable checkpoints. Binance and OKX OI commands are point-in-time snapshots, not historical backfills. Bybit OI is interval-based history (5m through 1d), while Bybit funding history is paginated by timestamp. Wallet transfers, liquidations, borrow rates, order-book depth, and Korean premium inputs remain unimplemented. Provider retention differs by endpoint, so coverage must be measured separately for every venue and metric.

## Local transactional research storage (initial implementation)

The research branch now includes `gcie.storage.SQLiteResearchStore` as a local,
dependency-free persistence foundation. It creates three tables:

- `raw_pages`: original provider response JSON plus request window/cursor metadata.
- `observations`: normalized observations keyed by venue, market type, instrument,
  metric, and event timestamp.
- `checkpoints`: per-venue/metric/instrument time-partition progress and opaque
  provider cursor.

Use `commit_page(...)` to write a raw response page, its normalized observations,
and the associated checkpoint in one SQLite transaction. Replaying a stable
`page_key` does not duplicate the raw page, and observation keys are upserted.
SQLite WAL mode is enabled for safer local worker access.

**Important scope:** this is the first storage primitive, not yet wired into the
Binance/OKX/Bybit collectors or a scheduled workflow. Existing CLI commands still
write JSONL. The store currently provides local SQLite persistence only; it does
not yet provide Supabase/PostgreSQL storage, distributed locking, retry/backoff,
automatic gap detection, or a coverage manifest. Do not start the nine-month
multi-symbol backfill until collector page capture, resume behavior, and bounded
batch execution are integrated and tested.

## Historical backfills

`gcie-backfill` collects public market data for a `[start, end)` range in UTC epoch
milliseconds. With `--db`, each partition is committed to SQLite with its raw provider
responses and a checkpoint, so an interrupted run can be repeated with the same command:
completed partitions are skipped and collection resumes where it stopped.

```bash
# Nine months of Binance 1m candles, resumable
gcie-backfill binance-spot --instrument BTCUSDT --interval 1m \
  --start-ms 1767225600000 --end-ms 1790812800000 --db data/raw/research.sqlite

# Same, also exporting the rows fetched in this run to JSONL
gcie-backfill okx-funding --instrument BTC-USDT-SWAP \
  --start-ms 1767225600000 --end-ms 1790812800000 \
  --db data/raw/research.sqlite --output data/processed/okx_funding.jsonl
```

- Requests retry HTTP 429/5xx and network errors with exponential backoff and honour
  `Retry-After`. HTTP 418 (Binance IP ban) stops the run immediately.
- Partitions that reach into the future are stored as `running` and refreshed next run.
- `--chunk-ms` changes the partition size; defaults are 1 day for candles, 7 days for
  open interest, and 30 days for funding.

