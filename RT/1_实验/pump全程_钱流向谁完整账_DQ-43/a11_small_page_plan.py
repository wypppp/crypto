"""用户覆盖小页禁令后的零费用方案：只读已有缓存，不请求Dune。"""

import hashlib
import json
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

import dune_get_json as J

H = Path(__file__).resolve().parent
PAGE_ROWS = 1000


def fee_budget(size_bytes):
    """继续遵守第十一轮2 credits/十进制MB预算，不利用取整缩减预留。"""
    if not isinstance(size_bytes, int) or size_bytes < 0:
        raise ValueError("字节数须为非负整数")
    return Decimal(size_bytes) * 2 / 1_000_000


def floor_hypothesis(size_bytes):
    return int(fee_budget(size_bytes).to_integral_value(rounding=ROUND_FLOOR))


def offsets(n):
    if not isinstance(n, int) or n < 0:
        raise ValueError("行数须为非负整数")
    return [
        {"offset": i, "limit": min(PAGE_ROWS, n - i)} for i in range(0, n, PAGE_ROWS)
    ]


def main():
    root = H / "raw/dune/A10T_JSON_GZIP.json-pages"
    identity = json.loads((root / "identity.json").read_text())
    cursor, rows = 0, []
    while cursor < identity["rows"]:
        path = root / f"{cursor:012d}.body"
        mark = json.loads(path.with_suffix(".json").read_text())
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != mark["sha256"]:
            raise ValueError("已有缓存哈希不符")
        page, _ = J.decode(body, mark["headers"])
        normalized, cursor = J.validate(page, identity, cursor)
        rows.extend(normalized)
    planned = offsets(len(rows))
    # 测本地规范化行数组的体积，仅用于发现数据形状变化。
    # 数字已变成精确字符串，这不是Dune的正文或计费字节。
    local_sizes = [
        len(
            json.dumps(
                rows[p["offset"] : p["offset"] + p["limit"]],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        )
        for p in planned
    ]
    out = {
        "authority": "用户本轮覆盖第十一轮禁止小页条款；仅零费用方案与预算",
        "scope": "existing A7-06 cached pages only; not a new FIRST/EDGE size calibration",
        "no_network": True,
        "cached_rows": len(rows),
        "page_rows": PAGE_ROWS,
        "planned_pages": planned,
        "local_normalized_row_array_bytes": local_sizes,
        "local_sizes_are_not_platform_billable_bytes": True,
        "hypothetical_free_threshold_decimal_bytes_strictly_below": 500000,
        "budget_credits_per_decimal_MB": 2,
        "execution_estimates_not_recalibrated": {
            "FIRST_r1": 2,
            "FIRST_r2": 2,
            "EDGE": 4,
        },
        "execution_caps_estimate_times_two": {"FIRST_r1": 4, "FIRST_r2": 4, "EDGE": 8},
        "proposed_trial_total_limit_not_approved": 25,
        "next_download_cap_formula": "4 * platform_result_metadata_bytes / 1000000; check actual spent plus this cap before starting",
        "no_old_approval_reactivated": True,
        "no_paid_permission_granted_by_this_plan": True,
        "full_not_approved": True,
    }
    (H / "runs/a11_small_page_plan.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "rows": len(rows),
                "planned_pages": len(planned),
                "last_page_rows": planned[-1]["limit"],
                "largest_local_array_bytes_not_billable_size": max(local_sizes),
                "no_network": True,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
