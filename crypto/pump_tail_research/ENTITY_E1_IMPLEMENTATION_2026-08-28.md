# Pump entity E1 implementation addendum

> Frozen before the 2026 entity-feature query is executed. The historical labels are already known, so this development experiment may kill the lane or define E2, but cannot authorize trading.

## Point-in-time feature source

- Cohort and base features remain exactly those in `T5M_EXPERIMENT.md`.
- Entity inputs use only successful Pump bonding-curve trades at or before canonical PumpSwap pool creation, plus PumpSwap buys through T+5m.
- The Dune probes on 2026-08-28 confirmed `pumpdotfun_solana.pump_evt_tradeevent` exposes `mint`, `user`, `evt_tx_id`, `evt_tx_signer`, direction and token/SOL amounts; `solana.transactions` exposes all transaction signers. No future outcome table is read.

## Frozen high-confidence entity rule

This first E1 implementation deliberately under-merges.

1. For each pre-migration Pump trade transaction, count distinct `user` accounts.
2. An atomic controller group exists only when the transaction has 2–8 distinct Pump users and every grouped user appears in `solana.transactions.signers`.
3. A wallet's entity key is its earliest qualifying atomic group for the current mint; otherwise the wallet remains its own entity.
4. Fee-payer equality alone never merges wallets. Same block, similar amount, shared router and high-fanout funders never merge wallets.
5. If a wallet appears in multiple atomic groups, the first group is used rather than building a transitive component. This sacrifices recall to cap false merges and runtime.

Direct-funder, creator-funded transfer and Jito bundle edges remain unavailable in this run and are represented as unavailable, not as observed zero. A failed E1-core therefore closes this implementation; it does not prove that every possible proprietary entity graph is useless.

## Frozen feature/control blocks

`WALLET_HOLDING` (new information but no entity merge):

- positive-holder wallet count;
- top wallet pre-migration net holding share and wallet holding HHI;
- creator's pre-migration net holding share.

`ENTITY_MERGE`:

- entity count and wallet/entity ratio;
- top entity holding share and entity holding HHI;
- creator-connected entity holding share;
- atomic-linked wallet and holding shares;
- top entity sellable holdings / migration pool base reserve;
- entity-level maximum buy-volume share and HHI through T+5m;
- top-share and HHI increments relative to wallet holdings.

Missing/zero conventions are fixed in SQL. Net holdings are clipped at zero for concentration denominators; this is an observable inventory proxy, not an SPL-account snapshot.

## Models and comparisons

Use the existing three forward folds, HGB parameters, Logistic diagnostic and validation top-10% threshold without retuning.

Compare:

1. `BASE`;
2. `WALLET_HOLDING`;
3. `ENTITY_MERGE`;
4. `BASE_PLUS_WALLET_HOLDING`;
5. `BASE_PLUS_ALL_ENTITY`.

The entity-specific increment is comparison 5 minus comparison 4. Comparison 5 minus 1 alone is not sufficient, because it conflates wallet holding concentration with reconstruction.

## Frozen economics

- Primary execution outcome is the already frozen `$500`, TP 2.0x, SL 0.5x, 4h first-passage rule in `FIRST_PASSAGE_EXPERIMENT.md`.
- For each fold/model, choose the validation top 10% score threshold, then apply it unchanged to that fold's test window.
- Report count precision, capacity-weighted precision, selected capacity P50, selected executable trades, mean net ROI, date-block bootstrap one-sided 95% lower bound and May/June/July segments.
- Passing still requires the gates in `ENTITY_INCREMENTAL_EXPERIMENT_2026-08-26.md`; no diagnostic cutoff substitutes for them.

## Data-quality gate

- Exactly one feature row per 26,496 base mints.
- No timestamp later than T+5m in feature SQL.
- Report atomic coverage and entity component sizes. If a component exceeds 8 wallets, or signer verification coverage is incomplete, stop before modeling.
- `BASE` rerun must reproduce the prior result within deterministic numerical tolerance.

