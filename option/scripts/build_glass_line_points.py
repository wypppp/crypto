# -*- coding: utf-8 -*-
"""从 T-033 的映射结果生成"可逐线分辨的浮法线—排口"点位清单。

规则与 map_glass_lines_to_ports.py 一致：
  - 只取废气类排口；
  - 点位名中带唯一线号者 -> 该线的主排口；
  - 备用/共用排口单独标记，不计入逐线口径；
  - 单浮法线企业若只有一个废气口，天然无歧义。
输出：data/public_official/glass_line_points.csv
"""
import csv, io, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN = os.path.join(ROOT, 'data/runs/20260824T171000+0800/derived')
PO = os.path.join(ROOT, 'data/public_official')
CN = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}


def line_numbers(n):
    """返回 (线号列表, 是否共用/备用口)。

    共用判定**优先于**线号解析：形如「玻璃熔窑1--4线备用排放口」会解析出唯一线号 4，
    但它是 1-4 线的备用口，不是 4 线的主排口。此前按"唯一线号即主口"处理，
    导致长城玻璃被多计一条线、并产生虚假的产能进出。
    """
    n = n or ''
    if re.search(r'备用|共用|应急|事故', n):
        return [], True
    if re.search(r'\d\s*[-–—]{1,2}\s*\d|[一二三四五六七八九十]\s*[-–—]{1,2}\s*[一二三四五六七八九十]', n):
        return [], True
    nums = {int(m.group(1)) for m in re.finditer(r'(\d{1,2})\s*[#号]?\s*线', n)}
    nums |= {CN[m.group(1)] for m in re.finditer(r'([一二三四五六七八九十])\s*线', n)}
    if re.search(r'[、,，]', n) and len(nums) > 1:
        return sorted(nums), True
    return sorted(nums), len(nums) != 1


def main():
    ports = list(csv.DictReader(io.open(os.path.join(RUN, 'ports.csv'), encoding='utf-8-sig')))
    mp = [m for m in csv.DictReader(io.open(os.path.join(PO, 'glass_line_port_mapping.csv'), encoding='utf-8-sig'))
          if int(m['float_lines']) > 0 and m['platform_id']]
    by_ps = {}
    for p in ports:
        by_ps.setdefault(p['psId'], []).append(p)

    out = []
    for m in mp:
        ps = by_ps.get(m['platform_id'], [])
        gas = [p for p in ps if p.get('port_type_name') in ('废气', 'VOC') or '废气' in (p.get('portName') or '')]
        floats = int(m['float_lines'])
        numbered = []
        for p in gas:
            nums, shared = line_numbers(p.get('portName'))
            if shared or len(nums) != 1:
                continue
            numbered.append((nums[0], p))
        if numbered:
            for ln, p in sorted(numbered, key=lambda x: x[0]):
                out.append(dict(enterprise=m['enterprise'], ps_id=m['platform_id'],
                                port_id=p['id'], port_type_id=p['portTypeId'],
                                port_name=p['portName'], line_no=ln, basis='line_no',
                                float_lines=floats, float_tpd=m['float_tpd']))
        elif floats == 1 and len(gas) >= 1:
            p = gas[0]
            out.append(dict(enterprise=m['enterprise'], ps_id=m['platform_id'],
                            port_id=p['id'], port_type_id=p['portTypeId'],
                            port_name=p['portName'], line_no=1, basis='single_line',
                            float_lines=floats, float_tpd=m['float_tpd']))

    fn = os.path.join(PO, 'glass_line_points.csv')
    with io.open(fn, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    firms = {}
    for r in out:
        firms.setdefault(r['enterprise'], []).append(r)
    print('可逐线分辨点位：%d 个，覆盖 %d 家企业' % (len(out), len(firms)))
    for e in sorted(firms, key=lambda x: -len(firms[x])):
        r = firms[e]
        print('  %-26s %d 个点  (清单浮法 %s 条 / %s t/d)' % (e[:26], len(r), r[0]['float_lines'], r[0]['float_tpd']))
    print('-> %s' % fn)


if __name__ == '__main__':
    main()
