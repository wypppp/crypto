import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {Connection, PublicKey} from '@solana/web3.js';
import {unpackMint, getExtensionTypes} from '@solana/spl-token';
import {DynamicBondingCurveClient, SwapMode, ActivationType} from '@meteora-ag/dynamic-bonding-curve-sdk';
import BN from 'bn.js';
const root=fileURLToPath(new URL('.',import.meta.url));
const read=f=>JSON.parse(fs.readFileSync(root+f,'utf8'));
const spec=read('spec.json');
const clean=x=>{
  if(BN.isBN(x)) return x.toString(10);
  if(x?.toBase58) return x.toBase58();
  if(typeof x==='bigint') return x.toString();
  if(Buffer.isBuffer(x)) return {base64:x.toString('base64')};
  if(Array.isArray(x)) return x.map(clean);
  if(x && typeof x==='object') return Object.fromEntries(Object.entries(x).map(([k,v])=>[k,clean(v)]));
  return x;
};
const save=(f,x)=>fs.writeFileSync(root+f,JSON.stringify(clean(x),null,2));
let calls=0;
const connection=new Connection('https://api.mainnet-beta.solana.com',{
  commitment:'finalized',disableRetryOnRateLimit:true,
  fetch:async(url,options)=>{
    if(++calls>spec.resource_budget.rpc_requests_max) throw Error('RPC budget exceeded');
    const request=JSON.parse(options.body);
    if(!['getMultipleAccounts','getBlockTime'].includes(request.method)) throw Error('Unexpected RPC method');
    const prefix=`raw/${calls}_${request.method}`;
    save(prefix+'.request.json',{source:url,request,started_at:new Date().toISOString()});
    const response=await fetch(url,{...options,signal:AbortSignal.timeout(15000)});
    fs.writeFileSync(root+prefix+'.response.json',await response.clone().text());
    save(prefix+'.http.json',{status:response.status,finished_at:new Date().toISOString()});
    return response;
  }
});
const client=new DynamicBondingCurveClient(connection,'finalized');
const result={run_id:spec.run_id,measurement_status:'unknown',economic_status:'undetermined',execution_check_status:{entry:{quote:'UNRUN',build:'UNRUN',simulation:'UNRUN',submission:'UNRUN'},exit:{quote:'UNRUN',build:'UNRUN',simulation:'UNRUN',submission:'UNRUN'}},limitations:spec.scope_limit};
try {
  const addresses=[spec.candidate,spec.candidate_accounts.config,spec.candidate_accounts.base_mint,spec.candidate_accounts.quote_mint].map(x=>new PublicKey(x));
  const snapshot=await connection.getMultipleAccountsInfoAndContext(addresses,{commitment:'finalized'});
  if(snapshot.value.some(x=>!x)) throw Error('Required account missing');
  const [p,c,b,q]=snapshot.value;
  if(!p.owner.equals(client.state.getProgram().programId)||!c.owner.equals(p.owner)) throw Error('Pool/config owner mismatch');
  const coder=client.state.getProgram().coder.accounts;
  const pool=coder.decode('virtualPool',p.data), config=coder.decode('poolConfig',c.data);
  if(!pool.poolState.config.equals(addresses[1])||!pool.poolState.baseMint.equals(addresses[2])||!config.quoteMint.equals(addresses[3])) throw Error('Pool/config/mint mapping mismatch');
  const baseMint=unpackMint(addresses[2],b,b.owner), quoteMint=unpackMint(addresses[3],q,q.owner);
  save('decoded_state.json',{context:snapshot.context,pool,config,baseMint,quoteMint,baseExtensions:getExtensionTypes(baseMint.tlvData),quoteExtensions:getExtensionTypes(quoteMint.tlvData)});
  result.context=snapshot.context;
  result.pool_owner=p.owner.toBase58();
  result.migration_progress=pool.poolState.migrationProgress;
  result.config_migration_option=config.migrationOption;
  result.base_decimals=baseMint.decimals; result.quote_decimals=quoteMint.decimals;
  result.base_extensions=getExtensionTypes(baseMint.tlvData);
  if(pool.poolState.isMigrated===1 || pool.poolState.migrationProgress!==0) throw Error('Migration state needs venue-specific interpretation before a DBC quote');
  let currentPoint;
  if(config.activationType===ActivationType.Slot) currentPoint=new BN(snapshot.context.slot);
  else if(config.activationType===ActivationType.Timestamp){
    const time=await connection.getBlockTime(snapshot.context.slot);
    if(time===null) throw Error('Block time unavailable');
    currentPoint=new BN(time);
  } else throw Error('Unknown activation type');
  result.current_point=currentPoint.toString();
  result.activation_type=config.activationType;
  result.quote=client.pool.swapQuote2({virtualPool:pool,config,swapBaseForQuote:false,swapMode:SwapMode.ExactIn,amountIn:new BN(spec.amount_in_atomic),slippageBps:50,hasReferral:false,eligibleForFirstSwapWithMinFee:false,currentPoint});
  result.measurement_status='known';
  result.execution_check_status.entry.quote='PASS';
  result.decision='OFFICIAL_SDK_STATE_AND_QUOTE_PATH_AVAILABLE';
} catch(error){
  result.error={name:error.name,message:error.message};
  result.decision='UNRESOLVED';
}
result.rpc_requests=calls;result.finished_at=new Date().toISOString();
save('result.json',result);
console.log(JSON.stringify(clean(result),null,2));
