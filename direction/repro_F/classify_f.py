#!/usr/bin/env python3
"""Probe F · F-λ 第一阶段最终分类。输入 F_lambda.json(detect_d1.py 产物),输出 F_final.json + CSV。
规则(原则性,不使用任何名单):自动 cap 切换 = t_touch→t_first_1h 间隔 1h±30min **且** 前值精确触 ±2%/±3%。"""
import json,datetime,csv,math
YRS=(datetime.datetime(2026,9,1)-datetime.datetime(2025,5,2)).days/365.25
gap=lambda e:(datetime.datetime.fromisoformat(e["t_first_1h"])-datetime.datetime.fromisoformat(e["t_touch"])).total_seconds()/3600
BND=lambda p: min(abs(abs(p)-0.02),abs(abs(p)-0.03))<=2e-5
ONEH=lambda e: 0.5<=gap(e)<=1.5
ev=json.load(open("F_lambda.json"))["events"]
for e in ev:
    e["gap_hours"]=round(gap(e),4)
    e["classification_final"]=("自动cap切换·正侧" if ONEH(e) and BND(e["pre_switch_funding"]) and e["pre_switch_funding"]>0
        else "自动cap切换·负侧" if ONEH(e) and BND(e["pre_switch_funding"]) else "管理性或非cap切换")
pos=[e for e in ev if e["classification_final"]=="自动cap切换·正侧"]
neg=[e for e in ev if e["classification_final"]=="自动cap切换·负侧"]
adm=[e for e in ev if e["classification_final"]=="管理性或非cap切换"]
out=dict(years=YRS,n_pos=len(pos),n_neg=len(neg),n_admin=len(adm),
         lam_pos=len(pos)/YRS,lam_neg=len(neg)/YRS,
         poisson95_pos=[1.366/YRS,10.242/YRS] if len(pos)==4 else None,events=ev)
json.dump(out,open("F_final.json","w"),ensure_ascii=False)
with open("F_lambda_events.csv","w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(ev[0].keys())); w.writeheader()
    for e in sorted(ev,key=lambda x:x["t_touch"]): w.writerow(e)
print(f"正侧 {len(pos)} ({len(pos)/YRS:.2f}/yr) | 负侧 {len(neg)} ({len(neg)/YRS:.1f}/yr) | 管理性/非cap {len(adm)}")
