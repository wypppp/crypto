"""DQ-21 R0：触发的集中度与首次可观察时刻（09-27 复核要求）。python concentration_r0.py → results/r0_concentration.json"""
import collections
import json
from pathlib import Path

import pandas as pd

H = Path(__file__).resolve().parent


def main():
    C = pd.read_csv(H / "results" / "all_coins.csv")
    W = pd.read_csv(H / "results" / "all_wallets.csv")
    S = pd.read_csv(H / "sample.csv")
    st = S[S.stratum.isin(["random", "winner", "matched"])].drop_duplicates("mint").set_index("mint").stratum
    C["stratum"] = C.mint.map(st)
    C = C[C.stratum.notna()]
    C["day"] = pd.to_datetime(C.t0, unit="s").dt.date.astype(str)
    out = {}
    for mode in ("strict", "lenient"):
        trig = C[C[f"trigger_{mode}"].fillna(False).astype(bool)]
        fund = collections.Counter()
        for r in trig.itertuples():
            w = W[W.mint == r.mint]
            pf = w[f"pf_{mode}"]
            cpf = getattr(r, f"creator_pf_{mode}")
            g = w[pf.notna() & (pf != "service")].groupby(f"pf_{mode}").size()
            fs = set(g[g >= 2].index)
            if getattr(r, f"V1n_{mode}") > 0:
                if w.direct_creator_link.any() or (pf == r.creator).any():
                    fs.add("creator:" + r.creator)
                if isinstance(cpf, str) and cpf != "service" and (pf == cpf).any():
                    fs.add(cpf)
            for f in fs:
                fund[f] += 1
        top = [c for _, c in fund.most_common(10)]
        first = trig[[f"V1_first_s_{mode}", f"V2_first_s_{mode}"]].min(axis=1)
        out[mode] = {"triggered": int(len(trig)), "by_stratum": trig.stratum.value_counts().to_dict(),
                     "distinct_trigger_funders": len(fund), "top1_coins": top[0] if top else 0,
                     "top5_coins": sum(top[:5]), "top10_coins": sum(top[:10]),
                     "top_funders": [(f[:16], c) for f, c in fund.most_common(5)],
                     "n_days": int(trig.day.nunique()), "creators_repeated": int(trig.creator.duplicated().sum()),
                     "V1_first_s_median": float(trig[f"V1_first_s_{mode}"].median()),
                     "V2_first_s_median": float(trig[f"V2_first_s_{mode}"].median()),
                     "V1_first_px_median": float(trig[f"V1_first_px_{mode}"].median()),
                     "V2_first_px_median": float(trig[f"V2_first_px_{mode}"].median()),
                     "first_s_q10_q50_q90": first.quantile([.1, .5, .9]).round(0).tolist()}
    (H / "results" / "r0_concentration.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
