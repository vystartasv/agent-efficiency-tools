#!/usr/bin/env python3
"""Compare OCR outputs and sizes locally; never print or save image text."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('image', help='local screenshot to inspect; contents remain local')
args = parser.parse_args()
source = Path(args.image)

def ocr(file):
    started = time.perf_counter()
    run = subprocess.run([str(root/'bin/image-text.swift'), str(file), '--json', '--max-chars', '100000'], capture_output=True, text=True)
    if run.returncode != 0:
        raise RuntimeError('OCR was empty, truncated, or failed; comparison cannot establish a baseline')
    data = json.loads(run.stdout)
    return Counter(re.findall(r'\w+', data['text'].casefold())), round(time.perf_counter() - started, 3)

try:
    if not source.is_file():
        parser.error('input is not an existing file')
    baseline, seconds = ocr(source)
    if not sum(baseline.values()):
        raise RuntimeError('baseline contains no recognized words')
    result = {'original': {'bytes': source.stat().st_size, 'recognized_words': sum(baseline.values()), 'ocr_seconds': seconds}, 'variants': {}}
    with tempfile.TemporaryDirectory(prefix='agent-image-benchmark-') as d:
        for size in (1600, 800):
            for fmt in ('png', 'jpg'):
                output = Path(d)/f'{size}.{fmt}'
                cmd = [str(root/'bin/image-prepare'), str(source), str(output), str(size)]
                if fmt == 'jpg': cmd.append('80')
                prep = subprocess.run(cmd, capture_output=True, text=True)
                if prep.returncode != 0:
                    raise RuntimeError('image preparation failed')
                words, elapsed = ocr(output)
                shared = sum((baseline & words).values())
                result['variants'][f'{size}-{fmt}'] = {'bytes': output.stat().st_size,
                    'recognized_words': sum(words.values()), 'baseline_words_retained': shared,
                    'baseline_word_recall': round(shared/sum(baseline.values()), 4), 'ocr_seconds': elapsed}
    print(json.dumps(result, indent=2))
except (OSError, ValueError, RuntimeError) as exc:
    parser.exit(2, f'real-image benchmark: {exc}\n')
