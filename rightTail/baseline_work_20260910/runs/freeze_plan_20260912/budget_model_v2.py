#!/usr/bin/env python3
"""300 样本调用量 / 墙钟的**条件压力情景**（v2）。只读既有三轮 + 首批正式对照的证据，不联网。

v1（`budget_model.py`，原字节保留）有三处错误，见 `ERRATA.md`：
把"错误数"当成"续跑进程数"、把每次错误的额外成本记成一个完整候选、Etherscan 只算 300 次。

本版区分三个层次，任何一层都不互相冒充：
  1. **网络请求**：逐条 RPC / Etherscan 执行记录；
  2. **候选级失败尝试**：一个候选中途失败时**已经消耗的失败前缀**（大小取决于失败发生的阶段）；
  3. **子运行续跑进程**：一次运行里可能有多个候选失败，续跑一次即可补齐多个 ⇒ 进程数 < 错误数。

输出 budget_model_v2.json。**这些是条件情景，不是预测**：错误率取各轮观察值作端点，
不做独立同分布外推（首轮错误在约 10 秒内聚集）；正式规模的墙钟与并行加速比**没有实测**。
"""
import json
import statistics as st
from pathlib import Path

W = Path(__file__).resolve().parents[2]
ROUNDS = {"round1": W / "runs/realchain_20260911", "round2": W / "runs/realchain2_20260911",
          "round3": W / "runs/v119_20260911T233131Z-546793",
          "formal_sub01": W / "runs/formal_sub01_20260912T003750Z-f0c3ee"}
FULL = {"measured_exit", "execution_reverted_unknown", "entry_unknown"}
N_FORMAL, N_SUBSET_PAIR = 300, 30
BATCH, N_BATCH = 20, 15
RPS = 3.0
RESUME_START_RPC = 2            # 续跑进程的启动开销：chainId + 快照（检查点绑定核验不发请求）


def counts(d):
    rpc = err = eth = 0
    stages = {}
    for f in sorted(Path(d).glob("*.evidence.jsonl")):
        for line in f.read_text(errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("kind") == "rpc":
                rpc += 1
                if (r.get("record") or {}).get("error"):
                    err += 1
                    stages[r.get("stage")] = stages.get(r.get("stage"), 0) + 1
            elif r.get("kind") == "etherscan":
                eth += 1
    return {"rpc": rpc, "errors": err, "etherscan": eth,
            "error_fraction": round(err / rpc, 6) if rpc else None, "error_stages": stages}


def candidate_costs():
    """完整候选成本、失败前缀、no_mint 成本 —— 全部来自本次实测、非检查点带出的记录。"""
    full, prefix, nomint = [], [], []
    for rd, d in ROUNDS.items():
        for doc in sorted(Path(d).glob("*.json")):
            if doc.name in ("driver.json",) or doc.name.startswith(("compare_", "recompare_")):
                continue
            try:
                j = json.loads(doc.read_text())
            except ValueError:
                continue
            for r in j.get("results") or []:
                if r.get("carried_from_checkpoint") or not r.get("rpc_calls"):
                    continue
                row = {"round": rd, "index": r["index"], "state": r["state"], "rpc": r["rpc_calls"]}
                if r["state"] in FULL:
                    full.append(row)
                elif r["state"] == "no_mint_by_cutoff":
                    nomint.append(row)
                else:
                    prefix.append(row)          # data_missing 等：中途失败，已消耗的前缀
    return full, prefix, nomint


def main():
    rounds = {k: counts(v) for k, v in ROUNDS.items()}
    full, prefix, nomint = candidate_costs()
    rpc_full = st.median([x["rpc"] for x in full])
    pre = sorted(x["rpc"] for x in prefix)
    pre_med, pre_lo, pre_hi = st.median(pre), min(pre), max(pre)
    # 实测的"错误数 → 续跑进程数"：不是 1:1
    observed = {"round3": {"errors": rounds["round3"]["errors"], "resume_procs": 3},
                "formal_sub01": {"errors": rounds["formal_sub01"]["errors"], "resume_procs": 2}}
    ratio = [v["resume_procs"] / v["errors"] for v in observed.values() if v["errors"]]

    # 基准（无错误、无重测）：方案 A = 300 个主采集 + 30×2 对照
    base_rpc = (N_FORMAL + 2 * N_SUBSET_PAIR) * rpc_full
    base_eth = N_FORMAL + 2 * N_SUBSET_PAIR          # 每候选 1 次，**360 次**，不是 300
    err_lo = min(r["error_fraction"] for r in rounds.values())
    err_hi = max(r["error_fraction"] for r in rounds.values())

    scen = {}
    for name, p in (("低", err_lo), ("高", err_hi)):
        n_err = base_rpc * p
        # 额外调用 = 失败前缀之和 + 续跑进程启动开销。**重测本身已含在基准里**
        # （基准按每候选一条最终成功路径计），v1 误把每次错误再加一整个候选。
        for pk, pv in (("前缀取中位", pre_med), ("前缀取最大", pre_hi)):
            procs_lo, procs_hi = n_err * min(ratio), n_err * 1.0     # 上界：每错误一个进程
            scen[f"{name}错误率·{pk}"] = {
                "error_fraction": p, "expected_rpc_errors": round(n_err, 1),
                "failure_prefix_each": pv,
                "resume_processes_range": [round(procs_lo, 1), round(procs_hi, 1)],
                "extra_rpc_range": [round(n_err * pv + procs_lo * RESUME_START_RPC),
                                    round(n_err * pv + procs_hi * RESUME_START_RPC)],
                "extra_etherscan_range": [round(n_err * 0), round(n_err)],
            }
    tot = {k: [round(base_rpc + v["extra_rpc_range"][0]), round(base_rpc + v["extra_rpc_range"][1])]
           for k, v in scen.items()}
    out = {
        "note": "条件压力情景，不是预测。区间端点来自各轮观察，不做 iid 外推；"
                "正式规模的墙钟与并行加速比没有实测",
        "inputs": {
            "rounds": rounds,
            "full_candidate_rpc_median": rpc_full,
            "failure_prefix_rpc": {"n": len(pre), "min": pre_lo, "median": pre_med, "max": pre_hi,
                                   "note": "取决于失败发生的阶段：exit_locate 早期约 40–47，"
                                           "restore_check 晚期接近完整候选"},
            "no_mint_rpc": sorted({x["rpc"] for x in nomint}),
            "observed_errors_to_resume_processes": observed,
            "resume_process_per_error_ratio_observed": [round(min(ratio), 2), round(max(ratio), 2)],
        },
        "plan_A_base": {"assumption": f"{N_FORMAL} 个主采集 + {N_SUBSET_PAIR}×2 对照，"
                                      f"全部按完整候选计（no_mint 更便宜，故这是偏保守的基准）",
                        "rpc": round(base_rpc), "etherscan": base_eth},
        "scenarios": scen, "total_rpc_range": tot,
        "batching": {"batch_size": BATCH, "n_batches": N_BATCH,
                     "per_batch_rpc": BATCH * rpc_full,
                     "limits": {"max_calls": 4000, "max_seconds": 3000, "max_wall_s": 3600},
                     "note": "每批 20 个：约 2100 次 RPC（上限 4000）、串行约 2532 s、并行两路约 1266 s"},
        "wall_clock": {"per_candidate_s_median_by_round": {
            rd: (round(st.median(_elapsed(rd)), 1) if _elapsed(rd) else None) for rd in ROUNDS},
            "caveat": "并行两路≈串行一半是**假设**，未在正式规模实测；"
                      f"rps={RPS:.0f} 的全局限流下界为 总调用/rps；"
                      "子运行墙钟之和不含尝试间等待、驱动与验收耗时，也不是主动工时"},
        "budget_gate": {"mechanism": "驱动的 --budget-rpc / --budget-etherscan / --budget-wall-s "
                                     "按运行目录累计（含中断尝试）拦截新子运行",
                        "note": "只设 --max-resumes 拦不住费用：每个子运行都会重新获得一份 "
                                "max_calls/max_seconds"},
    }
    Path("budget_model_v2.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"每完整候选RPC中位": rpc_full,
                      "失败前缀": out["inputs"]["failure_prefix_rpc"],
                      "错误→续跑进程比(实测)": out["inputs"]["resume_process_per_error_ratio_observed"],
                      "方案A基准": out["plan_A_base"], "总RPC区间": tot}, ensure_ascii=False, indent=2))


def _elapsed(rd):
    out = []
    for doc in sorted(Path(ROUNDS[rd]).glob("*.json")):
        try:
            j = json.loads(doc.read_text())
        except ValueError:
            continue
        for r in j.get("results") or []:
            if not r.get("carried_from_checkpoint") and r.get("state") in FULL and r.get("elapsed_s"):
                out.append(r["elapsed_s"])
    return out


if __name__ == "__main__":
    main()
