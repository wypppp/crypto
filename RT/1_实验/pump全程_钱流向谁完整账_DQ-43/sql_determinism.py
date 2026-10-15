"""第九轮取数 SQL 的静态护栏；已冻结的统计参照不在此改写。

全链键控制首笔与 ROWS。时间 RANGE 与聚合边的唯一地址对另验。
同时由 K.q 和本机检查拒绝键重复，不能靠补排序掩盖它。
"""

import sqlglot
from sqlglot import exp

CHAIN = {"slot", "txi", "oix", "iix"}


def check(sql):
    tree = sqlglot.parse_one(sql, read="trino")
    for n in tree.walk():
        if isinstance(n, exp.Column) and n.name.lower() == "amount_display":
            raise ValueError("金额不能取浮点 display 列")
        if isinstance(n, exp.Func):
            name = n.name if isinstance(n, exp.Anonymous) else n.sql_name()
            if name.lower().startswith("approx_") or name.lower() in (
                "to_unixtime",
                "time_to_unix",
            ):
                raise ValueError("近似或浮点时间函数")
        if isinstance(n, exp.DataType) and n.sql().upper() in (
            "FLOAT",
            "DOUBLE",
            "REAL",
        ):
            raise ValueError("浮点类型")
        if (
            isinstance(n, exp.Literal)
            and n.is_number
            and ("." in n.this or "e" in n.this.lower())
        ):
            raise ValueError("浮点数值字面量")
        if isinstance(n, exp.Limit):
            raise ValueError("LIMIT 违反取数契约")  # noqa: TRY004 -- SQL 策略值，不是 Python 输入类型
        if isinstance(n, exp.Func) and n.sql_name().lower() in ("min_by", "arg_min"):
            key = n.args.get("expression")
            names = {c.name for c in key.find_all(exp.Column)}
            if (
                not {
                    "evt_block_slot",
                    "evt_tx_index",
                    "evt_outer_instruction_index",
                    "evt_inner_instruction_index",
                }
                <= names
            ):
                raise ValueError("min_by 缺完整唯一键")
    for w in tree.find_all(exp.Window):
        order = w.args.get("order")
        if order is None:
            continue
        names = {c.name for c in order.find_all(exp.Column)}
        spec = w.args.get("spec")
        if spec and spec.args.get("kind") == "RANGE":
            if not isinstance(w.this, exp.Sum) or names != {"ts"}:
                raise ValueError("时间 RANGE 的整数求和契约变了")
        elif isinstance(w.this, exp.RowNumber) or spec:
            part = {c.name for c in w.args.get("partition_by", [])}
            edge_pair = names == {"t0", "from_owner"} and part == {"to_owner"}
            if not CHAIN <= names and not edge_pair:
                raise ValueError("排序缺完整链上键或唯一地址对")
    for order in tree.find_all(exp.Order):
        if isinstance(order.parent, exp.Window):
            continue
        names = {c.name for c in order.find_all(exp.Column)}
        if not (CHAIN | {"kind", "mint"}) <= names and names != {"kind", "a", "b", "x"}:
            raise ValueError("输出排序缺完整唯一键")
    return tree
