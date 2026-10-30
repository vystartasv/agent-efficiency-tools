"""Compare per-image Vision OCR calls with one bounded batch call."""
from pathlib import Path
import json
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        images = [root / f"screen-{n}.png" for n in range(3)]
        generator = r'''import AppKit
for (index, path) in CommandLine.arguments.dropFirst().enumerated() {
    let image = NSImage(size: NSSize(width: 900, height: 450))
    image.lockFocus()
    NSColor.white.setFill(); NSRect(x: 0, y: 0, width: 900, height: 450).fill()
    ("SCREEN \(index + 1) RESULT ID-\(index + 17)" as NSString).draw(at: NSPoint(x: 50, y: 200), withAttributes: [.font: NSFont.systemFont(ofSize: 58), .foregroundColor: NSColor.black])
    image.unlockFocus()
    let bitmap = NSBitmapImageRep(data: image.tiffRepresentation!)!
    try! bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: path))
}'''
        fixture = subprocess.run(["swift", "-e", generator, *map(str, images)], capture_output=True, text=True)
        if fixture.returncode:
            raise SystemExit(fixture.stderr)
        separate_outputs = []
        separate_start = time.perf_counter()
        for image in images:
            result = subprocess.run([str(ROOT / "bin/image-text.swift"), str(image), "--json"],
                                    capture_output=True, text=True)
            if result.returncode:
                raise SystemExit(result.stderr)
            separate_outputs.append(result.stdout)
        separate_seconds = time.perf_counter() - separate_start
        batch_start = time.perf_counter()
        batch = subprocess.run([str(ROOT / "bin/image-text.swift"), "--batch", *map(str, images)],
                               capture_output=True, text=True)
        batch_seconds = time.perf_counter() - batch_start
        if batch.returncode:
            raise SystemExit(batch.stderr or batch.stdout)
        batch_data = json.loads(batch.stdout)
        separate_data = [json.loads(output) for output in separate_outputs]
        exact = [item["text"] for item in separate_data] == [item["text"] for item in batch_data["results"]]
        report = {
            "image_count": len(images),
            "separate_processes": len(separate_outputs),
            "batch_processes": 1,
            "separate_elapsed_seconds": round(separate_seconds, 4),
            "batch_elapsed_seconds": round(batch_seconds, 4),
            "separate_output_bytes": sum(len(value.encode()) for value in separate_outputs),
            "batch_output_bytes": len(batch.stdout.encode()),
            "text_exactly_matches": exact,
            "recognized_text": [item["text"] for item in batch_data["results"]],
        }
        try:
            import tiktoken
            encoding = tiktoken.get_encoding("o200k_base")
            report["separate_output_tokens"] = sum(len(encoding.encode(value)) for value in separate_outputs)
            report["batch_output_tokens"] = len(encoding.encode(batch.stdout))
        except ImportError:
            report["tokenizer"] = "tiktoken unavailable; byte counts only"
        print(json.dumps(report, indent=2))
        if not exact:
            raise SystemExit("batch OCR text differed from individual OCR")


if __name__ == "__main__":
    main()
