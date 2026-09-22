"""One-off read-only RPC probe; no signing, submission, SDK math or generic indexer."""
import json, urllib.request, datetime, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = json.loads((ROOT / 'spec.json').read_text())
IDL = json.loads((ROOT / 'raw/dbc_idl.json').read_text())
CALLS = []
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def rpc(method, params):
    assert method in {'getVersion', 'getSignaturesForAddress', 'getTransaction', 'getAccountInfo'}
    assert len(CALLS) < SPEC['resource_budget']['rpc_requests_max']
    request = {'jsonrpc':'2.0', 'id':len(CALLS)+1, 'method':method, 'params':params}
    name = f'{len(CALLS)+1:02d}_{method}'
    record = {'request':request, 'source':'https://api.mainnet-beta.solana.com', 'started_at':now()}
    CALLS.append(record)
    try:
        with urllib.request.urlopen(urllib.request.Request(record['source'], data=json.dumps(request).encode(), headers={'Content-Type':'application/json'}), timeout=15) as response:
            payload = response.read()
            record.update(http_status=response.status, response_bytes=len(payload))
            (ROOT/'raw'/f'{name}.response.json').write_bytes(payload)
            result = json.loads(payload)
            record['response_path'] = f'raw/{name}.response.json'
    except Exception as exc:
        record.update(error_type=type(exc).__name__, error=str(exc))
        result = {'error':record['error']}
    record['finished_at'] = now()
    (ROOT/'raw'/f'{name}.request.json').write_text(json.dumps(record,indent=2))
    return result

# Decode only the 8-byte instruction discriminator to map names using the official IDL.
# No protocol amounts, account state layout or curve mathematics are reimplemented.
def base58_bytes(text):
    alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
    n = 0
    for c in text: n = n * 58 + alphabet.index(c)
    return b'\0' * (len(text)-len(text.lstrip('1'))) + n.to_bytes((n.bit_length()+7)//8,'big')

rpc('getVersion', [])
signatures = rpc('getSignaturesForAddress', [SPEC['program'], {'limit':5,'commitment':'finalized'}])
candidate = None
inspected = 0
for row in signatures.get('result', []):
    if row.get('err') is not None: continue
    if inspected >= 3: break
    inspected += 1
    tx = rpc('getTransaction',[row['signature'], {'encoding':'jsonParsed','maxSupportedTransactionVersion':0,'commitment':'finalized'}]).get('result')
    if not tx or tx['meta']['err'] is not None: continue
    instructions = list(tx['transaction']['message']['instructions'])
    for group in tx['meta'].get('innerInstructions') or []: instructions.extend(group['instructions'])
    for instruction in instructions:
        if instruction.get('programId') != SPEC['program'] or 'data' not in instruction: continue
        discriminator = list(base58_bytes(instruction['data'])[:8])
        definition = next((x for x in IDL['instructions'] if x['discriminator']==discriminator),None)
        if not definition: continue
        mapping = dict(zip([a['name'] for a in definition['accounts']], instruction['accounts']))
        pool = mapping.get('virtual_pool') or mapping.get('pool')
        if not pool: continue
        candidate = {'pool':pool,'signature':row['signature'],'transaction_slot':tx['slot'],'block_time':tx.get('blockTime'),'instruction':definition['name'],'accounts':mapping,'selection_role':'engineering_fixture','prior_exposure':'first inspected in this run; no price/return inspected'}
        break
    if candidate: break
if candidate:
    candidate['account_response'] = rpc('getAccountInfo',[candidate['pool'], {'encoding':'base64','commitment':'finalized'}])
result = {'candidate':candidate, 'rpc_requests':len(CALLS), 'inspected_transactions':inspected, 'economic_status':'undetermined','M_pi':{'value':None,'measurement_status':'not_applicable'},'M_star':{'value':None,'measurement_status':'not_applicable'},'execution_check_status':{'entry':{'quote':'UNRUN','build':'UNRUN','simulation':'UNRUN','submission':'UNRUN'},'exit':{'quote':'UNRUN','build':'UNRUN','simulation':'UNRUN','submission':'UNRUN'}},'completed_at':now()}
(ROOT/'result.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
