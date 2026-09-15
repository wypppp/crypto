#!/usr/bin/env python3
"""按 campaign 声明用**当前**验收工具重新验收某个运行目录。

    python3 verify_batch.py <运行目录>

期望值取自该目录 driver.json（创建目录时登记的代码/规格/样本/原语 hash 与参数），
侧别与验收模式取自 campaign.json 的批次声明。报告写成该目录下 recompare_<UTC时间>.json，
独占创建、不覆盖驱动自动产出的 compare_*.json。只读输入，不改任何既有文件。
"""
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE.parent
W = RUNS.parent
T = W / "realchain_tools"


def main():
    d = Path(sys.argv[1]).resolve()
    camp = json.loads((HERE / "campaign.json").read_text(encoding="utf-8"))
    drv = json.loads((d / "driver.json").read_text(encoding="utf-8"))
    name = Path(drv["sample"]).name
    sha = (drv.get("code_sha256") or {}).get("sample")
    batch = next((b for b in camp["batches"]
                  if b["sample"] == name and b["sample_sha256"] == sha), None)
    if batch is None:
        sys.exit(f"{d.name} 的样本 {name}({str(sha)[:12]}…) 不在 campaign 声明里，拒绝验收")
    rows = [json.loads(x) for x in (d / "runs.jsonl").read_text().splitlines() if x.strip()]
    cs = drv["code_sha256"]
    args = []
    for side in batch["sides"]:
        tags = [r["tag"] for r in rows if r.get("kind") == "run" and r.get("side") == side]
        if not tags:
            sys.exit(f"{d.name} 没有 {side} 侧的完成运行，无法按声明（{batch['sides']}）验收")
        args += [f"--{side}", ",".join(tags)]
    # 该侧之外的标签必须显式忽略，否则清单归属检查会把它们判成来历不明
    others = sorted({r["tag"] for r in rows if r.get("kind") == "run"}
                    - {t for s in batch["sides"] for t in
                       [r["tag"] for r in rows if r.get("kind") == "run" and r.get("side") == s]})
    for t in others:
        args += ["--ignore-tag", t]
    out = d / f"recompare_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    cmd = [sys.executable, str(T / "compare_runs.py"), "--dir", str(d), *args,
           "--sample", str(W / drv["sample"]), "--pin", drv["pin"],
           "--expect-script-sha", cs["pilot_measure.py"],
           "--expect-evidence-sha", cs["evidence.py"],
           "--expect-spec-sha", cs["spec"], "--expect-primitives-sha", cs["primitives"],
           "--expect-runtime-params", json.dumps(drv["runtime_params"]), "--out", str(out)]
    rc = subprocess.call(cmd, cwd=W)
    (d / f"{out.stem}.command.json").write_text(
        json.dumps({"argv": cmd, "exit": rc, "batch": batch["id"]}, ensure_ascii=False, indent=2) + "\n")
    rep = json.loads(out.read_text()) if out.is_file() else {}
    print(json.dumps({"batch": batch["id"], "exit": rc, "mode": rep.get("mode"),
                      "verdict": rep.get("verdict"), "report": out.name}, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    sys.exit(main())
