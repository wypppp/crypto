"""DQ-43 的 Dune 读取小工具（源自 DQ-20／DQ-26 的 dune_get.py）。

10-14 总控第七轮补 1：密钥只由 paid_guard 读取，本文件不再单独下载（main 已关闭）。
只剩三个函数：get（经 paid_guard.request，付费接口要锁内的批准）、norm（SQL 去空白比较）、page（取一页结果，不重试）。
下载用 run_dune.py，或 dune_get_stream.py --approve=<批准编号>。
"""

import re

import paid_guard as PG

H = PG.H


def get(path, ticket=None):
    """10-14 总控第七轮补 1：经 paid_guard.request（付费接口要锁内的批准），不重试。"""
    return PG.request("GET", path, ticket=ticket)


def norm(sql):
    return re.sub(r"\s+", "", sql)


def page(eid, offset, n, ticket):
    # 10-14 总控第六轮：结果页付费，失败（含 402）不自动重试、不拆页重取，直接停下
    return get(f"/execution/{eid}/results?limit={n}&offset={offset}", ticket)["result"][
        "rows"
    ]


def main():
    raise SystemExit(
        "10-14 总控第七轮：本脚本不再单独下载；用 run_dune.py 或 dune_get_stream.py --approve=<批准编号>"
    )


if __name__ == "__main__":
    main()
