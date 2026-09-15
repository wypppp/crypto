import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {Connection,PublicKey} from '@solana/web3.js';
import {DynamicBondingCurveClient,DAMM_V2_PROGRAM_ID} from '@meteora-ag/dynamic-bonding-curve-sdk';
const root=fileURLToPath(new URL('.',import.meta.url));
const spec=JSON.parse(fs.readFileSync(root+'spec.json'));
const save=(f,x)=>fs.writeFileSync(root+f,JSON.stringify(x,null,2));
let n=0;
const conn=new Connection('https://api.mainnet-beta.solana.com',{commitment:'finalized',disableRetryOnRateLimit:true,fetch:async(url,o)=>{
 if(++n>spec.budget.rpc_requests_max) throw Error('RPC budget exceeded');
 const request=JSON.parse(o.body);
 if(!['getSignaturesForAddress','getTransaction','getAccountInfo'].includes(request.method)) throw Error('Unexpected RPC');
 const name=`raw/${n}_${request.method}`;save(name+'.request.json',{request,source:url,started_at:new Date().toISOString()});
 const r=await fetch(url,{...o,signal:AbortSignal.timeout(15000)});
 fs.writeFileSync(root+name+'.response.json',await r.clone().text());save(name+'.http.json',{status:r.status,finished_at:new Date().toISOString()});return r;
}});
const program=new DynamicBondingCurveClient(conn,'finalized').state.getProgram();
let result={run_id:spec.run_id,decision:'UNRESOLVED',migration:null};
try{
 const signatures=await conn.getSignaturesForAddress(new PublicKey(spec.pool),{limit:spec.budget.signature_limit},'finalized');
 let inspected=0;
 for(const s of signatures){
  if(s.err) continue;
  if(inspected++>=spec.budget.transactions_max) break;
  const tx=await conn.getParsedTransaction(s.signature,{maxSupportedTransactionVersion:0,commitment:'finalized'});
  if(!tx||tx.meta.err) continue;
  const instructions=[...tx.transaction.message.instructions,...(tx.meta.innerInstructions??[]).flatMap(x=>x.instructions)];
  for(const ix of instructions){
   if(!ix.programId.equals(program.programId)||!ix.data)continue;
   const decoded=program.coder.instruction.decode(ix.data,'base58');
   if(decoded?.name!=='migrationDammV2') continue;
   const definition=program.idl.instructions.find(x=>x.name===decoded.name);
   const accounts=Object.fromEntries(definition.accounts.map((a,i)=>[a.name,ix.accounts[i].toBase58()]));
   if(accounts.virtualPool!==spec.pool) throw Error('Migration identity mismatch');
   result.migration={signature:s.signature,slot:tx.slot,blockTime:tx.blockTime,instruction:decoded.name,accounts};
   const target=await conn.getAccountInfoAndContext(new PublicKey(accounts.pool),{commitment:'finalized'});
   result.target={context:target.context,address:accounts.pool,owner:target.value?.owner.toBase58(),data_base64:target.value?.data.toString('base64')};
   result.decision=target.value?.owner.equals(DAMM_V2_PROGRAM_ID)?'MIGRATION_AND_TARGET_OWNER_CONFIRMED':'TARGET_UNRESOLVED';
   break;
  }
  if(result.migration)break;
 }
}catch(e){result.error={name:e.name,message:e.message};}
result.rpc_requests=n;result.finished_at=new Date().toISOString();save('result.json',result);console.log(JSON.stringify(result,null,2));
