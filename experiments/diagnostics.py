#!/usr/bin/env python3
"""Compare diagnostics from one generated Node test suite; no network or private data."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--encoding', help='optional tiktoken encoding, e.g. o200k_base')
args = parser.parse_args()
encoding = None
if args.encoding:
    try:
        import tiktoken
    except ImportError:
        parser.error('--encoding requires the optional tiktoken package')
    encoding = tiktoken.get_encoding(args.encoding)

def token_count(text):
    return len(encoding.encode(text, disallowed_special=())) if encoding else None

def run(command):
    started = time.perf_counter()
    p = subprocess.run(command, capture_output=True, text=True)
    output = p.stdout + p.stderr
    return {'exit': p.returncode, 'seconds': round(time.perf_counter() - started, 4), 'tokens': token_count(output),
            'bytes': len(output.encode()), 'test_name': 'important failure' in output,
            'expected_value': 'VALUE_EXPECTED_9' in output, 'actual_value': 'VALUE_ACTUAL_7' in output}, p

with tempfile.TemporaryDirectory(prefix='agent-diagnostics-') as d:
    test = Path(d) / 'sample.test.js'
    test.write_text("const {test}=require('node:test'); const assert=require('node:assert/strict');\n" +
                    ''.join(f"test('pass {i}',()=>assert.equal(1,1));\n" for i in range(30)) +
                    "test('important failure',()=>assert.equal('VALUE_ACTUAL_7','VALUE_EXPECTED_9'));\n")
    raw, _ = run(['node', '--test', str(test)])
    rtk, rtk_process = run(['rtk', 'test', 'node', '--test', str(test)])
    match = re.search(r'\[full output: ([^\]]+)\]', rtk_process.stdout + rtk_process.stderr)
    recovery = None
    if match:
        log = Path(os.path.expanduser(match.group(1)))
        if log.is_file():
            content = log.read_text(errors='replace')
            recovery = {'bytes': len(content.encode()), 'tokens': token_count(content),
                        'test_name': 'important failure' in content,
                        'expected_value': 'VALUE_EXPECTED_9' in content,
                        'actual_value': 'VALUE_ACTUAL_7' in content}
    junit, process = run(['node', '--test', '--test-reporter=junit', str(test)])
    report = Path(d) / 'report.xml'
    report.write_text(process.stdout)
    extracted, _ = run([str(root / 'bin/test-report'), str(report)])
    print(json.dumps({'encoding': args.encoding, 'raw': raw, 'rtk_summary': rtk, 'rtk_full_log': recovery,
                      'junit_generation': junit, 'junit_extraction': extracted,
                      'note': 'The JUnit test run is needed to generate the report; extraction is an additional step.'}, indent=2))
