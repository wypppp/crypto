# Data provenance

- `hf_migrations.parquet` and `hf_postgard_outcomes.parquet` are audit-only copies from the public `Slinky21/Pumpfun_Memecoin_Corpus` dataset.
- They are **not** inputs to the final analysis. The migrations file has only 5,701 rows and covers roughly 2026-06-09 through 2026-07-14, rather than the frozen 2026-05-01 through 2026-07-24 universe. Its migration timestamps also include synthetic/backfilled detections, and its outcomes stop at 48 hours.
- `dune_token_metrics.csv` is the intended full-query output and is intentionally absent until a Dune execution succeeds.
