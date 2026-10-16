"""第十四轮工程闸门；只做取数与实体集中度，不计算 S3 的 N/C/G。"""

from collections import Counter, defaultdict
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


def without_service_nodes(sql):
    """待用户选择才可付费重跑：在原完整边上计算度数，再删必跳过的边。"""
    if not sql.endswith(EDGE_END):
        raise ValueError("原 EDGE 尾部改变，须重新核查派生")
    return (
        sql[: -len(EDGE_END)]
        + ",\nsgt_export AS (\n"
        + EDGE_END.split("\n\nORDER BY")[0]
        + "),\ncomplete_neighbors AS (\n"
        + " SELECT kind,a AS wallet,b AS neighbor FROM sgt_export WHERE kind IN ('S','T')\n"
        + " UNION\n SELECT kind,b,a FROM sgt_export WHERE kind IN ('S','T')\n"
        + "),\ncomplete_hubs AS (\n"
        + " SELECT kind,wallet FROM complete_neighbors GROUP BY kind,wallet\n"
        + " HAVING count(DISTINCT neighbor)>200\n)\n"
        + "SELECT e.kind,e.a,e.b,e.x FROM sgt_export e\n"
        + "LEFT JOIN complete_hubs ha ON ha.kind=e.kind AND ha.wallet=e.a\n"
        + "LEFT JOIN complete_hubs hb ON hb.kind=e.kind AND hb.wallet=e.b\n"
        + "WHERE e.kind='G' OR (ha.wallet IS NULL AND hb.wallet IS NULL)\n"
        + "UNION ALL\n"
        + "SELECT 'V',usr,CAST(NULL AS varchar),CAST(NULL AS bigint) FROM seed\n"
        + "ORDER BY kind,a,b,x\n"
    )


def service_reduction_reference(rows):
    """可审 SQL 的独立本机操作；不使用任何 W+1 信息。"""
    neighbors = defaultdict(set)
    for row in rows:
        if row["kind"] in ("S", "T"):
            neighbors[row["kind"], row["a"]].add(row["b"])
            neighbors[row["kind"], row["b"]].add(row["a"])
    hubs = {key for key, values in neighbors.items() if len(values) > 200}
    return [
        row
        for row in rows
        if row["kind"] not in ("S", "T")
        or not ({(row["kind"], row["a"]), (row["kind"], row["b"])} & hubs)
    ]


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

    if iter(rows) is rows:
        raise ValueError("图输入须能重复读取，禁止耗尽一次性迭代器")
    seeds = set()
    for row in rows:
        if row["kind"] == "V":
            if not row["a"] or row["a"] in seeds or row["b"] or row["x"]:
                raise ValueError("种子名册为空、重复或列格式有误")
            seeds.add(row["a"])
        elif row["kind"] not in ("S", "G", "T"):
            raise ValueError("未知 EDGE 行类型")
    if not seeds:
        raise ValueError("缺少完整 W 种子，不能计算集中度")

    class Edges:
        def __iter__(self):
            return (row for row in rows if row["kind"] != "V")

    emap, _ = REF.entities(Edges(), set(cex))
    counts = Counter(emap.get(seed, seed) for seed in seeds)
    full_sizes = Counter(emap.values())
    top_entities = sorted(
        counts,
        key=lambda entity: (-counts[entity], -full_sizes.get(entity, 1), entity),
    )[:10]
    top = [counts[entity] for entity in top_entities]
    n = len(seeds)
    sizes_with_seeds = [full_sizes[e] for e in counts if full_sizes[e] > 1]
    return {
        "W_seed_wallets": n,
        "largest_entity_W_seed_wallets": top[0],
        "largest_entity_W_seed_fraction": top[0] / n,
        "top10_W_seed_wallets": top,
        "top10_W_seed_fractions": [v / n for v in top],
        "top10_W_seed_fraction_sum": sum(top) / n,
        "top10_total_wallets": [full_sizes.get(entity, 1) for entity in top_entities],
        "all_multiwallet_entities": len(full_sizes),
        "multiwallet_entities_with_W_seeds": len(sizes_with_seeds),
        "singlewallet_entities_with_W_seeds": sum(full_sizes[e] <= 1 for e in counts),
        "multiwallet_size_histogram_with_W_seeds": dict(Counter(sizes_with_seeds)),
        "all_multiwallet_size_histogram": dict(Counter(full_sizes.values())),
        "concentration_passed": 20 * top[0] <= n and 20 * sum(top) <= 3 * n,
    }
