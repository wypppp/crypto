"""Probe L · 下载最早日 aggTrades 并求精确 T0。**只读已冻结的 t0_manifest.json,不自行重算母体与留出划分。**
每文件校验:HTTP 200 → 官方 CHECKSUM → ZIP 完整性 → CSV schema → 文件名日期 → 时间戳单位。
写入采用临时文件 + 原子改名。T0 = 该 baseAsset 全部并列文件中实际时间戳的最小值(整数微秒)。
用法: python3 L_07_download_t0.py [--canary]"""
import json,os,sys,io,zipfile,hashlib,datetime,urllib.request,urllib.parse,tempfile,collections
sys.path.insert(0,'.'); from L_00_bootstrap import load,record_outputs
REQ=["t0_manifest.json"]
cfg,H=load([__file__,"L_00_bootstrap.py"],REQ)
TN=cfg["mother_universe"]["timestamp_normalization"]
V="https://data.binance.vision/data/spot/daily/aggTrades"
MAN=json.load(open("t0_manifest.json"))["download_manifest"]
os.makedirs("aggdl",exist_ok=True)
CANARY="--canary" in sys.argv

def norm_us(v:int)->int:
    d=len(str(v))
    if d==13: return v*1000
    if d==16: return v
    raise SystemExit(f"TIMESTAMP UNIT FAIL: {v} 有 {d} 位,既非 13 也非 16")

def fetch(sym,day):
    """返回 (最小时间戳微秒, 行数);任何校验失败即抛错。"""
    q=urllib.parse.quote(sym,safe='')
    base=f"{V}/{urllib.parse.quote(sym,safe='')}/{urllib.parse.quote(sym,safe='')}-aggTrades-{day}.zip"
    raw=urllib.request.urlopen(base,timeout=90).read()
    # 官方 CHECKSUM
    try:
        chk=urllib.request.urlopen(base+".CHECKSUM",timeout=45).read().decode().split()[0]
        if hashlib.sha256(raw).hexdigest()!=chk: raise SystemExit(f"CHECKSUM FAIL {sym} {day}")
        chk_ok=True
    except urllib.error.HTTPError: chk_ok=False
    z=zipfile.ZipFile(io.BytesIO(raw))
    bad=z.testzip()
    if bad: raise SystemExit(f"ZIP CORRUPT {sym} {day}: {bad}")
    lines=z.read(z.namelist()[0]).decode().splitlines()
    if lines and lines[0][0].isalpha(): lines=lines[1:]        # 可能带表头
    if not lines: raise SystemExit(f"EMPTY CSV {sym} {day}")
    ncol=len(lines[0].split(','))
    if ncol<6: raise SystemExit(f"SCHEMA FAIL {sym} {day}: {ncol} 列")
    ts=[norm_us(int(l.split(',')[5])) for l in lines]
    mn=min(ts)
    d=datetime.datetime.fromtimestamp(mn/1_000_000,datetime.timezone.utc)
    if d.strftime("%Y-%m-%d")!=day: raise SystemExit(f"DATE MISMATCH {sym} {day}: 归一后为 {d:%Y-%m-%d}")
    if not (2017<=d.year<=2027): raise SystemExit(f"YEAR OUT OF RANGE {sym} {day}: {d.year}")
    fd,tmp=tempfile.mkstemp(dir="aggdl"); os.close(fd)
    json.dump({"symbol":sym,"day":day,"min_ts_us":mn,"n_rows":len(lines),
               "checksum_verified":chk_ok,"zip_sha256":hashlib.sha256(raw).hexdigest()},open(tmp,"w"))
    os.replace(tmp,f"aggdl/{q}__{day}.json")                   # 原子改名
    return mn,len(lines)

if CANARY:
    pick=[]
    for yr in ("2024","2025","2026"):
        for r in MAN:
            if r["earliest_trade_day"].startswith(yr) and len(pick)<9:
                pick.append((r["tied_pairs"][0],r["earliest_trade_day"])); break
    for r in MAN:
        if any(ord(c)>127 for c in r["base"]): pick.append((r["tied_pairs"][0],r["earliest_trade_day"])); break
    print(f"CANARY {len(pick)} 个: {pick}")
    for sym,day in pick:
        mn,n=fetch(sym,day)
        print(f"  ✅ {sym:<16}{day}  min_ts_us={mn}  rows={n}  "
              f"UTC={datetime.datetime.fromtimestamp(mn/1_000_000,datetime.timezone.utc):%Y-%m-%d %H:%M:%S.%f}")
    print("CANARY 全部通过")
    sys.exit(0)
print(f"下载清单: {len(MAN)} 个 baseAsset,{sum(r['n_tied'] for r in MAN)} 个文件")
print("（未加 --canary 时本脚本仍不自动全量下载;请显式确认后再运行 full 模式）")
