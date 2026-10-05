#!/usr/bin/env python3
"""契约 v1.1 实现（eval_contract.py）的测试向量与需求曲线复算输出（10-05；供 GPT 批 1b 独立复算）。

python eval_contract_vectors.py  → 打印各向量；需求曲线按网格计算并检查单调。
需求曲线的名称按 GPT 批 0 A8：“指定二点模型、指定下注规则（半 Kelly）下的需求曲线”，不作普遍的乐观下限解释。
"""

import eval_contract as E


def main():
    print(
        "T1 g(p=0.1, K=13, f=0.0125) =",
        0.1 * E.h(0.0125, 13.0) + 0.9 * E.h(0.0125, 0.0),
    )
    for p, K, N in ((0.30, 1.3 / 0.30, 156), (0.10, 13.0, 1092)):
        s, fl = E.first_passage_two_point(p, K, N, E.half_kelly(p, K))
        print(
            "T5 首达 p=%.2f K=%.4f N=%d 半 Kelly：成功 %.6f，跌破 0.1 倍 %.6f"
            % (p, K, N, s, fl)
        )
    steps = [0.0, 0.5, 1.0, 2.0, 4.0, 10.0, 100.0]
    for L in (
        [0.40, 0.25, 0.12, 0.05, 0.015, 0.002],
        [0.40, 0.25, 0.12, 0.05, 0.02, 0.006],
    ):
        v, pr = E.conservative_distribution(steps, L)
        f_c, g_c = E.kelly_on_distribution(v, pr)
        print(
            "T6/T7 L=%s：证书 g_L(0.02)=%.10f，保守分布 E[R]=%.6f，f_c=%.8f，g*=%.10f"
            % (
                L,
                E.step_certificate(0.02, steps, L),
                sum(a * b for a, b in zip(v, pr)),
                f_c,
                g_c,
            )
        )
    print(
        "P4 规范化 [0.3,0.1,0.25,-0.1] →", E.clean_lower_bounds([0.3, 0.1, 0.25, -0.1])
    )
    print(
        "P12 反例：保守分布 {0:0.8, 6:0.2} 的 f_c =",
        E.kelly_on_distribution([0.0, 6.0], [0.8, 0.2])[0],
    )
    grid_p = [0.02, 0.05, 0.10, 0.20, 0.30]
    grid_K = [2, 3, 4, 5, 6, 8, 10, 13, 20, 30, 50, 100, 200]
    for N in (156, 520):
        print(
            "需求曲线（N=%d 注、首达 101 倍概率 ≥1%%、半 Kelly）：" % N,
            E.demand_curve(grid_p, N, 0.01, grid_K),
        )


if __name__ == "__main__":
    main()
