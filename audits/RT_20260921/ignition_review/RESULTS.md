# Ignition review (2026-09-21)

Command: `.venv/bin/python audits/RT_20260921/ignition_review/review_ignition.py`

## Mechanical first post-entry buy >= 4 SOL

The rule is `kind == buy`, `t_rel_entry > 0`, sorted by `(slot, tx_index)`, and `sol >= 4`. Results are in [first_ge4_by_case.csv](first_ge4_by_case.csv).

| pair | role | first time UTC | hours after entry | SOL | post-entry max buy SOL |
|---:|---|---|---:|---:|---:|
| 1 | winner | 2026-06-06 22:55:54 | 0.638056 | 4.406667 | 30.923631 |
| 1 | failure_control | none | — | — | 3.043358 |
| 2 | winner | 2026-06-02 01:10:13 | 7.548889 | 26.113797 | 26.113797 |
| 2 | failure_control | none | — | — | 0.786330 |
| 3 | winner | 2026-06-03 06:21:28 | 3.648333 | 4.889867 | 17.368240 |
| 3 | failure_control | none | — | — | 0 |

The maximum post-entry buy values for the three controls are therefore 3.043358, 0.786330, and 0 SOL, agreeing with the timing narrative. The narrative's BUvu “点火” at 3.12h is a later creator-led episode; the mechanical first-`>=4 SOL` event is the 0.638h, 4.406667 SOL buy. Thus the narrative event and the mechanical definition are not the same event for BUvu. GDP and B1C2 coincide with the first mechanical event shown here.

For the fixed review candidate rule — coin age >=30 minutes, event from original entry through entry+24h, current buy >=4 SOL, and prior 30-minute buy sum <4 SOL — the first qualifying events are exactly the three winner rows above; controls have no hit. The prior-window sums are BUvu 2.190296 SOL, B1C2 0 SOL, and GDP 0 SOL. These amounts are the existing trade file's net reserve-increment `sol` values, not decoded swap gross amounts.

`validate_candidate.py` removes all records after each detected event and reruns the rule: all six first-hit results are unchanged. Its synthetic boundary checks pass for the 4 SOL threshold, the inclusive 1,800-second boundary, and same-second `(slot, tx_index)` ordering; same-second later rows never enter the prior window.

## `top1_share > 0.7`

The F2 export has 14,121 rows including one `__SUMMARY__` row; after dropping that row and null `top1_share`, there are 14,080 coins. `top1_share` is `top1_net / pos_net_total` (F2 rounds the exported value to four decimals). Using the repository's winner label `ms_30d >= 10.0` gives:

* 8,455 coins with `top1_share > 0.7`;
* 18 winners;
* winner rate 0.212892% (0.21% rounded).

The full bucket reproduction is [top1_share_buckets.csv](top1_share_buckets.csv); the direct summary is [top1_share_summary.csv](top1_share_summary.csv). The bucket counts and rates reproduce the table in `三组逐笔时序_20260921.md` (for example, `<=0.1`: 1,213 / 52 / 4.286892%; `>0.7`: 8,455 / 18 / 0.212892%).

## F3 endpoint check

With the later scope extension, `validate_candidate.py` also checks the six case mints' 42 F3 A endpoints through 24h against the last matching trade price in `trades.csv`. All 42 are within 2.4e-6; maximum absolute difference is 4.948400749e-7. Details are in [f3_endpoint_check.csv](f3_endpoint_check.csv).
