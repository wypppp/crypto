// DQ-4：离线复现 DAMM v2 相邻两笔 swap；池结构取当前账户，sqrtPrice 取前一笔事件的成交后值
import fs from 'node:fs';
import {utils} from '@coral-xyz/anchor';
import BN from 'bn.js';
import {cpAmmCoder, CpAmmIdl, CP_AMM_PROGRAM_ID, swapQuoteExactInput, swapQuotePartialInput, swapQuoteExactOutput} from '@meteora-ag/cp-amm-sdk';
const PID=CP_AMM_PROGRAM_ID.toBase58();
const s=x=>x==null?x:(BN.isBN(x)?x.toString(10):(x.toBase58?x.toBase58():(typeof x==='bigint'?x.toString():x)));
const acctName=CpAmmIdl.accounts.map(a=>a.name).find(n=>/^pool$/i.test(n));
const snap=JSON.parse(fs.readFileSync('../raw/rpc/10_damm_pool_account_now.response.json','utf8')).result;
const raw=cpAmmCoder.accounts.decode(acctName, Buffer.from(snap.value.data[0],'base64'));
function events(file){
  const tx=JSON.parse(fs.readFileSync(file,'utf8')).result;
  const keys=[...tx.transaction.message.accountKeys, ...(tx.meta.loadedAddresses?.writable||[]), ...(tx.meta.loadedAddresses?.readonly||[])];
  const out=[];
  for(const g of tx.meta.innerInstructions||[]) for(const ix of g.instructions){
    if(keys[ix.programIdIndex]!==PID) continue;
    const b=Buffer.from(utils.bytes.bs58.decode(ix.data)); if(b.length<16) continue;
    try{ const ev=cpAmmCoder.events.decode(b.subarray(8).toString('base64')); if(ev) out.push(ev);}catch{}
  }
  return {slot:tx.slot, blockTime:tx.blockTime, err:tx.meta.err, events:out};
}
const prev=events('../raw/rpc/08_tx_damm_prev.response.json'), next=events('../raw/rpc/09_tx_damm_next.response.json');
const pe=prev.events.find(e=>/swap/i.test(e.name)), ne=next.events.find(e=>/swap/i.test(e.name));
const result={account_name:acctName, account_now:{context_slot:snap.context.slot, liquidity:s(raw.liquidity), sqrt_price:s(raw.sqrt_price), activation_type:raw.activation_type, collect_fee_mode:raw.collect_fee_mode, pool_status:raw.pool_status, dynamic_fee_initialized:raw.pool_fees.dynamic_fee.initialized, fee_version:raw.fee_version, layout_version:raw.layout_version},
  initial_liquidity_from_event:'9015283436793370279256537324536',
  prev:{slot:prev.slot,blockTime:prev.blockTime,err:prev.err,events:prev.events.map(e=>e.name)}, next:{slot:next.slot,blockTime:next.blockTime,err:next.err,events:next.events.map(e=>e.name)}};
result.liquidity_unchanged_since_migration = s(raw.liquidity)===result.initial_liquidity_from_event;
if(!pe||!ne){ result.decision='PAIR_NOT_TWO_SWAPS'; console.log(JSON.stringify(result,null,1)); process.exit(0); }
// SDK 期望的 camelCase PoolState：用 SDK 自带的账户解码器形状
const toCamel=o=>{ if(o==null||BN.isBN(o)||o.toBase58||typeof o!=='object'||Buffer.isBuffer(o)) return o; if(Array.isArray(o)) return o.map(toCamel); return Object.fromEntries(Object.entries(o).map(([k,v])=>[k.replace(/_([a-z0-9])/g,(_,c)=>c.toUpperCase()),toCamel(v)])); };
const pool=toCamel(raw);
pool.sqrtPrice=pe.data.swap_result.next_sqrt_price;
const d=ne.data, aToB = d.trade_direction===0, mode=d.params.swap_mode;
const currentPoint = raw.activation_type===1 ? new BN(next.blockTime) : new BN(next.slot);
let q, err;
try{
  if(mode===0) q=swapQuoteExactInput(pool,currentPoint,d.params.amount_0,0,aToB,d.has_referral,6,9);
  else if(mode===1) q=swapQuotePartialInput(pool,currentPoint,d.params.amount_0,0,aToB,d.has_referral,6,9);
  else q=swapQuoteExactOutput(pool,currentPoint,d.params.amount_0,0,aToB,d.has_referral,6,9);
}catch(e){ err=e.message; }
const obs=d.swap_result;
result.inputs={pre_sqrtPrice:s(pe.data.swap_result.next_sqrt_price), pre_reserve_a:s(pe.data.reserve_a_amount), pre_reserve_b:s(pe.data.reserve_b_amount), currentPoint:s(currentPoint), trade_direction:d.trade_direction, swap_mode:mode, amount_0:s(d.params.amount_0), amount_1:s(d.params.amount_1), collect_fee_mode:d.collect_fee_mode};
result.observed=Object.fromEntries(Object.entries(obs).map(([k,v])=>[k,s(v)]));
if(err){ result.quote_error=err; result.decision='QUOTE_ERROR'; }
else {
  result.quoted=Object.fromEntries(Object.entries(q).filter(([k,v])=>v!=null&&typeof v!=='object'||BN.isBN(v)).map(([k,v])=>[k,s(v)]));
  const cmp=(a,b)=>a!=null&&b!=null&&a.toString()===b.toString();
  result.match={outputAmount:cmp(q.outputAmount,obs.output_amount), nextSqrtPrice:cmp(q.nextSqrtPrice,obs.next_sqrt_price), claimingFee:cmp(q.claimingFee,obs.claiming_fee), protocolFee:cmp(q.protocolFee,obs.protocol_fee)};
  result.decision=Object.values(result.match).every(Boolean)?'EXACT_REPRODUCTION':'MISMATCH';
}
fs.writeFileSync('../raw/reproduce_damm_result.json',JSON.stringify(result,null,1));
console.log(JSON.stringify(result,null,1));
