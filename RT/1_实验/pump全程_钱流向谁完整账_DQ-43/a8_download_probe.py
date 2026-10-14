"""总控第八轮：只重下一个既有结果，锁内隔离 30 分钟观察下载费。

只发出一次已批准的下载，不执行 SQL，不重试。
观察期间持有同一把付费锁，阻止别的执行混入用量差。
长观察以后台进程运行，前台可继续 0 credits 核查。
"""

import datetime as dt
import hashlib
import json
import time

import paid_guard as PG
from dune_get_stream import fetch
from dune_get import get
from run_dune import budget_gate, usage

SQL = "sql/S3P_DETAIL_0811_p002.sql"
EID = "01M4WRPTY8WDKX1NVCQJNCAW8R"
QID = "8945017"
LABEL = "A8P_DOWNLOAD_A7_DETAIL"


def observe(approval="A8-01", wait_sec=1800):
    ticket = PG.check(approval, SQL)
    path = PG.H / "runs/a8_download_probe.json"
    out = {
        "approval": approval,
        "execution_id": EID,
        "query_id": QID,
        "no_query_executed": True,
        "isolation_lock_held": True,
        "observations": [],
    }

    def sample(name):
        u = usage()
        out["observations"].append(
            {
                "phase": name,
                "at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "used": None if u is None else u[0],
                "included": None if u is None else u[1],
            }
        )
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
        return u

    with PG.one_at_a_time(ticket):
        u0 = sample("before")
        why = budget_gate(u0, ticket.download_cap) or PG.round_gate(approval)
        if why:
            raise SystemExit(why)
        status = get(f"/execution/{EID}/status")
        mb = (
            float((status.get("result_metadata") or {}).get("result_set_bytes") or 0)
            / 1e6
        )
        if status["state"] != "QUERY_STATE_COMPLETED" or mb > ticket["max_mb"]:
            raise SystemExit("执行未完成或结果超过批准下载上限，不下载")
        out["result_mb"] = mb
        PG.mark_used(approval, EID, "下载及30分钟观察")
        try:
            fetch(QID, LABEL, SQL, ticket, execution_id=EID)
            immediate = sample("immediate")
            deadline = time.monotonic() + wait_sec
            out["observe_until_utc"] = (
                dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=wait_sec)
            ).isoformat()
            path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
            print(
                "下载完成，立即用量",
                None if immediate is None else immediate[0],
                "观察至",
                out["observe_until_utc"],
                flush=True,
            )
            while (remaining := deadline - time.monotonic()) > 0:
                time.sleep(min(5, remaining))
            u1 = sample("after_30_min")
            out["immediate_delta"] = (
                None if immediate is None else round(immediate[0] - u0[0], 6)
            )
            out["after_30_min_delta"] = None if u1 is None else round(u1[0] - u0[0], 6)
            raw = PG.H / "raw/dune" / (LABEL + ".csv.gz")
            out["raw_gzip_sha256"] = hashlib.sha256(raw.read_bytes()).hexdigest()
            path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
            print(json.dumps(out, ensure_ascii=False), flush=True)
        finally:
            latest = (
                out["observations"][-1]["used"]
                if len(out["observations"]) > 1
                else None
            )
            PG.record_actual(approval, EID, u0[0], latest, 0)


if __name__ == "__main__":
    observe()
