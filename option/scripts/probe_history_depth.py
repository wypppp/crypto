# -*- coding: utf-8 -*-
"""T-036：公开平台历史回溯能力探测（只读、限速、不建表、不产出研究结论）

只回答四个可行性问题：
  1. 接口是否接受任意历史区间；
  2. 实际能回溯多久（逐年二分探测）；
  3. 单次请求返回多少小时、是否分页；
  4. 吞吐与限速 -> 估算拉满一年 × N 条线需要多久。

**本脚本不保存任何监测数值用于研究**，只保存计数与时延；数值仅用于判断"是否有数"。
遵守 PUB 协议：不改写、不推断缺失、失败即记失败。
"""
import argparse, io, json, os, ssl, sys, time, urllib.parse, urllib.request
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = 'https://111.62.218.180:9920'
OUT = os.path.join(ROOT, 'data/public_only_v1/history_depth_probe')
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
# 与 collect_ps_public.py 保持一致：公开端点需要 X-ACCESS: ANONYMOUS
HDR = {'Accept': 'application/json, text/plain, */*',
       'Content-Type': 'application/json',
       'X-ACCESS': 'ANONYMOUS',
       'User-Agent': 'hebei-public-catalog-audit/1.0'}
MIN_INTERVAL = 1.2          # 秒，对公开政府平台限速
_last = [0.0]


def _wait():
    d = time.monotonic() - _last[0]
    if d < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - d)
    _last[0] = time.monotonic()


def call(path, payload=None, params=None, method='POST'):
    _wait()
    url = BASE + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, headers=HDR, method=method)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=45, context=CTX) as r:
            raw = r.read()
        return dict(ok=True, ms=round((time.monotonic() - t0) * 1000), bytes=len(raw),
                    json=json.loads(raw.decode('utf-8', 'replace')))
    except Exception as e:
        return dict(ok=False, ms=round((time.monotonic() - t0) * 1000), err=repr(e)[:160])


def _flatten(items, out=None):
    out = [] if out is None else out
    for it in (items or []):
        if isinstance(it, dict):
            out.append(it); _flatten(it.get('children'), out)
    return out


_HDR_CACHE = {}


def checked_headers(pt, data_type='2061'):
    """list 接口必须携带 headers；先向 column 端点取当前勾选列。"""
    key = (pt['port_id'], data_type)
    if key in _HDR_CACHE:
        return _HDR_CACHE[key]
    common = {'psId': pt['ps_id'], 'portId': pt['port_id'],
              'portTypeId': pt['port_type_id'], 'dataType': data_type}
    r = call('/online_statistics/v5/dataQuery/column', None, common, method='GET')
    ids = []
    if r['ok']:
        j = r['json']
        for x in _flatten(j if isinstance(j, list) else (j or {}).get('data')):
            if x.get('checked') and x.get('id') is not None:
                ids.append(str(x['id']))
    _HDR_CACHE[key] = ids
    return ids


def query(pt, start, end, size=500, index=1):
    hdrs = checked_headers(pt)
    payload = {'index': index, 'size': size, 'psId': pt['ps_id'], 'portId': pt['port_id'],
               'portTypeId': pt['port_type_id'], 'dataType': '2061',
               'headers': ','.join(hdrs),
               'startTime': '%s 00:00:00' % start, 'endTime': '%s 23:00:00' % end}
    r = call('/online_statistics/v5/dataQuery/list', payload)
    if not r['ok']:
        return r
    j = r['json'] if isinstance(r['json'], dict) else {}
    rows = j.get('data') or []
    r.update(rows=len(rows) if isinstance(rows, list) else 0,
             total=j.get('total'), code=j.get('code'), msg=str(j.get('msg'))[:60])
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--points', default='/tmp/claude-1000/-home-ancillary/f9510cdd-4e51-4bba-88a3-e08e385a49ae/scratchpad/probe_points.json')
    ap.add_argument('--limit-points', type=int, default=3)
    a = ap.parse_args()
    pts = json.load(io.open(a.points, encoding='utf-8'))[:a.limit_points]
    os.makedirs(OUT, exist_ok=True)
    log = dict(probed_at=datetime.now().astimezone().isoformat(timespec='seconds'),
               base=BASE, min_interval_s=MIN_INTERVAL, points=[], notes=[])

    today = date.today()
    for pt in pts:
        rec = dict(point=pt, windows=[])
        print('== %s / %s' % (pt['ps_name'], pt['port_name']))
        # (1) 近 7 天：确认接口与该点当前可用
        s = today - timedelta(days=7)
        r = query(pt, s.isoformat(), today.isoformat())
        print('   近7天      rows=%-5s total=%-6s %sms  %s' % (r.get('rows'), r.get('total'), r['ms'], '' if r['ok'] else r.get('err')))
        rec['windows'].append(dict(tag='last7d', start=s.isoformat(), end=today.isoformat(), **{k: r.get(k) for k in ('ok','rows','total','ms','code','msg','err')}))
        # (2) 逐年回溯：每年取同一个 7 天窗
        for back in (1, 2, 3, 4, 5):
            try:
                e = today.replace(year=today.year - back)
            except ValueError:
                e = today.replace(year=today.year - back, day=28)
            s = e - timedelta(days=7)
            r = query(pt, s.isoformat(), e.isoformat())
            print('   T-%dy       rows=%-5s total=%-6s %sms  %s' % (back, r.get('rows'), r.get('total'), r['ms'], '' if r['ok'] else r.get('err')))
            rec['windows'].append(dict(tag='T-%dy' % back, start=s.isoformat(), end=e.isoformat(), **{k: r.get(k) for k in ('ok','rows','total','ms','code','msg','err')}))
        # (3) 单请求容量：整月
        m_end = today.replace(day=1) - timedelta(days=1)
        m_start = m_end.replace(day=1)
        r = query(pt, m_start.isoformat(), m_end.isoformat(), size=1000)
        exp = (m_end - m_start).days * 24 + 24
        print('   上一整月    rows=%-5s total=%-6s 期望≈%d  %sms' % (r.get('rows'), r.get('total'), exp, r['ms']))
        rec['windows'].append(dict(tag='full_month', start=m_start.isoformat(), end=m_end.isoformat(),
                                   expected_hours=exp, **{k: r.get(k) for k in ('ok','rows','total','ms','code','msg','err')}))
        log['points'].append(rec)

    fn = os.path.join(OUT, 'probe_%s.json' % datetime.now().strftime('%Y%m%dT%H%M%S'))
    json.dump(log, io.open(fn, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n已写入 %s' % fn)

    ok = [w for p in log['points'] for w in p['windows'] if w.get('ok')]
    if ok:
        avg = sum(w['ms'] for w in ok) / len(ok)
        print('成功请求 %d，平均 %.0f ms；按限速 %.1fs/请求估算：' % (len(ok), avg, MIN_INTERVAL))
        per_req = max(MIN_INTERVAL, avg / 1000)
        for n_lines, months in ((34, 12), (34, 60)):
            reqs = n_lines * months
            print('   %d 条线 × %d 个月 = %d 请求 ≈ %.1f 分钟' % (n_lines, months, reqs, reqs * per_req / 60))
    else:
        print('无成功请求，无法估算吞吐')


if __name__ == '__main__':
    sys.exit(main())
