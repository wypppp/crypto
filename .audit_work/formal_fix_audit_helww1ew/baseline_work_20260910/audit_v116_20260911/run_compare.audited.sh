#!/usr/bin/env bash
# 真链串行 / 两路并行同快照对照。凭据只经 launch.py 以环境变量传入。
# 输出全部写到本目录；不触碰 pilot/ 与任何历史产物。
set -u
cd "$(dirname "$0")/../.."          # baseline_work_20260910
R=runs/realchain2_20260911
PIN="25950799:0xe7e5d3e8b2be05e6e1c537f1a8ea534121c5defc9b6e7ea8edc54d01dd446e82"
COMMON=(--sample pilot/dev_sample.json --pin-finalized "$PIN"
        --max-rss-mb 2048 --max-wall-s 3600 --hard-rss-mb 8192 --hard-cpu-s 3600)
run() {   # $1=标签 $2=并行路数 [$3=检查点，默认同标签]
  local tag=$1 par=$2 ck=${3:-$R/$1.checkpoint.jsonl}
  local t0=$(date +%s.%N)
  python3 $R/launch.py -- python3 pilot_measure.py measure "${COMMON[@]}" \
      --parallel "$par" --out "$R/$tag.json" --evidence "$R/$tag.evidence.jsonl" \
      --checkpoint "$ck" > "$R/$tag.stdout.log" 2> "$R/$tag.stderr.log"
  local rc=$?
  local t1=$(date +%s.%N)
  printf '{"tag":"%s","parallel":%s,"exit":%d,"wall_s":%.1f,"checkpoint":"%s"}\n' \
      "$tag" "$par" "$rc" "$(echo "$t1 - $t0" | bc)" "$ck" | tee -a "$R/runs.jsonl"
}
: > "$R/runs.jsonl"
run serial   1
sleep 30   # 首轮的端点断连恰好落在两轮衔接处；间隔不影响正确性
run parallel 2
sleep 30
# 恢复行为：用串行的检查点再跑一次 —— 应全部跳过、结果从检查点带出、证据链闭合
run resume_serial 1 "$R/serial.checkpoint.jsonl"
echo DONE
