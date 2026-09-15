#!/usr/bin/env python3
"""300 样本的调用量 / 墙钟预算模型：**全部输入来自已保存的三轮真链证据**，只读，不联网。

输出 budget_model.json。文档里的每个数字都应能由本脚本复算。

**这不是预测。** 错误率用三轮各自的观察值作区间端点，不做独立同分布假设的外推
（第一轮的 TLS 错误在约 10 秒内聚集，独立性明显不成立）；候选状态分布只有 8 个开发候选的观察，
n=8 的比例不足以推断 300 个的构成，因此以"全部候选都需完整测量"作为**上界情景**。
"""
import json
import statistics as st
from pathlib import Path

W = Path(__file__).resolve().parents[2]
ROUNDS = {
    "round1": W / "runs/realchain_20260911",
    "round2": W / "runs/realchain2_20260911",
    "round3": W / "runs/v119_20260911T233131Z-546793",
}
FULL_STATES = {"measured_exit", "execution_reverted_unknown"}
N_FORMAL = 300
RPS = 3.0                      # 当前全局限流
MAX_CALLS, MAX_SECONDS, MAX_WALL_S = 4000, 3000, 3600   # 当前单次运行预算


def count_evidence(d):
    rpc = err = eth = 0
    for f in sorted(Path(d).glob("*.evidence.jsonl")):
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("kind") == "rpc":
                rpc += 1
                if (r.get("record") or {}).get("error"):
                    err += 1
            elif r.get("kind") == "etherscan":
                eth += 1
    return {"rpc_records": rpc, "rpc_errors": err, "etherscan_records": eth,
            "error_fraction": round(err / rpc, 6) if rpc else None}


def per_candidate():
    """逐候选成本：只取**本次实测**（非检查点带出）且走完整流程的候选。"""
    full, nomint = [], []
    for rd, d in ROUNDS.items():
        for doc in sorted(Path(d).glob("*.json")):
            if doc.name in ("compare_report.json", "cross_round_report.json", "driver.json"):
                continue
            try:
                j = json.loads(doc.read_text())
            except ValueError:
                continue
            for r in j.get("results") or []:
                if r.get("carried_from_checkpoint") or not r.get("rpc_calls"):
                    continue
                row = {"round": rd, "doc": doc.name, "index": r["index"], "state": r["state"],
                       "rpc": r.get("rpc_calls"), "elapsed_s": r.get("elapsed_s")}
                if r["state"] in FULL_STATES:
                    full.append(row)
                elif r["state"] == "no_mint_by_cutoff":
                    nomint.append(row)
    return full, nomint


def main():
    rounds = {k: count_evidence(v) for k, v in ROUNDS.items()}
    full, nomint = per_candidate()
    rpc_full = [x["rpc"] for x in full]
    sec_full = [x["elapsed_s"] for x in full]
    sec_by_round = {rd: [x["elapsed_s"] for x in full if x["round"] == rd] for rd in ROUNDS}
    rpc_med = st.median(rpc_full)
    # 每候选耗时按轮分别取中位：端点当时的时延差异不该被平均掉
    sec_med = {rd: (round(st.median(v), 1) if v else None) for rd, v in sec_by_round.items()}
    sec_lo, sec_hi = min(v for v in sec_med.values() if v), max(v for v in sec_med.values() if v)

    base_rpc = N_FORMAL * rpc_med                       # 上界情景：300 个都完整测量
    err_lo = min(r["error_fraction"] for r in rounds.values())
    err_hi = max(r["error_fraction"] for r in rounds.values())
    # 一次传输错误 ⇒ 当次运行以 1 结束；检查点保住已完成候选，续跑只重测被打断的那一个。
    # 因此每次错误的代价 ≈ 启动（chainId + 快照 + 绑定核验，约 2 次 RPC）+ 重测一个候选。
    resume_rpc = rpc_med + 2
    scen = {}
    for name, p in (("低", err_lo), ("高", err_hi)):
        n_err = base_rpc * p
        scen[name] = {
            "error_fraction": p,
            "expected_transport_errors": round(n_err, 1),
            "extra_rpc_from_resumes": round(n_err * resume_rpc),
            "extra_rpc_pct": round(n_err * resume_rpc / base_rpc * 100, 1),
            "extra_wall_s_serial": round(n_err * sec_hi),
        }
    total_rpc = {k: round(base_rpc + v["extra_rpc_from_resumes"]) for k, v in scen.items()}
    # 墙钟：串行 = 逐候选时延之和；并行 2 路 = 时延减半与全局限流下界取大者
    ser = {k: {"low_latency": round(N_FORMAL * sec_lo + scen[k]["extra_wall_s_serial"]),
               "high_latency": round(N_FORMAL * sec_hi + scen[k]["extra_wall_s_serial"])}
           for k in scen}
    gate_floor = {k: round(total_rpc[k] / RPS) for k in scen}
    par2 = {k: {"low_latency": max(round(ser[k]["low_latency"] / 2), gate_floor[k]),
                "high_latency": max(round(ser[k]["high_latency"] / 2), gate_floor[k])}
            for k in scen}
    batch = {"by_max_calls": int(MAX_CALLS // rpc_med),
             "by_max_seconds": int(MAX_SECONDS // sec_hi),
             "by_max_wall_s": int(MAX_WALL_S // sec_hi)}
    batch["limit"] = min(batch.values())

    # ---- 采集方案对比：正式测量要不要把 300 个都测两遍（串行一遍 + 并行一遍）----
    # 对照是**工具一致性**证据，不是经济结论的输入。全量对照把调用量与费用翻倍，
    # 子集对照把覆盖从 8 个扩到 n_sub 个，成本可控。两者都列出，由决策方选。
    def plan(n_main_parallel2, n_sub_pair):
        rpc = (n_main_parallel2 + 2 * n_sub_pair) * rpc_med
        plans = {}
        for k, p_ in (("低", err_lo), ("高", err_hi)):
            n_err = rpc * p_
            tot = rpc + n_err * resume_rpc
            main_par = max(round(n_main_parallel2 * sec_hi / 2), round(tot / RPS / 2))
            sub = round(n_sub_pair * sec_hi) + max(round(n_sub_pair * sec_hi / 2), 0)
            plans[k] = {"rpc_incl_resumes": round(tot),
                        "expected_transport_errors": round(n_err, 1),
                        "wall_s_main_parallel2": main_par,
                        "wall_s_subset_pair": sub,
                        "wall_s_total": main_par + sub + round(n_err * sec_hi)}
        return plans
    SUB = 30
    plans = {
        "A_全量并行2路 + %d 个子集串并行对照" % SUB: plan(N_FORMAL, SUB),
        "B_全量串并行对照（300 个各测两遍）": plan(0, N_FORMAL),
    }

    out = {
        "inputs": {
            "rounds": rounds,
            "full_candidate_rpc": {"n": len(rpc_full), "min": min(rpc_full), "max": max(rpc_full),
                                   "median": rpc_med},
            "full_candidate_elapsed_s_median_by_round": sec_med,
            "no_mint_candidates": {"n": len(nomint),
                                   "rpc": sorted({x["rpc"] for x in nomint}),
                                   "elapsed_s": [round(x["elapsed_s"], 1) for x in nomint]},
            "rps": RPS, "run_budget": {"max_calls": MAX_CALLS, "max_seconds": MAX_SECONDS,
                                       "max_wall_s": MAX_WALL_S},
        },
        "upper_bound_scenario": {
            "assumption": "300 个候选全部走完整流程（不含任何 no_mint_by_cutoff 这类廉价候选）",
            "base_rpc": round(base_rpc), "etherscan": N_FORMAL,
        },
        "error_overhead": scen,
        "total_rpc_incl_resumes": total_rpc,
        "wall_s": {"serial": ser, "parallel2": par2, "rate_limit_floor_s": gate_floor},
        "collection_plans": plans,
        "batching": {
            "note": "单次运行受 max_calls / max_seconds / 治理器 max_wall_s 三者共同约束，取最小",
            "candidates_per_run": batch,
            "runs_needed_at_limit": -(-N_FORMAL // batch["limit"]),
        },
        "caveats": [
            "错误率区间取三轮各自的观察值，不做 iid 外推；第一轮错误在约 10 秒内聚集，独立性不成立",
            "候选状态分布只有 8 个开发候选的观察，不足以推断 300 个的构成；故按全部完整测量作上界",
            "每候选时延由端点当时状态支配（三轮中位 %s..%s 秒），不是本机可控量" % (sec_lo, sec_hi),
            "并行只把时延重叠，不放宽全局限流；rps=%.0f 下的限流下界是硬下界" % RPS,
            "计费单位（CU 等）与账户配额不在本模型内，须按账户当前计费表另行核对",
        ],
    }
    Path("budget_model.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"每候选RPC中位": rpc_med, "每候选秒数中位": sec_med,
                      "上界基准RPC": round(base_rpc), "错误率区间": [err_lo, err_hi],
                      "含续跑总RPC": total_rpc, "串行墙钟s": ser, "并行2路墙钟s": par2,
                      "限流下界s": gate_floor, "单次运行候选上限": batch,
                      "需要运行批次": out["batching"]["runs_needed_at_limit"],
                      "采集方案": {k: {kk: {"RPC": vv["rpc_incl_resumes"],
                                            "总墙钟h": round(vv["wall_s_total"] / 3600, 1)}
                                       for kk, vv in v.items()} for k, v in plans.items()}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
