#!/usr/bin/env python3
"""DQ-39 S1 报告：raw/s1_results.json → S1_结果.md（10-06；读法按 S1_预登记.md 第 6 节，写死）。"""

import json
from pathlib import Path

H = Path(__file__).resolve().parent
NAMES = {
    "V1": "时间＋链上文本（主）",
    "V2": "时间＋错位文本",
    "V3": "时间＋同周打乱文本",
    "V4": "只用时间",
}


def has0(ci):
    return ci[0] <= 0 <= ci[1]


def f(x, d=3):
    return "—" if x is None else ("%." + str(d) + "f") % x


def main():
    r = json.loads((H / "raw" / "s1_results.json").read_text())
    ci = r["ap_diff_ci95"]
    close = has0(ci["V1-V2"]) and has0(ci["V1-V3"])
    no_inc = has0(ci["V1-V4"])
    L = ["# DQ-39 SOLMEMES S1：三种文本对照（结果，10-06）", ""]
    L.append(
        "> 预登记：[S1_预登记.md](S1_预登记.md)，读结果前提交于 `7e23e1b9`。脚本 `s1_run.py`（独立虚拟环境），报告 `s1_report.py`。"
    )
    L.append(
        "> **论文口径参考，不作通过依据。** 分钟均价不是可成交价；收益只按论文口径算。证据层级：开发（DQ-37 开发周）。"
    )
    L.append("")
    L.append("## 1. 结论")
    L.append("")
    if close:
        L.append(
            "三种文本的结果接近：V1−V2 与 V1−V3 的 AP 差，95% 区间都含 0。按总控第五节，这说明文本没有带来币本身的信息，S2 的文本特征降低优先级。"
        )
    else:
        L.append(
            "三种文本的结果不全接近：V1−V2 或 V1−V3 的 AP 差，95% 区间不含 0。链上正确文本带来了可分辨的差别，S2 的文本特征保留原优先级。"
        )
    L.append("")
    if no_inc:
        L.append("V1−V4 的区间含 0：在这份数据上，文本在时间特征之外没有可分辨的增量。")
    else:
        L.append("V1−V4 的区间不含 0：文本在时间特征之外有可分辨的增量（方向见下表）。")
    L.append("")
    aps = [r["results"][v]["AP"] for v in ("V1", "V2", "V3", "V4")]
    L.append(
        "四个变体的 AP 在 %s～%s 之间，只比随机分类器（测试集正类比例 %s）高 %s～%s。只用时间特征也只略高于随机。"
        % (
            f(min(aps)),
            f(max(aps)),
            f(r["pos_rate_test"]),
            f(min(aps) - r["pos_rate_test"]),
            f(max(aps) - r["pos_rate_test"]),
        )
    )
    L.append("")
    eq = r["ipfs_vs_claimed_desc_equal"]
    L.append(
        "IPFS 上按 `token_uri` 取到的描述，与数据里认领到本币的元数据块：两者都有的 %d 个币里一致 %d 个。这验证了 S0b 的结论：元数据块整体错位，`token_uri` 跟着本行 token。"
        % (sum(eq.values()), eq.get("True", 0))
    )
    L.append("")
    L.append("## 2. 样本")
    L.append("")
    L.append("| 项 | 数 |")
    L.append("|---|---|")
    L.append("| 开发 token | %d |" % r["n_dev"])
    L.append("| 标签缺失（第 0 或第 14 分钟均价为空） | %d |" % r["n_missing_label"])
    L.append(
        "| 训练（2025-04-07 之前创建） | %d，正类比例 %s |"
        % (r["n_train"], f(r["pos_rate_train"]))
    )
    L.append(
        "| 测试（2025-04-07 周创建） | %d，正类比例 %s |"
        % (r["n_test"], f(r["pos_rate_test"]))
    )
    L.append(
        "| 正确文本的描述来源 | %s |"
        % "、".join("%s %d" % (k, v) for k, v in r["desc_source"].items())
    )
    L.append(
        "| IPFS 描述与数据里认领到的元数据块一致（两者都有时） | %s |"
        % "、".join(
            "%s %d" % ({"True": "一致", "False": "不一致"}[k], v)
            for k, v in r["ipfs_vs_claimed_desc_equal"].items()
        )
    )
    L.append(
        "| 模型 | ModernBERT-base（修订 `8949b909`），权重 sha256 `%s…` |"
        % r["model_sha256"][:16]
    )
    L.append("")
    L.append("## 3. 测试集结果（阈值 0.5）")
    L.append("")
    L.append(
        "| 变体 | AP | 准确率 | 精确率 | 召回率 | 交易数 | 平均 ROI15 | 平均调整 ROI15 | 置换 p |"
    )
    L.append("|---|---|---|---|---|---|---|---|---|")
    for v in ("V1", "V2", "V3", "V4"):
        x = r["results"][v]
        L.append(
            "| %s %s | %s | %s | %s | %s | %d | %s | %s | %s |"
            % (
                v,
                NAMES[v],
                f(x["AP"]),
                f(x["acc"]),
                f(x["precision"]),
                f(x["recall"]),
                x["trades"],
                f(x.get("roi15_mean")),
                f(x.get("roi_adj_mean")),
                f(x.get("perm_p")),
            )
        )
    L.append("")
    L.append("测试集正类比例 %s，即随机分类器的 AP 约为此值。" % f(r["pos_rate_test"]))
    L.append("")
    L.append("## 4. AP 差（测试集按 token 自助 1,000 次，95% 区间）")
    L.append("")
    L.append("| 差 | 区间 | 含 0 |")
    L.append("|---|---|---|")
    for k in ("V1-V2", "V1-V3", "V1-V4"):
        L.append(
            "| %s | [%s, %s] | %s |"
            % (k, f(ci[k][0]), f(ci[k][1]), "是" if has0(ci[k]) else "否")
        )
    L.append("")
    L.append("## 5. 局限")
    L.append("")
    L.append(
        "- 只有一个开发周做测试（04-07 周），论文的测试周 04-14～04-19 是检验周，没有碰。"
    )
    L.append("- 标签用分钟均价，不是我方可成交价；调整收益只是论文口径。")
    L.append("- 只用了 ModernBERT-base，没有做论文的 OpenAI 向量与调参版本。")
    L.append(
        "- 结果只说明这份发布数据与这条管线，不说明链上文本在 S2 的可成交口径下有没有用。"
    )
    out = H / "S1_结果.md"
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
