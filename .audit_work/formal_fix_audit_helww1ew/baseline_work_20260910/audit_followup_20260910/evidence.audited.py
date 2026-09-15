#!/usr/bin/env python3
"""证据层：请求级增量落盘、候选/阶段标识、版本 hash、资源计量、失败阻断。

设计要点（对应审查 §5）：
* **每条记录写完即 flush + fsync**。进程被杀时，已写的行仍可读；
  最后一行可能截断，读取端跳过不完整行而不是整文件报错。
* 运行头在**任何工作开始之前**写入，含脚本/规格/样本/台账 hash 与 chainId、finalized 快照。
* RPC 记录从 `RPC.records` **增量抽取**（游标），逐条打上候选与阶段标签。
* Etherscan 请求单独记录原始响应。
* 结束时写运行尾：计数、资源、机器可判的验收状态。任一候选未完成 → 非零退出。
"""
import hashlib, itertools, json, os, threading, time, uuid
from pathlib import Path


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def rss_kb():
    try:
        for line in open("/proc/self/status"):
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except OSError:
        pass
    return None


def cpu_seconds():
    try:
        t = os.times()
        return round(t.user + t.system, 3)
    except OSError:
        return None


class EvidenceLog:
    """JSONL 增量证据。每条 flush+fsync；中断后前缀仍可读。"""

    def __init__(self, path, *, secrets=()):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.secrets = {s for s in secrets if s and len(str(s)) >= 8}
        orphan = self._quarantine_partial_tail()
        self.fh = self.path.open("a", encoding="utf-8")
        self._lock = threading.Lock()
        self.seq = 0
        self.run_id = uuid.uuid4().hex
        self.t0 = time.time()
        self.counts = {}
        if orphan is not None:
            # 上一次运行被中断留下半行；已隔离到 .orphan，避免新运行头被拼接进去而一并丢失
            self.write("orphan_recovered", bytes_moved=len(orphan),
                       orphan_file=str(self.path) + ".orphan")

    def _quarantine_partial_tail(self):
        """若文件末尾是不完整的一行，移到 <path>.orphan 并截断。返回被移走的字节。"""
        if not self.path.exists() or self.path.stat().st_size == 0:
            return None
        data = self.path.read_bytes()
        if data.endswith(b"\n"):
            return None
        cut = data.rfind(b"\n") + 1          # 0 表示整个文件就是一行残片
        tail = data[cut:]
        Path(str(self.path) + ".orphan").write_bytes(tail)
        with self.path.open("r+b") as fh:
            fh.truncate(cut)
        return tail

    def redact(self, value):
        """统一脱敏：异常串、非 JSON 响应、参数都要过这里。"""
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False,
                                                              default=str)
        for sec in self.secrets:
            text = text.replace(str(sec), "<redacted>")
        if isinstance(value, str):
            return text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def write(self, kind, **fields):
        with self._lock:
            return self._write_locked(kind, fields)

    def _write_locked(self, kind, fields):
        self.seq += 1
        rec = {"seq": self.seq, "run_id": self.run_id, "kind": kind,
               "worker": getattr(threading.current_thread(), "worker_id", None),
               "at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z",
               "mono_s": round(time.time() - self.t0, 3)}
        rec.update(fields)
        if self.secrets:
            rec = self.redact(rec)
            rec = rec if isinstance(rec, dict) else {"kind": kind, "redaction_error": True}
        self.fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        self.fh.flush()
        os.fsync(self.fh.fileno())
        self.counts[kind] = self.counts.get(kind, 0) + 1
        return rec

    def resource(self, candidate=None, stage=None):
        return self.write("resource", candidate=candidate, stage=stage,
                          rss_kb=rss_kb(), cpu_s=cpu_seconds())

    def close(self):
        try:
            self.fh.close()
        except OSError:
            pass


_PENDING_SEQ = itertools.count(1)
_PENDING_LOCK = threading.Lock()


class RpcTap:
    """把 RPC.records 增量排空到证据日志，并打上候选/阶段标签。"""

    def __init__(self, rpc, log, gate=None, worker=None):
        self.rpc, self.log, self.cursor = rpc, log, 0
        self.candidate, self.stage = None, None
        self.pending = 0
        self.gate, self.worker = gate, worker

    def mark(self, candidate=None, stage=None):
        if candidate is not None:
            self.candidate = candidate
        if stage is not None:
            self.stage = stage

    def drain(self):
        """把尚未落盘的 RPC 记录写出。返回本次落盘条数。"""
        new = self.rpc.records[self.cursor:]
        for item in new:
            self.log.write("rpc", candidate=self.candidate, stage=self.stage, record=item)
        self.cursor += len(new)
        return len(new)

    # 代理：每次调用后立即排空，保证中断时已发生的请求都在盘上
    def _begin(self, op, detail):
        """先落一条 begin。若进程在重试中被杀，只有 begin 没有配对完成记录
        —— 该请求的结果按【未知】处理，不得当作未发生或已失败。"""
        with _PENDING_LOCK:
            pid = next(_PENDING_SEQ)      # 全局唯一，避免多个 tap 的编号相撞
        self.pending = pid
        return self.log.write("rpc_begin", candidate=self.candidate, stage=self.stage,
                              op=op, detail=detail, pending_id=pid)

    def _end(self, pending_id, drained):
        self.log.write("rpc_end", candidate=self.candidate, stage=self.stage,
                       pending_id=pending_id, records_drained=drained)

    def request(self, method, params):
        b = self._begin("request", {"method": method})
        if self.gate:
            self.gate.acquire(self.worker)
        try:
            return self.rpc.request(method, params)
        finally:
            self._end(b["pending_id"], self.drain())

    def call(self, to, data, block, overrides=None):
        b = self._begin("call", {"to": to, "block": block,
                                 "has_overrides": bool(overrides)})
        if self.gate:
            self.gate.acquire(self.worker)
        try:
            return self.rpc.call(to, data, block, overrides)
        finally:
            self._end(b["pending_id"], self.drain())

    def __getattr__(self, name):
        return getattr(self.rpc, name)


def run_header(log, *, script, spec, sample, universe, declared_universe_sha,
               chain_id, snapshot, params):
    """任何工作开始前写入。台账 hash 不符、或规格文件缺失，一律拒绝。"""
    spec = Path(spec)
    if not spec.is_absolute():
        spec = Path(script).resolve().parent / spec      # 按脚本目录定位，不用工作目录
    if not spec.is_file():
        log.write("abort", reason="spec_missing", spec=str(spec))
        raise SystemExit(f"规格文件缺失：{spec} —— 无版本标识不得采集")
    u_now = sha256_file(universe)
    ok = (u_now == declared_universe_sha)
    log.write("run_header",
              script_sha256=sha256_file(script),
              evidence_module_sha256=sha256_file(Path(__file__).resolve()),
              spec_path=str(spec), spec_sha256=sha256_file(spec),
              sample_sha256=sha256_file(sample),
              universe_sha256_now=u_now,
              universe_sha256_declared=declared_universe_sha,
              universe_match=ok,
              chain_id=chain_id, finalized_snapshot=snapshot,
              params=params,
              started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    if not ok:
        raise SystemExit(f"universe.csv 与声明的 hash 不符：{u_now[:16]}… vs "
                         f"{declared_universe_sha[:16]}… —— 拒绝复用，样本与台账必须同源")
    return ok


class Checkpoint:
    """
    断点续跑的检查点：**追加式**，一次候选尝试一条，永不覆盖。

    绑定四要素 —— 冻结样本、规格、脚本版本、finalized 状态块。
    任一不符即拒绝复用（`verify_binding` 抛 SystemExit），避免把不同口径的
    结果拼在一起。失败历史全部保留，不用最终成功覆盖原失败。
    """

    BINDING_KEYS = ("sample_sha256", "spec_sha256", "script_sha256",
                    "evidence_module_sha256", "primitives_sha256", "universe_sha256",
                    "finalized_number", "finalized_hash", "runtime_params")

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records = []
        # 与证据日志同样处理：上次中断留下的半行必须先隔离，
        # 否则新记录会拼在它后面而被整行丢弃（审查反例 7）
        if self.path.exists() and self.path.stat().st_size:
            data = self.path.read_bytes()
            if not data.endswith(b"\n"):
                cut = data.rfind(b"\n") + 1
                Path(str(self.path) + ".orphan").write_bytes(data[cut:])
                with self.path.open("r+b") as fh:
                    fh.truncate(cut)
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip():
                    try:
                        self.records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass                       # 半行丢弃，不影响已完成的判定
        self.fh = self.path.open("a", encoding="utf-8")
        self._lock = threading.Lock()

    def _append(self, rec):
        with self._lock:
            return self._append_locked(rec)

    def _append_locked(self, rec):
        self.fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        self.fh.flush()
        os.fsync(self.fh.fileno())
        self.records.append(rec)

    @property
    def binding(self):
        for r in self.records:
            if r.get("kind") == "binding":
                return r
        return None

    def write_binding(self, **kw):
        rec = {"kind": "binding", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        rec.update(kw)
        self._append(rec)
        return rec

    def verify_binding(self, **kw):
        """与既有绑定比对。不符即拒绝；无既有绑定则写入。返回 (是否续跑, 差异)。"""
        old = self.binding
        if old is None:
            self.write_binding(**kw)
            return False, {}
        diff = {k: {"checkpoint": old.get(k), "now": kw.get(k)}
                for k in self.BINDING_KEYS if old.get(k) != kw.get(k)}
        if diff:
            self._append({"kind": "refused", "reason": "binding_mismatch", "diff": diff,
                          "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            raise SystemExit("检查点绑定不符，拒绝复用：" +
                             ", ".join(f"{k}({v['checkpoint']}→{v['now']})"
                                       for k, v in diff.items()))
        return True, {}

    def attempts(self, candidate=None):
        out = [r for r in self.records if r.get("kind") == "attempt"]
        return [r for r in out if r.get("candidate") == candidate] if candidate is not None else out

    def completed(self):
        """已完成的候选集合：至少有一次 completed=true 的尝试。"""
        return {r["candidate"] for r in self.attempts() if r.get("completed") is True}

    def record_attempt(self, candidate, state, completed, **kw):
        n = len(self.attempts(candidate)) + 1
        rec = {"kind": "attempt", "candidate": candidate, "attempt": n,
               "state": state, "completed": bool(completed),
               "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        rec.update(kw)
        self._append(rec)
        return rec

    def close(self):
        try:
            self.fh.close()
        except OSError:
            pass


class SharedGate:
    """
    **全局**限流与调用预算闸门 —— 两路并行共用一份，不是各分一半。

    只在锁内占用「发车时刻」与预算计数，HTTP 请求本身在锁外执行，
    因此限流是全局的、I/O 仍可并发。各 worker 的 `V.RPC` 自身限流设为不生效
    （rps 极大），真正的节流由本闸门统一施加，从而复用已验证的 RPC 实现而不改它。
    """

    #: 单个逻辑请求在底层最多发出的 HTTP 次数（V.RPC 对 429/502/503/504 重试一次）
    MAX_HTTP_ATTEMPTS = 2

    def __init__(self, rps, max_calls, max_seconds):
        self.lock = threading.Lock()
        self.interval = 1.0 / rps if rps > 0 else 0.0
        self.next_slot = 0.0
        self.calls = 0
        self.max_calls = max_calls
        self.max_seconds = max_seconds
        self.started = time.monotonic()
        self.per_worker = {}

    def acquire(self, worker=None, kind="rpc"):
        """占用一个逻辑请求的额度与发车时刻。

        额度按 **MAX_HTTP_ATTEMPTS** 预留：底层 `V.RPC` 对特定 HTTP 状态会自行重试一次，
        若只扣 1，实际发出的 HTTP 次数会超出共享预算（审查反例 9）。
        时间预算在**发车之后**再核一次：等待可能把发车推过截止（反例 12）。
        """
        with self.lock:
            need = self.MAX_HTTP_ATTEMPTS
            if self.calls + need > self.max_calls:
                raise RuntimeError("shared call budget exhausted")
            if time.monotonic() - self.started >= self.max_seconds:
                raise RuntimeError("shared time budget exhausted")
            self.calls += need
            k = (worker, kind)
            self.per_worker[k] = self.per_worker.get(k, 0) + need
            now = time.monotonic()
            slot = max(now, self.next_slot)
            self.next_slot = slot + self.interval
        wait = slot - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        if time.monotonic() - self.started >= self.max_seconds:
            raise RuntimeError("shared time budget exhausted after wait")

    def stats(self):
        per = {}
        for (w, kind), v in self.per_worker.items():
            per.setdefault(str(w), {})[kind] = v
        return {"total_reserved": self.calls, "max_http_attempts": self.MAX_HTTP_ATTEMPTS,
                "per_worker": per,
                "elapsed_s": round(time.monotonic() - self.started, 2)}


def read_evidence(path, *, report=False):
    """读取证据。

    **尾部截断**（最后一行不完整）与**中间损坏**必须区分：前者是中断的正常后果，
    后者说明文件被改动或写坏，正式验收不得当作完整。返回 (recs, bad_line_count)；
    report=True 时返回 (recs, diag)，diag 含损坏位置、seq 连续性、运行归属与结束记录。
    """
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    recs, bad = [], []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            bad.append(i)
    if not report:
        return recs, len(bad)
    last = len(lines) - 1
    tail_only = bad == [last] if bad else True
    runs = {}
    for r in recs:
        runs.setdefault(r.get("run_id"), []).append(r.get("seq"))
    gaps = {}
    for rid, seqs in runs.items():
        want = list(range(1, len(seqs) + 1))
        if sorted(s for s in seqs if s is not None) != want:
            gaps[rid] = {"seen": sorted(s for s in seqs if s is not None), "expected_n": len(seqs)}
    footers = {r.get("run_id") for r in recs if r.get("kind") == "run_footer"}
    begins = {(r.get("run_id"), r.get("pending_id"), r.get("worker"))
              for r in recs if r.get("kind") == "rpc_begin"}
    ends = {(r.get("run_id"), r.get("pending_id"), r.get("worker"))
            for r in recs if r.get("kind") == "rpc_end"}
    unmatched = sorted(str(x) for x in (begins - ends))
    diag = {"bad_lines": bad, "tail_truncation_only": tail_only,
            "unmatched_rpc_begin": unmatched,
            "mid_file_corruption": bool(bad) and not tail_only,
            "runs": {k: len(v) for k, v in runs.items()},
            "seq_gaps": gaps,
            "runs_with_footer": sorted(x for x in footers if x),
            "runs_without_footer": sorted(x for x in runs if x and x not in footers),
            "complete": ((not bad or tail_only) and not gaps
                         and not unmatched          # 有请求发出但结果未知 ⇒ 不完整
                         and all(x in footers for x in runs if x))}
    return recs, diag
