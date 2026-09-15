#!/usr/bin/env python3
"""生成并冻结正式 300 样本及其批次切片。**独立脚本，不改 pilot_measure.py**
（实现文件的 hash 进检查点绑定，冻结前不动它）。抽样逻辑与 `pilot_measure.declare` 相同：
同一 SEED、同一 universe、`category=weth` 行，`random.Random(SEED).sample`。

口径（2026-09-12 决策）：取 308 个后**排除 8 个开发候选**，得到干净的 300 个。
排除集合、seed、universe sha256 全部写进样本文件，可离线复算。

用法：python3 declare_formal.py <输出目录>   （目录必须不存在；只写该目录）
"""
import csv
import hashlib
import json
import random
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[2]
UNIVERSE = W / "universe_run" / "universe.csv"
DEV_SAMPLE = W / "pilot" / "dev_sample.json"
SEED = 20260910          # 与 dev 样本同一 seed，保持抽样可复算
OVERSAMPLE = 308         # 300 + 8 个待排除的开发候选
N_FORMAL = 300
CUTOFF = 24781026        # 首次 Mint cutoff；weth 行本就全部 ≤ 此值
BATCH = 20               # 单次运行受 max_seconds 3000 最紧约束（见 BUDGET_300.md）。
#                        23 个时串行墙钟约 2912s、距上限仅 88s，端点稍慢即预算耗尽；
#                        取 20 个：300 整除成 15 批，串行约 2532s（余量 15.6%），并行 2 路约 1266s
SUBSET_BATCHES = [15, 15]   # 串并行对照子集：共 30 个，分两批以留出预算余量


def rows_weth():
    return [r for r in csv.DictReader(open(UNIVERSE, encoding="utf-8")) if r["category"] == "weth"]


def as_cand(r):
    from_weth = r["token0"] if r["token1"].lower() == "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2" else r["token1"]
    return {"index": int(r["index"]), "pair": r["pair"], "token": from_weth,
            "created_block": int(r["block"])}


def write_sample(path, cands, universe_sha, **extra):
    blob = {"declared_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
            "seed": SEED, "n": len(cands), "universe_sha256": universe_sha,
            "universe_weth_rows": extra.pop("weth_rows", None), **extra,
            "sample": sorted(cands, key=lambda c: c["index"])}
    path.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=False)
    rows = rows_weth()
    universe_sha = hashlib.sha256(UNIVERSE.read_bytes()).hexdigest()
    dev = json.loads(DEV_SAMPLE.read_text(encoding="utf-8"))
    dev_idx = {c["index"] for c in dev["sample"]}
    assert dev["universe_sha256"] == universe_sha, "universe 与开发样本声明的不一致，拒绝生成"

    picked = random.Random(SEED).sample(rows, OVERSAMPLE)
    kept = [r for r in picked if int(r["index"]) not in dev_idx]
    assert len(picked) - len(kept) == len(dev_idx) == 8, "排除的开发候选数不是 8"
    assert len(kept) >= N_FORMAL, len(kept)
    formal = [as_cand(r) for r in kept[:N_FORMAL]]
    idx = [c["index"] for c in formal]
    assert len(idx) == len(set(idx)) == N_FORMAL
    assert not (set(idx) & dev_idx), "正式样本仍含开发候选"
    assert all(c["created_block"] <= CUTOFF for c in formal), "有候选超出 cutoff"

    meta = {"purpose": "FORMAL 300-candidate sample (frozen); oversampled 308 then excluded the 8 dev candidates",
            "oversample": OVERSAMPLE, "excluded_dev_indices": sorted(dev_idx),
            "dev_sample_sha256": hashlib.sha256(DEV_SAMPLE.read_bytes()).hexdigest(),
            "cutoff_block": CUTOFF, "weth_rows": len(rows)}
    full_sha = write_sample(out / "formal_sample_300.json", formal, universe_sha, **dict(meta))

    manifest = {"formal_sample_300.json": full_sha, "seed": SEED, "universe_sha256": universe_sha,
                "batches": [], "subset_batches": []}
    # 主采集批次：按 index 排序后顺序切片，每批 BATCH 个
    ordered = sorted(formal, key=lambda c: c["index"])
    for i in range(0, len(ordered), BATCH):
        part = ordered[i:i + BATCH]
        name = f"batch_{i // BATCH + 1:02d}.json"
        sha = write_sample(out / name, part, universe_sha,
                           purpose=f"formal batch {i // BATCH + 1} of main collection",
                           parent_sample_sha256=full_sha, weth_rows=len(rows))
        manifest["batches"].append({"file": name, "n": len(part), "sha256": sha,
                                    "indices": [c["index"] for c in part]})
    # 串并行对照子集：从正式 300 里按同一 seed 另抽 30，再分两批
    sub = sorted(random.Random(SEED + 1).sample(formal, sum(SUBSET_BATCHES)), key=lambda c: c["index"])
    pos = 0
    for j, size in enumerate(SUBSET_BATCHES, 1):
        part = sub[pos:pos + size]; pos += size
        name = f"subset_pair_{j:02d}.json"
        sha = write_sample(out / name, part, universe_sha,
                           purpose=f"serial/parallel consistency subset batch {j}",
                           parent_sample_sha256=full_sha, weth_rows=len(rows))
        manifest["subset_batches"].append({"file": name, "n": len(part), "sha256": sha,
                                           "indices": [c["index"] for c in part]})
    (out / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    blocks = sorted(c["created_block"] for c in formal)
    print(f"正式样本 {len(formal)} 个 -> {out}/formal_sample_300.json  sha256={full_sha[:16]}…")
    print(f"  排除开发候选 {sorted(dev_idx)}")
    print(f"  创建块范围 {blocks[0]}..{blocks[-1]}（cutoff {CUTOFF}）")
    print(f"  主采集 {len(manifest['batches'])} 批（每批 ≤{BATCH}）；对照子集 {len(sub)} 个分 {len(SUBSET_BATCHES)} 批")


if __name__ == "__main__":
    main()
