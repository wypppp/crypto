# -*- coding: utf-8 -*-
"""T-034 M0：只用公开数据预测重污染天气预警发布（基准模型）

目的不是"预测得准"，而是量出**公开数据能做到的最好水平**。
使用者持有的省控站/未联网站点数据的真实 Edge = AUC(M2) - AUC(M0)，不是 AUC(M2) 本身。

标签：data/public_official/alert_calendar_<city>.csv 中 action ∈ {raise, upgrade}
特征：data/public_aqi/city_hourly.csv（公开城市级逐小时；国控站数据完全公开，非独占）
切分：按时间，训练期与检验期不重叠，不做同期拟合同期检验
"""
import io, os, sys
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AQI = os.path.join(ROOT, 'data/public_aqi/city_hourly.csv')
CAL = os.path.join(ROOT, 'data/public_official/alert_calendar_%s.csv')

TARGET = '邯郸'
NEIGH = ['邢台', '安阳', '石家庄', '濮阳', '聊城']      # 传输通道邻近城市
TYPES = ['AQI', 'PM2.5', 'PM10', 'SO2', 'NO2', 'CO', 'O3']
HORIZON = 2          # t+1..t+2 日内是否发布预警 ≈ 48 小时
SPLIT = '2024-07-01'  # 训练/检验时间切点


def load_daily():
    df = pd.read_csv(AQI, dtype={'date': str})
    df = df[df['type'].isin(TYPES)]
    cols = [TARGET] + NEIGH
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df['d'] = pd.to_datetime(df['date'], format='%Y%m%d')
    # 日聚合：均值与最大值
    g = df.groupby(['d', 'type'])[cols].agg(['mean', 'max'])
    g.columns = ['%s_%s' % (a, b) for a, b in g.columns]
    out = g.unstack('type')
    out.columns = ['%s_%s' % (a, b) for a, b in out.columns]
    return out.sort_index()


def load_labels(city):
    p = CAL % city
    cal = pd.read_csv(p, encoding='utf-8-sig')
    cal = cal[cal['action'].isin(['raise', 'upgrade'])]
    return pd.to_datetime(cal['pubdate']).dt.normalize().unique()


def build(feat, alert_days):
    X = feat.copy()
    base = [c for c in X.columns if c.endswith('_AQI')]
    # 滞后与变化率
    for lag in (1, 2, 3):
        for c in base:
            X['%s_lag%d' % (c, lag)] = X[c].shift(lag)
    for c in base:
        X['%s_d1' % c] = X[c] - X[c].shift(1)
        X['%s_ma3' % c] = X[c].rolling(3).mean()
    # 季节
    doy = X.index.dayofyear.values
    X['sin_doy'] = np.sin(2 * np.pi * doy / 365.25)
    X['cos_doy'] = np.cos(2 * np.pi * doy / 365.25)
    X['month'] = X.index.month
    # 距上次预警天数（只用过去信息）
    aset = pd.DatetimeIndex(sorted(alert_days))
    since = []
    for d in X.index:
        prev = aset[aset < d]
        since.append((d - prev[-1]).days if len(prev) else 999)
    X['days_since_alert'] = np.minimum(since, 999)
    # 标签：t+1..t+HORIZON 内是否有 raise/upgrade
    aday = set(pd.DatetimeIndex(alert_days).normalize())
    y = [int(any((d + pd.Timedelta(days=k)) in aday for k in range(1, HORIZON + 1))) for d in X.index]
    X['y'] = y
    return X.dropna()


def main():
    if not os.path.exists(AQI):
        sys.exit('缺少特征文件，请先运行 fetch_public_city_aqi.py')
    feat = load_daily()
    alerts = load_labels('邯郸市')
    data = build(feat, alerts)
    # 只保留采暖季前后，与采集范围一致
    data = data[data['month'].isin([10, 11, 12, 1, 2, 3, 4])]
    tr = data[data.index < SPLIT]
    te = data[data.index >= SPLIT]
    fx = [c for c in data.columns if c != 'y']
    print('样本：训练 %d 天（正例 %d，基础率 %.3f）｜检验 %d 天（正例 %d，基础率 %.3f）'
          % (len(tr), tr['y'].sum(), tr['y'].mean(), len(te), te['y'].sum(), te['y'].mean()))
    if tr['y'].sum() < 5 or te['y'].sum() < 3:
        sys.exit('正例过少，样本不足以评估；请扩大采集范围')
    m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=0.3, class_weight='balanced'))
    m.fit(tr[fx], tr['y'])
    for name, s in (('训练期', tr), ('检验期', te)):
        p = m.predict_proba(s[fx])[:, 1]
        print('%s  AUC=%.4f  PR-AUC=%.4f（基础率 %.4f）'
              % (name, roc_auc_score(s['y'], p), average_precision_score(s['y'], p), s['y'].mean()))
    # 单特征参考：仅用当日邯郸 AQI 均值
    solo = '%s_mean_AQI' % TARGET
    if solo in te.columns:
        print('参考·仅当日 %s：检验期 AUC=%.4f' % (solo, roc_auc_score(te['y'], te[solo])))
    coef = pd.Series(m[-1].coef_[0], index=fx).sort_values(key=abs, ascending=False)
    print('\n权重最大的 12 个特征：')
    for k, v in coef.head(12).items():
        print('  %-28s %+.3f' % (k, v))
    print('\n【口径提醒】本结果是 M0，全部特征均为公开数据。'
          '\n成分 A 的 Edge 必须报告为 AUC(M2)-AUC(M0)，不得以 AUC(M2) 单独宣称。')


if __name__ == '__main__':
    main()
