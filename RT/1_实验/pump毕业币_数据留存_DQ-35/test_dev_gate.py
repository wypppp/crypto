"""dev_gate 的手算预期值测试（10-05）。"""

import csv
import gzip

import dev_gate as g


def test_to_epoch_hand():
    # 2026-10-05 00:00 UTC＝1,791,158,400（与 DQ-37 test_forward 的推算一致）
    assert g.to_epoch("2026-10-05 00:00:00.000 UTC") == 1_791_158_400
    assert g.to_epoch("1791158400.0") == 1_791_158_400
    assert g.CUTOFF_EPOCH == 1_791_158_400


def test_is_dev_created_hand():
    # 2025-10-07 在开发周；2026-06-14 在检验周（DQ-37 weeks.week_class）；2026-10-05 起属前向批次
    assert g.is_dev_created(g.to_epoch("2025-10-07 12:00:00.000 UTC"))
    assert not g.is_dev_created(g.to_epoch("2026-06-14 12:00:00.000 UTC"))
    assert not g.is_dev_created(g.to_epoch("2026-10-05 00:00:00.000 UTC"))


def test_stream_drops_at_parse_hand(tmp_path):
    p = tmp_path / "x.csv.gz"
    with gzip.open(p, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pool", "t", "v"])
        w.writerow(["A", "1791158399", "1"])  # 开发池、10-04 23:59:59：保留
        w.writerow(["A", "1791158400", "2"])  # 开发池、10-05 00:00：丢（R3）
        w.writerow(["B", "1700000000", "3"])  # 非开发池：丢
    rows, drop = g.stream(None, "pool", {"A"}, time_col="t", path=p)
    assert [r["v"] for r in rows] == ["1"] and drop == 2
    assert g.stream(None, "pool", {"A"}, path=tmp_path / "none.csv.gz") == ([], 0)
