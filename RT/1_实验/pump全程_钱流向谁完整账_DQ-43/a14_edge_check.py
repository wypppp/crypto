"""完成下载后单独运行；只核 EDGE 质量及 W 种子实体集中度。"""

import argparse
import csv
import gzip
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import a14_full as F
from wm2_identity_v5 import StrongRows, size_bins

H = Path(__file__).resolve().parent
ADDRESS = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,44}\Z")


class Rows:
    def __init__(self, path):
        self.path = path

    def __iter__(self):
        with gzip.open(self.path, "rt", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != ["kind", "a", "b", "x"]:
                raise ValueError("EDGE 列名或次序不符")
            yield from reader


def quality(rows, expected_rows):
    kinds, previous, n = Counter(), None, 0
    for row in rows:
        kind, a, b, x = (row[k] for k in ("kind", "a", "b", "x"))
        if kind not in ("S", "G", "T", "V") or not ADDRESS.fullmatch(a or ""):
            raise ValueError("EDGE 类型或首端点不合法")
        if kind == "V":
            if b or x:
                raise ValueError("种子行的 b/x 须为空")
        elif not ADDRESS.fullmatch(b or "") or a == b:
            raise ValueError("EDGE 第二端点不合法或自环")
        if kind == "G":
            if not x.isdigit() or not 0 <= int(x) <= 200:
                raise ValueError("G 扇出缺失、非整数或超限")
        elif x:
            raise ValueError("S/T/V 的 x 须为空")
        # SQL ORDER BY kind,a,b,x；NULL 在末。完整次序也能查出重复。
        key = kind, a, b, x == "", 0 if x == "" else int(x)
        if previous is not None and key <= previous:
            raise ValueError("EDGE 重复行或全局排序改变")
        previous = key
        kinds[kind] += 1
        n += 1
    if n != expected_rows or not kinds["V"]:
        raise ValueError("EDGE 总行数不符或种子名册缺失")
    return {"rows": n, "kind_rows": dict(kinds), "quality_passed": True}


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label")
    args = parser.parse_args()
    if Path(args.label).name != args.label:
        raise ValueError("标签只能是文件名")
    label = args.label
    completed = json.loads((H / "runs" / f"{label}_completed.json").read_text())
    transport = json.loads((H / "runs" / f"{label}_transport.json").read_text())
    meta = completed["result_metadata"]
    for key in ("execution_id", "query_id", "sql_sha256"):
        if str(completed[key]) != str(transport[key]):
            raise ValueError("完成与下载身份不一致")
    if transport["rows"] != meta["row_count"]:
        raise ValueError("下载行数不符")
    path = H / "raw/dune" / f"{label}.csv.gz"
    rows = Rows(path)
    out = quality(rows, meta["row_count"])
    cex_path = H.parent / "pump曲线_资金关系可构造性_DQ-21/raw/dune/Q_cex_all.csv.gz"
    with gzip.open(cex_path, "rt", newline="") as f:
        cex = {r["address"] for r in csv.DictReader(f)}
    main_distribution = F.concentration(rows, cex)
    strong_distribution = F.concentration(StrongRows(rows, cex), cex)
    for distribution in (main_distribution, strong_distribution):
        distribution["multiwallet_size_bins_with_W_seeds"] = size_bins(
            distribution["multiwallet_size_histogram_with_W_seeds"]
        )
        distribution["all_multiwallet_size_bins"] = size_bins(
            distribution["all_multiwallet_size_histogram"]
        )
    out.update(
        concentration=main_distribution,
        strong_sensitivity_concentration=strong_distribution,
        entity_threshold_passed=main_distribution["concentration_passed"],
        new_paid_execution_allowed=False,
        raw_sha256=sha(path),
        cex_sha256=sha(cex_path),
        execution_id=completed["execution_id"],
        sql_sha256=completed["sql_sha256"],
        s3_statistics_computed=False,
    )
    target = H / "runs" / f"{label}_entity_gate.json"
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
