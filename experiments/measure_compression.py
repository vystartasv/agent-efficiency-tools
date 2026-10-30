#!/usr/bin/env python3
import json, os, subprocess, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory() as d:
    p = Path(d)
    swift = p / 'fixture.swift'
    swift.write_text('''import AppKit
let image = NSImage(size: NSSize(width: 2400, height: 1200))
image.lockFocus()
NSColor.white.setFill(); NSRect(x: 0, y: 0, width: 2400, height: 1200).fill()
for (i, size) in [72.0, 36.0, 18.0, 10.0].enumerated() {
 let text = "ORDER 7264 READY SIZE \\(Int(size))" as NSString
 text.draw(at: NSPoint(x: 80, y: 1000 - i * 200), withAttributes: [.font: NSFont.systemFont(ofSize: size), .foregroundColor: NSColor.black])
}
image.unlockFocus()
let rep = NSBitmapImageRep(data: image.tiffRepresentation!)!
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
''')
    src = p/'input.png'
    subprocess.run(['swift', str(swift), str(src)], check=True)
    results = {}
    for width in (1600, 800):
        for fmt, quality in [('png', None), ('jpeg', 80), ('jpeg', 40)]:
            out = p / f'{width}-{fmt}-{quality}.img'
            cmd = ['sips', '-s', 'format', fmt]
            if quality: cmd += ['-s', 'formatOptions', str(quality)]
            cmd += ['-Z', str(width), str(src), '--out', str(out)]
            start = time.perf_counter()
            prep = subprocess.run(cmd, capture_output=True)
            elapsed = round(time.perf_counter()-start, 3)
            ocr = subprocess.run([str(ROOT/'bin/image-text.swift'), str(out)], capture_output=True, text=True) if prep.returncode == 0 else None
            results[f'{width}-{fmt}-{quality}'] = {'encode_exit': prep.returncode, 'encode_seconds': elapsed, 'bytes': out.stat().st_size if out.exists() else None, 'ocr_exit': ocr.returncode if ocr else None, 'exact_lines': sum(f'ORDER 7264 READY SIZE {x}' in ocr.stdout for x in (72,36,18,10)) if ocr else None}
    output = p/'capture.log'
    child = ['python3', '-c', 'import sys; print("failure: important"); print("normal\\n" * 100); sys.exit(7)']
    run = subprocess.run([str(ROOT/'bin/output-capture'), '--output', str(output), '--tail-bytes', '100', '--', *child], capture_output=True, text=True)
    results['output_capture'] = {'exit': run.returncode, 'display_bytes': len(run.stdout.encode()), 'full_bytes': output.stat().st_size, 'full_contains_failure': 'failure: important' in output.read_text(), 'display_contains_failure': 'failure: important' in run.stdout, 'omission_marked': 'Earlier output omitted' in run.stdout, 'mode': oct(output.stat().st_mode & 0o777)}
    collision = subprocess.run([str(ROOT/'bin/output-capture'), '--output', str(output), '--', *child], capture_output=True)
    results['overwrite_refused'] = collision.returncode != 0 and 'failure: important' in output.read_text()
    print(json.dumps(results, indent=2))
