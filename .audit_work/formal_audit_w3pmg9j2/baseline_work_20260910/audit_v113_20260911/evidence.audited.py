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
import contextlib, hashlib, http.client, itertools, json, os, socket, threading, time
import urllib.request, uuid
from pathlib import Path


class BudgetExhausted(RuntimeError):
    """全局调用/时间预算耗尽。在**发出 HTTP 之前**抛出，故不会越过上限。"""


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def result_sha256(obj):
    """候选结果的规范 hash：键排序、无空白，跨会话可复算。"""
    blob = json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _proc_status(field):
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith(field):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def rss_kb():
    """当前 RSS。**是采样值**，两次采样之间的尖峰看不到。"""
    return _proc_status("VmRSS:")


def rss_peak_kb():
    """RSS 峰值。取内核维护的高水位 `VmHWM` —— 这是**实测峰值**，
    不是采样：进程从启动至今到达过的最高 RSS，采样间隙里的尖峰同样计入。

    /proc 不可用时退回 `getrusage(RUSAGE_SELF).ru_maxrss`（Linux 上单位为 KB）。
    """
    v = _proc_status("VmHWM:")
    if v is not None:
        return v
    try:
        import resource as _r
        return _r.getrusage(_r.RUSAGE_SELF).ru_maxrss
    except (ImportError, OSError):
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
        self.counts_by_candidate = {}    # (kind, candidate) -> n，并行下按候选归集
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

    def try_write(self, kind, **fields):
        """**非阻塞**写一条。拿不到锁就放弃，返回 False。

        用于强制退出前的最后一条记录：那条路径上不能等锁 ——
        锁可能正被卡在 fsync 的线程持有，一等就把"最后兜底"本身拖住
        （审查 v1.11 反例 2）。
        """
        if not self._lock.acquire(blocking=False):
            return False
        try:
            self._write_locked(kind, fields)
            return True
        except Exception:                                         # noqa: BLE001
            return False
        finally:
            self._lock.release()

    def note_fd(self, text):
        """绕开一切锁与缓冲，直接把一行写到证据文件旁边的 `.escalation`。

        `os.write` 到一个独立 fd，不碰日志锁、不 fsync。
        """
        try:
            fd = os.open(str(self.path) + ".escalation",
                         os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        except OSError:
            return False
        try:
            os.write(fd, (text.rstrip("\n") + "\n").encode("utf-8", "replace"))
            return True
        except OSError:
            return False
        finally:
            try:
                os.close(fd)
            except OSError:
                pass

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
        ck = (kind, fields.get("candidate"))
        self.counts_by_candidate[ck] = self.counts_by_candidate.get(ck, 0) + 1
        return rec

    def resource(self, candidate=None, stage=None):
        # rss_kb 是采样、rss_peak_kb 是内核高水位（实测峰值）—— 分开记，别混用
        return self.write("resource", candidate=candidate, stage=stage,
                          rss_kb=rss_kb(), rss_peak_kb=rss_peak_kb(),
                          cpu_s=cpu_seconds())

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
        # acquire 必须在 try 内：闸门拒绝时该请求并未发出，
        # 若跳过 _end 就会留下无配对的 begin，被读取端判成"结果未知"。
        try:
            if self.gate:
                self.gate.acquire(self.worker)
            return self.rpc.request(method, params)
        finally:
            self._end(b["pending_id"], self.drain())

    def call(self, to, data, block, overrides=None):
        b = self._begin("call", {"to": to, "block": block,
                                 "has_overrides": bool(overrides)})
        try:
            if self.gate:
                self.gate.acquire(self.worker)
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
            lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
            bad = []
            for i, line in enumerate(lines):
                if not line.strip():
                    continue
                try:
                    self.records.append(json.loads(line))
                except json.JSONDecodeError:
                    bad.append(i)
            # 尾部半行已在上面隔离掉了，所以此处任何坏行都在**中段** ——
            # 说明检查点被改动或写坏，不能只是跳过（审查反例 1）。
            if bad:
                raise SystemExit(
                    f"检查点中段损坏：{self.path} 第 {[i + 1 for i in bad]} 行无法解析 —— "
                    f"拒绝复用。请核对文件来源，或改用新的检查点重新测量。")
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
        """已完成的候选集合：至少有一次 completed=true 的尝试。

        **注意**：completed 只说明当时那一次跑完了，不保证结果还拿得到。
        续跑要跳过某个候选，必须用 `deliverable()` —— 它另外要求
        检查点里存着通过 hash 校验的那份结果。
        """
        return {r["candidate"] for r in self.attempts() if r.get("completed") is True}

    def deliverable(self):
        """可交付的已完成候选：{candidate: (result, attempt_record)}。

        逐条校验内联结果的 sha256。**校验不过或结果缺失的候选不算已完成**，
        必须重新测量，不能只凭 completed 标志跳过（审查反例 1）。
        返回 (ok, broken)：broken 列出有 completed 标志却拿不出可信结果的候选。
        """
        ok, broken = {}, []
        for r in self.attempts():
            if r.get("completed") is not True:
                continue
            cand = r.get("candidate")
            res = r.get("result")
            want = r.get("result_sha256")
            if res is None or not want:
                broken.append({"candidate": cand, "reason": "result_absent_in_checkpoint",
                               "attempt": r.get("attempt")})
                ok.pop(cand, None)
                continue
            got = result_sha256(res)
            if got != want:
                broken.append({"candidate": cand, "reason": "result_hash_mismatch",
                               "attempt": r.get("attempt"),
                               "checkpoint": want, "recomputed": got})
                ok.pop(cand, None)
                continue
            ok[cand] = (res, r)
        return ok, broken

    def record_attempt(self, candidate, state, completed, *, result=None, **kw):
        n = len(self.attempts(candidate)) + 1
        rec = {"kind": "attempt", "candidate": candidate, "attempt": n,
               "state": state, "completed": bool(completed),
               "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        rec.update(kw)
        if completed:
            # 已完成必须连同结果一起持久化，且带 hash。
            # 否则「检查点说做完了、结果却拿不出来」时，续跑会交付一份空汇总。
            if result is None:
                raise ValueError("record_attempt(completed=True) 必须带 result")
            rec["result"] = result
            rec["result_sha256"] = result_sha256(result)
        self._append(rec)
        return rec

    def close(self):
        try:
            self.fh.close()
        except OSError:
            pass


class Shutdown(Exception):
    """有序停机信号。**不是**测量失败，也**不是**成功 —— 它是"没做完就停了"。"""

    def __init__(self, reason, detail=None):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail or {}


class ResourceGovernor:
    """资源上限与停机策略。

    与「资源采样」的区别：
    * 采样只是每隔一段时间记一条 `resource`，**尖峰会漏**，也不会拦住任何事；
    * 本类用内核高水位 `VmHWM` 作**实测峰值**，并由一个后台线程按 `poll_s`
      巡检，越线即置停机标志。

    停机是**有序**的：只置标志，由调用方在安全点（候选之间、阶段之间）检查
    并抛 `Shutdown`。不在写证据的中途把进程打死 —— 那会留下半行、
    留下无配对的 rpc_begin，把"资源超限"变成"证据损坏"。

    `RLIMIT_AS` 只作**最后兜底**（可选，默认不设）：它触发时是 MemoryError，
    位置不可控，正是我们想避免的。所以兜底值应显著高于软阈值。
    """

    def __init__(self, *, max_rss_kb=None, max_cpu_s=None, max_wall_s=None,
                 poll_s=0.25, clock=None,
                 grace_calls=16, grace_seconds=15.0, escalate_after=5.0,
                 force_exit_after=1.0,
                 hard_rss_kb=None, hard_cpu_s=None, on_escalate=None):
        # 软阈值：越线置停机标志，靠各处**协作检查**生效。不是强制约束。
        self.max_rss_kb = max_rss_kb
        self.max_cpu_s = max_cpu_s
        self.max_wall_s = max_wall_s
        # 硬兜底：内核强制，与工作线程是否检查无关。见 apply_hard_limits()。
        self.hard_rss_kb = hard_rss_kb
        self.hard_cpu_s = hard_cpu_s
        self.hard_applied = {}
        self.hard_requested = bool(hard_rss_kb or hard_cpu_s)
        self.on_escalate = on_escalate
        # 停机后的收尾预算 —— 停机耗时的上界由它给出，不由巡检频率给出
        self.grace_calls = grace_calls
        self.grace_seconds = grace_seconds
        self.stopped_at = None
        self.escalate_after = escalate_after
        # 升级回调开始后再过这么久，无条件强制退出（None 关闭）
        self.force_exit_after = force_exit_after
        self._force_exit_timer = None
        self._inflight = {}                # token -> closer；在途响应，供到点强制关闭
        self._inflight_seq = itertools.count(1)
        self._deadline_timer = None
        self._escalate_timer = None
        self.deadline_closures = 0         # 到点被强制关闭的在途响应数
        self.escalations = 0
        self.calls_after_stop = 0
        self.winddown_calls = 0            # 收尾窗口内的实际 HTTP 次数
        self.winddown_logical = 0          # 收尾窗口内的逻辑请求次数
        self._wd = threading.local()
        self.poll_s = poll_s
        self._clock = clock or time.monotonic
        self.started = self._clock()
        self._stop = threading.Event()      # 「请求停机」——只有越线或信号会置
        self._done = threading.Event()      # 「看门狗该收工了」——正常关闭也会置
        self._reason = None
        self._detail = {}
        self._lock = threading.Lock()
        self._thread = None
        self.observations = 0          # 巡检次数，用于证明看门狗真的在跑

    # ---- 测量 ----
    def snapshot(self):
        return {"rss_kb": rss_kb(), "rss_peak_kb": rss_peak_kb(),
                "cpu_s": cpu_seconds(),
                "wall_s": round(self._clock() - self.started, 3)}

    def limits(self):
        return {"hard_requested": bool(self.hard_rss_kb or self.hard_cpu_s),
                "hard_problems": self.hard_limit_problems(),
                "soft_thresholds": {
                    "max_rss_kb": self.max_rss_kb, "max_cpu_s": self.max_cpu_s,
                    "max_wall_s": self.max_wall_s, "poll_s": self.poll_s,
                    "kind": "cooperative soft thresholds: set a stop flag; "
                            "they do NOT prevent further allocation or execution"},
                "hard_backstop": {
                    "hard_rss_kb": self.hard_rss_kb, "hard_cpu_s": self.hard_cpu_s,
                    "applied": self.hard_applied,
                    "kind": "kernel-enforced RLIMIT; independent of any in-process check"},
                "stop_grace": {"grace_calls": self.grace_calls,
                               "grace_seconds": self.grace_seconds,
                               "kind": "upper bound on work after a stop is requested"}}

    # ---- 判定 ----
    def check(self):
        """巡检一次。越线则置停机标志并返回原因，否则返回 None。"""
        self.observations += 1
        snap = self.snapshot()
        hit = None
        peak = snap["rss_peak_kb"]
        if self.max_rss_kb is not None and peak is not None and peak > self.max_rss_kb:
            hit = ("rss_limit_exceeded",
                   {"rss_peak_kb": peak, "max_rss_kb": self.max_rss_kb})
        elif self.max_cpu_s is not None and snap["cpu_s"] is not None \
                and snap["cpu_s"] > self.max_cpu_s:
            hit = ("cpu_limit_exceeded",
                   {"cpu_s": snap["cpu_s"], "max_cpu_s": self.max_cpu_s})
        elif self.max_wall_s is not None and snap["wall_s"] > self.max_wall_s:
            hit = ("wall_limit_exceeded",
                   {"wall_s": snap["wall_s"], "max_wall_s": self.max_wall_s})
        if hit:
            self.request_stop(hit[0], dict(hit[1], measured=snap))
            return hit[0]
        return None

    def request_stop(self, reason, detail=None):
        """外部触发（信号等）。**第一个原因胜出**，后续不覆盖。"""
        with self._lock:
            if self._reason is None:
                self._reason = reason
                self._detail = detail or {}
                self._detail.setdefault("measured", self.snapshot())
                self.stopped_at = self._clock()
        self._stop.set()
        self._done.set()          # 已经决定停了，看门狗无需再巡检
        self._arm_deadline()

    # ---- 绝对墙钟截止：socket timeout 管不住的那部分 ----
    #
    # socket timeout 是**每次读的不活动超时**，不是整段响应的完成期限：
    # 服务端每 35ms 吐一小段，0.15s 的 timeout 永远不会触发，
    # 整体却可以拖到任意长（审查 v1.10，真实 loopback 实测 0.387s）。
    # 所以必须另有一条**绝对**期限，并且能作用在**已经开始**的请求上。
    def absolute_deadline(self):
        """停机后的绝对完成期限（monotonic 秒）。未停机返回 None。"""
        if not self._stop.is_set() or self.stopped_at is None:
            return None
        return self.stopped_at + self.grace_seconds

    def register_inflight(self, closer):
        """登记一个在途响应的关闭器。返回 token；结束时务必 unregister。

        已经过期就**立刻**关闭 —— 停机发生在请求开始之后同样要管住。
        """
        tok = next(self._inflight_seq)
        with self._lock:
            self._inflight[tok] = {"closer": closer, "closed": False}
        dl = self.absolute_deadline()
        if dl is not None and self._clock() >= dl:
            self._close_inflight(only=tok)
        return tok

    def unregister_inflight(self, tok):
        with self._lock:
            self._inflight.pop(tok, None)

    def _close_inflight(self, only=None):
        """到点强制关闭。**关闭之后不注销登记** ——

        注销要由请求的持有方在真正结束时做（`close()` / `__exit__`）。
        若关了 socket 之后它仍留在登记表里，说明那个线程还卡在 I/O 上，
        这正是升级要检测的情形。关完就注销的话，永远也检测不到。
        """
        with self._lock:
            items = ([(only, self._inflight.get(only))] if only is not None
                     else list(self._inflight.items()))
        n = 0
        for tok, ent in items:
            if not ent or ent.get("closed"):
                continue
            try:
                ent["closer"]()
            except Exception:                                     # noqa: BLE001
                pass
            ent["closed"] = True
            n += 1
        if n:
            with self._lock:
                self.deadline_closures += n
        return n

    def _arm_deadline(self):
        """到期强制关闭在途响应；再过 escalate_after 仍未结束则升级。"""
        if self._deadline_timer is not None or not self.grace_seconds >= 0:
            return
        left = max(0.0, (self.absolute_deadline() or 0) - self._clock())
        t = threading.Timer(left, self._close_inflight)
        t.daemon = True
        self._deadline_timer = t
        t.start()
        if self.escalate_after and self.escalate_after > 0:
            t2 = threading.Timer(left + self.escalate_after, self._escalate)
            t2.daemon = True
            self._escalate_timer = t2
            t2.start()

    def _escalate(self):
        """到点关闭之后仍有在途请求 ⇒ 线程卡在 I/O 里。

        **先武装一个无条件的强制退出定时器，再调回调。**
        回调里可能要写日志/写 stderr，那些都可能阻塞（拿不到日志锁、
        fsync 卡住、管道写满）；一旦阻塞，`os._exit` 就永远执行不到，
        "最后兜底"本身失去上界（审查 v1.11 反例 2）。
        所以退出的时机不能取决于回调能不能跑完。
        """
        with self._lock:
            stuck_now = len(self._inflight)
        if stuck_now and self.force_exit_after is not None:
            t = threading.Timer(self.force_exit_after, self._hard_exit)
            t.daemon = True
            self._force_exit_timer = t
            t.start()
        return self._escalate_body()

    def _hard_exit(self):
        """无条件退出。

        **不写任何可能阻塞的东西。** 裸 `os.write(2, …)` 不等于非阻塞：
        stderr 若是写满的管道，它照样等在那里，`try/except` 打断不了
        一个仍在等待的写（审查 v1.12：预期 0.06s 退出，0.4s 后进程还活着）。
        所以先把 fd 2 设成非阻塞再试着写；设不了或写不进就直接放弃 ——
        诊断信息另有 `<evidence>.escalation` 这条不经过 stderr 的路。
        """
        try:
            os.set_blocking(2, False)
            os.write(2, b"[governor] forced exit: escalation deadline\n")
        except Exception:                                         # noqa: BLE001
            pass
        os._exit(3)

    def _escalate_body(self):
        """关闭 socket 之后仍有在途请求 ⇒ 线程卡在 I/O 里，关闭没能解开。

        这是最后一级：交给调用方登记的 `on_escalate` 处理（通常是落一条
        证据后强制退出）。**强制终止时不承诺 footer 完整** —— 已 fsync 的
        前缀可读，未完成部分交给检查点与恢复机制。
        """
        with self._lock:
            # 仍在登记表里的 = 关过 socket 但持有方还没结束 ⇒ 卡住了
            stuck = len(self._inflight)
            if stuck:
                self.escalations += 1
        if stuck and self.on_escalate is not None:
            try:
                self.on_escalate({"stuck_inflight": stuck,
                                  "grace_seconds": self.grace_seconds,
                                  "escalate_after": self.escalate_after,
                                  "reason": self._reason})
            except Exception:                                     # noqa: BLE001
                pass

    def pending_inflight(self):
        with self._lock:
            return len(self._inflight)

    def cancel_timers(self, keep_backstop_if_pending=True):
        """撤销定时器。

        **还有在途请求时不撤销最后兜底** —— 否则"运行已收尾"与
        "后台还卡着一个请求"会同时成立，而兜底已经没了
        （审查 v1.12 反例 1）。
        """
        names = ["_deadline_timer", "_escalate_timer", "_force_exit_timer"]
        if keep_backstop_if_pending and self.pending_inflight():
            # 升级链上的两个都要留：force_exit 要等 escalate 触发才武装
            names = ["_deadline_timer"]
        for name in names:
            t = getattr(self, name, None)
            if t is not None:
                try:
                    t.cancel()
                except Exception:                                 # noqa: BLE001
                    pass
                setattr(self, name, None)

    # ---- 停机后的请求闸门：给出**上界** ----
    @contextlib.contextmanager
    def winddown(self):
        """收尾窗口。窗口内允许有限次请求（做必要的复读/恢复核验）。

        窗口外，停机之后的任何请求一律拒绝 —— 主测量工作**立刻**停止发起，
        这样"信号之后还会发多少次请求"就有了确定上界，而不是取决于
        安全点埋得够不够密、也不取决于看门狗的巡检频率。
        """
        prev = getattr(self._wd, "on", False)
        self._wd.on = True
        try:
            yield
        finally:
            self._wd.on = prev

    def grace_remaining(self):
        """收尾窗口还剩多少秒。未停机返回 None；已超期返回 0.0。"""
        if not self._stop.is_set() or self.stopped_at is None:
            return None
        left = self.grace_seconds - (self._clock() - self.stopped_at)
        return max(0.0, left)

    def gate_request(self, kind="rpc"):
        """**逻辑请求**准入（RPC 与 Etherscan 的 acquire 路径）。

        `grace_calls` 对**两种口径同时**封顶，取先到者：逻辑请求数在这里扣，
        实际 HTTP 次数在 `gate_http()` 扣。一个逻辑请求可能对应多次 HTTP
        （底层对 503 会重试），所以两路都必须封 —— 只封逻辑层，重试会溜过去；
        只封 HTTP 层，底层被换成受控实现时就没有上界了。
        """
        if not self._stop.is_set():
            return
        with self._lock:
            self.calls_after_stop += 1
            if not getattr(self._wd, "on", False):
                raise Shutdown(self._reason or "stop_requested",
                               dict(self._detail, refused=kind, layer="logical",
                                    why="new work refused after stop"))
            self.winddown_logical += 1
            over = self.winddown_logical > self.grace_calls
        left = self.grace_remaining()
        if over or (left is not None and left <= 0):
            # 两个口径同时封顶：逻辑请求数在这里，实际 HTTP 次数在 gate_http()。
            # 底层被换成受控实现时没有真实 HTTP，只有逻辑层这一路还能封住上界。
            raise Shutdown("grace_exhausted",
                           dict(self._detail, layer="logical",
                                winddown_logical=self.winddown_logical,
                                grace_calls=self.grace_calls,
                                grace_remaining_s=left,
                                grace_seconds=self.grace_seconds))

    def gate_http(self):
        """**每一次真实 HTTP** 发出前调用 —— 含底层对 503 的重试。

        停机闸门只挂在逻辑层是不够的：`V.RPC` 内部的重试直接走 urlopen，
        绕过 `acquire()`，于是停机后仍会再发一次（审查 v19 反例 A）。
        返回本次允许的剩余收尾秒数（None 表示未停机、不设期限）。
        """
        if not self._stop.is_set():
            return None
        in_wd = getattr(self._wd, "on", False)
        with self._lock:
            if not in_wd:
                raise Shutdown(self._reason or "stop_requested",
                               dict(self._detail, layer="http",
                                    why="HTTP refused after stop (incl. retries)"))
            self.winddown_calls += 1
            over_calls = self.winddown_calls > self.grace_calls
        left = self.grace_remaining()
        if over_calls or left is None or left <= 0:
            raise Shutdown("grace_exhausted",
                           dict(self._detail, layer="http",
                                winddown_calls=self.winddown_calls,
                                grace_calls=self.grace_calls,
                                grace_remaining_s=left,
                                grace_seconds=self.grace_seconds))
        return left

    # ---- 硬兜底：内核强制，不依赖任何协作检查 ----
    def apply_hard_limits(self):
        """设置 RLIMIT。**这才是硬上限**，越界由内核处理，与代码是否检查无关。

        代价：触发点不可控 —— `RLIMIT_AS` 越界是任意位置的 `MemoryError`，
        `RLIMIT_CPU` 硬限是 `SIGKILL`。所以硬兜底触发时**不承诺证据完整**，
        只承诺已 fsync 的前缀可读；未完成的部分交给检查点与恢复机制。
        软阈值应设得比硬兜底低，让有序停机先发生。
        """
        self.hard_requested = bool(self.hard_rss_kb or self.hard_cpu_s)
        try:
            import resource as _r
        except ImportError:
            self.hard_applied = {"error": "resource module unavailable"}
            return self.hard_applied
        applied = {}
        if self.hard_rss_kb:
            want = int(self.hard_rss_kb) * 1024
            try:
                soft, hard = _r.getrlimit(_r.RLIMIT_AS)
                cap = want if hard in (_r.RLIM_INFINITY,) else min(want, hard)
                _r.setrlimit(_r.RLIMIT_AS, (cap, hard))
                # **读回核验**：setrlimit 返回不代表限额真的生效
                back_soft, _back_hard = _r.getrlimit(_r.RLIMIT_AS)
                applied["RLIMIT_AS"] = {
                    "bytes": cap, "readback": back_soft,
                    "verified": back_soft == cap,
                    "note": ("限的是地址空间，不等于 RSS；作为兜底偏保守。"
                             "越界为任意位置的 MemoryError")}
                if back_soft != cap:
                    applied["RLIMIT_AS"]["error"] = (
                        f"readback mismatch: wanted {cap}, got {back_soft}")
            except (ValueError, OSError) as e:
                applied["RLIMIT_AS"] = {"error": str(e)[:120], "verified": False}
        if self.hard_cpu_s:
            want = int(self.hard_cpu_s)
            try:
                soft, hard = _r.getrlimit(_r.RLIMIT_CPU)
                hard_cap = want + 5 if hard == _r.RLIM_INFINITY else min(want + 5, hard)
                _r.setrlimit(_r.RLIMIT_CPU, (want, hard_cap))
                back_soft, back_hard = _r.getrlimit(_r.RLIMIT_CPU)
                applied["RLIMIT_CPU"] = {
                    "soft_s": want, "hard_s": hard_cap,
                    "readback": [back_soft, back_hard],
                    "verified": back_soft == want,
                    "note": "软限发 SIGXCPU（可捕获→有序停机），硬限 SIGKILL"}
                if back_soft != want:
                    applied["RLIMIT_CPU"]["error"] = (
                        f"readback mismatch: wanted {want}, got {back_soft}")
            except (ValueError, OSError) as e:
                applied["RLIMIT_CPU"] = {"error": str(e)[:120], "verified": False}
        self.hard_applied = applied
        return applied

    def hard_limit_problems(self):
        """请求过硬兜底但没装上 ⇒ 返回问题清单（空表示没问题）。

        **不能只在报告角落留一个 error 就继续跑**：使用者要的控制没生效，
        前置条件就不成立（审查 v19 反例 1）。
        """
        if not (self.hard_rss_kb or self.hard_cpu_s):
            return []                      # 没要求硬兜底，不算问题
        a = self.hard_applied
        if not a:
            return [{"limit": "*", "reason": "apply_hard_limits() 未被调用"}]
        if "error" in a and len(a) == 1:
            return [{"limit": "*", "reason": a["error"]}]
        problems = []
        for name, want in (("RLIMIT_AS", self.hard_rss_kb),
                           ("RLIMIT_CPU", self.hard_cpu_s)):
            if not want:
                continue
            got = a.get(name)
            if got is None:
                problems.append({"limit": name, "reason": "requested but not applied"})
            elif got.get("error") or got.get("verified") is not True:
                problems.append({"limit": name,
                                 "reason": got.get("error", "not verified"),
                                 "detail": got})
        return problems

    @property
    def stopping(self):
        return self._stop.is_set()

    @property
    def reason(self):
        return self._reason

    @property
    def detail(self):
        return dict(self._detail)

    def raise_if_stopping(self, where=None):
        """安全点检查。停机中则抛 `Shutdown`，由调用方有序收尾。"""
        if self._stop.is_set():
            raise Shutdown(self._reason or "stop_requested",
                           dict(self._detail, where=where))

    # ---- 看门狗 ----
    def start(self):
        if self._thread is not None or not any(
                (self.max_rss_kb, self.max_cpu_s, self.max_wall_s)):
            return self
        def loop():
            # 用 _done 收工，**不能**用 _stop —— 正常关闭若置 _stop，
            # `stopping` 会变真，没设限额的运行也会被判成"停机"
            while not self._done.wait(self.poll_s):
                if self.check():
                    return
        self._thread = threading.Thread(target=loop, daemon=True,
                                        name="resource-governor")
        self._thread.start()
        return self

    def close(self):
        self._done.set()
        self.cancel_timers()          # 有在途请求时保留最后兜底
        t = self._thread
        if t is not None:
            t.join(timeout=2.0)
        self._thread = None

    def report(self):
        lat = (round(self._clock() - self.stopped_at, 3)
               if self.stopped_at is not None else None)
        return {"limits": self.limits(), "final": self.snapshot(),
                "watchdog_observations": self.observations,
                "stopped": self.stopping, "stop_reason": self._reason,
                "stop_detail": self.detail,
                "stop_latency_s": lat,             # 从置标志到收尾结束的实测耗时
                "requests_refused_or_graced_after_stop": self.calls_after_stop,
                "winddown_http_requests": self.winddown_calls,
                "winddown_logical_requests": self.winddown_logical,
                "absolute_deadline_closures": self.deadline_closures,
                "escalations": self.escalations,
                "pending_inflight": self.pending_inflight(),
                "backstop_armed": self._force_exit_timer is not None,
                "deadline_basis": ("absolute wall-clock deadline on the whole "
                                   "response (socket timeout alone is a per-read "
                                   "inactivity timeout, not a completion deadline)"),
                "peak_basis": "kernel VmHWM (measured high-water mark, not a sample)"}


class SharedGate:
    """
    **全局**限流与调用预算闸门 —— 两路并行共用一份，不是各分一半。

    只在锁内占用「发车时刻」与预算计数，HTTP 请求本身在锁外执行，
    因此限流是全局的、I/O 仍可并发。各 worker 的 `V.RPC` 自身限流设为不生效
    （rps 极大），真正的节流由本闸门统一施加，从而复用已验证的 RPC 实现而不改它。

    计数字段见 `stats()`：`http_sent` 才是实际发出次数，`http_reserved` 是预算口径。
    （旧的 `calls` 别名已删除 —— 它名为实际、实为预留。）

    限流与预算施加在**真实 HTTP 边界**（`install_http_gate` 包住 urlopen），
    不是逻辑请求边界：`V.RPC` 对 429/502/503/504 会在自己内部重试一次，
    那次重试同样是一次真实 HTTP，必须同样排队、同样计数（审查反例 9/retry）。
    因此 `calls` 是**实际发生的 HTTP 次数**，不再是预留额度。

    `acquire()` 退化为逻辑请求的登记与**预检**（至少还能负担一次 HTTP、
    时间未到截止），真正的节流/扣减在 `acquire_http()`。
    """

    def __init__(self, rps, max_calls, max_seconds):
        self.lock = threading.Lock()
        self.interval = 1.0 / rps if rps > 0 else 0.0
        self.next_slot = 0.0
        # 三个计数分开，不能混为一谈（审查 v1.5 反例 3）：
        #   reserved —— 已占用的额度，**预算判定的依据**；并发下必须先占后发，
        #               否则两个线程可能同时通过检查而一起越界。
        #   sent     —— 真正交给传输层的次数，**唯一可当作实际网络调用量**的数。
        #   rejected_after_wait —— 占了额度、排队后被时间闸门拒绝，请求并未发出。
        # 恒等式：reserved == sent + rejected_after_wait + (正在途中的)
        self.reserved = 0
        self.sent = 0
        self.rejected_after_wait = 0
        self.logical = 0                # 逻辑请求次数
        self.max_calls = max_calls
        self.max_seconds = max_seconds
        self.started = time.monotonic()
        self.per_worker = {}
        self.per_worker_reserved = {}
        self.per_worker_sent = {}
        self.governor = None          # 由 measure() 挂上；停机后的请求闸门
        self._ctx = threading.local()

    # 刻意**不**保留 `calls` 这个名字：它正是"名为实际、实为预留"的来源
    # （审查 v1.5 反例 3）。调用方必须明写 reserved 还是 sent。

    # ---- 逻辑请求层：登记归属 + 扣逻辑额度（不排队，排队在 HTTP 层）----
    def acquire(self, worker=None, kind="rpc"):
        """`max_calls` 对**两种口径同时**封顶，取先到者：

        * 逻辑请求数（这里扣）—— 底层被替换成受控实现时，这一路仍然封顶；
        * 实际 HTTP 次数（`acquire_http` 扣）—— 含 `V.RPC` 内部重试。

        真实运行里 HTTP ≥ 逻辑，先撞上限的是 HTTP；受控测试里没有 HTTP，
        先撞上限的是逻辑。两路都封，才不会出现"某一口径超了上限"。
        """
        # 停机后由治理器决定这次请求能不能发 —— RPC 与 Etherscan 共用此路径，
        # 因此"停机之后最多还会发多少次请求"有确定上界（审查 v18 反例 2）
        if self.governor is not None:
            self.governor.gate_request(kind)
        self._ctx.attr = (worker, kind)
        with self.lock:
            if self.logical + 1 > self.max_calls:
                raise BudgetExhausted("shared call budget exhausted (logical requests)")
            if self.reserved + 1 > self.max_calls:
                raise BudgetExhausted("shared call budget exhausted (http)")
            if time.monotonic() - self.started >= self.max_seconds:
                raise BudgetExhausted("shared time budget exhausted")
            self.logical += 1
            k = (worker, kind)
            self.per_worker[k] = self.per_worker.get(k, 0) + 1

    # ---- 真实 HTTP 层：排队 + 扣额度。重试也从这里过 ----
    def acquire_http(self):
        """在发出**每一次**真实 HTTP 之前调用。抛出即表示该 HTTP 未发生。

        这里只**占额度**并排队；额度是保守的（占了就不退，避免并发下越界），
        所以它不等于实际发出次数。真正发出时由 `note_sent()` 另计。
        """
        k = getattr(self._ctx, "attr", (None, "unattributed"))
        with self.lock:
            if self.reserved + 1 > self.max_calls:
                raise BudgetExhausted("shared call budget exhausted (http)")
            if time.monotonic() - self.started >= self.max_seconds:
                raise BudgetExhausted("shared time budget exhausted")
            self.reserved += 1
            self.per_worker_reserved[k] = self.per_worker_reserved.get(k, 0) + 1
            now = time.monotonic()
            slot = max(now, self.next_slot)
            self.next_slot = slot + self.interval
        wait = slot - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        # 等待可能把发车推过截止（反例 12）——此时该 HTTP 仍未发出。
        # 额度保守地不退还，但必须记成"未发出"，不能计进实际次数。
        if time.monotonic() - self.started >= self.max_seconds:
            with self.lock:
                self.rejected_after_wait += 1
            raise BudgetExhausted("shared time budget exhausted after wait")
        # 排队期间可能刚好停机 / 收尾预算刚好耗尽 —— 等待之后必须**再核一次**，
        # 否则排在队里的请求会带着过期的许可发出去。
        if self.governor is not None:
            try:
                return self.governor.gate_http()
            except Exception:
                with self.lock:
                    self.rejected_after_wait += 1
                raise
        return None

    def note_sent(self):
        """在**真正调用传输层之前**登记一次实际发出。"""
        k = getattr(self._ctx, "attr", (None, "unattributed"))
        with self.lock:
            self.sent += 1
            self.per_worker_sent[k] = self.per_worker_sent.get(k, 0) + 1

    def stats(self):
        def fold(d):
            per = {}
            for (w, kind), v in d.items():
                per.setdefault(str(w), {})[kind] = v
            return per
        return {"http_sent": self.sent,                     # 实际网络调用量
                "http_reserved": self.reserved,             # 预算口径（保守，不退还）
                "http_rejected_after_wait": self.rejected_after_wait,
                "max_calls": self.max_calls,
                "logical_requests": self.logical,
                "http_sent_per_worker": fold(self.per_worker_sent),
                "http_reserved_per_worker": fold(self.per_worker_reserved),
                "logical_per_worker": fold(self.per_worker),
                "interval_s": self.interval,
                "elapsed_s": round(time.monotonic() - self.started, 2),
                "note": ("http_reserved 是预算口径，占用后即使请求未发出也不退还；"
                         "只有 http_sent 可当作实际网络调用量。")}


# --------------------------------------------------------------------------
# 真实 HTTP 边界的闸门。`V.RPC` 与 Etherscan 都直接调用 urllib.request.urlopen，
# 重试也在其内部；只有在这一层包住，全局速率/预算才是闭合的。
# 传输层留一个可注入点 `transport`，测试可以在**闸门之下**换掉传输，
# 从而在真实边界上验证节流，而不是绕过闸门。
# --------------------------------------------------------------------------
class _DeadlineResponse:
    """给响应对象套上**绝对完成期限**。

    冻结包里是 `with urlopen(...) as r: r.read(N)` —— 只把 timeout 传下去
    管不住分段慢响应：每段都在 timeout 内到达，整段却可以拖很久。
    这里做两件事：

    1. 每次 `read` 前后核对绝对期限，超了就抛 `Shutdown`；
    2. 把自己登记到治理器，让到点的定时器**强制 close 底层 socket** ——
       这是唯一能解开"已经阻塞在 read 里"的手段。
    """

    def __init__(self, resp, gov):
        self._resp = resp
        self._gov = gov
        self._tok = gov.register_inflight(self._force_close)
        # 连接阶段登记的 token 一并接管：响应关闭时统一注销
        self._conn_tokens = list(getattr(resp, "_rt_conn_tokens", ()))

    def _release_tokens(self):
        self._gov.unregister_inflight(self._tok)
        for t in self._conn_tokens:
            self._gov.unregister_inflight(t)
        self._conn_tokens = []

    def _force_close(self):
        """真正解开已经阻塞的 read —— 只调 `response.close()` 关不掉，
        必须 `shutdown(SHUT_RDWR)` 底层 socket。见 `_force_close_response`。"""
        _force_close_response(self._resp)

    def _expired(self):
        dl = self._gov.absolute_deadline()
        return dl is not None and time.monotonic() >= dl

    def _raise(self):
        self._release_tokens()          # 放弃这次请求 ⇒ 交还登记，别留陈旧项
        raise Shutdown("wall_deadline_exceeded",
                       {"layer": "response",
                        "grace_seconds": self._gov.grace_seconds,
                        "why": "absolute completion deadline passed"})

    def read(self, *a, **kw):
        if self._expired():
            self._force_close()
            self._raise()
        try:
            data = self._resp.read(*a, **kw)
        except Exception:                                         # noqa: BLE001
            if self._expired():
                self._raise()      # 到点强制关闭导致的读失败 ⇒ 如实归因为停机
            raise
        if self._expired():
            # 分段响应可能在期限内读到一部分，整段却已超期 —— 结果不可用
            self._force_close()
            self._raise()
        return data

    def close(self):
        self._release_tokens()
        return self._resp.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._release_tokens()
        ex = getattr(self._resp, "__exit__", None)
        return ex(*exc) if ex else None

    def __getattr__(self, name):
        return getattr(self._resp, name)


#: 监督线程的轮询粒度。停机后最多多等这么久才发现超期。
_SUPERVISE_TICK_S = 0.02

_HTTP = {"orig": None, "gate": None, "transport": None, "installed": False}


def _gated_urlopen(*a, **kw):
    gate = _HTTP["gate"]
    deadline = None
    if gate is not None:
        # acquire_http 会在排队之后再核一次停机，并返回剩余收尾秒数
        deadline = gate.acquire_http()
        gate.note_sent()          # 紧挨着传输调用登记，中间不再有可能抛出的判定
    if deadline is not None:
        # 把收尾期限压到这次请求的 timeout 上（管住"一直没数据"的情形）。
        old = kw.get("timeout")
        kw["timeout"] = deadline if old is None else min(old, deadline)
    fn = _HTTP["transport"] or _HTTP["orig"]
    gov = getattr(gate, "governor", None) if gate is not None else None
    if gov is None:
        return fn(*a, **kw)
    # **始终**走监督路径：停机可能发生在调用已经进入传输之后（比如正在收
    # 响应头），那时调用方已经阻塞在里面，没有线程跳转就唤不醒
    # （审查 v1.11：stop_during_headers 实测 0.421s）。
    resp = _supervised_open(fn, gov, a, kw)
    # 再套一层**绝对完成期限**，覆盖响应体的分段慢流
    return _DeadlineResponse(resp, gov) if hasattr(resp, "read") else resp


class _RecordingHTTPConnection(http.client.HTTPConnection):
    """连接建立后**立刻**把 socket 登记到治理器。

    这样停机时定时器能直接 `shutdown()` 它，**阻塞在 read 的调用线程自己**
    就被唤醒 —— 不需要为每个请求另开线程，也不需要轮询。
    """

    _ctx = threading.local()      # 由 _supervised_open 在调用前后设置

    def connect(self):
        super().connect()
        _record_conn(self.sock)


class _RecordingHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        super().connect()
        _record_conn(self.sock)


def _record_conn(sock):
    """连接刚建好就登记 socket，并把 token 记到本次调用的收集器里。

    **token 的归属只有一个**：谁发起这次调用，谁负责注销。
    （上一版由工作线程持有、调用方放弃后无人注销，登记项会变成陈旧证据，
    可能导致错误升级 —— 审查 v1.12 反例 1。）
    """
    ctx = getattr(_RecordingHTTPConnection._ctx, "cur", None)
    if ctx is None or sock is None:
        return
    gov, tokens = ctx
    tokens.append(gov.register_inflight(_socket_closer(sock)))


def _socket_closer(sock):
    def close():
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except (OSError, ValueError):
            pass
        try:
            sock.close()
        except (OSError, ValueError):
            pass
    return close


class _RecordingHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_RecordingHTTPConnection, req)


class _RecordingHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_RecordingHTTPSConnection, req)


_RECORDING_OPENER = None
_RECORDING_LOCK = threading.Lock()


def _recording_opener():
    global _RECORDING_OPENER
    if _RECORDING_OPENER is None:
        _RECORDING_OPENER = urllib.request.build_opener(
            _RecordingHTTPHandler, _RecordingHTTPSHandler)
    return _RECORDING_OPENER


def _supervised_open(fn, gov, a, kw):
    """在**发出请求之前**就把这次操作纳入监督，覆盖连接/发送/收响应头整段。

    实现方式：用一个会在 `connect()` 后立刻登记 socket 的 opener。
    停机时定时器 `shutdown()` 那个 socket，**当前线程**（正阻塞在 read 上的
    那个）立刻被唤醒 —— 不额外开线程、不轮询，稳态开销为零。

    上一版为了同样的目的给每个请求开了工作线程 + 20ms 轮询，代价是
    每请求一个线程、外加最多 20ms 的发现延迟，而且线程的生命周期与
    登记项的归属容易脱节（审查 v1.12 反例 1）。这里换成把 socket 交给
    定时器，归属只有一个：谁建的连接谁负责注销。

    仍有一段管不住：**TCP 连接建立本身**（还没有 socket）。它由
    socket timeout 约束，停机时该 timeout 已被压到剩余收尾时间。
    """
    transport = _HTTP["transport"]
    if transport is not None:
        # 测试注入了受控传输：没有真实 socket 可登记，登记一个占位，
        # 让升级语义仍可被测；调用方直接同步执行。
        tok = gov.register_inflight(lambda: None)
        try:
            return fn(*a, **kw)
        finally:
            gov.unregister_inflight(tok)
    tokens = []
    _RecordingHTTPConnection._ctx.cur = (gov, tokens)
    try:
        resp = _recording_opener().open(*a, **kw)
    except BaseException:
        for t in tokens:
            gov.unregister_inflight(t)        # 放弃/失败 ⇒ 立刻交还，不留陈旧登记
        left = gov.grace_remaining()
        if left is not None and left <= 0:
            # 到点强制 shutdown 掉 socket 导致的失败：**如实归因为停机**，
            # 不能让它看起来像普通的传输故障（那会把"我们主动掐断"
            # 说成"对端出问题"）。
            raise Shutdown("wall_deadline_exceeded",
                           {"layer": "request",
                            "phase": "connect/send/headers",
                            "grace_seconds": gov.grace_seconds,
                            "why": "socket closed by deadline before response"})
        raise
    finally:
        _RecordingHTTPConnection._ctx.cur = None
    # 成功：token 随响应一起交给 _DeadlineResponse，响应关闭时注销
    resp._rt_conn_tokens = tokens
    return resp


def _force_close_response(resp):
    """触到底层 socket 才能真正打断阻塞的读。"""
    sock = None
    try:
        sock = resp.fp.raw._sock
    except AttributeError:
        for attr in ("_sock", "sock", "raw"):
            sock = getattr(resp, attr, None)
            if hasattr(sock, "shutdown"):
                break
            sock = None
    if sock is not None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except (OSError, ValueError):
            pass
        try:
            sock.close()
        except (OSError, ValueError):
            pass
    try:
        resp.close()
    except Exception:                                             # noqa: BLE001
        pass


def install_http_gate(gate, transport=None):
    """把全局闸门装到 urlopen 上。幂等；返回 gate。"""
    if not _HTTP["installed"]:
        _HTTP["orig"] = urllib.request.urlopen
        urllib.request.urlopen = _gated_urlopen
        _HTTP["installed"] = True
    _HTTP["gate"] = gate
    if transport is not None:
        _HTTP["transport"] = transport
    return gate


def uninstall_http_gate():
    if _HTTP["installed"]:
        urllib.request.urlopen = _HTTP["orig"]
        _HTTP["installed"] = False
    _HTTP.update({"gate": None, "transport": None})


def http_gate_installed():
    return _HTTP["installed"] and _HTTP["gate"] is not None


def verify_evidence_supports(path, *, run_id, candidate, result_sha256,
                             binding=None, ignore_runs=()):
    """核验一份证据文件**确实支持**被复用的那条结果。

    文件自身结构完整，不代表它跟这条结果有任何关系 —— 换成另一个运行的
    完整证据同样"结构完整"（审查 v1.5 反例 1）。所以必须逐项对上：

    1. 文件可读、且（排除进行中的运行后）结构完整；
    2. 里面**存在**记录中的那个 `run_id`；
    3. 该运行有 `run_header`，且其绑定（脚本/证据模块/规格/样本/台账/finalized 块）
       与检查点绑定一致；
    4. 该运行里有这个候选的 `candidate_result`，且其 `record` 的规范 hash
       等于检查点记的 `result_sha256`。

    返回问题清单（空列表表示通过）。
    """
    problems = []
    p = Path(path)
    if not p.is_file():
        return [{"reason": "evidence_file_missing", "path": str(path)}]
    try:
        recs, diag = read_evidence(p, report=True, ignore_runs=ignore_runs)
    except OSError as e:
        return [{"reason": "evidence_unreadable", "path": str(path),
                 "error": str(e)[:120]}]
    if not diag.get("complete"):
        problems.append({"reason": "evidence_incomplete", "path": str(path),
                         "diag": {k: diag[k] for k in
                                  ("bad_lines", "mid_file_corruption", "empty",
                                   "unmatched_rpc_begin", "orphan_rpc_end",
                                   "duplicate_pending_id", "runs_without_footer",
                                   "runs_without_header") if k in diag}})
    mine = [r for r in recs if r.get("run_id") == run_id]
    if not mine:
        # 最要命的一种：文件很完整，但根本不是这次运行的证据
        problems.append({"reason": "evidence_run_id_absent", "path": str(path),
                         "want_run_id": run_id,
                         "runs_present": sorted({str(r.get("run_id")) for r in recs})})
        return problems

    headers = [r for r in mine if r.get("kind") == "run_header"]
    if not headers:
        problems.append({"reason": "evidence_run_header_missing",
                         "path": str(path), "run_id": run_id})
    elif binding:
        h = headers[0]
        snap = h.get("finalized_snapshot") or {}
        _MISSING = object()
        pairs = [("script_sha256", h.get("script_sha256", _MISSING),
                  binding.get("script_sha256")),
                 ("evidence_module_sha256", h.get("evidence_module_sha256", _MISSING),
                  binding.get("evidence_module_sha256")),
                 ("spec_sha256", h.get("spec_sha256", _MISSING),
                  binding.get("spec_sha256")),
                 ("sample_sha256", h.get("sample_sha256", _MISSING),
                  binding.get("sample_sha256")),
                 ("universe_sha256", h.get("universe_sha256_now", _MISSING),
                  binding.get("universe_sha256")),
                 ("finalized_number", snap.get("number", _MISSING),
                  binding.get("finalized_number")),
                 ("finalized_hash", snap.get("hash", _MISSING),
                  binding.get("finalized_hash"))]
        # 检查点绑定里有值的字段，运行头里**必须存在**。
        # 旧写法是 `if a is not None and a != b`，字段一旦被删就直接跳过 ——
        # 六个绑定字段全都能靠"删掉"绕过（审查 v16）。缺失比不符更可疑，不是更安全。
        missing = [k for k, a, b in pairs if a is _MISSING and b is not None]
        diffs = {k: {"evidence": a, "checkpoint": b}
                 for k, a, b in pairs if a is not _MISSING and a != b}
        if missing:
            problems.append({"reason": "evidence_binding_field_missing",
                             "path": str(path), "run_id": run_id, "fields": missing})
        if diffs:
            problems.append({"reason": "evidence_binding_mismatch",
                             "path": str(path), "run_id": run_id, "diff": diffs})

    hits = [r for r in mine
            if r.get("kind") == "candidate_result" and r.get("candidate") == candidate]
    if not hits:
        problems.append({"reason": "candidate_result_absent_in_evidence",
                         "path": str(path), "run_id": run_id, "candidate": candidate})
        return problems
    got = [result_sha256_of(r.get("record")) for r in hits]
    if result_sha256 not in got:
        problems.append({"reason": "candidate_result_hash_mismatch",
                         "path": str(path), "run_id": run_id, "candidate": candidate,
                         "checkpoint": result_sha256, "evidence": got})
    return problems


def result_sha256_of(obj):
    return None if obj is None else result_sha256(obj)


def read_evidence(path, *, report=False, ignore_runs=()):
    """读取证据。

    **尾部截断**（最后一行不完整）与**中间损坏**必须区分：前者是中断的正常后果，
    后者说明文件被改动或写坏，正式验收不得当作完整。返回 (recs, bad_line_count)；
    report=True 时返回 (recs, diag)，diag 含损坏位置、seq 连续性、运行归属与结束记录。

    `ignore_runs`：诊断时排除这些 run_id。用于**正在进行中的本次运行** ——
    它此刻当然还没有运行尾，不该因此把同一文件里的历史运行判成不完整。
    被排除的记录仍在返回的 recs 里，只是不参与完整性判定。
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
    ignore = set(ignore_runs)
    judged = [r for r in recs if r.get("run_id") not in ignore] if ignore else recs
    runs = {}
    for r in judged:
        runs.setdefault(r.get("run_id"), []).append(r.get("seq"))
    gaps = {}
    for rid, seqs in runs.items():
        want = list(range(1, len(seqs) + 1))
        if sorted(s for s in seqs if s is not None) != want:
            gaps[rid] = {"seen": sorted(s for s in seqs if s is not None), "expected_n": len(seqs)}
    footers = {r.get("run_id") for r in judged if r.get("kind") == "run_footer"}
    headers = {r.get("run_id") for r in judged if r.get("kind") == "run_header"}

    def key(r):
        return (r.get("run_id"), r.get("pending_id"), r.get("worker"))

    begin_list = [key(r) for r in judged if r.get("kind") == "rpc_begin"]
    end_list = [key(r) for r in judged if r.get("kind") == "rpc_end"]
    begins, ends = set(begin_list), set(end_list)
    unmatched = sorted(str(x) for x in (begins - ends))
    # 反方向同样是缺陷：有完成记录却没有对应的发起记录，说明前缀被删或被改
    orphan_ends = sorted(str(x) for x in (ends - begins))
    dup = sorted(str(k) for k in begins if begin_list.count(k) > 1)
    dup += sorted(str(k) for k in ends if end_list.count(k) > 1)
    # 合法运行必须有运行头：只有尾没有头 ⇒ 结构不完整
    no_header = sorted(x for x in runs if x and x not in headers)
    empty = not judged
    diag = {"bad_lines": bad, "tail_truncation_only": tail_only,
            "ignored_runs": sorted(str(x) for x in ignore),
            "unmatched_rpc_begin": unmatched,
            "orphan_rpc_end": orphan_ends,
            "duplicate_pending_id": dup,
            "empty": empty,
            "mid_file_corruption": bool(bad) and not tail_only,
            "runs": {k: len(v) for k, v in runs.items()},
            "seq_gaps": gaps,
            "runs_with_footer": sorted(x for x in footers if x),
            "runs_without_footer": sorted(x for x in runs if x and x not in footers),
            "runs_without_header": no_header,
            "complete": (not empty                  # 空文件不是"完整"，是没有证据
                         and (not bad or tail_only) and not gaps
                         and not unmatched          # 有请求发出但结果未知 ⇒ 不完整
                         and not orphan_ends        # 有结果却无发起记录 ⇒ 前缀缺失
                         and not dup                # pending_id 必须唯一配对
                         and not no_header
                         and all(x in footers for x in runs if x))}
    return recs, diag
