#!/usr/bin/env python3
"""Benchmark the current macOS tools against portable candidates on generated fixtures."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def run(args, cwd=None, allowed=(0,)):
    result = subprocess.run(list(map(str, args)), cwd=cwd, capture_output=True, text=True)
    if result.returncode not in allowed:
        raise RuntimeError(f"{args[0]} failed ({result.returncode}): {result.stderr.strip()}")
    return result.stdout


def measured(fn, count=9):
    elapsed, value = [], None
    for _ in range(count):
        start = time.perf_counter()
        value = fn()
        elapsed.append(time.perf_counter() - start)
    return {"median_ms": round(statistics.median(elapsed) * 1000, 2), "result": value}


def json_run(args):
    return json.loads(run(args, allowed=(0, 1)))


def word_counts(text):
    return Counter(re.findall(r"[\w]+", text.casefold(), re.UNICODE))


def make_pdf(path):
    stream = b"BT /F1 12 Tf 20 180 Td (HELLO PAGE ONE) Tj T* (ORDER 7264 READY) Tj ET"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"]
    data, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-bin", type=Path, default=ROOT / "native/agent-tools-native")
    parser.add_argument("--pdf-dir", type=Path, help="optional directory of PDFs for a corpus comparison")
    args = parser.parse_args()
    dependencies = ("swift", "sips", "magick", "tesseract", "pdfinfo", "pdftotext", "pdftoppm")
    missing = [name for name in dependencies if not shutil.which(name)]
    if missing:
        parser.error("install benchmark dependencies: " + ", ".join(missing))
    if not args.native_bin.is_file():
        parser.error(f"build the Go binary first; not found: {args.native_bin}")
    args.native_bin = args.native_bin.resolve()

    report = {"native_binary_bytes": args.native_bin.stat().st_size}
    with tempfile.TemporaryDirectory(prefix="agent-tools-bench-") as tmp:
        directory = Path(tmp)
        script = directory / "fixture.swift"
        script.write_text(r'''import AppKit
import PDFKit
let dir = URL(fileURLWithPath: CommandLine.arguments[1])
let image = NSImage(size: NSSize(width: 1000, height: 500))
image.lockFocus()
NSColor.white.setFill(); NSRect(x: 0, y: 0, width: 1000, height: 500).fill()
("ORDER 7264 READY" as NSString).draw(at: NSPoint(x: 80, y: 250), withAttributes: [.font: NSFont.systemFont(ofSize: 64), .foregroundColor: NSColor.black])
image.unlockFocus()
let bitmap = NSBitmapImageRep(data: image.tiffRepresentation!)!
try! bitmap.representation(using: .png, properties: [:])!.write(to: dir.appendingPathComponent("sample.png"))
let doc = PDFDocument(); doc.insert(PDFPage(image: image)!, at: 0)
guard doc.write(to: dir.appendingPathComponent("scan.pdf")) else { exit(1) }
''')
        run(["swift", script, directory])
        image, scan = directory / "sample.png", directory / "scan.pdf"
        text_pdf = directory / "text.pdf"
        make_pdf(text_pdf)

        def resize(engine):
            output = directory / f"resize-{engine}.png"
            output.unlink(missing_ok=True)
            if engine == "sips":
                run(["sips", "-s", "format", "png", "-Z", "800", image, "--out", output])
            elif engine == "go":
                run([args.native_bin, "image-prepare", image, output, "800"])
            else:
                run(["magick", image, "-resize", "800x800>", f"PNG:{output}"])
            return output.stat().st_size

        def crop(engine):
            output = directory / f"crop-{engine}.png"
            output.unlink(missing_ok=True)
            if engine == "swift":
                run([ROOT / "bin/agent-tools", "image-crop", image, output, "0", "0", "500", "250"])
            elif engine == "go":
                run([args.native_bin, "image-crop", image, output, "0", "0", "500", "250"])
            else:
                run(["magick", image, "-crop", "500x250+0+0", "+repage", output])
            return output.stat().st_size

        report["resize"] = {e: measured(lambda e=e: resize(e)) for e in ("sips", "go", "imagemagick")}
        report["crop"] = {e: measured(lambda e=e: crop(e)) for e in ("swift", "go", "imagemagick")}
        report["image_ocr"] = {
            "vision": measured(lambda: json_run([ROOT / "bin/agent-tools", "image-text", image, "--json"])["text"]),
            "tesseract": measured(lambda: json_run([args.native_bin, "image-text", image, "--json"])["text"]),
        }
        report["image_ocr"]["exact_match"] = report["image_ocr"]["vision"]["result"] == report["image_ocr"]["tesseract"]["result"]
        report["pdf_text"] = {
            "pdfkit": measured(lambda: json_run([ROOT / "bin/agent-tools", "pdf-text", text_pdf])["pages"][0]["text"]),
            "go": measured(lambda: json_run([args.native_bin, "pdf-text", text_pdf])["pages"][0]["text"]),
            "poppler": measured(lambda: run(["pdftotext", "-layout", "-nopgbrk", text_pdf, "-"]).strip()),
        }
        report["pdf_ocr"] = {
            "vision": measured(lambda: json_run([ROOT / "bin/agent-tools", "pdf-ocr", scan, "1"])["pages"][0]["text"], 5),
            "go_tesseract": measured(lambda: json_run([args.native_bin, "pdf-ocr", scan, "1"])["pages"][0]["text"], 5),
        }
        def pdf_ocr_poppler():
            prefix = directory / "rendered"
            rendered = prefix.with_suffix(".png")
            rendered.unlink(missing_ok=True)
            run(["pdftoppm", "-f", "1", "-l", "1", "-r", "200", "-png", "-singlefile", scan, prefix])
            return run(["tesseract", rendered.name, "stdout", "--psm", "6"], cwd=directory).strip()

        report["pdf_ocr"]["poppler_plus_tesseract"] = measured(pdf_ocr_poppler, 5)
        for section in ("pdf_text", "pdf_ocr"):
            report[section]["seed_found"] = {name: "7264" in value["result"]
                                               for name, value in report[section].items()
                                               if isinstance(value, dict) and "result" in value}
        if args.pdf_dir:
            documents = []
            go_total = poppler_total = 0.0
            for path in sorted(args.pdf_dir.glob("*.pdf")):
                info = run(["pdfinfo", path])
                pages = int(re.search(r"^Pages:\s+(\d+)", info, re.M).group(1))
                started = time.perf_counter()
                extracted = json_run([args.native_bin, "pdf-text", path, "1", str(min(20, pages))])
                go_total += time.perf_counter() - started
                go_words = word_counts("\n".join(page["text"] for page in extracted["pages"]))
                started = time.perf_counter()
                poppler_words = word_counts(run(["pdftotext", "-layout", "-nopgbrk", path, "-"]))
                poppler_total += time.perf_counter() - started
                total = max(1, sum(poppler_words.values()))
                recall = sum((go_words & poppler_words).values()) / total
                documents.append({"file": path.name, "bytes": path.stat().st_size,
                                  "go_word_count": sum(go_words.values()),
                                  "poppler_word_count": sum(poppler_words.values()),
                                  "poppler_word_recall": round(recall, 4)})
            report["pdf_corpus"] = {
                "documents": documents,
                "go_total_ms": round(go_total * 1000, 2),
                "poppler_total_ms": round(poppler_total * 1000, 2),
                "mean_per_document_poppler_word_recall": round(
                    statistics.mean(item["poppler_word_recall"] for item in documents), 4
                ) if documents else None,
            }
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
