"""DQ-37 检验周预登记（10-03，总控第十三轮第一节第 1 条）。

只存规则，不存周次列表。规则写定后不改；要改只能另起 v2 并在总入口 §3.1 记录。
任何开发代码在读结果之前，先用 week_class() / filter_dev() 去掉检验周与封存周。

规则：
- 周：UTC 自然周，周一 00:00 起。
- 币的周：曲线创建时刻（UTC）所在周；同一个币只属于一个周，不按成交时刻拆。
- 范围：与 2025-03-01～2026-09-30 相交的周（周一 2025-02-24～2026-09-28）；范围外为 out_of_scope，
  使用前须另定规则。
- 封存：T3 封存周 2026-06-15～07-12（4 周）保持封存，既不是开发周也不是检验周。
- 检验周：sha256("RT-DQ37-testweek-v1|<SALT>|<周一 ISO 日期>") 第一个字节 mod 4 == 0（约 1/4）。
  SALT 是预登记时仓库的 HEAD 提交号（7ad8e425），选规则时已固定，不能挑。
- 其余范围内的周为开发周（dev）。
"""

import datetime as dt
import hashlib

TAG = "RT-DQ37-testweek-v1"
SALT = "7ad8e42504f6adb637881bd57a73a7681d847ba4"
MOD = 4
FIRST_MONDAY = dt.date(2025, 2, 24)
LAST_MONDAY = dt.date(2026, 9, 28)
SEALED_FIRST_MONDAY = dt.date(2026, 6, 15)
SEALED_LAST_MONDAY = dt.date(2026, 7, 6)

DEV, TEST, SEALED, OUT = "dev", "test", "sealed", "out_of_scope"


def _to_date(ts):
    """接受 date、datetime（无时区按 UTC）、ISO 字符串或 pandas Timestamp，返回 UTC 日期。"""
    if isinstance(ts, str):
        ts = dt.datetime.fromisoformat(ts.replace("Z", "+00:00").replace(" UTC", ""))
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if isinstance(ts, dt.datetime):
        if ts.tzinfo is not None:
            ts = ts.astimezone(dt.timezone.utc).replace(tzinfo=None)
        return ts.date()
    if isinstance(ts, dt.date):
        return ts
    raise TypeError("不支持的时间类型: %r" % type(ts))


def week_monday(ts):
    d = _to_date(ts)
    return d - dt.timedelta(days=d.weekday())


def _hash_says_test(monday):
    msg = "%s|%s|%s" % (TAG, SALT, monday.isoformat())
    return hashlib.sha256(msg.encode("utf-8")).digest()[0] % MOD == 0


def week_class(ts):
    """返回 'dev' / 'test' / 'sealed' / 'out_of_scope'。ts 是币的曲线创建时刻。"""
    m = week_monday(ts)
    if m < FIRST_MONDAY or m > LAST_MONDAY:
        return OUT
    if SEALED_FIRST_MONDAY <= m <= SEALED_LAST_MONDAY:
        return SEALED
    return TEST if _hash_says_test(m) else DEV


def is_dev(ts):
    return week_class(ts) == DEV


def filter_dev(df, created_col):
    """只保留开发周创建的币（pandas DataFrame）。被去掉的行不返回，也不统计。"""
    mask = df[created_col].map(is_dev)
    return df.loc[mask.astype(bool)].copy()


def assert_dev(values):
    """开发代码的守卫：任何一个时刻不在开发周就报错（不报是哪一周）。"""
    bad = sum(1 for v in values if not is_dev(v))
    if bad:
        raise ValueError("有 %d 个币不在开发周，开发代码不能读" % bad)
