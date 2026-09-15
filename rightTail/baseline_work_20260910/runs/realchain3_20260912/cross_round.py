#!/usr/bin/env python3
"""跨轮复现观察：第二轮串行（v1.16 代码、快照 25950799）vs 本轮串行（v1.19 代码、另一快照）。

**这是观察，不是验收判据。** 两轮钉的 finalized 快照不同 —— 第一、二轮钉的是同一个块，
本轮是第一次跨快照比较。逐候选测量本身只读候选自己的历史块（entry_block / exit_block），
快照主要约束 cutoff 与新鲜度检查，所以"结果是否随快照变化"本身就是要观察的事实，
不预设它必须一致。只读两轮结果文件，不写历史目录。
"""
import json
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[2] if (Path(__file__).resolve().parents[2] / "pilot_measure.py").is_file() \
    else Path("/home/ancillary/rightTail/baseline_work_20260910")
R2 = W / "runs" / "realchain2_20260911"
#: 允许不同：耗时/计数/带出标记（同第二轮 compare.py），以及 v1.17 起新增的结果字段
#: （v1.16 的结果文件里没有这些键，属于已记录的格式增补，不算不一致）
ALLOWED_TOP = {"elapsed_s", "rpc_calls", "etherscan_calls", "carried_from_checkpoint"}
NEW_IN_V117 = {"validation_status"}
#: v1.17 四态带来的**结果格式增补**：这些键在 v1.16 的结果文件里根本不存在。
#: 单独归类为 schema_addition，不与"同一字段取值变了"混在一起。
NEW_KEYS_V117 = {"status", "unavailable", "failures", "passed", "interrupted_by"}


def diff(a, b, path="", top=True):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if top and k in ALLOWED_TOP:
                continue
            if top and k in NEW_IN_V117 and k not in a:
                continue                      # 旧轮没有这个键：格式增补
            p = f"{path}.{k}" if path else k
            if k not in a:
                out.append((p, "<缺>", b[k]))
            elif k not in b:
                out.append((p, a[k], "<缺>"))
            else:
                out += diff(a[k], b[k], p, top=False)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append((path, f"len={len(a)}", f"len={len(b)}"))
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, f"{path}[{i}]", top=False)
    elif a != b:
        out.append((path, a, b))
    return out


def main():
    old_doc, new_doc, out_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    old = json.loads(old_doc.read_text(encoding="utf-8"))
    new = json.loads(new_doc.read_text(encoding="utf-8"))
    A = {r["index"]: r for r in old["results"]}
    B = {r["index"]: r for r in new["results"]}
    rep = {"round2_doc": str(old_doc), "round3_doc": str(new_doc), "round2": {"snapshot": old["finalized_snapshot"], "spec": old.get("spec"),
                      "script_sha256": old.get("script_sha256")},
           "round3": {"snapshot": new["finalized_snapshot"], "spec": new.get("spec"),
                      "script_sha256": new.get("script_sha256")},
           "same_snapshot": old["finalized_snapshot"] == new["finalized_snapshot"],
           "same_sample": sorted(A) == sorted(B), "per_candidate": []}
    for i in sorted(set(A) | set(B)):
        d = diff(A.get(i, {}), B.get(i, {}))
        adds = [(p, x, y) for p, x, y in d
                if x == "<缺>" and p.rsplit(".", 1)[-1] in NEW_KEYS_V117]
        vals = [(p, x, y) for p, x, y in d if (p, x, y) not in adds]
        rep["per_candidate"].append(
            {"index": i, "round2_state": A.get(i, {}).get("state"),
             "round3_state": B.get(i, {}).get("state"),
             "same_state": A.get(i, {}).get("state") == B.get(i, {}).get("state"),
             "schema_additions": [p for p, _, _ in adds],
             "value_changes": [{"path": p, "round2": x, "round3": y} for p, x, y in vals],
             "identical_ignoring_schema_additions": not vals})
    rep["n_same_state"] = sum(c["same_state"] for c in rep["per_candidate"])
    rep["n_identical"] = sum(c["identical_ignoring_schema_additions"] for c in rep["per_candidate"])
    out_path.write_text(json.dumps(rep, ensure_ascii=False, indent=2, default=str) + "\n")
    print(f"同一快照={rep['same_snapshot']}  同一样本={rep['same_sample']}")
    for c in rep["per_candidate"]:
        print(f"  {c['index']}: 第二轮={c['round2_state']:<26} 本轮={c['round3_state']:<26} "
              f"状态一致={c['same_state']} 除格式增补外一致={c['identical_ignoring_schema_additions']}"
              f" 格式增补 {len(c['schema_additions'])} 处"
              + ("" if not c["value_changes"] else f" **取值变化**={[v['path'] for v in c['value_changes']][:4]}"))
    print(f"状态一致 {rep['n_same_state']}/{len(rep['per_candidate'])}；"
          f"除 v1.17 格式增补外逐字段一致 {rep['n_identical']}/{len(rep['per_candidate'])}")


if __name__ == "__main__":
    main()
