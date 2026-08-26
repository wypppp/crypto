# -*- coding: utf-8 -*-
"""A01：拉取可逐线分辨浮法线的逐小时排放历史（按月分片、限速、原始留档）

遵守 PUB 协议：
  - 原始响应逐片保存并计 SHA-256，不改写、不推断缺失；
  - 失败月份记入 failures.jsonl，不静默补全；
  - 已完成分片跳过，可中断续跑。
接口要点（T-036 实测）：
  - 必须带 X-ACCESS: ANONYMOUS，否则 404；
  - 必须先 GET /online_statistics/v5/dataQuery/column 取 checked 列，
    再把 headers=... 传给 POST /online_statistics/v5/dataQuery/list，
    否则 HTTP 200 但静默返回 0 行。
"""
import argparse, csv, hashlib, io, json, os, ssl, sys, time, urllib.parse, urllib.request
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PO = os.path.join(ROOT, 'data/public_official')
OUT = os.path.join(ROOT, 'data/public_only_v1/glass_line_hourly')
BASE = 'https://111.62.218.180:9920'
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
HDR = {'Accept': 'application/json, text/plain, */*', 'Content-Type': 'application/json',
       'X-ACCESS': 'ANONYMOUS', 'User-Agent': 'hebei-public-catalog-audit/1.0'}
MIN_INTERVAL = 1.2
_last = [0.0]


def _wait():
    d = time.monotonic() - _last[0]
    if d < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - d)
    _last[0] = time.monotonic()


def call(path, payload=None, params=None, method='POST', tries=3):
    for i in range(tries):
        _wait()
        url = BASE + path + ('?' + urllib.parse.urlencode(params) if params else '')
        body = json.dumps(payload).encode() if payload is not None else None
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=HDR, method=method),
                                        timeout=90, context=CTX) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                return ('__ERR__' + repr(e)[:200]).encode()
            time.sleep(2.0 * (i + 1))


def _flatten(items, out=None):
    out = [] if out is None else out
    for it in (items or []):
        if isinstance(it, dict):
            out.append(it); _flatten(it.get('children'), out)
    return out


_HC = {}


def headers_for(pt, data_type='2061'):
    k = pt['port_id']
    if k in _HC:
        return _HC[k]
    raw = call('/online_statistics/v5/dataQuery/column', None,
               {'psId': pt['ps_id'], 'portId': pt['port_id'],
                'portTypeId': pt['port_type_id'], 'dataType': data_type}, method='GET')
    ids = []
    if not raw.startswith(b'__ERR__'):
        j = json.loads(raw.decode('utf-8', 'replace'))
        for x in _flatten(j if isinstance(j, list) else (j or {}).get('data')):
            if x.get('checked') and x.get('id') is not None:
                ids.append(str(x['id']))
    _HC[k] = ids
    return ids


def months(start, end):
    y, m = start.year, start.month
    out = []
    while (y, m) <= (end.year, end.month):
        nxt = (y + 1, 1) if m == 12 else (y, m + 1)
        last = date(nxt[0], nxt[1], 1).toordinal() - 1
        out.append((date(y, m, 1), date.fromordinal(last)))
        y, m = nxt
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', default=None, help='YYYY-MM-DD，默认一年前当月')
    ap.add_argument('--end', default=None, help='YYYY-MM-DD，默认上月末')
    ap.add_argument('--limit-points', type=int, default=0)
    a = ap.parse_args()

    today = date.today()
    end = date.fromisoformat(a.end) if a.end else date(today.year, today.month, 1).toordinal() - 1
    if not a.end:
        end = date.fromordinal(end)
    start = date.fromisoformat(a.start) if a.start else date(end.year - 1, end.month, 1)

    pts = list(csv.DictReader(io.open(os.path.join(PO, 'glass_line_points.csv'), encoding='utf-8-sig')))
    if a.limit_points:
        pts = pts[:a.limit_points]
    mons = months(start, end)
    os.makedirs(OUT, exist_ok=True)
    failp = os.path.join(OUT, 'failures.jsonl')
    man_path = os.path.join(OUT, 'manifest.jsonl')
    done = set()
    if os.path.exists(man_path):
        for ln in io.open(man_path, encoding='utf-8'):
            try: done.add(json.loads(ln)['shard'])
            except Exception: pass

    total = len(pts) * len(mons)
    print('点位 %d × 月份 %d = %d 个分片；区间 %s ~ %s；已完成 %d'
          % (len(pts), len(mons), total, start, end, len(done)), flush=True)
    n = ok = rows_all = 0
    t0 = time.monotonic()
    man = io.open(man_path, 'a', encoding='utf-8')
    for pt in pts:
        hdrs = headers_for(pt)
        if not hdrs:
            io.open(failp, 'a', encoding='utf-8').write(json.dumps(
                dict(port_id=pt['port_id'], reason='no_checked_headers'), ensure_ascii=False) + '\n')
            continue
        for ms, me in mons:
            shard = '%s_%s' % (pt['port_id'], ms.strftime('%Y%m'))
            n += 1
            if shard in done:
                continue
            payload = {'index': 1, 'size': 2000, 'psId': pt['ps_id'], 'portId': pt['port_id'],
                       'portTypeId': pt['port_type_id'], 'dataType': '2061',
                       'headers': ','.join(hdrs),
                       'startTime': '%s 00:00:00' % ms, 'endTime': '%s 23:00:00' % me}
            raw = call('/online_statistics/v5/dataQuery/list', payload)
            if raw.startswith(b'__ERR__'):
                io.open(failp, 'a', encoding='utf-8').write(json.dumps(
                    dict(shard=shard, month=str(ms), err=raw.decode('utf-8', 'replace')[:200]),
                    ensure_ascii=False) + '\n')
                continue
            d = os.path.join(OUT, 'raw', pt['port_id'])
            os.makedirs(d, exist_ok=True)
            fn = os.path.join(d, ms.strftime('%Y%m') + '.json')
            io.open(fn, 'wb').write(raw)
            try:
                j = json.loads(raw.decode('utf-8', 'replace'))
                nrows = len(j.get('data') or []) if isinstance(j, dict) else 0
            except Exception:
                nrows = -1
            ok += 1; rows_all += max(nrows, 0)
            man.write(json.dumps(dict(shard=shard, enterprise=pt['enterprise'], line_no=pt['line_no'],
                                      port_id=pt['port_id'], port_name=pt['port_name'],
                                      month=ms.strftime('%Y-%m'), rows=nrows, bytes=len(raw),
                                      sha256=hashlib.sha256(raw).hexdigest(),
                                      fetched_at=datetime.now().astimezone().isoformat(timespec='seconds')),
                                 ensure_ascii=False) + '\n')
            if ok % 20 == 0:
                man.flush()
                el = time.monotonic() - t0
                print('  %d/%d 分片  成功 %d  累计 %d 行  已用 %.1f 分  预计剩 %.1f 分'
                      % (n, total, ok, rows_all, el / 60, (total - n) * (el / max(ok, 1)) / 60), flush=True)
    man.close()
    print('完成：分片 %d/%d，成功 %d，累计 %d 行，用时 %.1f 分钟'
          % (n, total, ok, rows_all, (time.monotonic() - t0) / 60))
    print('原始留档 -> %s' % os.path.join(OUT, 'raw'))


if __name__ == '__main__':
    sys.exit(main())
