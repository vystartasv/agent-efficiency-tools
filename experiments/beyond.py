#!/usr/bin/env python3
"""Probe document extraction and structured-data blind spots on synthetic fixtures."""
import csv, io, json, subprocess, tempfile, time
from pathlib import Path

with tempfile.TemporaryDirectory() as d:
    p = Path(d)
    source = p / 'report.html'
    source.write_text('<html><body><h1>Quarterly report</h1><p>Revenue 1200</p><table><tr><th>Region</th><th>Profit</th></tr><tr><td>West</td><td>450</td></tr></table><p style="display:none">CONFIDENTIAL HIDDEN</p></body></html>')
    start = time.perf_counter()
    r = subprocess.run(['textutil', '-convert', 'txt', '-stdout', str(source)], capture_output=True, text=True)
    text = r.stdout
    document = {'exit': r.returncode, 'seconds': round(time.perf_counter()-start, 4), 'input_bytes': source.stat().st_size, 'output_bytes': len(text.encode()), 'heading_found': 'Quarterly report' in text, 'table_values_found': all(x in text for x in ['Region','Profit','West','450']), 'hidden_text_included': 'CONFIDENTIAL HIDDEN' in text, 'output': text}
    csvtext = 'id,name,note\n1,Alice,"first line\nsecond line"\n2,Bob,"comma, here"\n'
    rows = list(csv.DictReader(io.StringIO(csvtext)))
    records = {'input_bytes': len(csvtext.encode()), 'physical_lines': len(csvtext.splitlines()), 'records': len(rows), 'multiline_field_preserved': rows[0]['note'] == 'first line\nsecond line', 'quoted_comma_preserved': rows[1]['note'] == 'comma, here'}
    data = {'items': [{'id': 1, 'status': 'failed'}, {'id': 2, 'status': 'FAILED'}, {'id': 3, 'state': 'error'}]}
    (p / 'mixed.json').write_text(json.dumps(data))
    jq = subprocess.run(['jq', '-c', '.items[] | select(.status == "failed")', str(p / 'mixed.json')], capture_output=True, text=True)
    mixed = {'exit': jq.returncode, 'known_failures': 3, 'selected_records': len(jq.stdout.splitlines()), 'output': jq.stdout.strip()}
    print(json.dumps({'document': document, 'csv': records, 'json_unknown_schema': mixed}, indent=2))
