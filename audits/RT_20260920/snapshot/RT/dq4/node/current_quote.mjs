// DQ-4：只读 RPC（上限 10 次），对目标 DAMM v2 池做一次当前状态报价：买入 0.01 SOL，再报价卖出所得
import fs from 'node:fs';
import {Connection, PublicKey} from '@solana/web3.js';
import {unpackMint, getExtensionTypes} from '@solana/spl-token';
import {CpAmm} from '@meteora-ag/cp-amm-sdk';
import BN from 'bn.js';
const RAW='../raw/current_quote/'; fs.mkdirSync(RAW,{recursive:true});
const POOL=new PublicKey('AQ7q2SabJfGSTsSZzZhNvj7Mddj3KHjKBEMfJ9SusH3T');
const MAX=10; let calls=0;
const clean=x=>{ if(x==null) return x; if(typeof x==='bigint') return x.toString(); if(x.toBase58) return x.toBase58(); if(BN.isBN(x)) return x.toString(10); if(Buffer.isBuffer(x)) return {base64:x.toString('base64')}; if(Array.isArray(x)) return x.map(clean); if(typeof x==='object') return Object.fromEntries(Object.entries(x).map(([k,v])=>[k,clean(v)])); return x; };
const conn=new Connection('https://api.mainnet-beta.solana.com',{commitment:'finalized',disableRetryOnRateLimit:true,fetch:async(url,o)=>{
  if(++calls>MAX) throw Error('RPC budget exceeded');
  const req=JSON.parse(o.body);
  if(!['getAccountInfo','getMultipleAccounts','getSlot','getBlockTime','getEpochInfo'].includes(req.method)) throw Error('Unexpected RPC '+req.method);
  const name=RAW+calls+'_'+req.method;
  fs.writeFileSync(name+'.request.json',JSON.stringify({request:req,source:url,started_at:new Date().toISOString()},null,2));
  const r=await fetch(url,{...o,signal:AbortSignal.timeout(15000)});
  fs.writeFileSync(name+'.response.json',await r.clone().text());
  return r;
}});
const result={pool:POOL.toBase58(), entry_Q_lamports:'10000000', note:'当前状态报价，不代表历史时点；卖出报价沿用同一池状态，未计入我方买入对池子的影响；不签名、不广播'};
try{
  const amm=new CpAmm(conn);
  const pool=await amm.fetchPoolState(POOL);
  const slot=await conn.getSlot('finalized');
  const time=await conn.getBlockTime(slot);
  const epoch=(await conn.getEpochInfo('finalized')).epoch;
  const mints=await conn.getMultipleAccountsInfo([pool.tokenAMint,pool.tokenBMint],'finalized');
  const mintA=unpackMint(pool.tokenAMint,mints[0],mints[0].owner), mintB=unpackMint(pool.tokenBMint,mints[1],mints[1].owner);
  Object.assign(result,{slot,time,epoch,
    tokenA:{mint:pool.tokenAMint.toBase58(),decimals:mintA.decimals,program:mints[0].owner.toBase58(),extensions:getExtensionTypes(mintA.tlvData)},
    tokenB:{mint:pool.tokenBMint.toBase58(),decimals:mintB.decimals,program:mints[1].owner.toBase58(),extensions:getExtensionTypes(mintB.tlvData)},
    pool_state:{sqrtPrice:pool.sqrtPrice, liquidity:pool.liquidity, activationPoint:pool.activationPoint, activationType:pool.activationType, poolStatus:pool.poolStatus, collectFeeMode:pool.collectFeeMode, feeVersion:pool.feeVersion, dynamicFeeInitialized:pool.poolFees?.dynamicFee?.initialized, baseFee:pool.poolFees?.baseFee, tokenAAmount:pool.tokenAAmount, tokenBAmount:pool.tokenBAmount}});
  const wsol='So11111111111111111111111111111111111111112';
  const solIsA=pool.tokenAMint.toBase58()===wsol;
  const tokInfo=(mint,info)=>({mint:info,currentEpoch:epoch});
  const buy=await amm.getQuote({inAmount:new BN(10_000_000), inputTokenMint: solIsA?pool.tokenAMint:pool.tokenBMint, slippage:0.5, poolState:pool, currentTime:time, currentSlot:slot, tokenADecimal:mintA.decimals, tokenBDecimal:mintB.decimals, inputTokenInfo: solIsA?tokInfo(pool.tokenAMint,mintA):tokInfo(pool.tokenBMint,mintB), outputTokenInfo: solIsA?tokInfo(pool.tokenBMint,mintB):tokInfo(pool.tokenAMint,mintA)});
  result.buy_quote=clean(buy);
  const sell=await amm.getQuote({inAmount:buy.swapOutAmount, inputTokenMint: solIsA?pool.tokenBMint:pool.tokenAMint, slippage:0.5, poolState:pool, currentTime:time, currentSlot:slot, tokenADecimal:mintA.decimals, tokenBDecimal:mintB.decimals, inputTokenInfo: solIsA?tokInfo(pool.tokenBMint,mintB):tokInfo(pool.tokenAMint,mintA), outputTokenInfo: solIsA?tokInfo(pool.tokenAMint,mintA):tokInfo(pool.tokenBMint,mintB)});
  result.sell_quote_same_state=clean(sell);
  result.roundtrip_ratio_same_state=Number(sell.swapOutAmount.toString())/10_000_000;
  result.decision='CURRENT_STATE_QUOTE_PATH_WORKS';
}catch(e){ result.error={name:e.name,message:String(e.message).slice(0,500)}; result.decision='UNRESOLVED'; }
result.rpc_requests=calls; result.finished_at=new Date().toISOString();
fs.writeFileSync('../raw/current_quote_result.json',JSON.stringify(clean(result),null,2));
console.log(JSON.stringify(clean(result),null,2));
