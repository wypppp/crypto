# -*- coding: utf-8 -*-
"""T-034 M0 特征源：公开城市级逐小时空气质量数据采集

来源：中国环境监测总站"全国城市空气质量实时发布平台"的公开第三方存档
      https://quotsoft.net/air/data/china_cities_YYYYMMDD.csv
性质：完全公开数据，任何人可获取。**不构成任何独占信息优势**，仅作为 M0 基准特征。
只保留分析所需城市列，其余丢弃；已下载日期跳过；失败日期记入 missing.txt 不静默补全。
"""
import csv, io, os, ssl, sys, time, urllib.error, urllib.request
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data/public_aqi')
BASE = 'https://quotsoft.net/air/data/china_cities_%s.csv'

# 邯郸 + 河北其余市 + 输送通道邻近城市（河南北部、山东西部）+ 京津
CITIES = ['北京', '天津', '石家庄', '唐山', '秦皇岛', '邯郸', '保定', '张家口', '承德',
          '廊坊', '沧州', '衡水', '邢台', '安阳', '鹤壁', '新乡', '焦作', '濮阳',
          '聊城', '德州', '济南', '淄博', '太原', '长治', '晋城']
MONTHS = {10, 11, 12, 1, 2, 3, 4}          # 采暖季及前后，预警几乎全部落在此区间
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = 'Mozilla/5.0 (research; public air quality archive)'


def fetch(d, tries=3):
    url = BASE % d.strftime('%Y%m%d')
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                return r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(1.5 * (i + 1))
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def main(start, end):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, 'city_hourly.csv')
    seen = set()
    if os.path.exists(path):
        with io.open(path, encoding='utf-8') as f:
            for row in csv.DictReader(f):
                seen.add(row['date'])
    new, miss, hdr = 0, [], ['date', 'hour', 'type'] + CITIES
    f = io.open(path, 'a', encoding='utf-8', newline='')
    w = csv.writer(f)
    if not seen:
        w.writerow(hdr)
    d, n = start, 0
    while d <= end:
        if d.month not in MONTHS or d.strftime('%Y%m%d') in seen:
            d += timedelta(days=1); continue
        txt = fetch(d)
        n += 1
        if not txt:
            miss.append(d.isoformat())
        else:
            rd = csv.DictReader(io.StringIO(txt))
            for row in rd:
                w.writerow([row.get('date', ''), row.get('hour', ''), row.get('type', '')] +
                           [row.get(c, '') for c in CITIES])
            new += 1
        if n % 50 == 0:
            f.flush(); print('  %s  已请求 %d  新增 %d  缺 %d' % (d, n, new, len(miss)), flush=True)
        time.sleep(0.35)
        d += timedelta(days=1)
    f.close()
    if miss:
        io.open(os.path.join(OUT, 'missing.txt'), 'a', encoding='utf-8').write('\n'.join(miss) + '\n')
    print('完成：请求 %d 天，新增 %d 天，缺失 %d 天 -> %s' % (n, new, len(miss), path))


if __name__ == '__main__':
    a = sys.argv[1] if len(sys.argv) > 1 else '2019-10-01'
    b = sys.argv[2] if len(sys.argv) > 2 else '2026-03-31'
    main(date.fromisoformat(a), date.fromisoformat(b))
