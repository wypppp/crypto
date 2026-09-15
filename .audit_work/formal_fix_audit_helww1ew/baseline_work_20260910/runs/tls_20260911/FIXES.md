# 连接全过程的停机监督：DNS / TCP / TLS（规格 v1.14）

对应审核：`audit_v113_20260911/REVIEW.md`。源码 hash 见 `source_hashes.json`。
规格 **v1.14**（`f8dc892cca096369…`）；v1.13（`32a0805cd2822d6d…`）、v1.12 原始字节未动。
**§1–§4 测量判据一字未改。未跑真链。正式冻结与 300 样本仍关闭。**

TLS 观测已在同字节源码（`evidence.py` = `b45707a8…`）上复现：TLS 期间登记 0、升级 0、停机后 0.525s。

## 一、我在 v1.13 的声明范围错了

v1.13 写的是「仍有一段管不住：TCP 连接建立本身」。审核指出 TLS 握手也管不住；
按审核要求逐阶段核对后，实际是 **DNS、TCP 建连、TLS 握手三段都不在监督之内**，
其中 **DNS 完全没有上界**。旧快照实测（反向验证日志 `test_audit_followup.ON_PREFIX_CODE.log`）：

| 阶段 | v1.13 快照 | v1.14 |
|---|---|---|
| DNS（`getaddrinfo` 卡 30s） | 登记 **0**，进程**一直不退出**（rc=9） | 登记 1，升级兜底强制退出（**rc=3**） |
| TCP 建连（socket timeout 3s） | **2.927s**（等满 timeout） | **0.169s** |
| TLS 握手（TCP 已建立） | 登记 **0**，**0.822s** | 登记 1，**0.16s** |

## 二、先实测各阶段"能被什么打断"，再设计

从另一线程打断阻塞中的各阶段（本机 loopback）：

| 阶段 | 操作 | 结果 |
|---|---|---|
| TCP connect | `shutdown()` | **能**，0.151s |
| TCP connect | `close()` | **不能**，等满 2s timeout |
| TLS 握手 | 原 socket 的 `dup().shutdown()` | **能**，0.153s |
| DNS | — | 无 socket，**不可中断** |

`close()` 打断不了 `connect()` 这一条很关键 —— 凭直觉很容易选错。

## 三、实现

**从 DNS 之前**就把整次操作登记为一个在途项（`_OpHandle`），关闭器作用于
「当前阶段能打断的句柄」，句柄随阶段推进而替换：

* **TCP**：`HTTPConnection` 通过 `self._create_connection` 建连，换成
  `_supervised_create_connection` —— 与 `socket.create_connection` 等价，
  唯一区别是 socket 在 `connect()` **之前**就交给句柄。
* **TLS**：`wrap_socket` 会接管原 socket 的 fd，握手期间原 socket 对象已 detach。
  所以握手前先 `dup()` 一份作句柄；shutdown 作用于连接本身而非某个 fd，
  能立刻打断握手。之后的响应阶段也沿用这份 dup，**不在另一线程里改动 SSLSocket 内部状态**。
* **DNS**：没有句柄。操作已登记在途，所以升级机制看得见它；截止时关闭器无事可做，
  登记项留着 → 升级 → 无条件强制退出。**上界 = grace + escalate_after + force_exit_after，
  结局是进程退出（rc=3），不是当前请求抛 `Shutdown`。** 这是 DNS 在进程内不可中断的必然代价。

**证书校验没有被削弱**：`_RecordingHTTPSHandler` 沿用标准库的 context 与
`check_hostname`。实测：不信任测试证书时照样 `CERTIFICATE_VERIFY_FAILED`。

## 四、顺带修掉一处归因竞态

全量测试中第 20 节偶发 `RpcFailure: Non-JSON RPC response`。根因：`_expired()`
只比较时钟，而 `threading.Timer` 可能比单调时钟的截止点**早一丝**触发 ——
打断后 `read` 带着截断数据返回时，时钟判断还没到期，截断的 JSON 就被当成
正常结果交给了 `V.RPC`。

改为**先看是否真的打断过，再看时钟**：归因依据实际发生的事，而不是时钟读数。
同场景（停机前发起 / 在途停机）各连跑 20 次：**40/40 全部正确归因为 `Shutdown`**。

## 五、实测汇总

真实 urllib + 冻结包 RPC + 本机 loopback，期限 0.15s（`phase_probe.log`、`verify_and_dns_probe.log`）：

| 场景 | 结果 | 停机后耗时 |
|---|---|---:|
| TLS 握手中停机 | `Shutdown(tls_handshake)`，握手期间登记 1 | 0.16s |
| TCP 建连中停机（socket timeout 3s） | `Shutdown(tcp_connect)` | 0.169s |
| 真实 TLS 慢响应体（停机后发起） | `Shutdown(response)` | 0.16s |
| **HTTPS 未停机对照（校验开启）** | **`0x1`，无残留登记** | — |
| 不信任证书 | `CERTIFICATE_VERIFY_FAILED` | — |
| DNS 卡 30s | DNS 期间登记 1，**rc=3** | 子进程 0.643s（含解释器启动） |

开销（交替 A/B，300 对）：逐对差 **+0.09ms**（中位数 +0.06，标准差 2.56），
测量期间创建线程 **0** —— HTTPS 改动没有给热路径加成本。

## 六、回归守卫与反向验证

`test_audit_followup.py` 新增 §23（10 项）。HTTPS 场景由子进程运行探针
（隔离 socket/线程/环境变量），通过 `RT_CODE_ROOT` 指向被测代码 ——
反向验证时指向旧快照。缺 openssl 时 HTTPS 场景**判失败而非跳过**。

| 被测源码 | 结果 |
|---|---|
| 修复后 `44f54f2c…` / `1fe5c43c…` | **226 通过 / 0 失败，退出 0** |
| 修复前（v1.13 快照 `b45707a8…`） | **221 通过 / 5 失败** |

审查方 `reproduce_tls.py` 现退出 1（缺口不再复现）；`verify_exit.py` 仍退出 0（满 stderr 退出修复未回退）。

## 七、复跑方法

```
$ cd /home/ancillary/rightTail/baseline_work_20260910
$ python3 test_evidence.py     # 0/29    $ python3 test_resume.py         # 0/23
$ python3 test_first_mint.py   # 0/17    $ python3 test_parallel.py       # 0/23
$ python3 test_step3.py        # 0/27    $ python3 test_audit_fixes.py    # 0/34
$ python3 test_step4.py        # 0/18    $ python3 test_audit_followup.py # 0/226
$ python3 test_e2e_blocking.py # 0/41
                               # 合计 438 项断言，9 个入口全部退出 0

# 逐阶段探针需要一份本机测试证书（不入库，用完即弃）：
$ openssl req -x509 -newkey rsa:2048 -nodes -keyout /tmp/k.pem -out /tmp/c.pem \
      -days 1 -subj /CN=127.0.0.1 -addext subjectAltName=IP:127.0.0.1
$ SSL_CERT_FILE=/tmp/c.pem python3 runs/tls_20260911/phase_probe.py /tmp/c.pem /tmp/k.pem
$ env -u SSL_CERT_FILE python3 runs/tls_20260911/verify_and_dns_probe.py /tmp/c.pem /tmp/k.pem
```

## 八、仍未关闭

- **真链串行/并行同快照对照未做。** 本轮未启动，等放行。
- **DNS 的上界是进程退出，不是干净中止。** 在进程内打断不了 `getaddrinfo`；
  若要干净中止，需要把解析放到可被杀掉的独立进程或换成可取消的异步解析器 ——
  本轮没做，只保证了它**有上界**。
- DNS 场景用替换 `getaddrinfo` 模拟（真实解析器无法可控地卡住），不冒充真实 DNS 故障实测。
- 强制终止（硬兜底 RLIMIT、超期升级）触发时不承诺证据完整，只承诺已 fsync 前缀可读。
- 绝对截止只在**停机之后**生效。
- 工程验收即便通过，**也不赋予**跨期持仓充分性或经济统计资格。
  `economic_results_eligible` / `measurement_semantics_verified` 仍为 `false`。
