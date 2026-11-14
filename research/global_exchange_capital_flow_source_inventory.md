# Global Exchange & Capital-Flow Source Inventory

**Research branch:** `research/nine-month-indicator-blueprint-v1`  
**Status:** source inventory and acquisition plan; no claim that historical coverage is already complete.  
**Research window:** 2026-02-14 through 2026-11-14.

## 1. Coverage policy

The engine must not treat every exchange as interchangeable. Each observation retains venue, market type, instrument, quote currency, event timestamp, collection timestamp, source endpoint, and coverage status. Cross-venue features are calculated only after timestamp alignment, FX conversion, contract normalization, and symbol/entity mapping.

Venue inclusion means "candidate data source to integrate", not proof that every requested field is publicly available for the full nine-month window. Private account balances, customer-level positions, and private wallet labels are not assumed accessible.

## 2. Priority venue matrix

| Region / market | Venues to cover | Primary datasets | Important limitations / treatment |
|---|---|---|---|
| South Korea | Upbit, Bithumb, Coinone, Korbit, GOPAX | KRW spot trades, candles, order books, quote volume, listings/notices | KRW markets are essential for Korean demand and Kimchi premium. Public market data is distinct from private customer deposit/withdrawal/account data. Verify each venue's historical retention and rate limits. |
| China-linked / offshore Asia | OKX, Binance, HTX, Gate.io, KuCoin, Bitget, MEXC | Spot, perpetual swaps, futures, OI, funding, taker flow, liquidations, borrow/lending rates where published | Mainland China is not treated as a domestic centralized crypto-exchange market: regulatory restrictions mean "Chinese exchanges" must be represented as offshore venues / Chinese-language or Asia-linked liquidity hubs, not falsely labelled mainland-licensed exchanges. |
| Japan | bitFlyer, Coincheck, bitbank, GMO Coin, Binance Japan | JPY spot trades, order books, candles, market listings | JPY conversion and local pair liquidity must be retained. Derivatives availability differs by venue and jurisdiction. |
| United States | Coinbase Exchange, Kraken, Gemini, Bitstamp (US-accessible market), Crypto.com Exchange where available; CME crypto futures as a separate regulated derivatives venue | USD spot trades/order books/candles; listed futures OI, volume, basis and settlement data where licensed/public | Do not conflate US spot venues with offshore perpetual venues. Product availability and access vary by state and regulation. |
| Global derivatives venues | Binance USDⓈ-M / COIN-M, OKX, Bybit, Bitget, Gate.io, MEXC, Hyperliquid, Kraken Futures, Deribit | Contract metadata, OI, funding history, mark/index prices, basis, long/short account ratios, taker buy/sell, liquidation feeds | OI is outstanding contracts, not a directional "short position" count. Long and short exposure coexist. Use venue-specific contract multipliers and USD notionals. Historical depth differs sharply by provider. |
| Global reference / FX | USD/KRW, USD/JPY, USD/CNY reference rates; stablecoin/USD and stablecoin/KRW prices | FX conversion, stablecoin premium, reference price construction | Preserve source and timestamp; do not use a daily FX close to convert intraday premiums without marking the timing mismatch. |

### Priority order

1. **Tier 1 (first adapters):** Binance spot + USDⓈ-M futures, Upbit, Bithumb, OKX, Bybit.
2. **Tier 2:** Coinone, Korbit, Coinbase, Kraken, Gate.io, Bitget, MEXC, bitFlyer, GMO Coin, Coincheck, bitbank.
3. **Tier 3 / specialist:** HTX, KuCoin, Gemini, Deribit, Kraken Futures, Hyperliquid, CME and other venues only where instrument coverage and permitted public data add material value.

This order is for implementation efficiency, not a judgement about exchange importance.

## 3. Required cross-exchange signals (not conventional indicator-first research)

### A. Spot capital-flow pressure

- Quote-currency-normalized aggressive buy notional minus aggressive sell notional.
- Taker buy/sell imbalance, persistence, acceleration and venue contribution.
- Net aggressive flow divided by executable depth and by trailing same-symbol baseline.
- Spot-vs-perpetual lead/lag: whether spot demand leads OI expansion or leverage leads price.
- Venue share migration: whether a small asset's volume and buy pressure are concentrating in KRW, JPY, USD or USDT venues.
- Price impact per unit of net flow, to detect absorption versus thin-book price jumps.

### B. Wallet and whale intelligence

- Large transfers by USD notional, native-asset notional, circulating-supply share and historical percentile.
- Exchange-labelled wallet inflows/outflows, hot/cold wallet movements, bridge flows and token contract movements.
- Repeated flows between identified entities, exchange clusters and newly funded wallets only when label confidence is explicit.
- Exchange inflow pressure and outflow pressure separated; transfers are not automatically interpreted as buys or sells.
- Wallet cohorts: known exchange, market maker, bridge, treasury, vesting, foundation, unknown.
- Entity clustering is probabilistic and must preserve provenance; do not assert common ownership from one transfer.
- For tokens without reliable chain attribution, mark on-chain coverage unavailable rather than manufacturing a whale score.

### C. Derivatives positioning and leverage

- Open interest in contracts, coin units and USD notional; OI change over multiple windows.
- Price/OI quadrant: price up + OI up, price up + OI down, price down + OI up, price down + OI down.
- Funding level, change, persistence, dispersion across venues, and annualized equivalent with the actual funding interval.
- Perpetual-vs-spot basis and mark/index premium.
- Taker buy/sell volume in derivatives, account long/short ratios and top-trader positioning where available.
- Liquidation notional by side and clustering around price levels.
- Detect crowded leverage and squeeze risk; high positive funding is not automatically bullish.
- Keep venue-level OI separate before constructing a deduplicated cross-venue aggregate.

### D. Borrowing rates and financing cost

- Margin borrow rates / lending rates by asset and quote currency.
- Utilization, available borrow quota, margin loan ratios, and rate changes where public.
- Distinguish spot-margin borrowing interest from perpetual funding and dated-futures basis.
- If historical borrowing-rate data is not publicly retained, record the limitation and begin prospective capture.

### E. Kimchi Premium and regional segmentation

For a coin with a valid KRW market and synchronized global reference:

`KimchiPremium_bps = 10,000 * ((P_KRW / FX_USDKRW) / P_global_USD - 1)`

- Calculate per venue (Upbit, Bithumb, Coinone, Korbit) and robust market aggregate.
- Calculate both coin premium and USDT/KRW or USDC/KRW premium; stablecoin premium helps separate crypto-specific demand from KRW dollar-access pressure.
- Match timestamps tightly; account for stale quotes, fees, withdrawal restrictions, local market hours and executable depth.
- Track premium level, rate of change, dispersion between Korean venues, persistence, and volume-weighted premium.
- Do not assume a large premium is directly arbitrageable or a guaranteed pump signal.

### F. Cross-venue capital migration

- Same-asset spot flow by venue and quote currency.
- Relative premium and volume share between KRW, JPY, USD and stablecoin markets.
- Detect whether a move begins in Korea, offshore derivatives, US spot, or another venue.
- Lead/lag must be tested out of sample and corrected for timezone, latency, market hours and symbol mapping.

## 4. Canonical data contract

Every raw observation should include:

- `venue`, `region`, `market_type` (spot, margin, perpetual, dated_future, option, onchain, fx)
- `instrument_id`, `base_asset_id`, `quote_asset_id`, `native_symbol`, `contract_type`
- `event_time` (UTC), `observed_at` (UTC), `ingested_at` (UTC)
- `metric`, `value`, `unit`, `notional_usd` when safely convertible
- `source_endpoint`, `source_record_id`, `raw_payload_hash`
- `coverage_status`, `quality_flags`, `label_confidence`, `fx_source`

Store raw provider payloads separately from normalized observations. Never overwrite source-native values. Deduplicate on provider-native identifiers where possible; otherwise use a deterministic natural key and retain collision diagnostics.

## 5. Historical feasibility and honest coverage

- Binance publishes bulk spot/futures market archives; use them for reproducible historical candles/trades where the requested product exists.
- OKX publishes historical trades, candles, funding, order-book and borrowing-rate downloads with different start dates by dataset.
- Public APIs on Upbit expose market pairs, candles, trades, tickers and order books; public endpoints do not expose private customer holdings.
- Bybit documents public market endpoints for klines, order books, trades, funding history, OI and account ratios.
- Some OI endpoints have short retention windows. Binance's public OI-history endpoint documents only the latest month; this cannot be backfilled to nine months from that endpoint alone. Begin prospective snapshots immediately and seek official archive / licensed historical sources for older OI.
- OKX's downloadable historical data has broader history for some series, but API history endpoints can be shorter. Prefer the official downloadable archive when it covers the requested range.
- Historical L2 order books, liquidation streams, wallet labels and entity attribution may be incomplete or commercial. Capture prospective data continuously and report actual coverage by venue/metric.
- Do not claim nine months of OI, wallet-level exchange flows, order books or funding merely because nine months of candles exist.

## 6. Research and validation safeguards

- Build the asset universe from historical venue listings, including delisted and renamed instruments.
- Maintain canonical asset identity separately from ticker symbols.
- Normalize FX and contract sizes before aggregation.
- Treat unavailable data as missing plus a coverage flag, never zero.
- Use event-time joins and point-in-time availability; no later wallet labels, exchange notices, or revised metadata may leak into past rows.
- Separate historical backfill from prospective live capture.
- Evaluate each venue and signal family individually before combining them.
- Use chronological walk-forward splits and purge overlapping future-label windows.
- Benchmark capital-flow signals against matched assets and time periods, not only price momentum.

## 7. First implementation sequence

1. Implement venue registry, canonical asset/instrument identity and source capability metadata.
2. Implement Tier 1 spot adapters and timestamp/FX normalization.
3. Add derivatives adapters for OI, funding, basis, taker flow and liquidations.
4. Add KRW venue panel and Kimchi premium calculations.
5. Add on-chain wallet flow adapters with explicit label provenance/confidence.
6. Start prospective capture for datasets whose historical retention is insufficient.
7. Generate per-source coverage reports before feature construction or model training.

## Official references reviewed

- Binance Futures market-data documentation: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api
- Bybit market API explorer: https://bybit-exchange.github.io/docs/api-explorer/v5/market/market
- OKX API documentation: https://www.okx.com/docs-v5/en/
- OKX historical data: https://www.okx.com/historical-data
- Upbit API overview: https://global-docs.upbit.com/reference/api-overview
