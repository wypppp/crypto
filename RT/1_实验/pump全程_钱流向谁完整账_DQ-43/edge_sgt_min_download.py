"""未批准执行的导出草稿：删去必被参照跳过的高扇出 G，合并重复 T。

S/T 的全部对手保留，服务节点度数仍由原完整关系计算。
交易所名单仍在本机应用。只减少无效 G 和四列重复关系。
"""

import edge_sgt_integer as I


def build(*args, **kwargs):
    if kwargs.get("smoke"):
        raise ValueError("这是下载草稿，标定仍用已批准的整数 SQL")
    sql = I.build(*args, **kwargs)
    return sql.replace(
        "SELECT kind,a,b,x FROM out",
        "SELECT DISTINCT kind,a,b,x FROM out WHERE kind <> 'G' OR (x IS NOT NULL AND x <= 200)",
    )


def compact_rows(edges):
    # 与 SQL 相同，供已有边的 0 credits 量体积；身份保持完整。
    rows = {}
    for e in edges:
        x = e.get("x")
        if e["kind"] == "G" and (
            x in (None, "") or __import__("decimal").Decimal(str(x)) > 200
        ):
            continue
        r = {k: e.get(k) for k in ("kind", "a", "b", "x")}
        rows.setdefault(tuple(r.values()), r)
    return list(rows.values())
