"""真实明细复放入口：手算的阶段、首笔成熟买入和映射边界。"""

from s3_real_replay import replay
from test_s3_sql import EMAP, hand


def test_replay_hand_counts_and_equivalence():
    out = replay(hand().detail(), EMAP)
    assert out["N_structure"]["n_coins_w"] == 6
    assert out["N_structure"]["n_coins_w1"] == 1
    assert out["N_structure"]["n_rows_w"] == 15
    assert out["N_structure"]["n_rows_w1"] == 2
    assert out["N_structure"]["n_amm_rows"] == 1
    assert out["diff_sql_vs_reference"] == {}
    assert out["local_double_run_identical"]
    assert out["remove_W1_keeps_selection"]
