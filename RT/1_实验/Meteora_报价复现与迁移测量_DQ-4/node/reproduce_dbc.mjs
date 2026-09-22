// DQ-4：离线复现 DBC 相邻两笔 swap——用前一笔事件的成交后状态，复算后一笔的链上成交
import fs from 'node:fs';
import {Connection, PublicKey} from '@solana/web3.js';
import {utils} from '@coral-xyz/anchor';
import BN from 'bn.js';
import {DynamicBondingCurveClient, SwapMode} from '@meteora-ag/dynamic-bonding-curve-sdk';
const W00='/home/ancillary/RT/RT-W00_真实探针证据包_20260914/';
const client=new DynamicBondingCurveClient(new Connection('http://127.0.0.1:1'),'finalized');
const program=client.state.getProgram(); const PID=program.programId.toBase58();
const s=x=>x==null?x:(BN.isBN(x)?x.toString(10):(x.toBase58?x.toBase58():x));
function events(file){
  const tx=JSON.parse(fs.readFileSync(file,'utf8')).result;
  const keys=[...tx.transaction.message.accountKeys, ...(tx.meta.loadedAddresses?.writable||[]), ...(tx.meta.loadedAddresses?.readonly||[])];
  const out=[];
  for(const g of tx.meta.innerInstructions||[]) for(const ix of g.instructions){
    if(keys[ix.programIdIndex]!==PID) continue;
    const b=Buffer.from(utils.bytes.bs58.decode(ix.data)); if(b.length<16) continue;
    try{ const ev=program.coder.events.decode(b.subarray(8).toString('base64')); if(ev) out.push(ev);}catch{}
  }
  return {slot:tx.slot, blockTime:tx.blockTime, err:tx.meta.err, events:out};
}
const prev=events('../raw/rpc/06_tx_dbc_prev.response.json'), next=events('../raw/rpc/07_tx_dbc_next.response.json');
const pe=prev.events.find(e=>e.name==='evtSwap2'), ne=next.events.find(e=>e.name==='evtSwap2');
const result={prev:{slot:prev.slot,err:prev.err,events:prev.events.map(e=>e.name)}, next:{slot:next.slot,err:next.err,events:next.events.map(e=>e.name)}};
if(!pe||!ne){ result.decision='PAIR_NOT_TWO_SWAPS'; console.log(JSON.stringify(result,null,1)); process.exit(0); }
// 结构与静态字段：取自 RT-W00 保存的原始账户字节（slot 446918342），只替换随成交变化的状态
const snap=JSON.parse(fs.readFileSync(W00+'quote/raw/1_getMultipleAccounts.response.json','utf8')).result;
const coder=program.coder.accounts;
const pool=coder.decode('virtualPool',Buffer.from(snap.value[0].data[0],'base64'));
const config=coder.decode('poolConfig',Buffer.from(snap.value[1].data[0],'base64'));
pool.poolState.sqrtPrice=pe.data.swapResult.nextSqrtPrice;
pool.poolState.quoteReserve=pe.data.quoteReserveAmount;
pool.poolState.isMigrated=0; pool.poolState.migrationProgress=0;
const swapBaseForQuote = ne.data.tradeDirection===0;
const mode = ne.data.swapParameters.swapMode;
const params={virtualPool:pool, config, swapBaseForQuote, hasReferral:ne.data.hasReferral, eligibleForFirstSwapWithMinFee:false, currentPoint:new BN(next.slot), slippageBps:0};
let q;
if(mode===SwapMode.ExactOut) q=client.pool.swapQuote2({...params, swapMode:mode, amountOut:ne.data.swapParameters.amount0});
else q=client.pool.swapQuote2({...params, swapMode:mode, amountIn:ne.data.swapParameters.amount0});
const obs=ne.data.swapResult;
const pick=o=>Object.fromEntries(Object.entries(o).map(([k,v])=>[k,s(v)]));
result.inputs={pre_sqrtPrice:s(pe.data.swapResult.nextSqrtPrice), pre_quoteReserve:s(pe.data.quoteReserveAmount), currentPoint:next.slot, activationPoint:s(pool.poolState.activationPoint), tradeDirection:ne.data.tradeDirection, swapMode:mode, amount0:s(ne.data.swapParameters.amount0), amount1:s(ne.data.swapParameters.amount1), dynamicFeeInitialized:config.poolFees.dynamicFee.initialized, baseFeeMode:config.poolFees.baseFee.baseFeeMode};
result.observed=pick(obs);
result.quoted=pick(q);
const cmp=(a,b)=>a!=null&&b!=null&&a.toString()===b.toString();
result.match={outputAmount:cmp(q.outputAmount,obs.outputAmount), nextSqrtPrice:cmp(q.nextSqrtPrice,obs.nextSqrtPrice), tradingFee:cmp(q.tradingFee,obs.tradingFee), protocolFee:cmp(q.protocolFee,obs.protocolFee)};
result.decision=Object.values(result.match).every(Boolean)?'EXACT_REPRODUCTION':'MISMATCH';
fs.writeFileSync('../raw/reproduce_dbc_result.json',JSON.stringify(result,null,1));
console.log(JSON.stringify(result,null,1));
