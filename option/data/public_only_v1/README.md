# public-only v1 data controls

This directory controls `public-only-v1@2026-08-24T16:52:37+08:00`. Observation data is restricted to the supplied Hebei public platform.

- `vintage.json`: source policy, cutoff and immutable source hashes;
- `source_coverage.csv`: closed source-universe counts;
- `candidate_registry.csv`: the frozen 13 seed-term discovery registry;
- `pilot_points.csv`: five enabled wave-1 public points;
- `pilot_baseline.csv`: bounded results from the three saved 2026-08-24 polls;
- `poll_registry.csv`: immutable manifest hashes for imported baselines and new wave-1 polls;
- `wave1_schedule.csv`: frozen seven-day target hour and five poll slots per day;
- `field_semantics.csv` / `point_field_audit.csv`: field labels, units, response-only fields and template/status conflicts from the fixed `+80` anchor;
- `discovery_audit_sample.csv`: 122-row deterministic public-name sample; labels are kept separately;
- `discovery_audit_labels.csv` / `discovery_audit_summary.csv`: public-text-only S1 review, with no production or topology inference;
- `history_registry.csv`: immutable hash for the bounded seven-day historical current-view query;
- `historical_window_profile.csv` / `historical_daily_coverage.csv`: returned coverage and arithmetic-dependence checks; these do not measure original availability;
- `wave1_slot_timing.csv` / `wave1_point_slot_timing.csv` / `wave1_point_day_summary.csv`: scheduled-versus-actual timing, target-row visibility bounds and target-row hash stability;
- `wave1_pre_adjudication.csv` / `.json`: day-1 S0-S5 point-level pre-adjudication, input hashes and remaining blockers; not a final PUB1 award;
- `poll_change_events.csv` / `poll_change_summary.csv`: separates newly filled template rows from revisions to already numeric rows;
- `quick_feasibility/`: history-only diagnostic outputs, `proxy_threshold_sensitivity.csv`, verdict and `minimum_viable_signal_card.csv`; uses no newly fetched data and remains separate from forward adjudication;
- `polls/`: future immutable raw public snapshots, ignored by Git except `.gitkeep`.
- `history/`: immutable raw historical current-view snapshots, ignored by Git except `.gitkeep`.

One future poll is collected with an explicit non-overwriting directory:

```bash
python3 option/scripts/collect_ps_public.py snapshot \
  option/data/public_only_v1/pilot_points.csv \
  --study-id public-only-v1 \
  --output option/data/public_only_v1/polls/<run-id>
```

After a sequence of polls:

```bash
python3 option/scripts/summarize_t026_public.py \
  --poll-root option/data/public_only_v1/polls \
  --ledger option/data/public_only_v1/public_visibility.csv \
  --state option/data/public_only_v1/public_state.csv
python3 option/scripts/validate_public_only_v1.py
```

Rebuild the non-waiting audits from saved responses:

```bash
python3 option/scripts/audit_public_only_fields.py \
  option/data/public_only_v1/polls/20260825T081931+0800
python3 option/scripts/analyze_public_history.py \
  option/data/public_only_v1/history/20260825T083300+0800 \
  option/data/public_only_v1/historical_window_profile.csv \
  option/data/public_only_v1/historical_daily_coverage.csv
python3 option/scripts/compare_public_snapshots.py \
  option/data/public_only_v1/polls \
  option/data/public_only_v1/poll_change_events.csv \
  option/data/public_only_v1/poll_change_summary.csv
python3 option/scripts/audit_wave1_timing.py \
  option/data/public_only_v1/wave1_schedule.csv \
  option/data/public_only_v1/polls \
  option/data/public_only_v1/wave1_slot_timing.csv \
  option/data/public_only_v1/wave1_point_slot_timing.csv \
  option/data/public_only_v1/wave1_point_day_summary.csv
python3 option/scripts/build_public_only_pre_adjudication.py \
  option/data/public_only_v1
python3 option/scripts/evaluate_public_proxy_quick.py \
  option/data/public_only_v1/history/20260825T083300+0800 \
  option/data/public_only_v1/quick_feasibility \
  --followup-snapshot option/data/public_only_v1/polls/20260825T092000+0800 \
  --event-first-observed-snapshot option/data/public_only_v1/polls/20260825T081931+0800 \
  --timing-summary option/data/public_only_v1/wave1_point_day_summary.csv
```

The legacy summarizer filename is retained for compatibility; its outputs here describe only the public source. A validation pass does not award `PUB1/PUB2` or any trading status.
