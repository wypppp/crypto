#!/usr/bin/env python3
"""Verify this release's bytes and evidence links. Standard library; no network.

v3 change: the historical records (revision report, saved-copy evidence) keep the
v2 bytes on purpose. Files revised since then are declared in ERRATA-v3.md with
their old and new SHA-256; this script bridges the two. A file whose hash differs
from the historical record WITHOUT a matching errata entry is a tampering failure.
"""
import hashlib
import json
from pathlib import Path
import re
import sys

RELEASE_ID = 'right-tail-release-20260909-v3'
ERRATA = 'ERRATA-v3.md'

EXPECTED = {
    'verify_capabilities.py', 'baseline-execution-config.md',
    'right-tail-coverage-ledger.md', 'revision-and-verification-report.md',
    'offline_verification.json', 'verification_log.json', 'offline_recheck.json',
    'saved-copy-verification.json', 'START_HERE.md', 'verify_package.py',
    ERRATA,
}

# Files whose hash the historical report and saved-copy evidence pin down.
HISTORICAL = ('verify_capabilities.py', 'baseline-execution-config.md',
              'right-tail-coverage-ledger.md', 'offline_verification.json',
              'verification_log.json')


def parse_errata(text):
    """Return {filename: (old_sha, new_sha)} for each revision block."""
    revised = {}
    for block in re.split(r'^### ', text, flags=re.M)[1:]:
        name = re.search(r'^\| 文件 \| `([^`]+)` \|$', block, re.M)
        old = re.search(r'^\| 旧 SHA-256 \| `([0-9a-f]{64})` \|$', block, re.M)
        new = re.search(r'^\| 新 SHA-256 \| `([0-9a-f]{64})` \|$', block, re.M)
        if name and old and new:
            revised[name.group(1)] = (old.group(1), new.group(1))
    return revised


def verify(root):
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('release_id') != RELEASE_ID:
        raise ValueError('Unexpected release ID')
    entries = manifest['files']
    if not isinstance(entries, list) or len(entries) != len(EXPECTED):
        raise ValueError('Unexpected file count')
    if {x['name'] for x in entries} != EXPECTED:
        raise ValueError('Manifest file set mismatch')
    hashes = {}
    for item in entries:
        name = item['name']
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Missing or symlinked file: ' + name)
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != item['sha256'] or len(data) != item['size_bytes']:
            raise ValueError('Hash/size mismatch: ' + name)
        hashes[name] = digest
        print('OK', name, digest)

    revised = parse_errata((root / ERRATA).read_text(encoding='utf-8'))
    for name, (old_sha, new_sha) in revised.items():
        if name not in hashes:
            raise ValueError('Errata names a file not in this release: ' + name)
        if hashes[name] != new_sha:
            raise ValueError('Errata new-hash does not match the file: ' + name)
    # What the historical records should say for each file: the pre-revision hash.
    def historical_expected(name):
        return revised[name][0] if name in revised else hashes[name]

    report = (root / 'revision-and-verification-report.md').read_text(encoding='utf-8')
    report_hashes = dict(re.findall(r'^\| ([\w.-]+) \| ([0-9a-f]{64}) \|$', report, re.M))
    for name in HISTORICAL:
        if report_hashes.get(name) != historical_expected(name):
            raise ValueError('Original report does not match: ' + name)
    for name in ('offline_verification.json', 'offline_recheck.json', 'verification_log.json'):
        log = json.loads((root / name).read_text(encoding='utf-8'))
        if log['script_sha256'] != hashes['verify_capabilities.py']:
            raise ValueError('Evidence references another script: ' + name)
        if log['baseline_ready'] is not False:
            raise ValueError('Unexpected baseline-ready claim')
        expected_counts = ({'PASS': 0, 'FAIL': 1, 'UNRUN': 7} if name == 'verification_log.json'
                           else {'PASS': 21, 'FAIL': 0, 'UNRUN': 0})
        actual_counts = {s: sum(x['status'] == s for x in log['results'])
                         for s in ('PASS', 'FAIL', 'UNRUN')}
        if log['counts'] != expected_counts or actual_counts != expected_counts:
            raise ValueError('Unexpected evidence counts: ' + name)
    saved = json.loads((root / 'saved-copy-verification.json').read_text(encoding='utf-8'))
    for name, record in saved.items():
        if name not in hashes or record['saved_copy_identical'] is not True:
            raise ValueError('Saved-copy evidence mismatch: ' + name)
        if record['sha256'] != historical_expected(name):
            raise ValueError('Saved-copy evidence mismatch: ' + name)
    note = ''
    if revised:
        note = '; revised since v2 (declared in %s): %s' % (ERRATA, ', '.join(sorted(revised)))
    print('PACKAGE VERIFIED: %d files; original report and logs match%s. '
          'This is not a strategy or endpoint approval.' % (len(EXPECTED), note))


if __name__ == '__main__':
    try:
        verify(Path(__file__).resolve().parent)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('PACKAGE FAILED:', exc, file=sys.stderr)
        sys.exit(1)
