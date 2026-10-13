"""校验交叉索引与方向总账的一致性。

用法：python3 -I check_index.py <仓库根目录>

只用标准库。检查三件事：
1. 2_交叉索引_163.csv 与 2b_总账未单列对象.csv 的编号、词表（判定词表 v2.1）与母项；
2. “原始出处”里的仓库路径都存在；
3. 方向总账的状态词只用 8 个、§0 的计数与实际行数一致、
   交叉索引记的“总账状态”与总账当前状态一致（漂移即报错）。
有错误时退出码为 1。
"""

import collections
import csv
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
INDEX = HERE / "2_交叉索引_163.csv"
EXTRA = HERE / "2b_总账未单列对象.csv"

LEDGER_STATES = ["活跃", "被动前向", "实现关闭", "资源停止", "无效检验", "未测", "暂缓", "只描述"]
VOCAB = {
    "单元类型": {"假说", "实现检验", "描述测量", "基础设施", "检索筛查", "方法治理"},
    "认识状态": {
        "未测",
        "测不到",
        "测量无效",
        "局部负·强",
        "局部负·弱",
        "局部·未决",
        "局部正·待确认",
        "描述",
        "停止·非证据",
        "非方向",
        "排除",
    },
    "证据性质": {"案头", "内部描述", "内部开发", "内部冻结检验", "前向待开", "外部+内部描述", "描述", "无"},
    "独立核验": {"无", "同源复算", "部分复算", "部分原件重建"},
    "基准": {"绝对", "相对", "不适用"},
    "描述性产出": {"本方测量", "案头资料", "无"},
}
# 词表 v2.1：问题类型多值，按严重度固定排序（P6）；基准只在结果类状态填写（S6）
ISSUE_ORDER = ["错误关闭", "错误归因", "遗漏", "状态误标", "证据栏误标", "重复", "标签混用", "无"]
RESULT_STATES = {"局部负·强", "局部负·弱", "局部·未决", "局部正·待确认", "测量无效"}
STAGES = {"S0", "S1", "S2", "S3", "S4", "SX", "S*"}
CONSTRAINTS = {
    "无",
    "违法",
    "监管受限",
    "平台条款禁止",
    "身份或地域资格不足",
    "资金不足",
    "技术不可实现",
    "信息不可获得",
    "经济上不值得投入",
    "伦理上不接受",
    "范围外",
}
EXTRA_KINDS = {"合同未入行", "聚合压缩", "依赖项不计数", "对象级缺口"}
ROW_START = "| 编号与名称 | 出处 | 状态"


def split_top(text):
    """按顶层“；”切分，括号内的“；”不切。"""
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch == "（":
            depth += 1
        elif ch == "）":
            depth -= 1
        if ch == "；" and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def check_index(rows, root, errors):
    ids = [r["索引号"] for r in rows]
    if len(rows) != 163:
        errors.append(f"交叉索引应有 163 行，实际 {len(rows)}")
    if ids != [f"K{i:03d}" for i in range(1, len(rows) + 1)]:
        errors.append("索引号不是从 K001 起连续编号")
    lines = [r["总账行号"] for r in rows]
    if len(set(lines)) != len(lines):
        errors.append("总账行号有重复")
    known = set(ids)
    for r in rows:
        k = r["索引号"]
        for col, allowed in VOCAB.items():
            if r[col] not in allowed:
                errors.append(f"{k} {col} 不在词表：{r[col]}")
        if r["总账状态"] not in LEDGER_STATES:
            errors.append(f"{k} 总账状态不在 8 个词内：{r['总账状态']}")
        if r["价值流"].split("（")[0] not in {f"V{i}" for i in range(10)}:
            errors.append(f"{k} 价值流不在词表：{r['价值流']}")
        issues = r["问题类型"].split("；")
        if any(p not in ISSUE_ORDER for p in issues) or ("无" in issues and len(issues) > 1):
            errors.append(f"{k} 问题类型不在词表：{r['问题类型']}")
        elif issues != sorted(issues, key=ISSUE_ORDER.index) or len(set(issues)) != len(issues):
            errors.append(f"{k} 问题类型没有按严重度排序或有重复：{r['问题类型']}")
        if (r["基准"] != "不适用") != (r["认识状态"] in RESULT_STATES):
            errors.append(f"{k} 基准与认识状态不匹配（S6）：{r['认识状态']}／{r['基准']}")
        for s in r["生命周期阶段"].split("-"):
            if s not in STAGES:
                errors.append(f"{k} 生命周期阶段不在词表：{r['生命周期阶段']}")
        for part in split_top(r["约束类型"]):
            if part.split("（")[0] not in CONSTRAINTS:
                errors.append(f"{k} 约束类型不在词表：{part}")
        parent = r["母项"]
        if parent and (parent not in known or parent == k):
            errors.append(f"{k} 母项无效：{parent}")
        if root is not None:
            for p in r["原始出处"].split(" ; "):
                if p.startswith("RT/") and not (root / p).exists():
                    errors.append(f"{k} 原始出处不存在：{p}")


def check_extra(rows, known, errors):
    seen = set()
    for r in rows:
        k = r["编号"]
        if k in seen:
            errors.append(f"2b 编号重复：{k}")
        seen.add(k)
        if r["类别"] not in EXTRA_KINDS:
            errors.append(f"2b {k} 类别不在词表：{r['类别']}")
        for h in filter(None, r["挂靠索引号"].split(";")):
            if h not in known:
                errors.append(f"2b {k} 挂靠索引号不存在：{h}")


def parse_ledger(path):
    rows, in_table = {}, False
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith(ROW_START):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("| "):
            cells = line[2:].rstrip(" |").split(" | ")
            word = next((w for w in LEDGER_STATES if cells[2].replace("**", "").startswith(w)), None)
            rows[no] = word
            continue
        in_table = False
    return rows


def check_ledger(root, index_rows, errors):
    path = root / "RT" / "方向总账.md"
    if not path.exists():
        errors.append(f"找不到 {path}")
        return
    ledger = parse_ledger(path)
    bad = [n for n, w in ledger.items() if w is None]
    if bad:
        errors.append(f"总账有 {len(bad)} 行状态词不在 8 个词内，行号 {bad[:10]}")
    counts = collections.Counter(w for w in ledger.values() if w)
    head = re.search(r"共 (\d+) 行[^：]*：(.+?)。", path.read_text(encoding="utf-8"))
    if head:
        if int(head.group(1)) != len(ledger):
            errors.append(f"总账 §0 写 {head.group(1)} 行，实际 {len(ledger)} 行")
        for word, n in re.findall(r"(\S+?) (\d+)", head.group(2)):
            word = word.lstrip("、")
            if word in LEDGER_STATES and counts[word] != int(n):
                errors.append(f"总账 §0 写 {word} {n}，实际 {counts[word]}")
    for r in index_rows:
        no = int(r["总账行号"])
        if ledger.get(no) != r["总账状态"]:
            errors.append(f"{r['索引号']} 漂移：交叉索引记“{r['总账状态']}”，总账第 {no} 行现为“{ledger.get(no)}”")
    print(f"总账：{len(ledger)} 行；" + "、".join(f"{w} {counts[w]}" for w in LEDGER_STATES))


def main(argv):
    root = pathlib.Path(argv[1]).resolve() if len(argv) > 1 else None
    errors = []
    rows = read_csv(INDEX)
    check_index(rows, root, errors)
    check_extra(read_csv(EXTRA), {r["索引号"] for r in rows}, errors)
    if root is not None:
        check_ledger(root, rows, errors)
    for col in ("单元类型", "认识状态", "问题类型"):
        c = collections.Counter(r[col] for r in rows)
        print(f"{col}：" + "、".join(f"{k} {v}" for k, v in c.most_common()))
    if errors:
        print(f"\n发现 {len(errors)} 处问题：")
        for e in errors:
            print(" -", e)
        return 1
    print("\n通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
