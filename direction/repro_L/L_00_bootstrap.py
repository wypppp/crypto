"""Probe L · 引导。唯一可执行来源 = 与本脚本**同目录**的 L_config.json。
回显全文、校验顶层与嵌套键;每阶段显式声明 required_inputs,缺失立即失败;
输入哈希在读取前记录,输出哈希在写完后单独记录。

⚠ CFG_PATH 默认**必须**是脚本同目录,不得指向仓库根目录 ——
否则复现包不自足:校验包内 v1.6 哈希全通过,运行时却加载根目录的 v1.8.8 规则
(2026-09-06 审查实证)。跨目录使用须显式设置 L_CONFIG 环境变量。"""
import json,hashlib,sys,os
_HERE=os.path.dirname(os.path.abspath(__file__))
CFG_PATH=os.environ.get("L_CONFIG",os.path.join(_HERE,"L_config.json"))
REQUIRED={
 "_meta":["version","frozen_utc"],
 "mother_universe":["endpoint","detail_endpoint","catalog_id","catalog_name_expected","window_start_utc",
                    "window_end_utc","expected_count_in_window","crawl","classification","extract","dedup_rule",
                    "event_id","leveraged_token_rule","earliest_month_probe","t0_procedure","timestamp_normalization"],
 "timestamps":["T_scheduled","T_first_trade","T0_for_strategy"],
 "filters":["computable","not_computable","main_spec"],
 "price_proxy":["entry","entry_tolerance_minutes","exit","exit_tolerance_hours","on_missing"],
 "estimators":["must_report_separately","primary","full_universe_mean"],
 "concurrency":["f_policy_cap","max_slots","slot_hold_days","selection_when_oversubscribed","output_name"],
 "holdout":["rule","enforcement","open_condition","open_count_limit"],
 "b_leg":["linkage_rule","must_store","allowed_outputs","forbidden_outputs"],
 "lambda_layers":None,"lambda_exec":None,"assertions":None}
def sha(p): return hashlib.sha256(open(p,'rb').read()).hexdigest()
def load(code_files,required_inputs=()):
    raw=open(CFG_PATH,'rb').read(); cfg=json.loads(raw)
    unknown=set(cfg)-set(REQUIRED); missing=[k for k in REQUIRED if k not in cfg]
    nested=[f"{k}.{s}" for k,subs in REQUIRED.items() if subs for s in subs
            if k in cfg and s not in (cfg[k] if isinstance(cfg[k],dict) else {})]
    if unknown or missing or nested:
        sys.exit(f"CONFIG FAIL 未识别={sorted(unknown)} 缺失顶层={missing} 缺失嵌套={nested}")
    absent=[f for f in required_inputs if not os.path.exists(f)]
    if absent: sys.exit(f"REQUIRED INPUT MISSING: {absent}")      # 缺失立即失败,不静默跳过
    h={"L_config.json":hashlib.sha256(raw).hexdigest()}
    for f in code_files: h["code:"+os.path.basename(f)]=sha(f)
    for f in required_inputs: h["input:"+f]=sha(f)
    print("="*78)
    print(f"CONFIG {CFG_PATH}  v{cfg['_meta']['version']}  frozen={cfg['_meta']['frozen_utc']}")
    for k,v in h.items(): print(f"  SHA256 {v}  {k}")
    print("-"*78+"\nCONFIG 全文回显:"); print(json.dumps(cfg,ensure_ascii=False,indent=1)); print("="*78,flush=True)
    return cfg,h
def record_outputs(paths):
    print("-"*78+"\n输出产物哈希(写入后):")
    for p in paths:
        if os.path.exists(p): print(f"  SHA256 {sha(p)}  output:{p}")
        else: print(f"  ⚠ 输出缺失: {p}")
    print("-"*78,flush=True)
