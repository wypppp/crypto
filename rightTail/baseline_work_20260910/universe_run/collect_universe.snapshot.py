"""Read-only Q1 universe reconstruction. No sampling, balances, swaps or attribution."""
import argparse
import collections
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import shutil
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
START, END = 24136053, 24781026
I0, I1 = 476626, 493136
WETH = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'


def check(ok, message):
    if not ok:
        raise ValueError(message)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, obj):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n')
    tmp.replace(path)


def ledger(logs, R, i0=I0, i1=I1):
    """Retain every factory index, including unknown token identities and missing events."""
    indices, keys, pairs = {}, {}, set()
    for lg in logs:
        check(START <= int(lg['blockNumber'], 16) <= END, 'event outside window')
        check(lg['address'].lower() == R.chain_cfg()['factory'].lower(), 'wrong factory')
        check(len(lg['topics']) == 3 and lg['topics'][0].lower() == R.TOPIC_PAIR_CREATED,
              'wrong event topics')
        check(not lg.get('removed', False) and len(lg['data']) == 130, 'removed/malformed event')
        key = (lg['transactionHash'].lower(), int(lg['logIndex'], 16))
        canonical = (lg['blockNumber'], lg['data'].lower(), tuple(x.lower() for x in lg['topics']))
        if key in keys:
            check(keys[key] == canonical, 'conflicting duplicate event')
            continue
        keys[key] = canonical
        idx = R.pair_index_of(lg)-1  # event ordinal is one-based; allPairs index is zero-based
        check(i0 <= idx < i1 and idx not in indices, 'invalid/duplicate factory index')
        data = lg['data'][2:]
        check(data[:24] == '0'*24, 'noncanonical pair padding')
        t0, t1, pair = R.parse_pair_created(lg)
        check(int(pair, 16) > 0 and pair not in pairs, 'invalid/duplicate pair')
        pairs.add(pair)
        known = (all(re.fullmatch('0x'+'0'*24+'[0-9a-fA-F]{40}', t) for t in lg['topics'][1:])
                 and 0 < int(t0, 16) < int(t1, 16))
        category = ('weth' if WETH in (t0, t1) else 'non_weth') if known else 'unknown'
        indices[idx] = dict(index=idx, pair=pair, token0=t0, token1=t1, category=category,
                            block=int(lg['blockNumber'],16), tx=key[0], log_index=key[1],
                            reason='' if known else 'invalid_token_identity')
    return [indices.get(i, dict(index=i, pair='', token0='', token1='', category='unknown',
                               block='', tx='', log_index='', reason='missing_event'))
            for i in range(i0, i1)]


class BudgetExhausted(BaseException):
    pass


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True)
    ap.add_argument('--max-http', type=int, default=400)
    ap.add_argument('--max-seconds', type=int, default=900)
    args = ap.parse_args()
    check(args.max_http > 0 and args.max_seconds > 0, 'invalid budget')
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    resource.setrlimit(resource.RLIMIT_AS, (768*1024**2, 768*1024**2))
    os.nice(10)
    values = {}
    for line in (ROOT.parent/'.env').read_text().splitlines():
        m = re.match(r'\s*(?:export\s+)?([^:=]+?)\s*[:=]\s*(.*?)\s*$', line)
        if m:
            values[m[1].strip().lower()] = m[2].strip().strip('\"\'')
    for env, label in [('RTA_RPC_ETH','alchemy endpoint url'), ('ETHERSCAN_API_KEY','etherscan key')]:
        os.environ[env] = os.environ.get(env) or values.get(env.lower(), values.get(label,''))
        check(bool(os.environ[env]), 'Missing '+env)
    os.environ.update(RTA_CHAIN='ethereum', RTA_PAIR_LOGS='etherscan')
    R = load(ROOT/'rt_a_attribution.py', 'universe_rta')
    B = load(ROOT/'baseline_20260909/verify_capabilities.py', 'universe_abi')
    R.SPEC.update(chain='ethereum', pair_logs_page_size=1000)
    R.rpc_limiter = R.Limiter(3)
    R.scan_limiter = R.Limiter(3)
    source_files = [Path(__file__), ROOT/'rt_a_attribution.py', ROOT/'baseline_20260909/verify_capabilities.py']
    hashes = {str(p): sha(p) for p in source_files}
    for p in source_files:
        shutil.copyfile(p, out/(p.stem+'.snapshot.py'))
    summary = dict(state='running', exit=None, started_at=R.now_iso(), source_hashes=hashes,
                   scope='universe_only', baseline_ready=False, memory_mib=768,
                   max_http=args.max_http, max_seconds=args.max_seconds)
    started = time.monotonic()
    counts = collections.Counter()
    stopped = threading.Event()
    def resources():
        with (out/'resources.jsonl').open('a', buffering=1) as f:
            while not stopped.is_set():
                u = resource.getrusage(resource.RUSAGE_SELF)
                f.write(json.dumps(dict(at=R.now_iso(), max_rss_kib=u.ru_maxrss,
                                        cpu_seconds=u.ru_utime+u.ru_stime))+'\n')
                stopped.wait(5)
    threading.Thread(target=resources, daemon=True).start()
    def checkpoint():
        summary.update(http_attempts=dict(counts), elapsed_seconds=round(time.monotonic()-started,3))
        save(out/'execution.json', summary)
    evidence = (out/'requests.jsonl').open('a', buffering=1)
    original = R._session.request
    def tracked(method, url, **kw):
        if sum(counts.values()) >= args.max_http or time.monotonic()-started >= args.max_seconds:
            raise BudgetExhausted('collection HTTP/time budget exhausted')
        kind = 'etherscan' if url.startswith(R.ETHERSCAN_V2) else 'rpc'
        if kind == 'rpc':
            check(kw['json']['method'] in {'eth_chainId','eth_getBlockByNumber','eth_getCode','eth_call'},
                  'forbidden RPC method')
        else:
            check(kw['params']['module'] == 'logs' and kw['params']['action'] == 'getLogs',
                  'forbidden Etherscan action')
        counts[kind] += 1
        record = dict(at=R.now_iso(), kind=kind, request=kw.get('json',kw.get('params')))
        t = time.monotonic()
        try:
            result = original(method, url, **kw)
            record.update(http_status=result.status_code, response=result.text)
            if kind == 'rpc' and result.status_code == 200:
                B.validate_envelope(result.json(), kw['json']['id'])
            return result
        except Exception as e:
            record['error'] = R.safe_error(str(e))
            raise
        finally:
            record['elapsed_s'] = round(time.monotonic()-t,3)
            text = json.dumps(record)
            for secret in [os.environ['RTA_RPC_ETH'],os.environ['ETHERSCAN_API_KEY'],values.get('alchemy key','')]:
                if secret:
                    text = text.replace(secret, '[REDACTED]')
            evidence.write(text+'\n'); evidence.flush()
            checkpoint()
    R._session.request = tracked
    checkpoint()
    def rpc(method, params):
        value, err = R.rpc(method, params)
        check(not err and value is not None, 'RPC read failed: '+str(err))
        return value
    def block(n):
        b = rpc('eth_getBlockByNumber',[hex(n) if isinstance(n,int) else n,False])
        check(not isinstance(n,int) or int(b['number'],16)==n, 'block number mismatch')
        return {k:b[k] for k in ['number','timestamp','hash']}
    def call(target, signature, *vals):
        return rpc('eth_call',[{'to':target,'data':B.calldata(signature,*vals)},hex(END)])
    rc = 1
    try:
        check(int(rpc('eth_chainId',[]),16)==1, 'wrong chain')
        finalized = block('finalized')
        boundaries = {str(n):block(n) for n in [START-1,START,END,END+1]}
        check(int(finalized['number'],16)>END, 'window not finalized')
        check(int(boundaries[str(START-1)]['timestamp'],16)<1767225600<=int(boundaries[str(START)]['timestamp'],16), 'start timestamp boundary')
        check(int(boundaries[str(END)]['timestamp'],16)<1775001600<=int(boundaries[str(END+1)]['timestamp'],16), 'end timestamp boundary')
        factory = R.chain_cfg()['factory']
        factory_code = rpc('eth_getCode',[factory,hex(END)])
        check(factory_code != '0x', 'factory code absent')
        payload = dict(version='baseline-universe-events-v1', chain_id=1, factory=factory,
                       start_block=START,end_block=END,expected_index_range=[I0,I1],
                       expected_N_all=I1-I0,window_utc=['2026-01-01T00:00:00Z','2026-04-01T00:00:00Z'],
                       finalized=finalized,boundaries=boundaries,source_hashes=hashes,
                       factory_code_sha256=hashlib.sha256(bytes.fromhex(factory_code[2:])).hexdigest(),
                       enumeration='PairCreated ordinal minus one; full event coverage, sampled registry calls',
                       candidate_filter='exactly one side WETH',weth=WETH,
                       market_outcomes_read=False,formal_experiment_frozen=False)
        digest = hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        save(out/'collection_frozen.json',dict(payload=payload,payload_sha256=digest))
        logs,gaps = R.etherscan_pair_logs(START,END)
        save(out/'events.json',dict(logs=logs,gaps=gaps))
        rec = R.reconcile_pair_logs(logs,START,END)
        save(out/'reconciliation.json',rec)
        rows = ledger(logs,R,I0,I1)
        with (out/'universe.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]))
            writer.writeheader();writer.writerows(rows)
        categories = collections.Counter(row['category'] for row in rows)
        summary.update(categories=dict(categories),N_all=I1-I0,N=None,universe_sha256=sha(out/'universe.csv'))
        check(not gaps and rec['ok'], 'incomplete event collection')
        check(rec['all_pairs_length_before']==I0 and rec['all_pairs_length_end']==I1, 'count boundary changed')
        check(sum(categories.values())==I1-I0 and categories['unknown']==0, 'unidentified universe entries')
        # Deterministic evenly spaced registry checks; never claim all indices were called.
        positions = sorted({0,len(rows)-1,*[j*(len(rows)-1)//9 for j in range(10)]})
        checks=[]
        for pos in positions:
            row=rows[pos]
            p=B.addr_from_word(call(factory,'allPairs(uint256)',row['index']))
            check(p==row['pair'], 'allPairs vs event mismatch')
            check(B.addr_from_word(call(p,'token0()'))==row['token0'], 'token0 mismatch')
            check(B.addr_from_word(call(p,'token1()'))==row['token1'], 'token1 mismatch')
            check(B.addr_from_word(call(factory,'getPair(address,address)',row['token0'],row['token1']))==p, 'getPair mismatch')
            checks.append(row['index'])
        save(out/'registry_checks.json',dict(indices=checks,each_checked=['allPairs','token0','token1','getPair'],ok=True))
        check(block(int(finalized['number'],16))==finalized, 'finalized snapshot changed')
        for n,old in boundaries.items():
            check(block(int(n))==old, 'boundary hash changed')
        check(rpc('eth_getCode',[factory,hex(END)])==factory_code, 'factory code changed')
        summary.update(state='complete',N=categories['weth'],registry_indices_checked=len(checks))
        rc=0
    except (Exception,BudgetExhausted,KeyboardInterrupt) as e:
        summary.update(state='incomplete',error=R.safe_error(str(e)))
    finally:
        summary['exit']=rc
        checkpoint();stopped.set();evidence.close()
    print(json.dumps(summary,ensure_ascii=False))
    return rc


if __name__=='__main__':
    sys.exit(main())
