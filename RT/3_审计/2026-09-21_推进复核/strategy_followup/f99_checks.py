import hashlib,json
from pathlib import Path
import pandas as pd
import numpy as np
ROOT=Path('/home/ancillary'); outdir=ROOT/'audits/RT_20260921/strategy_followup'
SOL=69.76; FX=7.1; FEE=.004; MULT=.025
spec=[('A',ROOT/'RT/dq7/raw/F2_dev.csv','b50'),('B',ROOT/'RT/dq1f/raw/F1_val.csv','x50_24h')]
out={}
for lab,p,rc in spec:
 d=pd.read_csv(p); d=d[d.mint!='__SUMMARY__'].copy(); d=d[d[rc].notna()].copy(); d['r']=d[rc]-.004; d['cap_cny']=MULT*d.entry_x_sol*SOL*FX; d['score']=d.cap_cny*(d.r-1)
 # capacity*net ranking among positive earnings only; negative scores are not "profit"
 pos=d[d.r>1].copy().sort_values('score',ascending=False,kind='mergesort')
 P=(d.r-1).clip(lower=0).sum()
 conc={}
 for k in (5,50):
  x=pos.head(k); conc[str(k)]={'mint_count':len(x),'positive_profit_share':float(x.score.sum()/pos.score.sum()),'positive_profit_cny':float(x.score.sum()),'total_positive_profit_cny':float(pos.score.sum()),'population_share':k/len(d)}
 # equal return ranking
 eq=d.sort_values('r',ascending=False,kind='mergesort'); eqc={str(k):float((eq.head(k).r-1).clip(lower=0).sum()/P) for k in (5,50)}
 top=pos.head(20).copy(); topstats={c:{'median':float(top[c].median()),'n_nonnull':int(top[c].notna().sum())} for c in ['peak_dt','pre_peak_pm','n_buyers_pre'] if c in top};
 # actual A names fields differ: peak_dt/pre_peak_pm/n_buyers_pre exist
 out[lab]={'input':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'n':len(d),'positive_n':int((d.r>1).sum()),'concentration_capacity_net':conc,'concentration_equal_return':eqc,'top20_stats':topstats,'top20_mints':top.mint.tolist()}
# F3 natural adjacent pm ratio calculation
p=ROOT/'RT/dq8/raw/F3_devA.csv'; f=pd.read_csv(p); f3meta={'input':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'rows':len(f),'mints':int(f.mint.nunique()),'duplicate_mint_iv':int(f.duplicated(['mint','iv']).sum()),'iv_counts':{str(k):int(v) for k,v in f.iv.value_counts().sort_index().items()}}
# checkpoint last pm f_pm and new buyer feature. Adjacent checkpoints where both iv and iv+1 rows exist; ratio is next/prev pm.
# Exclude iv0 baseline (no prior interval), only adjacent observed checkpoints; pair f_newb30 at prior checkpoint to next pm ratio.
f=f.sort_values(['mint','iv']); rows=[]
for mint,g in f.groupby('mint',sort=False):
 ix={int(r.iv):r for _,r in g.iterrows()}
 for i in range(0,11):
  if i in ix and i+1 in ix:
   a,b=ix[i],ix[i+1]
   if pd.notna(a.f_pm) and pd.notna(b.f_pm) and a.f_pm>0 and b.f_pm>0 and pd.notna(a.f_newb30):
    rows.append({'mint':mint,'iv_from':i,'iv_to':i+1,'f_newb30':float(a.f_newb30),'pm_ratio':float(b.f_pm/a.f_pm),'pm_prev':float(a.f_pm),'pm_next':float(b.f_pm)})
pairs=pd.DataFrame(rows)
# Spearman via pandas; split before/after f_newb30 relative to median? Natural split: f_newb30==0 vs >0 likely claims counts 37124/6703 and correlations.
# Also total count and split by iv <=? report candidate basic splits.
def corr(x):
 if len(x)<=1: return None
 v=x.f_newb30.corr(x.pm_ratio,method='spearman')
 return None if pd.isna(v) else float(v)
f3meta['adjacent_pairs']=len(pairs); f3meta['pair_mint_count']=int(pairs.mint.nunique())
f3meta['spearman_all']=corr(pairs)
f3meta['split_zero_vs_positive']={'zero':{'n':int((pairs.f_newb30==0).sum()),'rho':corr(pairs[pairs.f_newb30==0])},'positive':{'n':int((pairs.f_newb30>0).sum()),'rho':corr(pairs[pairs.f_newb30>0])}}
f3meta['by_iv']={str(i):{'n':int((pairs.iv_from==i).sum()),'rho':corr(pairs[pairs.iv_from==i])} for i in sorted(pairs.iv_from.unique())}
f3meta['time_boundaries_seconds']=[0,300,900,1800,3600,7200,14400,28800,86400,259200,604800]
fg=f.sort_values(['mint','iv']).copy(); gp=fg.groupby('mint',sort=False)
pr=gp.shift(1); nx=gp.shift(-1)
middle=(pr.iv.notna() & nx.iv.notna())
before=fg.f_pm/pr.f_pm; after=nx.f_pm/fg.f_pm
def side_stats(ratio):
 ok=middle & ratio.notna() & fg.f_newb30.notna()
 z=fg.loc[ok,['mint','f_newb30']].copy(); z['ratio']=ratio[ok].to_numpy()
 return {'n':int(ok.sum()),'mints':int(z.mint.nunique()),'rho':float(z.f_newb30.corr(z.ratio,method='spearman'))}
f3meta['reported_style_any_previous_next']={'before':side_stats(before),'after':side_stats(after),
 'middle_with_both_values':int(middle.sum()),'middle_mints':int(fg.loc[middle,'mint'].nunique()),
 'note':'group shift crosses missing/no-trade iv rows; iv boundaries are non-equidistant'}
f3meta['interpretation']='f_pm is interval-last pm; f_newb30 is interval-last feature. Reported-style ratios use previous/next observed rows (may skip iv); no grid search.'
out['F3_devA']=f3meta
(outdir/'f99_checks.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str,allow_nan=False)+'\n')
print(json.dumps(out,ensure_ascii=False,indent=2,default=str))
