"""rule_window_infer 的手算预期值测试（10-06 v2；含 GPT 批 1b B 的三簇非单调反例）。"""

import itertools
import math

import numpy as np

import rule_window_infer as R


def test_cr1_cr2_hand():
    # y = 1,2,3,10,4，簇 a={1,2}、b={3,10,4}；n=5，均值 4，残差 −3,−2,−1,6,0；簇和 a −5、b +5
    y = [1, 2, 3, 10, 4]
    g = ["a", "a", "b", "b", "b"]
    gi, G = R._groups(g)
    # CR1：G/(G−1)·Σs²/n² = 2·(25+25)/25 = 4 → 2
    assert abs(R.cr1_se(y, gi, G) - 2.0) < 1e-12
    # CR2：a 簇 −5/√(1−2/5)，b 簇 5/√(1−3/5)；(25/0.6 + 25/0.4)/25 → 2.041241
    assert abs(R.cr2_se(y, g) - math.sqrt((25 / 0.6 + 25 / 0.4) / 25)) < 1e-12


def test_bm_df_hand():
    # 等大的簇：G'G＝c²m(I − J/G)，非零特征值都是 c²m、共 G−1 个 → df＝G−1
    g = np.repeat(np.arange(6), 10)
    assert abs(R.bm_df(g) - 5.0) < 1e-9
    # 规模不等时自由度变小
    g2 = np.repeat(np.arange(6), [100, 2, 2, 2, 2, 2])
    assert R.bm_df(g2) < 5.0
    # 有效簇数：等大时等于 G
    assert abs(R.effective_clusters(g) - 6.0) < 1e-12


def test_wcr_pvalue_two_singletons_hand():
    # 两个单元素簇 y=(1,3)、μ0=0：t = (a+b)/|a−b| = 2；自助 t* = (w1·1 + w2·3)/|w1·1 − w2·3|。穷举 36 种权重
    ge = 0
    for w1, w2 in itertools.product(R.WEBB, repeat=2):
        d = abs(w1 - 3 * w2)
        ts = (w1 + 3 * w2) / d if d > 0 else 0.0
        ge += ts >= 2 - 1e-12
    assert abs(R.wcr_pvalue([1, 3], ["a", "b"], 0.0) - (1 + ge) / 37) < 1e-12


def test_gpt_three_cluster_nonmonotone_counterexample():
    # GPT 复算证据 audit_b_edges.json 第 1 例：μ0＝−0.0538 时 p＝0.2028（>0.2，被接受），旧二分法返回 +0.0237
    ng = [58, 163, 109]
    vals = [-0.3051232980125395, 1.8130407228147216, 0.21026510297521808]
    y = np.repeat(vals, ng)
    g = np.repeat(np.arange(3), ng)
    assert R.wcr_pvalue(y, g, -0.05381090770202872) > 0.2
    r = R.wcr_lower(y, g, level=0.8, n_grid=2001)
    assert r["status"] == "ok" and r["lower"] <= -0.0538
    assert r["nonmonotone"] is True


def test_zero_variance_undetermined():
    y = [0.1] * 12
    g = np.repeat(np.arange(4), 3)
    out = R.lower_bound(y, g)
    assert out["status"] == "undetermined" and out["conservative"] is None


def test_lower_bound_reasonable():
    rng = np.random.default_rng(1)
    g = np.repeat(np.arange(12), 20)
    y = 0.02 + rng.normal(0, 0.1, 12)[g] + rng.normal(0, 0.2, len(g))
    assert R.wcr_pvalue(y, g, -0.5, B=999) < 0.05
    assert R.wcr_pvalue(y, g, 0.5, B=999) > 0.95
    lb = R.lower_bound(y, g, level=0.8, B=999)
    assert lb["status"] == "ok"
    assert (
        lb["conservative"]
        == min(lb["wcr"]["lower"], lb["cr2"]["lower"])
        < float(np.mean(y))
    )


def test_concurrent_and_blocks_hand():
    # 同起同止两仓：f＝0.1，R＝3 与 0 → log(1 + 0.1·2 + 0.1·(−1)) = log(1.1)
    out = R.concurrent_log_growth([(0, 7, 3.0), (0, 7, 0.0), (1, 8, 2.0)], 0.1)
    assert (
        abs(out[0][2] - math.log(1.1)) < 1e-12
        and abs(out[1][2] - math.log(1.1)) < 1e-12
    )
    assert R.block_ids([0, 1, 2, 3, 4], 2) == [0, 0, 1, 1, 2]
    # 正负交替的周序列：各阶自相关都显著 → 块长取上限＋1
    assert R.choose_block_len([1, -1] * 10, max_len=4) == 5
