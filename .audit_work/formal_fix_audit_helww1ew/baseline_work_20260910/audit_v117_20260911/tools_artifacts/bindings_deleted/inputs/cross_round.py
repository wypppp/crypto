"""跨轮复现：首轮串行 vs 第二轮串行，同一钉住的块、同一样本。
两轮代码只差启动阶段的异常处理（v1.15 → v1.16），不涉及逐候选逻辑。
允许不同的字段与 compare.py 相同：elapsed_s、rpc_calls、carried_from_checkpoint。
"""
import sys, json
from pathlib import Path
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here))
from compare import diff  # 复用同一套逐字段比较
r1 = json.loads((here.parent / "realchain_20260911" / "serial.json").read_text())
r2 = json.loads((here / "serial.json").read_text())
A = {r["index"]: r for r in r1["results"]}
B = {r["index"]: r for r in r2["results"]}
out = {"round1_snapshot": r1["finalized_snapshot"], "round2_snapshot": r2["finalized_snapshot"],
       "same_snapshot": r1["finalized_snapshot"] == r2["finalized_snapshot"], "per_candidate": []}
for i in sorted(set(A) | set(B)):
    d = diff(A.get(i, {}), B.get(i, {}))
    out["per_candidate"].append({"index": i, "round1": A.get(i, {}).get("state"),
                                 "round2": B.get(i, {}).get("state"),
                                 "identical_except_allowed": not d,
                                 "diff_paths": [p for p, _, _ in d][:12]})
(here / "cross_round_report.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
for c in out["per_candidate"]:
    print(f"  {c['index']}: 首轮={c['round1']:<28} 第二轮={c['round2']:<28} 一致={c['identical_except_allowed']}"
          + ("" if c["identical_except_allowed"] else f"  差异路径={c['diff_paths'][:4]}"))
print("同一快照:", out["same_snapshot"])
