"""Disk-backed cache for successful immutable backfill reads from retained evidence."""
import hashlib
import json
from pathlib import Path
import sqlite3
import zlib


def records(path):
    """Recover complete JSONL records even when reboot left the gzip footer unwritten."""
    decoder=zlib.decompressobj(31)
    pending=b''
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(65536),b''):
            pending+=decoder.decompress(chunk)
            lines=pending.split(b'\n');pending=lines.pop()
            for line in lines:
                if line:yield json.loads(line)
    if decoder.eof and pending.strip():
        yield json.loads(pending)


def key(kind,args,kwargs):
    return json.dumps([kind,args,kwargs],sort_keys=True,separators=(',',':'))


def reusable(kind,args,kwargs):
    if kind=='rpc':
        if args[0] in ('eth_chainId','eth_blockNumber'):return False
        if args[0]=='eth_call':return False  # Recheck population boundaries against the live endpoint.
        return 'latest' not in json.dumps(args)
    if kind=='etherscan':
        return args[:2]==['logs','getLogs'] or args[:2]==('logs','getLogs')
    return False


class ReplayCache:
    def __init__(self,db_path,evidence):
        self.con=sqlite3.connect(db_path)
        self.con.execute('CREATE TABLE IF NOT EXISTS responses(key TEXT PRIMARY KEY,response TEXT,source TEXT)')
        self.sources=[]
        for path in evidence:
            path=Path(path).resolve()
            digest=hashlib.sha256()
            with path.open('rb') as f:
                for chunk in iter(lambda:f.read(65536),b''):digest.update(chunk)
            sha=digest.hexdigest()
            count=0
            for row in records(path):
                response=row.get('response')
                if not response or response[0] is None or response[1] is not None:continue
                args=row['args'];kwargs=row.get('kwargs',{});kind=row['kind']
                if not reusable(kind,args,kwargs):continue
                self.con.execute('INSERT OR IGNORE INTO responses VALUES(?,?,?)',
                    (key(kind,args,kwargs),json.dumps(response),str(path)))
                count+=1
            self.con.commit();self.sources.append({'path':str(path),'sha256':sha,'success_records':count})
    def get(self,kind,args,kwargs):
        if not reusable(kind,args,kwargs):return None
        row=self.con.execute('SELECT response,source FROM responses WHERE key=?',(key(kind,args,kwargs),)).fetchone()
        return (json.loads(row[0]),row[1]) if row else None
