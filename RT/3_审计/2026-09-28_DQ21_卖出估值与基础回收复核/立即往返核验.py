"""审核核验：旧曲线卖出式是否“方向错误”。0 credits，只读 H1 已缓存的 Helius 原件。

python 立即往返核验.py → checks/立即往返核验.json
找链上同一钱包“买入后紧接着卖出同样数量、中间无他人成交”的曲线交易对，比较两种反事实估值：
- 旧式（S0/S1 旧 SQL）：把我方仓位留在曲线里再卖回，= x*y/(y-q) - x，(x, y) 为我方买入前状态；
- 新式（F116“修正”）：卖进不含我方仓位的状态，= x*q/(y+q)。
链上卖出所得 sol_amount 是真值。
"""
import glob
import gzip
import json
import statistics as st
import sys
from pathlib import Path

H = Path(__file__).resolve().parent
D21 = H.parents[1] / "1_实验" / "pump曲线_资金关系可构造性_DQ-21"
H1 = H.parents[1] / "1_实验" / "pump曲线_案例时序与点火跟随_H1" / "raw"
sys.path.insert(0, str(D21))
from evt_decode import iter_events  # noqa: E402


def main():
    ev = {}
    for f in sorted(glob.glob(str(H1 / "full24h_*.jsonl.gz"))) + sorted(glob.glob(str(H1 / "ext_*.jsonl.gz"))):
        for line in gzip.open(f, "rt"):
            x = json.loads(line)
            if x["meta"].get("err"):
                continue
            for e in iter_events(x):
                if e["name"] == "TradeEvent":
                    e.update(slot=x["slot"], txi=x.get("transactionIndex", 0), sig=x["transaction"]["signatures"][0])
                    ev[(e["sig"], e["oix"], e["iix"])] = e
    ev = sorted(ev.values(), key=lambda e: (e["mint"], e["slot"], e["txi"], e["oix"], e["iix"]))
    pairs = []
    for a, b in zip(ev, ev[1:]):
        if a["mint"] == b["mint"] and a["is_buy"] and not b["is_buy"] and a["user"] == b["user"] \
                and a["token_amount"] == b["token_amount"]:
            x0 = a["virtual_sol_reserves"] - a["sol_amount"]
            y0 = a["virtual_token_reserves"] + a["token_amount"]
            q = a["token_amount"]
            pairs.append(dict(mint=a["mint"], buy_sol=a["sol_amount"], sell_sol=b["sol_amount"],
                              old=x0 * y0 / (y0 - q) - x0, new=x0 * q / (y0 + q)))
    err = lambda k: [abs(p["sell_sol"] - p[k]) / p["sell_sol"] for p in pairs]
    out = {"pairs": len(pairs), "coins": len({p["mint"] for p in pairs}),
           "old_rel_err_median": st.median(err("old")), "old_rel_err_max": max(err("old")),
           "new_rel_err_median": st.median(err("new")), "new_rel_err_max": max(err("new")),
           "sell_over_buy_sol_median": st.median(p["sell_sol"] / p["buy_sol"] for p in pairs),
           "examples": pairs[:5]}
    (H / "checks" / "立即往返核验.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in out.items() if k != "examples"}, indent=1))


if __name__ == "__main__":
    main()
