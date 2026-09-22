// DQ-4：零 RPC，从 RT-W00 已保存交易的内部指令中解码 emit_cpi 事件
import fs from 'node:fs';
import {Connection} from '@solana/web3.js';
import {utils} from '@coral-xyz/anchor';
import {DynamicBondingCurveClient} from '@meteora-ag/dynamic-bonding-curve-sdk';
import {cpAmmCoder, CpAmmIdl, CP_AMM_PROGRAM_ID} from '@meteora-ag/cp-amm-sdk';
const W00='/home/ancillary/RT/RT-W00_真实探针证据包_20260914/';
const dbc=new DynamicBondingCurveClient(new Connection('http://127.0.0.1:1'),'finalized').state.getProgram();
const DBC_ID=dbc.programId.toBase58(), CPAMM_ID=CP_AMM_PROGRAM_ID.toBase58();
const clean=x=>{ if(x==null) return x; if(typeof x==='bigint') return x.toString(); if(x.toBase58) return x.toBase58(); if(x.constructor&&x.constructor.name==='BN') return x.toString(10); if(Array.isArray(x)) return x.map(clean); if(typeof x==='object') return Object.fromEntries(Object.entries(x).map(([k,v])=>[k,clean(v)])); return x; };
const files=[W00+'raw/03_getTransaction.response.json', ...fs.readdirSync(W00+'migration/raw').filter(f=>/getTransaction\.response\.json$/.test(f)).map(f=>W00+'migration/raw/'+f)];
const out=[];
for (const file of files){
  const tx=JSON.parse(fs.readFileSync(file,'utf8')).result;
  if(!tx){ out.push({file, note:'no result'}); continue; }
  const msg=tx.transaction.message;
  const keys=[...(msg.accountKeys||[]).map(k=>typeof k==='string'?k:k.pubkey), ...((tx.meta.loadedAddresses?.writable)||[]), ...((tx.meta.loadedAddresses?.readonly)||[])];
  const events=[];
  for (const group of (tx.meta.innerInstructions||[])){
    for (const ix of group.instructions){
      const pid = ix.programId ?? keys[ix.programIdIndex];
      if(!ix.data || (pid!==DBC_ID && pid!==CPAMM_ID)) continue;
      let bytes; try { bytes=Buffer.from(utils.bytes.bs58.decode(ix.data)); } catch { continue; }
      if(bytes.length<16) continue;
      const b64=bytes.subarray(8).toString('base64');
      const coder = pid===DBC_ID ? dbc.coder : cpAmmCoder;
      let ev=null; try { ev=coder.events.decode(b64); } catch {}
      if(ev) events.push({program: pid===DBC_ID?'DBC':'DAMM_V2', tag_hex: bytes.subarray(0,8).toString('hex'), name: ev.name, data: clean(ev.data)});
    }
  }
  out.push({file: file.replace(W00,''), slot: tx.slot, blockTime: tx.blockTime, err: tx.meta.err, n_events: events.length, events});
}
const types=Object.fromEntries(CpAmmIdl.types.map(t=>[t.name,t]));
const f=n=>types[n]?.type?.fields?.map(x=>x.name+':'+(typeof x.type==='string'?x.type:JSON.stringify(x.type).slice(0,40)));
const idlFields={EvtInitializePool:f('EvtInitializePool'), EvtLiquidityChange:f('EvtLiquidityChange')};
fs.writeFileSync('../raw/decoded_saved_events.json', JSON.stringify({dbc_program:DBC_ID, cpamm_program:CPAMM_ID, idlFields, transactions: out}, null, 2));
console.log(JSON.stringify(idlFields));
for (const t of out){ console.log('\n==', t.file, 'slot', t.slot, 'err', JSON.stringify(t.err), 'events', t.n_events); for (const e of (t.events||[])) console.log(' ', e.program, e.name, JSON.stringify(e.data).slice(0,900)); }
