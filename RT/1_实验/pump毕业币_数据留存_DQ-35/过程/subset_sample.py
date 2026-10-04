#!/usr/bin/env python3
"""DQ-35 v2.1 样本入库（10-04）：把 raw/dune 下的扩大样本裁成可入库的子集，放到 samples/。

python 过程/subset_sample.py <逐笔原始标签> <上限事件数> <SQL 结果标签...>
- 母体取逐笔原始文件的 'C' 行，先剔除曲线创建在 DQ-37 检验周的池（入口过滤，与对照脚本相同），
  再按池地址字典序依次纳入，累计事件数不超过上限（至少 1 个池）；'X' 行（排除计数）原样保留。
- 各 SQL 结果文件（B、P、L 层）只保留这些池的行；M 层（单行计数）原样拷贝。
- 文件名加后缀 _sub；子集上 M 层计数与 'C' 行不再相等，对照报告以全量版为准（runs/*_compare.md），子集供独立复算其余各项。
"""

import csv
import gzip
import sys
from pathlib import Path

H = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(H))
from compare_sample_v21 import dev_week  # noqa: E402

RAW = H / "raw" / "dune"
OUT = H / "samples"


def rows(label):
    with gzip.open(RAW / ("%s.csv.gz" % label), "rt", newline="") as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)


def write(label, cols, rs):
    with gzip.open(OUT / ("%s_sub.csv.gz" % label), "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rs)


def main():
    rawlab, cap, labs = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
    cols, raw = rows(rawlab)
    key = "ev" if "ev" in cols else "kind"
    idc = "pool" if "pool" in cols else "mint"
    cre = "q_user" if key == "ev" else "qa"
    crow = [r for r in raw if r[key] == "C" and dev_week(float(r[cre]))]
    n_ev = {}
    for r in raw:
        if r[key] not in ("C", "X"):
            n_ev[r[idc]] = n_ev.get(r[idc], 0) + 1
    keep, tot = set(), 0
    for r in sorted(crow, key=lambda r: r[idc]):
        k = n_ev.get(r[idc], 0)
        if keep and tot + k > cap:
            continue
        keep.add(r[idc])
        tot += k
    write(rawlab, cols, [r for r in raw if r[key] == "X" or r[idc] in keep])
    for lab in labs:
        c2, rs = rows(lab)
        if len(rs) == 1 and idc not in c2:  # M 层
            write(lab, c2, rs)
            continue
        k2 = "pool" if "pool" in c2 else "mint"
        write(lab, c2, [r for r in rs if r[k2] in keep])
    print(
        "%s：纳入 %d 个池（共 %d 个开发周池），事件 %d"
        % (rawlab, len(keep), len(crow), tot)
    )


if __name__ == "__main__":
    main()
