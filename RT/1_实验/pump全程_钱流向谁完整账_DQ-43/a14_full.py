"""第十四轮工程闸门；只做取数与实体集中度，不计算 S3 的 N/C/G。"""

from collections import Counter
from decimal import Decimal

EDGE_END = (
    "SELECT DISTINCT kind,a,b,x FROM out WHERE kind <> 'G' "
    "OR (x IS NOT NULL AND x <= 200)\n\nORDER BY kind,a,b,x\n"
)


def with_seeds(sql):
    """保持原 S/G/T 导出不变；追加完整 W 种子，包括孤立钱包。"""
    if not sql.endswith(EDGE_END):
        raise ValueError("原 EDGE 尾部改变，须重新核查派生")
    return (
        sql[: -len(EDGE_END)]
        + ",\nsgt_export AS (\n"
        + EDGE_END.split("\n\nORDER BY")[0]
        + ")\nSELECT kind,a,b,x FROM sgt_export\nUNION ALL\n"
        + "SELECT 'V',usr,CAST(NULL AS varchar),CAST(NULL AS bigint) FROM seed\n"
        + "ORDER BY kind,a,b,x\n"
    )


def expected_gate(expected, cap):
    """第十四轮上限必须等于预登记预计的两倍。"""
    try:
        expected, cap = Decimal(str(expected)), Decimal(str(cap))
    except ArithmeticError as exc:
        raise ValueError("缺少有效的预计费用") from exc
    if not expected.is_finite() or expected <= 0 or cap != 2 * expected:
        raise ValueError("执行上限须为有限正预计的两倍")
    return expected


def metadata_gate(metadata, seconds_per_page=4):
    """只读状态元数据；一千万行之上不得进入下载。"""
    rows, size = metadata.get("row_count"), metadata.get("result_set_bytes")
    if any(type(v) is not int or v <= 0 for v in (rows, size)):
        raise ValueError("结果行数或体积缺失、为零或非整数")
    pages = (rows + 999) // 1000
    return {
        "rows": rows,
        "result_set_bytes": size,
        "pages_1000": pages,
        "download_hours_at_4_seconds_per_page": pages * seconds_per_page / 3600,
        "download_allowed_by_row_gate": rows <= 10_000_000,
        "includes_seed_roster": True,
    }


def concentration(rows, cex=()):
    """分母只用完整 W 种子；代表与成员来自冻结 entities()。"""
    import s3_ref as REF

    seeds, edges = set(), []
    for row in rows:
        if row["kind"] == "V":
            if not row["a"] or row["a"] in seeds or row["b"] or row["x"]:
                raise ValueError("种子名册为空、重复或列格式有误")
            seeds.add(row["a"])
        elif row["kind"] in ("S", "G", "T"):
            edges.append(row)
        else:
            raise ValueError("未知 EDGE 行类型")
    if not seeds:
        raise ValueError("缺少完整 W 种子，不能计算集中度")
    emap, _ = REF.entities(edges, set(cex))
    counts = Counter(emap.get(seed, seed) for seed in seeds)
    top = sorted(counts.values(), reverse=True)[:10]
    n = len(seeds)
    full_sizes = Counter(emap.values())
    sizes_with_seeds = [full_sizes[e] for e in counts if full_sizes[e] > 1]
    return {
        "W_seed_wallets": n,
        "largest_entity_W_seed_wallets": top[0],
        "largest_entity_W_seed_fraction": top[0] / n,
        "top10_W_seed_wallets": top,
        "top10_W_seed_fractions": [v / n for v in top],
        "top10_W_seed_fraction_sum": sum(top) / n,
        "multiwallet_entities_with_W_seeds": len(sizes_with_seeds),
        "multiwallet_size_histogram_with_W_seeds": dict(Counter(sizes_with_seeds)),
        "all_multiwallet_size_histogram": dict(Counter(full_sizes.values())),
        "concentration_passed": 20 * top[0] <= n and 20 * sum(top) <= 3 * n,
    }
