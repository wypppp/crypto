"""config 原子写入。直接 json.dump 到原文件会在异常时留下**被截断的 config**
(2026-09-06 实测:set 不可序列化 ⟹ 写坏 L_config.json,靠归档才恢复)。
一律先写临时文件、校验可解析、再原子替换。"""
import json,os,hashlib,tempfile
def save(cfg,path="L_config.json"):
    d=os.path.dirname(os.path.abspath(path))
    fd,tmp=tempfile.mkstemp(dir=d,suffix=".tmp"); os.close(fd)
    try:
        with open(tmp,"w") as f: json.dump(cfg,f,ensure_ascii=False,indent=1)
        json.load(open(tmp))                      # 校验可解析后才替换
        os.replace(tmp,path)
    except Exception:
        if os.path.exists(tmp): os.remove(tmp)
        raise
    return hashlib.sha256(open(path,'rb').read()).hexdigest()
