# -*- coding: utf-8 -*-
"""T-033：河北省工信厅平板玻璃生产线清单 ↔ 公开污染源平台企业/点位 映射证据

只产出证据，不判定"对应成立"。名称相似不构成映射证据；结论按 §4 的等级输出。
输入：
  data/public_official/hebei_flat_glass_lines_2024.pdf   （工信厅 2024 年度清单附件 2）
  data/runs/20260824T171000+0800/derived/enterprises.csv （U-PUB-ENT-v1）
  data/runs/20260824T171000+0800/derived/ports.csv       （U-PUB-POINT-v1）
输出：
  data/public_official/glass_lines_parsed.csv
  data/public_official/glass_line_port_mapping.csv
"""
import csv, io, os, re, sys, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, 'data/public_official/hebei_flat_glass_lines_2024.pdf')
RUN = os.path.join(ROOT, 'data/runs/20260824T171000+0800/derived')
OUT = os.path.join(ROOT, 'data/public_official')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def pdf_text(path):
    import pypdf
    r = pypdf.PdfReader(path)
    return '\n'.join((p.extract_text() or '') for p in r.pages)


def classify(name):
    n = name.upper()
    if '压延' in name or '光伏' in name or '太阳能' in name:
        return 'pv_rolled'
    if ('汽车' in name or '电子' in name) and '浮法' not in name:
        return 'auto_electronic'
    if '浮法' in name or 'LOW-E' in n or '镀膜' in name or '超白' in name:
        return 'float'
    return 'unclassified'


def parse_lines(text):
    """逐行扫描：公司序号行更新当前公司；含(投产时间, 产能)的行产出一条生产线。"""
    ent_re = re.compile(r'^\s*(\d{1,3})\s+(\S*?(?:有限公司|集团有限公司|股份有限公司|科技有限公司))\s*(.*)$')
    line_re = re.compile(r'^(.*?)\s+((?:20\d{2}[\.\-/]\d{1,2}(?:[\.\-/]\d{1,2})?)|在建)\s+(\d{2,4})\s*$')
    rows, cur_no, cur_ent, cur_addr, pending = [], None, None, '', ''
    for raw in text.split('\n'):
        s = raw.strip()
        if not s:
            continue
        m = ent_re.match(s)
        if m:
            cur_no, cur_ent = int(m.group(1)), m.group(2)
            cur_addr, pending = m.group(3).strip(), ''
            s = m.group(3).strip()
            if not s:
                continue
        m2 = line_re.match(s)
        if m2 and cur_ent:
            name = (pending + ' ' + m2.group(1)).strip()
            # 行首若残留地址片段，剥掉到第一个产能/产品词
            k = re.search(r'(\d{2,4}\s*(?:\+\s*\d{2,4}\s*)?t/d|年产|超白|太阳能|光伏|特种玻璃|防紫外线)', name)
            addr_frag = name[:k.start()].strip() if k and k.start() > 0 else ''
            if addr_frag:
                cur_addr = addr_frag
                name = name[k.start():].strip()
            rows.append(dict(seq=cur_no, enterprise=cur_ent, address=cur_addr,
                             line_name=name, commissioned=m2.group(2),
                             capacity_tpd=int(m2.group(3)), product_class=classify(name)))
            pending = ''
        else:
            pending = s if len(s) < 60 and not line_re.match(s) else ''
    return rows


def norm(name):
    return re.sub(r'[\s()（）]', '', name or '')


# 工信厅清单用母公司名，平台用法人主体名；别名须逐条留证，不得靠模糊匹配
ALIASES = {
    '中国耀华玻璃集团有限公司': ['耀华（秦皇岛）玻璃有限公司',
                                 '耀华（秦皇岛）玻璃有限公司（海港区厂区）',
                                 '耀华特种玻璃（秦皇岛）有限公司'],
}

CN_NUM = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}


def line_numbers(port_name):
    """从点位名抽取线号。备用/共用排口返回全部涉及线号，并标记 shared。"""
    n = port_name or ''
    nums = set()
    for m in re.finditer(r'(\d{1,2})\s*[#号]?\s*线', n):
        nums.add(int(m.group(1)))
    for m in re.finditer(r'([一二三四五六七八九十])\s*线', n):
        nums.add(CN_NUM[m.group(1)])
    shared = bool(re.search(r'备用|共用|--|—|、', n)) and len(nums) != 1
    return sorted(nums), shared


def main():
    if not os.path.exists(PDF):
        sys.exit('missing PDF: ' + PDF)
    lines = parse_lines(pdf_text(PDF))
    if not lines:
        sys.exit('parse produced 0 lines')

    ents = list(csv.DictReader(io.open(os.path.join(RUN, 'enterprises.csv'), encoding='utf-8-sig')))
    ports = list(csv.DictReader(io.open(os.path.join(RUN, 'ports.csv'), encoding='utf-8-sig')))
    by_norm = {}
    for e in ents:
        by_norm.setdefault(norm(e['enterprise_name_public']), []).append(e)
    ports_by_ps = {}
    for p in ports:
        ports_by_ps.setdefault(p['psId'], []).append(p)

    os.makedirs(OUT, exist_ok=True)
    with io.open(os.path.join(OUT, 'glass_lines_parsed.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['seq', 'enterprise', 'address', 'line_name',
                                          'commissioned', 'capacity_tpd', 'product_class'])
        w.writeheader(); w.writerows(lines)

    firms = {}
    for r in lines:
        d = firms.setdefault(r['enterprise'], dict(lines=0, float_lines=0, tpd=0, float_tpd=0, seq=r['seq']))
        d['lines'] += 1; d['tpd'] += r['capacity_tpd']
        if r['product_class'] == 'float':
            d['float_lines'] += 1; d['float_tpd'] += r['capacity_tpd']

    out = []
    for name, d in sorted(firms.items(), key=lambda x: x[1]['seq']):
        hit = by_norm.get(norm(name), [])
        if not hit:
            for al in ALIASES.get(name, []):
                hit += by_norm.get(norm(al), [])
        if len(hit) >= 1:
            e = hit[0]
            level = ('exact' if e['enterprise_name_public'] == name
                     else ('alias' if name in ALIASES else 'normalized'))
            ps = []
            for h in hit:
                ps += ports_by_ps.get(h['enterprise_public_id'], [])
            waste_gas = [p for p in ps if p.get('port_type_name') in ('废气', 'VOC') or '废气' in (p.get('portName') or '')]
            numbered, shared_n = set(), 0
            for p in waste_gas:
                ns, sh = line_numbers(p.get('portName'))
                if sh:
                    shared_n += 1
                elif len(ns) == 1:
                    numbered |= set(ns)
            out.append(dict(enterprise=name, match_level=level,
                            numbered_line_ports=len(numbered), shared_ports=shared_n,
                            platform_name=e['enterprise_name_public'],
                            platform_id=e['enterprise_public_id'],
                            industry=e.get('regulation_industry_name', ''),
                            city=e.get('city', ''), county=e.get('county', ''),
                            lines=d['lines'], float_lines=d['float_lines'],
                            design_tpd=d['tpd'], float_tpd=d['float_tpd'],
                            platform_ports=len(ps), gas_ports=len(waste_gas),
                            port_names='|'.join(sorted({(p.get('portName') or '') for p in ps}))[:300]))
        else:
            out.append(dict(enterprise=name, match_level='none' if not hit else 'ambiguous',
                            numbered_line_ports=0, shared_ports=0,
                            platform_name='', platform_id='', industry='', city='', county='',
                            lines=d['lines'], float_lines=d['float_lines'],
                            design_tpd=d['tpd'], float_tpd=d['float_tpd'],
                            platform_ports=0, gas_ports=0, port_names=''))

    with io.open(os.path.join(OUT, 'glass_line_port_mapping.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)

    matched = [r for r in out if r['match_level'] in ('exact', 'normalized')]
    print('PDF sha256      :', sha256(PDF))
    print('清单企业 / 生产线 : %d / %d 条，设计合计 %d t/d' % (len(firms), len(lines), sum(r['capacity_tpd'] for r in lines)))
    print('其中浮法          : %d 条，%d t/d' % (sum(1 for r in lines if r['product_class'] == 'float'),
                                                 sum(r['capacity_tpd'] for r in lines if r['product_class'] == 'float')))
    print('平台匹配到企业    : %d / %d' % (len(matched), len(firms)))
    print('匹配企业覆盖浮法  : %d t/d（占清单浮法 %.1f%%）' % (
        sum(r['float_tpd'] for r in matched),
        100.0 * sum(r['float_tpd'] for r in matched) / max(1, sum(r['float_tpd'] for r in out))))
    print()
    print('%-26s %-10s %5s %5s %7s %6s %6s %8s %6s' % (
        '企业', '匹配', '线数', '浮法', '浮法t/d', '点位', '废气点', '带线号口', '共用口'))
    for r in out:
        print('%-26s %-10s %5d %5d %7d %6d %6d %8d %6d' % (
            r['enterprise'][:26], r['match_level'], r['lines'], r['float_lines'],
            r['float_tpd'], r['platform_ports'], r['gas_ports'],
            r['numbered_line_ports'], r['shared_ports']))
    # 可逐线分辨 = 点位名带线号；单浮法线企业只要有废气口即天然无歧义
    for r in out:
        if r['numbered_line_ports'] > 0:
            r['resolvable_lines'] = min(r['numbered_line_ports'], r['float_lines'])
        elif r['float_lines'] == 1 and r['gas_ports'] >= 1:
            r['resolvable_lines'] = 1
        else:
            r['resolvable_lines'] = 0
        r['resolvable_tpd'] = (0 if not r['float_lines'] else
                               int(round(r['float_tpd'] * r['resolvable_lines'] / r['float_lines'])))
    tot_l = sum(r['float_lines'] for r in out); res_l = sum(r['resolvable_lines'] for r in out)
    tot_t = sum(r['float_tpd'] for r in out);   res_t = sum(r['resolvable_tpd'] for r in out)
    print()
    print('可逐线分辨的浮法线：%d / %d 条（%.1f%%）' % (res_l, tot_l, 100.0 * res_l / max(1, tot_l)))
    print('可逐线分辨的浮法产能：%d / %d t/d（%.1f%%）' % (res_t, tot_t, 100.0 * res_t / max(1, tot_t)))
    print('占全国浮法设计总日熔 200,000 t/d 的 %.2f%%' % (100.0 * res_t / 200000))
    print()
    print('无法逐线分辨的企业（需 T-033 后续逐条处理）：')
    for r in out:
        if r['float_lines'] and r['resolvable_lines'] < r['float_lines']:
            print('  %-26s 浮法 %d 条 %5d t/d  已分辨 %d  匹配=%s  废气口=%d'
                  % (r['enterprise'][:26], r['float_lines'], r['float_tpd'],
                     r['resolvable_lines'], r['match_level'], r['gas_ports']))


if __name__ == '__main__':
    main()
