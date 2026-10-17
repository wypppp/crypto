"""第十九轮：新进程验证实际导入来源，不访问网络或密钥。"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

H = Path(__file__).resolve().parent


def probe(code):
    result = subprocess.run(
        [sys.executable, "-c", code, str(H)],
        cwd="/tmp",
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    "entry",
    ["contract_filter_isolated", "contract_pairs_isolated", "build_wm2_sql", "s3_ref"],
)
def test_local_paid_entrypoints_do_not_get_shadowed(entry):
    out = probe(
        f"""
import importlib,json,socket,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
def blocked(*args,**kwargs): raise AssertionError('network forbidden')
socket.socket.connect=blocked
original_read=Path.read_text
def read(self,*args,**kwargs):
    if self.name=='.env': raise AssertionError('must not read credentials during import')
    return original_read(self,*args,**kwargs)
Path.read_text=read
before=sys.path[:]
importlib.import_module({entry!r})
assert sys.path==before
names=('run_dune','dune_get','dune_get_stream','paid_guard','s3_ref')
print(json.dumps({{name:importlib.import_module(name).__file__ for name in names}}))
"""
    )
    assert out == {name: str(H / (name + ".py")) for name in out}


def test_frozen_dependencies_are_exact_and_foreign_cache_is_restored():
    out = probe("""
import json,sys,types
from pathlib import Path
sys.path.insert(0,sys.argv[1])
foreign={n:types.ModuleType(n) for n in ('weeks','forward')}
sys.modules.update(foreign)
before=sys.path[:]
import contract_filter_isolated as CF
import contract_pairs_isolated as CP
assert sys.path==before
assert all(sys.modules[n] is m for n,m in foreign.items())
assert CF.W is CP.W
assert CF.F._to_date is CF.W._to_date
print(json.dumps({'forward':CF.F.__file__,'weeks':CP.W.__file__,'selection':[CP.select()['old'].isoformat(),*[d.isoformat() for d in CP.select()['late']]],'allowed':CF.coin_allowed('2026-06-01T12:00:00Z','ABCX'),'protected':CF.coin_allowed('2026-06-20T12:00:00Z','ABCX')}))
""")
    assert Path(out["forward"]).parent == H.parent / "发射台_前期右尾评测底座_DQ-37"
    assert Path(out["weeks"]).parent == H.parent / "发射台_前期右尾评测底座_DQ-37"
    assert out["selection"] == ["2026-05-25", "2026-07-27", "2026-08-10"]
    assert out["allowed"] and not out["protected"]


def test_failure_restores_original_search_path_and_modules(tmp_path):
    out = probe(f"""
import json,sys
sys.path.insert(0,sys.argv[1])
import frozen_contract_imports as I
before=sys.path[:]
original={{n:sys.modules.get(n) for n in ('weeks','forward')}}
I.H=__import__('pathlib').Path({str(tmp_path)!r})
try:
    I.contract_module('contract_filter')
except FileNotFoundError:
    pass
else:
    raise AssertionError('missing frozen source must fail')
assert sys.path==before
assert all(sys.modules.get(n) is m for n,m in original.items())
print(json.dumps({{'restored':True}}))
""")
    assert out == {"restored": True}


def test_closeout_revokes_execution_but_keeps_fixed_download(tmp_path, monkeypatch):
    import paid_guard as PG

    policy = tmp_path / "policy.json"
    monkeypatch.setattr(PG, "S3_POLICY", policy)
    binding = {
        "query_id": 8951402,
        "execution_id": "existing",
        "sql_sha256": "sha",
        "metadata_bytes": 353426281,
        "expected_credits": "0",
        "page_rows": 1000,
        "metadata_gate_passed": True,
        "row_count": 4092254,
        "max_page_billed_bytes": 250000,
        "max_unchecked_pages": 5,
    }
    policy.write_text(
        json.dumps(
            {
                "active_paid_source_prefix": "总控第十四轮",
                "gpt_review_passed": True,
                "full_approved": False,
                "allowed_execution_approvals": ["revoked"],
                "full_execution_sql_sha256": ["sha"],
                "download_bindings": {"download-only": binding},
            }
        )
    )
    execute = PG.Ticket("revoked", 84, 0)
    execute.source, execute.sql_sha, execute.download_cap = "总控第十四轮", "sha", 0
    execute.expected = 42
    with pytest.raises(PG.Refused, match="分段"):
        PG.execution_review_gate(execute)
    download = PG.Ticket("download-only", 0, 353.426281)
    download.source, download.sql_sha, download.download_cap = "总控第十四轮", "sha", 5
    assert PG.small_download_binding(download, eid="existing", qid=8951402) == binding
    with pytest.raises(PG.Refused, match="执行号"):
        PG.small_download_binding(download, eid="another", qid=8951402)
