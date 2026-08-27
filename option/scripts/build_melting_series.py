# -*- coding: utf-8 -*-
"""A01：河北浮法玻璃「在产日熔量」日度序列

三档口径（使用者 2026-08-26 裁决）：
  在产  = 正常生产
  过渡  = 启炉/启炉过程/停炉/停炉过程/烘炉/焖炉/故障 及其组合  —— 单独报，不并入任何一边
  停运  = 停运
  无数据 = 工况字段为空

产能归属（逐条记录依据，不做隐式近似）：
  line_no  : 工信厅清单该企业线号唯一且可与平台线号对齐时，按线取设计产能
  even     : 线号不唯一（如长城分批次编号 1#,2#/1#,2#/1#-4#）或清单无线号时，
             按企业浮法总产能在其可分辨点位间均摊

轮流生产组（2026-08-26 修正）：同企业内互斥率 ≥90%% 且同时在产条数恒定的点位组，
共用同一座熔窑，其产能按**组**计一次，不按点位求和；否则会把窑内换线记成产能进出。
实测仅南和县长红 1 线⟷2 线构成该形态（互斥率 100.0%%，同时在产恒为 1）。

政策窗口来自 T-031 L1（邢台）。非邢台企业标记 na（其所在市日历未采集），不得外推。
输出：data/public_only_v1/melting_series_daily.csv
"""
import csv, io, json, glob, os, re, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PO = os.path.join(ROOT, 'data/public_official')
RAW = os.path.join(ROOT, 'data/public_only_v1/glass_line_hourly/raw')
OUT = os.path.join(ROOT, 'data/public_only_v1')

RUN = {'正常生产'}
IDLE = {'停运'}
TRANS = {'启炉', '停炉', '启炉过程', '停炉过程', '烘炉', '焖炉', '故障', '生产设施故障'}
CN = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
XT = {'沙河市长城玻璃有限公司','沙河市安全实业有限公司','河北德金玻璃有限公司',
      '河北鑫利玻璃有限公司','河北正大玻璃有限公司','南和县长红玻璃有限公司',
      '沙河市金东玻璃有限公司','沙河市鸿昇玻璃有限公司','河北金宏阳太阳能科技股份有限公司'}


def classify(w):
    w = (w or '').strip()
    if not w: return 'unknown'
    parts = {p.strip() for p in re.split(r'[、,，]', w) if p.strip()}
    if parts & TRANS: return 'transition'          # 过渡优先：组合中含过渡态即为过渡
    if parts <= RUN: return 'running'
    if parts <= IDLE: return 'idle'
    return 'transition'


def official_line_no(name):
    n = {int(m.group(1)) for m in re.finditer(r'[（(]\s*(\d{1,2})\s*#?\s*[)）]', name)}
    n |= {CN[m.group(1)] for m in re.finditer(r'[（(]\s*([一二三四五六七八九十])\s*线\s*[)）]', name)}
    return sorted(n)


def capacity_map():
    lines = [r for r in csv.DictReader(io.open(os.path.join(PO, 'glass_lines_parsed.csv'), encoding='utf-8-sig'))
             if r['product_class'] == 'float']
    pts = list(csv.DictReader(io.open(os.path.join(PO, 'glass_line_points.csv'), encoding='utf-8-sig')))
    by_ent_lines = collections.defaultdict(list)
    for r in lines:
        by_ent_lines[r['enterprise']].append(r)
    by_ent_pts = collections.defaultdict(list)
    for p in pts:
        by_ent_pts[p['enterprise']].append(p)

    cap, basis = {}, {}
    for ent, ps in by_ent_pts.items():
        ols = by_ent_lines.get(ent, [])
        nums = [official_line_no(o['line_name']) for o in ols]
        flat = [x for k in nums for x in k]
        unique_ok = ols and all(len(k) == 1 for k in nums) and len(set(flat)) == len(flat)
        if unique_ok:
            tbl = {official_line_no(o['line_name'])[0]: int(o['capacity_tpd']) for o in ols}
            if all(int(p['line_no']) in tbl for p in ps):
                for p in ps:
                    cap[p['port_id']] = tbl[int(p['line_no'])]; basis[p['port_id']] = 'line_no'
                continue
        tot = sum(int(o['capacity_tpd']) for o in ols) or int(ps[0]['float_tpd'])
        share = tot / float(len(ps))
        for p in ps:
            cap[p['port_id']] = share; basis[p['port_id']] = 'even'
    return cap, basis, {p['port_id']: p for p in pts}


def policy_windows():
    rows = list(csv.DictReader(io.open(os.path.join(PO, 'alert_calendar_邢台市.csv'), encoding='utf-8-sig')))
    rows.sort(key=lambda r: (r['pubdate'], int(r['act_id'] or 0)))
    win, cur = [], None
    for r in rows:
        if r['action'] in ('raise', 'upgrade'):
            if cur is None: cur = dict(start=r['pubdate'], level=r['level_en'] or 'orange')
            elif r['level_en']: cur['level'] = r['level_en']
        elif r['action'] == 'lift' and cur:
            cur['end'] = r['pubdate']; win.append(cur); cur = None
    return win


def alt_groups():
    """读取轮流生产组；每组视为共用一座熔窑。"""
    fn = os.path.join(PO, 'alternating_groups.json')
    if not os.path.exists(fn):
        return []
    return [set(g) for g in json.load(io.open(fn, encoding='utf-8'))]


def main():
    cap, basis, pts = capacity_map()
    groups = alt_groups()
    gmap = {}
    for i, g in enumerate(groups):
        for pid in g:
            gmap[pid] = i
    if groups:
        print('轮流生产组 %d 个，涉及 %d 个点位（组内产能只计一次）'
              % (len(groups), sum(len(g) for g in groups)))
    wins = policy_windows()
    print('产能归属：line_no %d 个点，even %d 个点，合计 %.0f t/d'
          % (sum(1 for v in basis.values() if v == 'line_no'),
             sum(1 for v in basis.values() if v == 'even'), sum(cap.values())))

    # (date, port) -> 各状态小时数
    acc = collections.defaultdict(lambda: collections.Counter())
    for f in glob.glob(os.path.join(RAW, '*', '*.json')):
        pid = os.path.basename(os.path.dirname(f))
        for r in (json.load(io.open(f, encoding='utf-8')).get('data') or []):
            t = (r.get('time') or '')[:10]
            if not t: continue
            acc[(t, pid)][classify(r.get('stop-stopDcsType'))] += 1

    days = collections.defaultdict(lambda: collections.defaultdict(float))
    gdone = collections.defaultdict(set)          # date -> 已计入的组号
    for (d, pid), c in sorted(acc.items()):
        tot = sum(c.values()) or 1
        tpd = cap.get(pid, 0.0)
        ent = pts.get(pid, {}).get('enterprise', '')
        gi = gmap.get(pid)
        if gi is not None:
            if gi in gdone[d]:
                continue                          # 同组已计，跳过（共用熔窑不重复计产能）
            gdone[d].add(gi)
            # 组内产能取组内点位之和（即该熔窑全部设计产能），状态取组内最"在产"的一档
            tpd = sum(cap.get(x, 0.0) for x in groups[gi])
            merged = collections.Counter()
            for x in groups[gi]:
                merged += acc.get((d, x), collections.Counter())
            best = collections.Counter()
            hrs = sum(merged.values()) or 1
            for st in ('running', 'transition', 'idle', 'unknown'):
                best[st] = merged[st]
            # 组内任一点位在产即视为该熔窑在产
            run_h = max(acc.get((d, x), collections.Counter())['running'] for x in groups[gi])
            c = collections.Counter({'running': run_h,
                                     'idle': max(0, 24 - run_h)})
            tot = sum(c.values()) or 1
        for st in ('running', 'transition', 'idle', 'unknown'):
            days[d]['cap_' + st] += tpd * c[st] / tot
            days[d]['h_' + st] += c[st]
        days[d]['n_pts'] += 1
        if ent in XT:
            days[d]['cap_xt'] += tpd * c['running'] / tot

    def lvl(d):
        for w in wins:
            if w['start'] <= d <= w['end']:
                return w['level']
        return ''

    out = []
    for d in sorted(days):
        r = days[d]
        tot = sum(r['cap_' + s] for s in ('running', 'transition', 'idle', 'unknown'))
        out.append(dict(date=d, n_points=int(r['n_pts']),
                        cap_running=round(r['cap_running'], 1),
                        cap_transition=round(r['cap_transition'], 1),
                        cap_idle=round(r['cap_idle'], 1),
                        cap_unknown=round(r['cap_unknown'], 1),
                        cap_total=round(tot, 1),
                        util=round(r['cap_running'] / tot, 4) if tot else '',
                        cap_running_xingtai=round(r['cap_xt'], 1),
                        policy_level=lvl(d), in_policy_window=int(bool(lvl(d)))))
    fn = os.path.join(OUT, 'melting_series_daily.csv')
    with io.open(fn, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)

    print('日度序列 %d 天：%s ~ %s' % (len(out), out[0]['date'], out[-1]['date']))
    rn = [r['cap_running'] for r in out]
    print('在产日熔量 t/d：最低 %.0f  中位 %.0f  最高 %.0f' % (min(rn), sorted(rn)[len(rn)//2], max(rn)))
    print('产能口径合计 %.0f t/d（对照清单浮法 31,340 t/d）' % out[0]['cap_total'])
    pw = [r for r in out if r['in_policy_window']]
    print('政策窗口内 %d 天 (%.1f%%)，窗口外 %d 天' % (len(pw), 100*len(pw)/len(out), len(out)-len(pw)))
    if pw:
        a = sum(r['cap_running'] for r in pw)/len(pw)
        b = sum(r['cap_running'] for r in out if not r['in_policy_window'])/(len(out)-len(pw))
        print('窗口内均值 %.0f  vs  窗口外均值 %.0f   差 %.1f%%' % (a, b, 100*(a-b)/b))
    print('-> %s' % fn)


if __name__ == '__main__':
    main()
