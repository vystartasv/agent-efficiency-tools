#!/usr/bin/env python3
"""Reproduce small local image and command-output experiments on macOS."""
import json, subprocess, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def run(args, cwd=ROOT):
    start = time.perf_counter()
    p = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {"exit": p.returncode, "seconds": round(time.perf_counter()-start, 3),
            "stdout_bytes": len(p.stdout), "stderr_bytes": len(p.stderr),
            "stdout": p.stdout.decode(errors="replace"), "stderr": p.stderr.decode(errors="replace")}

with tempfile.TemporaryDirectory(prefix="agent-tools-bench-") as d:
    tmp = Path(d)
    swift = tmp / "fixture.swift"
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
    original = tmp / "fixture.png"
    fixture = run(["swift", str(swift), str(original)])
    results = {"fixture": fixture, "images": {}}
    if fixture["exit"] != 0:
        print(json.dumps(results, indent=2)); raise SystemExit(1)
    for size in (2400, 1600, 800):
        output = tmp / f"image-{size}.png"
        prep = run([str(ROOT / "bin/image-prepare"), str(original), str(output), str(size)])
        ocr = run([str(ROOT / "bin/image-text.swift"), str(output)]) if prep["exit"] == 0 else None
        results["images"][size] = {"prepare": prep, "file_bytes": output.stat().st_size if output.exists() else None, "ocr": ocr}
    results["images"]["overwrite"] = run([str(ROOT / "bin/image-prepare"), str(original), str(original)])
    results["images"]["missing_ocr"] = run([str(ROOT / "bin/image-text.swift"), str(tmp / "missing.png")])
    results["images"]["overwrite"].pop("stdout")
    results["images"]["overwrite"].pop("stderr")
    results["images"]["missing_ocr"].pop("stdout")
    results["images"]["missing_ocr"].pop("stderr")
    print(json.dumps(results, indent=2))
