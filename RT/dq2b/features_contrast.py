#!/usr/bin/env python3
"""DQ-2b：按冻结卡片抽取上市前特征、与 DQ-2 结果对照、计算 T50 退出与容量代理。开发性分析，不打开留出集。"""
import csv, json, re, os, sys, statistics, hashlib, datetime as dt
from pathlib import Path
sys.path.insert(0, '/home/ancillary/RT/dq2')
import dq2_listing_tail as m
m.RAW = Path('/home/ancillary/RT/dq2/raw')          # 只读复用 DQ-2 缓存（206 个 USDT 对）
HERE = Path(__file__).resolve().parent
DIR = Path('/home/ancillary/direction/archive/v1.8.40')
RESULTS = Path('/home/ancillary/RT/dq2/runs/20260915T013907Z-full/results.csv')
BTC = json.load(open(HERE / 'raw/btcusdt_daily_close.json'))
H = 180
t0recs = {r['base_asset']: r for r in json.load(open(DIR / 'L_t0_exact_v2.json'))['records'] if r['status'] == 'VERIFIED_COMPLETE'}
KW = {'Launchpad': r'launchpad', 'Launchpool': r'launchpool', 'HODLer Airdrop': r'hodler airdrop', 'Megadrop': r'megadrop', 'Pre-Market': r'pre-?market'}
TAG = {'Seed Tag': r'seed tag', 'Monitoring Tag': r'monitoring tag'}
def fnum(x):
    try: return float(x)
    except Exception: return None
rows = list(csv.DictReader(open(RESULTS)))
assert len(rows) == 206
out = []
for r in rows:
    b = r['base']; rec = t0recs[b]; t0_ms = rec['T0_exact_us'] // 1000
    texts, rels = [], []
    for a in rec['source_article_ids']:
        body = json.load(open(DIR / f'ann_body/{a}.json'))
        if body.get('releaseDate') and body['releaseDate'] < t0_ms:
            texts.append((body.get('title') or '') + '\n' + (body.get('text') or '')); rels.append(body['releaseDate'])
    full = '\n'.join(texts); low = full.lower()
    f = {'base': b, 'T0_day': r['T0_day'], 'n_articles_pre_T0': len(texts)}
    snippets = {}
    for k, pat in {**KW, **TAG}.items():
        mt = re.search(pat, low)
        f[k] = bool(mt)
        if mt: snippets[k] = full[max(0, mt.start() - 50): mt.end() + 50].replace('\n', ' ')
    f['无渠道关键词'] = not any(f[k] for k in KW)
    if rels:
        lead_h = (t0_ms - min(rels)) / 3_600_000
        f['lead_hours'] = round(lead_h, 2)
        f['X3_lead'] = '<=24h' if lead_h <= 24 else ('24-72h' if lead_h <= 72 else '>72h')
        ann_day = dt.datetime.fromtimestamp(min(rels) / 1000, dt.timezone.utc).date()
        d1 = (ann_day - dt.timedelta(days=1)).isoformat(); d90 = (ann_day - dt.timedelta(days=91)).isoformat()
        if d1 in BTC and d90 in BTC:
            ratio = BTC[d1] / BTC[d90]; f['btc90_ratio'] = round(ratio, 4)
            f['X4_btc90'] = '>=1.2' if ratio >= 1.2 else ('0.8-1.2' if ratio >= 0.8 else '<0.8')
        else:
            f['btc90_ratio'] = None; f['X4_btc90'] = '不可用'
    else:
        f['lead_hours'] = None; f['X3_lead'] = '不可用'; f['btc90_ratio'] = None; f['X4_btc90'] = '不可用'
    # 结果标签（冻结：a30、H180、M*close）
    st = r.get('a30_H180_status'); mc = fnum(r.get('a30_H180_mstar_close'))
    if mc is not None and mc >= 5: g = 'W'
    elif st == 'complete' and mc is not None and mc < 2: g = 'L'
    elif st == 'complete' and mc is not None: g = 'M'
    else: g = 'U'
    f['group'] = g; f['mstar_close_180'] = mc; f['mpi_180'] = fnum(r.get('a30_H180_mpi')); f['a30_H180_status'] = st
    # T50 退出与容量代理：日 K 收盘，参考高点包含入场价
    f.update({'mpi_T50': None, 'T50_exit_day': None, 'T50_reason': None, 'entry_day_quote_volume': None, 'exit_day_quote_volume': None})
    price = fnum(r.get('a30_price'))
    if price and r.get('a30_time_utc'):
        entry_day = dt.datetime.fromisoformat(r['a30_time_utc']).date()
        day0 = dt.date.fromisoformat(r['T0_day']); end_day = day0 + dt.timedelta(days=H)
        daily = m.daily_rows(r['symbol'], entry_day, min(end_day, m.DATA_END))
        if entry_day in daily: f['entry_day_quote_volume'] = daily[entry_day]['qv']
        peak = price; exit_day = None; reason = None
        for d in sorted(daily):
            c = daily[d]['c']; peak = max(peak, c)
            if c <= 0.5 * peak: exit_day, reason = d, 'trailing_50'; break
        if exit_day is None and daily:
            last = max(daily)
            exit_day = last
            reason = 'time_180' if last == end_day else ('immature' if end_day > m.DATA_END else 'data_ended')
        if exit_day:
            f['mpi_T50'] = daily[exit_day]['c'] / price; f['T50_exit_day'] = exit_day.isoformat(); f['T50_reason'] = reason
            f['exit_day_quote_volume'] = daily[exit_day]['qv']
    f['snippets'] = json.dumps(snippets, ensure_ascii=False)
    out.append(f)
# 写 features.csv
cols = list(out[0].keys())
with open(HERE / 'features.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(out)
# 对照
groups = ['W', 'M', 'L', 'U']; gsize = {g: sum(1 for x in out if x['group'] == g) for g in groups}
values = [(k, True) for k in list(KW) + ['无渠道关键词'] + list(TAG)] + \
         [('X3_lead', v) for v in ['<=24h', '24-72h', '>72h', '不可用']] + [('X4_btc90', v) for v in ['>=1.2', '0.8-1.2', '<0.8', '不可用']]
table = []
for k, v in values:
    sel = [x for x in out if x[k] == v]
    row = {'feature': k, 'value': str(v), 'n_all': len(sel), **{f'n_{g}': sum(1 for x in sel if x['group'] == g) for g in groups}}
    row['cov_W'] = row['n_W'] / gsize['W'] if gsize['W'] else None
    row['cov_all'] = len(sel) / len(out)
    row['lift_W'] = (row['cov_W'] / row['cov_all']) if row['cov_W'] is not None and row['cov_all'] else None
    row['meets_1'] = bool(row['cov_W'] is not None and row['cov_W'] >= 0.5 and row['cov_all'] <= 0.3)
    table.append(row)
def med(g, key):
    v = [x[key] for x in out if x['group'] == g and x[key] is not None]
    return (statistics.median(v), len(v)) if v else (None, 0)
exit_summary = {g: {'mpi_T50_median_n': med(g, 'mpi_T50'), 'mpi_180_median_n': med(g, 'mpi_180'), 'mstar_close_median_n': med(g, 'mstar_close_180')} for g in groups}
c1 = any(t['meets_1'] for t in table); c2 = gsize['W'] >= 5; w_t50 = exit_summary['W']['mpi_T50_median_n'][0]; c3 = w_t50 is not None and w_t50 >= 2
verdict = '值得验证' if (c1 and c2 and c3) else '不值得'
winners = sorted([x for x in out if x['group'] == 'W'], key=lambda x: -(x['mstar_close_180'] or 0))
res = {'group_sizes': gsize, 'criteria': {'c1_discriminating_value': c1, 'c2_W_at_least_5': c2, 'c3_W_median_mpi_T50_ge_2': c3, 'W_median_mpi_T50': w_t50},
       'verdict': verdict, 'table': table, 'exit_summary': exit_summary,
       'winners': [{k: x[k] for k in ['base', 'T0_day', 'mstar_close_180', 'mpi_180', 'mpi_T50', 'T50_reason', 'T50_exit_day', 'exit_day_quote_volume', 'entry_day_quote_volume', 'Launchpad', 'Launchpool', 'HODLer Airdrop', 'Megadrop', 'Seed Tag', 'X3_lead', 'X4_btc90']} for x in winners],
       'inputs': {'results_csv_sha256': hashlib.sha256(RESULTS.read_bytes()).hexdigest(), 'card_sha256': hashlib.sha256((HERE / 'DQ2b_卡.md').read_bytes()).hexdigest(), 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
       'implementation_notes': ['T50 参考高点包含入场价与入场日及之后的日收盘价', '容量代理为日 K quote_volume（USDT），不是可执行深度', 'W 含 M*close 为下界已达 5 的记录']}
json.dump(res, open(HERE / 'contrast.json', 'w'), ensure_ascii=False, indent=1, default=str)
L = [f"# DQ-2b 对照（脚本生成，开发性描述）", '', f"组规模：{gsize}；判据：c1={c1} c2={c2} c3={c3}（W 的 Mπ_T50 中位 {w_t50}）→ **{verdict}**", '',
     '| 特征 | 取值 | 全部 | W | M | L | U | W 覆盖 | 全部覆盖 | 富集倍数 | 满足判据1 |', '|---|---|---|---|---|---|---|---|---|---|---|']
for t in table:
    L.append(f"| {t['feature']} | {t['value']} | {t['n_all']} | {t['n_W']} | {t['n_M']} | {t['n_L']} | {t['n_U']} | {t['cov_W']:.0%} | {t['cov_all']:.0%} | {t['lift_W']:.2f} | {t['meets_1']} |" if t['cov_W'] is not None and t['lift_W'] is not None else f"| {t['feature']} | {t['value']} | {t['n_all']} | {t['n_W']} | {t['n_M']} | {t['n_L']} | {t['n_U']} | — | {t['cov_all']:.0%} | — | {t['meets_1']} |")
L += ['', '## 退出对照（中位数, n）', '', '| 组 | Mπ_T50 | Mπ180 | M*close180 |', '|---|---|---|---|']
for g in groups:
    e = exit_summary[g]; fm = lambda p: '—' if p[0] is None else f"{p[0]:.2f} (n={p[1]})"
    L.append(f"| {g} | {fm(e['mpi_T50_median_n'])} | {fm(e['mpi_180_median_n'])} | {fm(e['mstar_close_median_n'])} |")
L += ['', '## W 组明细', '', '| base | T0 | M*close180 | Mπ180 | Mπ_T50 | T50 原因/日 | 退出日成交额 USDT | 入场日成交额 USDT | 渠道/标签 | 提前量 | BTC90 |', '|---|---|---|---|---|---|---|---|---|---|---|']
for x in res['winners']:
    ch = ','.join(k for k in ['Launchpad', 'Launchpool', 'HODLer Airdrop', 'Megadrop', 'Seed Tag'] if x[k]) or '无'
    fv = lambda v, p=2: '—' if v is None else (f'{v:,.0f}' if p == 0 else f'{v:.{p}f}')
    L.append(f"| {x['base']} | {x['T0_day']} | {fv(x['mstar_close_180'])} | {fv(x['mpi_180'])} | {fv(x['mpi_T50'])} | {x['T50_reason']} {x['T50_exit_day']} | {fv(x['exit_day_quote_volume'],0)} | {fv(x['entry_day_quote_volume'],0)} | {ch} | {x['X3_lead']} | {x['X4_btc90']} |")
open(HERE / 'contrast.md', 'w').write('\n'.join(L) + '\n')
print('\n'.join(L))
print('downloads', m.STATS)
