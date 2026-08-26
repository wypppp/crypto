# -*- coding: utf-8 -*-
"""T-031 L1：河北各市重污染天气预警日历采集

只采标题与发布日期，解析为 发布/解除 事件与预警等级；不抓正文、不改写、不推断缺失。
预警级别按《河北省重污染天气应急预案》：黄色=III级、橙色=II级、红色=I级。
输出：data/public_official/alert_calendar_<city>.csv 与 alert_calendar_all.csv
"""
import csv, io, json, os, re, sys, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data/public_official')

# 已验证可用的市级来源；未验证的市不得凭猜测加入
SOURCES = {
    '邯郸市': dict(kind='ruoyi', url='https://sthj.hd.gov.cn/main/getList', category=243),
    # 邢台市生态环境局「环境应急」栏目；沙河市属邢台，是 A01 核心产区
    # 站点为 http://stj.xingtai.gov.cn（非 sthj/xtsthjj），列表分页 /html/1355/list-N.html
    '邢台市': dict(kind='xt_html', base='http://stj.xingtai.gov.cn', column=1355, max_pages=12),
}

LEVEL = [('红色', 'red', 'I'), ('橙色', 'orange', 'II'), ('黄色', 'yellow', 'III')]


def post(url, data, timeout=25):
    req = urllib.request.Request(
        url, data=urllib.parse.urlencode(data).encode(),
        headers={'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                 'X-Requested-With': 'XMLHttpRequest',
                 'User-Agent': 'Mozilla/5.0 (research; public disclosure audit)'})
    import ssl
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


def classify(title):
    """返回 (action, level_cn, level_en, response_level)。无法判定的一律返回 None，不猜。"""
    t = title or ''
    if '重污染天气' not in t and '应急响应' not in t:
        return None
    if '解除' in t:
        action = 'lift'
    elif '发布' in t or '启动' in t or '升级' in t or '调整' in t:
        action = 'raise' if '升级' not in t else 'upgrade'
    else:
        return None
    for cn, en, resp in LEVEL:
        if cn in t:
            return action, cn, en, resp
    m = re.search(r'([ⅠⅡⅢ])\s*级', t)
    if m:
        resp = {'Ⅰ': 'I', 'Ⅱ': 'II', 'Ⅲ': 'III'}[m.group(1)]
        cn, en = {'I': ('红色', 'red'), 'II': ('橙色', 'orange'), 'III': ('黄色', 'yellow')}[resp]
        return action, cn, en, resp
    return action, '', '', ''          # 解除通知常不带级别，保留空值不猜


def collect_ruoyi(city, cfg, page_size=50, max_pages=40):
    rows, page = [], 1
    while page <= max_pages:
        d = post(cfg['url'], {'categoryId': cfg['category'], 'pageNum': page, 'pageSize': page_size})
        got = d.get('rows') or []
        rows += got
        total = d.get('total') or 0
        if page * page_size >= total or not got:
            break
        page += 1
        time.sleep(1.0)                # 公开政府站，限速
    return rows, total


def collect_xt_html(city, cfg):
    """邢台市局 CMS：/html/{column}/ 为首页，/html/{column}/list-N.html 为第 N 页。
    只取列表页的日期与标题，不抓正文。空页即停止，不猜测总页数。"""
    import ssl
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    pat = re.compile(r'/html/\d+/(\d{4}-\d{2}-\d{2})/content-(\d+)\.html"[^>]*>\s*([^<]{4,120}?)\s*<')
    rows, seen = [], set()
    for page in range(1, cfg.get('max_pages', 12) + 1):
        url = '%s/html/%d/%s' % (cfg['base'], cfg['column'], '' if page == 1 else 'list-%d.html' % page)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (research; public disclosure audit)'})
        try:
            with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
                html = r.read().decode('utf-8', 'replace')
        except Exception:
            break
        got = pat.findall(html)
        if not got:
            break
        fresh = 0
        for d, aid, title in got:
            if aid in seen:
                continue
            seen.add(aid); fresh += 1
            rows.append({'title': re.sub(r'\s+', ' ', title).strip(),
                         'pubdateStr': d, 'actId': int(aid)})
        if fresh == 0:
            break
        time.sleep(1.0)                # 公开政府站，限速
    return rows, len(rows)


def main():
    os.makedirs(OUT, exist_ok=True)
    allrows = []
    for city, cfg in SOURCES.items():
        if cfg.get('kind') == 'xt_html':
            raw, total = collect_xt_html(city, cfg)
        else:
            raw, total = collect_ruoyi(city, cfg)
        with io.open(os.path.join(OUT, 'alert_raw_%s.json' % city), 'w', encoding='utf-8') as f:
            json.dump(raw, f, ensure_ascii=False, indent=1)
        parsed = []
        for r in raw:
            c = classify(r.get('title'))
            if not c:
                continue
            action, cn, en, resp = c
            parsed.append(dict(city=city, pubdate=(r.get('pubdateStr') or '')[:10],
                               action=action, level_cn=cn, level_en=en, response_level=resp,
                               title=r.get('title'), act_id=r.get('actId')))
        parsed.sort(key=lambda x: (x['pubdate'], x['act_id'] or 0))
        with io.open(os.path.join(OUT, 'alert_calendar_%s.csv' % city), 'w',
                     encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['city', 'pubdate', 'action', 'level_cn',
                                              'level_en', 'response_level', 'title', 'act_id'])
            w.writeheader(); w.writerows(parsed)
        allrows += parsed
        print('%s: 栏目 %d 条 -> 识别为预警事件 %d 条' % (city, total, len(parsed)))
        if parsed:
            print('   时间跨度 %s .. %s' % (parsed[0]['pubdate'], parsed[-1]['pubdate']))
            from collections import Counter
            print('   动作分布:', dict(Counter(p['action'] for p in parsed)))
            print('   级别分布:', dict(Counter(p['level_cn'] or '(未标级别)' for p in parsed)))

    if allrows:
        allrows.sort(key=lambda x: (x['city'], x['pubdate']))
        with io.open(os.path.join(OUT, 'alert_calendar_all.csv'), 'w',
                     encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(allrows[0].keys()))
            w.writeheader(); w.writerows(allrows)
        print('\n合计 %d 条，已写入 alert_calendar_all.csv' % len(allrows))
        print('\n覆盖的市：%s' % '、'.join(SOURCES))
        print('未覆盖（须逐市另行验证来源，不得外推）：邢台市（沙河）、秦皇岛市、唐山市、廊坊市、石家庄市 等')


if __name__ == '__main__':
    main()
