# -*- coding: utf-8 -*-
"""郑商所每日行情表采集（FG 玻璃等品种）

来源：https://www.czce.com.cn/cn/DFSStaticFiles/Future/{YYYY}/{YYYYMMDD}/FutureDataDaily.txt
性质：交易所官方公开数据，免费。只保留指定品种前缀的合约行。
非交易日返回"当日无数据"页，记为 skip，不静默补全。
输出：data/market/czce_daily.csv
"""
import argparse, csv, io, os, ssl, sys, time, urllib.request
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data/market')
URL = 'https://www.czce.com.cn/cn/DFSStaticFiles/Future/%d/%s/FutureDataDaily.txt'
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0 (research; exchange public data)'}
COLS = ['date', 'contract', 'prev_settle', 'open', 'high', 'low', 'close', 'settle',
        'chg1', 'chg2', 'volume', 'oi', 'oi_chg', 'turnover', 'delivery_settle']


def num(s):
    s = (s or '').strip().replace(',', '')
    return s if s not in ('', '-') else ''


def fetch(d, tries=3):
    u = URL % (d.year, d.strftime('%Y%m%d'))
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30, context=CTX) as r:
                b = r.read()
            t = b.decode('utf-8', 'replace')
            return None if '当日无数据' in t or '<html' in t[:200].lower() else t
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', default='2020-01-01')
    ap.add_argument('--end', default=None)
    ap.add_argument('--prefix', default='FG', help='品种前缀，逗号分隔')
    a = ap.parse_args()
    pref = tuple(x.strip().upper() for x in a.prefix.split(','))
    start = date.fromisoformat(a.start)
    end = date.fromisoformat(a.end) if a.end else date.today() - timedelta(days=1)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, 'czce_daily.csv')
    seen = set()
    if os.path.exists(path):
        for r in csv.DictReader(io.open(path, encoding='utf-8')):
            seen.add(r['date'])
    f = io.open(path, 'a', encoding='utf-8', newline='')
    w = csv.writer(f)
    if not seen:
        w.writerow(COLS)

    d, n, got, skip, rows = start, 0, 0, 0, 0
    t0 = time.monotonic()
    while d <= end:
        if d.weekday() >= 5 or d.isoformat() in seen:
            d += timedelta(days=1); continue
        n += 1
        txt = fetch(d)
        if txt is None:
            skip += 1
        else:
            got += 1
            for ln in txt.split('\n'):
                p = [x.strip() for x in ln.split('|')]
                if len(p) < 13 or not p[0] or not p[0].upper().startswith(pref):
                    continue
                c = p[0].strip().upper()
                if not any(ch.isdigit() for ch in c):
                    continue
                w.writerow([d.isoformat(), c] + [num(x) for x in p[1:14]])
                rows += 1
        if n % 60 == 0:
            f.flush()
            el = time.monotonic() - t0
            print('  %s  请求%d 有数据%d 非交易日%d 行%d  已用%.1f分' % (d, n, got, skip, rows, el/60), flush=True)
        time.sleep(0.4)
        d += timedelta(days=1)
    f.close()
    print('完成：请求 %d 天，有数据 %d，非交易日 %d，写入 %d 行 -> %s'
          % (n, got, skip, rows, path))


if __name__ == '__main__':
    sys.exit(main())
