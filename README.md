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
