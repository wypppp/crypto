#!/usr/bin/env python3
"""DQ-18 F111 ⑥⑦ 用修正版函数重算（10-05；总控第十九轮第五节第 1 条；代码审计第 5 处）。

把 analyze_d.simulate、analyze_d.oracle 换成 analyze_d_v2 的修正版（期末已到期的回款计入现金），其余照原 main() 运行；
原 results/summary.json 由调用方在运行后用 git 恢复，新结果另存 results/summary_v2.json。原 analyze_d.py 不改。
F132：估值期跨过 2026-07-15 的部分仍用不含虚拟报价储备的储备，数字待逐笔重算；本次只修第 5 处。
"""

import shutil

import analyze_d
import analyze_d_v2

analyze_d.simulate = analyze_d_v2.simulate
analyze_d.oracle = analyze_d_v2.oracle

if __name__ == "__main__":
    analyze_d.main()
    shutil.move(
        analyze_d.ROOT / "results" / "summary.json",
        analyze_d.ROOT / "results" / "summary_v2.json",
    )
