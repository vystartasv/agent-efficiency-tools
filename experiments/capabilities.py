#!/usr/bin/env python3
"""Compare bounded extraction with raw synthetic data; no network or private inputs."""
import json, subprocess, tempfile, time
from pathlib import Path

def call(args):
    start = time.perf_counter()
    p = subprocess.run(args, capture_output=True)
    return p.returncode, p.stdout.decode(), round(time.perf_counter() - start, 4)

def result(raw, output, elapsed, facts):
    return {'raw_bytes': len(raw.encode()), 'output_bytes': len(output.encode()), 'seconds': elapsed, 'facts': facts}

with tempfile.TemporaryDirectory() as d:
    path = Path(d)
    records = [{'id': i, 'status': 'failed' if i == 437 else 'ok', 'message': 'disk full' if i == 437 else 'healthy'} for i in range(1000)]
    source = path / 'records.json'
    source.write_text(json.dumps(records, indent=2))
    code, out, elapsed = call(['jq', '-c', '.[] | select(.status == "failed")', str(source)])
    results = {'json_select': result(source.read_text(), out, elapsed, {'exit': code, 'failure_found': '"id":437' in out and 'disk full' in out})}
    log = path / 'run.log'
    log.write_text(''.join(f'{i:04} INFO healthy\n' if i != 437 else '0437 ERROR disk full\n' for i in range(1000)))
    code, out, elapsed = call(['rg', '-n', '-C', '1', 'ERROR', str(log)])
    results['log_context'] = result(log.read_text(), out, elapsed, {'exit': code, 'error_and_neighbors_found': all(s in out for s in ['0436 INFO healthy', '0437 ERROR disk full', '0438 INFO healthy'])})
    code, out, elapsed = call(['rg', '-n', 'NONEXISTENT', str(log)])
    results['log_no_match'] = {'exit': code, 'output_bytes': len(out.encode()), 'seconds': elapsed}
    code, out, elapsed = call(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', '-y', str(path / 'tone.wav')])
    if code == 0:
        code, out, elapsed = call(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_name,sample_rate,channels', '-of', 'json', str(path / 'tone.wav')])
        data = json.loads(out)
        results['audio_metadata'] = {'exit': code, 'output_bytes': len(out.encode()), 'seconds': elapsed, 'duration_seconds': float(data['format']['duration']), 'codec': data['streams'][0]['codec_name']}
    test = path / 'sample.test.js'
    test.write_text("const {test}=require('node:test'); const assert=require('node:assert/strict');\n" + ''.join(f"test('pass {i}',()=>assert.equal(1,1));\n" for i in range(30)) + "test('important failure',()=>assert.equal('actual','expected'));\n")
    def test_run(args):
        start = time.perf_counter()
        p = subprocess.run(args, capture_output=True, text=True)
        out = p.stdout + p.stderr
        return {'exit': p.returncode, 'bytes': len(out.encode()), 'seconds': round(time.perf_counter()-start, 4), 'failure_named': 'important failure' in out, 'actual_expected_present': 'actual' in out and 'expected' in out}
    results['test_failure'] = {'raw': test_run(['node', '--test', str(test)]), 'rtk': test_run(['rtk', 'test', 'node', '--test', str(test)])}
    print(json.dumps(results, indent=2))
