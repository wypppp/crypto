# Round 0 v2 universe tables

`v2@2026-08-24T17:05:00+08:00` is the active common cutoff. The old `v1` remains an incomplete historical vintage and must not be backfilled.

As of the 2026-08-25 source-boundary correction, this vintage is `source_scope_blocked`, not merely awaiting a user export. There is no independent internal observation source or product-capacity master. The public pollution-source catalog is retained separately as `U-PUB-OBS` evidence and must not be copied into the three empty tables to make Round 0 appear complete.

Files:

- `venue_coverage_v2.csv`: nine-venue completeness control;
- `u_mkt_v2.csv`: positively discovered standardized commodity-option product families;
- `u_econ_v2.csv`: Hebei product/capacity universe; source unavailable in the current scope;
- `u_obs_v2.csv`: the originally assumed `INT-CEMS/INT-AIR` universe; no such accessible source exists;
- `u_proc_v2.csv`: product–core-process–facility–outlet topology; source unavailable in the current scope;
- `exclusions_v2.csv`: explicit exclusions and their reopen conditions.

Rows marked `discovered_member_unfrozen` are not a frozen universe and do not yet confer formal `W0`. `venue_coverage_v2.csv` is the completeness gate: CME remains unenumerated; ICE and LME are enumerated only from current catalogs; the other venues still lack parts of the listing-date/current-contract/hash evidence. A row marked `current_catalog_member_cutoff_not_proven` is discovery evidence only, not proof that it belonged to the universe at the cutoff. Do not change `vintage_cutoff` when filling later evidence; use `accessed_at` to record when evidence was obtained.

The CZCE PFMI PDF was downloaded to a temporary working file and hashed as `62bd0d0b...`; its official URL and full hash are recorded in the tables. Other pages marked `not_saved` or `not_saved_waf` have not satisfied the local snapshot requirement.

ICE discovery is rebuilt from the saved official product-code CSV with:

```bash
python3 option/scripts/import_ice_u_mkt.py --write
```

The importer verifies the frozen CSV hash and applies a fixed 17-group commodity filter. Its 281 rows are post-cutoff discoveries, not cutoff membership proof; each therefore remains explicitly blocked on a formal first-listing date.

CME's official FPRF directory contains four dated option reference ZIPs for `2026-08-21`, before the cutoff. Their names and observed directory metadata are frozen in `cme_fprf_sources_v2.json`; all direct download routes failed in the current environment, so CME remains at zero rather than being reconstructed from memory. When the files become reachable:

```bash
python3 option/scripts/collect_cme_fprf.py fetch <new-snapshot-dir>
python3 option/scripts/collect_cme_fprf.py inventory <new-snapshot-dir> <new-inventory.csv>
```

The inventory is deliberately a staging table. Audit and freeze the official `SeriesProdCmplx` commodity allowlist before any CME row is written into `u_mkt_v2.csv`.

Run the structural gate after every edit:

```bash
python3 option/scripts/validate_universe_v2.py
```

A `STRUCTURE PASS` only means that IDs, cutoffs, schemas, counts and uniqueness agree. Warnings are live completeness gaps; the result does not freeze the universe or award `W0/W1`.

The user has no pending action in this directory. Reopening the three source-blocked universes requires genuinely new source access or an explicitly new research vintage with different universe definitions; it cannot be achieved by filling unknowns from point names.
