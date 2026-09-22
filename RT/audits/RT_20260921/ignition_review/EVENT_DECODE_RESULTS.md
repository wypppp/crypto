# Archived event amount audit

Run with `.venv/bin/python audits/RT_20260921/ignition_review/decode_archived_events.py`.

The parser reads all six `full24h_*.jsonl.gz` archives and the checked-in `pump.json` / `pump_amm.json` IDLs. It recognizes events by the IDL discriminator in `Program data` (base64), not by log text. Curve buys use `TradeEvent.sol_amount`; AMM buys use `BuyEvent.quote_amount_in_with_lp_fee`.

It decoded 13,993 transaction rows. There were 8,351 rows with a buy amount, 4,057 with a sell event, and 11 with a liquidity/migration event. Event data is accepted only while the active invoke stack is the actual Pump or PumpAMM program; curve `TradeEvent.mint` and AMM `BuyEvent.pool` must match the six-coin venue. Among 8,314 pure-buy curve/pool trade rows, 8,305 had a recognized amount; 8,299 matched `trades.csv.sol` exactly at lamport precision and 6 differed. Nine eligible rows have unsupported/missing amounts. The six differences are retained in [event_trade_reconciliation.csv](event_trade_reconciliation.csv); they are preserved as decoded and are not silently adjusted with a fee fallback.

The requested normalized six-coin transaction output is [normalized_events.csv](normalized_events.csv), with the requested columns plus `event_names` and `decode_fail`. The three mechanically selected >=4 SOL events decode as:

| mint prefix | event | buy lamports |
|---|---|---:|
| BUvuChjf | TradeEvent.sol_amount | 4,406,666,666 |
| 5i1SVh2A | BuyEvent.quote_amount_in_with_lp_fee | 4,889,866,666 |
| B1C2xfcU | BuyEvent.quote_amount_in_with_lp_fee | 26,113,797,485 |

The amount values are event fields; no economic interpretation or fee fallback is applied.
