"""Re-run local delivery probes without overwriting their original outputs."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

D = Path(__file__).resolve().parent
W = D.parent
results = []
with tempfile.TemporaryDirectory(prefix="rta-v114-audit-cert-") as tmp:
    cert, key = Path(tmp) / "cert.pem", Path(tmp) / "key.pem"
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(key), "-out", str(cert), "-days", "1",
        "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1",
    ], check=True, capture_output=True)
    for name in ("phase_probe", "verify_and_dns_probe", "verify_tls", "verify_exit"):
        env = dict(os.environ, RT_CODE_ROOT=str(W))
        env.pop("SSL_CERT_FILE", None)
        if name == "phase_probe":
            env["SSL_CERT_FILE"] = str(cert)
        cmd = [sys.executable, str(D / (name + ".py"))]
        if name in ("phase_probe", "verify_and_dns_probe"):
            cmd += [str(cert), str(key)]
        p = subprocess.run(cmd, cwd=W, env=env, capture_output=True, text=True, timeout=70)
        (D / (name + ".log")).write_text(p.stdout + p.stderr)
        rec = {"probe": name, "exit": p.returncode, "stdout": p.stdout}
        results.append(rec)
        print(json.dumps(rec, ensure_ascii=False), flush=True)
(D / "phase_checks.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
assert all(r["exit"] == 0 for r in results)
phase = json.loads((D / "phase_probe.json").read_text())
assert len(phase) == 4
assert all(r["结果"].startswith("Shutdown:") and r["停机后耗时s"] < .35 for r in phase[:3])
assert phase[0]["握手期间登记数"] >= 1
assert phase[3]["结果"] == "0x1" and phase[3]["在途登记残留"] == 0
other = [json.loads(line) for line in results[1]["stdout"].splitlines()]
assert other[0]["判定"] == "REJECTED" and other[0]["残留登记"] == 0
assert other[1]["退出码"] == 3 and int(other[1]["DNS期间在途登记"]) >= 1
assert other[1]["子进程总耗时s"] < 2 and not other[1]["未被强制退出"]
print("PHASE CHECKS PASSED", flush=True)
