import re, sys, html as htmlmod

MSG_BLOCK_RE = re.compile(r'<div class="tgme_widget_message_wrap.*?(?=<div class="tgme_widget_message_wrap|\Z)', re.S)
POST_ID_RE = re.compile(r'data-post="[^/]+/(\d+)"')
TIME_RE = re.compile(r'<time datetime="([^"]+)"')
TEXT_RE = re.compile(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>\s*(?:<div class="tgme_widget_message_reactions|<div class="tgme_widget_message_footer|<div class="tgme_widget_message_inline)', re.S)
TAG_RE = re.compile(r'<[^>]+>')
EDITED_RE = re.compile(r'tgme_widget_message_meta[^<]*<[^>]*edited', re.S)

def strip_tags(t):
    t = re.sub(r'<br\s*/?>', '\n', t)
    t = TAG_RE.sub('', t)
    return htmlmod.unescape(t).strip()

def parse_messages(text):
    out = []
    for block in MSG_BLOCK_RE.findall(text):
        idm = POST_ID_RE.search(block)
        if not idm:
            continue
        mid = int(idm.group(1))
        tm = TIME_RE.search(block)
        t = tm.group(1) if tm else None
        txtm = TEXT_RE.search(block)
        raw_text = txtm.group(1) if txtm else ""
        clean_text = strip_tags(raw_text)
        edited = 'edited' in block.split('tgme_widget_message_meta')[-1][:200].lower() if 'tgme_widget_message_meta' in block else False
        out.append({"id": mid, "time": t, "text": clean_text, "edited": edited, "raw_len": len(block)})
    return out
