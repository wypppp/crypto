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
import hashlib, itertools, json, os, threading, time, urllib.request, uuid
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


class SharedGate:
    """
    **全局**限流与调用预算闸门 —— 两路并行共用一份，不是各分一半。

    只在锁内占用「发车时刻」与预算计数，HTTP 请求本身在锁外执行，
    因此限流是全局的、I/O 仍可并发。各 worker 的 `V.RPC` 自身限流设为不生效
    （rps 极大），真正的节流由本闸门统一施加，从而复用已验证的 RPC 实现而不改它。

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
_HTTP = {"orig": None, "gate": None, "transport": None, "installed": False}


def _gated_urlopen(*a, **kw):
    gate = _HTTP["gate"]
    if gate is not None:
        gate.acquire_http()
        gate.note_sent()          # 紧挨着传输调用登记，中间不再有可能抛出的判定
    fn = _HTTP["transport"] or _HTTP["orig"]
    return fn(*a, **kw)


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
        pairs = [("script_sha256", h.get("script_sha256"), binding.get("script_sha256")),
                 ("evidence_module_sha256", h.get("evidence_module_sha256"),
                  binding.get("evidence_module_sha256")),
                 ("spec_sha256", h.get("spec_sha256"), binding.get("spec_sha256")),
                 ("sample_sha256", h.get("sample_sha256"), binding.get("sample_sha256")),
                 ("universe_sha256", h.get("universe_sha256_now"),
                  binding.get("universe_sha256")),
                 ("finalized_number", snap.get("number"), binding.get("finalized_number")),
                 ("finalized_hash", snap.get("hash"), binding.get("finalized_hash"))]
        diffs = {k: {"evidence": a, "checkpoint": b}
                 for k, a, b in pairs if a is not None and a != b}
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
