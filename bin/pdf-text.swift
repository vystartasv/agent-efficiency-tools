#!/usr/bin/swift
import Foundation
import PDFKit
import AppKit
import Vision

func fail(_ message: String) -> Never {
    fputs("pdf-text: \(message)\n", stderr)
    exit(2)
}
var args = Array(CommandLine.arguments.dropFirst())
let ocrMissing = args.contains("--ocr-missing")
args.removeAll { $0 == "--ocr-missing" }
if args.isEmpty || args.count > 3 { fail("usage: pdf-text INPUT.pdf [FIRST_PAGE [LAST_PAGE]] [--ocr-missing]") }
let url = URL(fileURLWithPath: args[0])
guard let doc = PDFDocument(url: url) else { fail("could not open PDF") }
if doc.isLocked { fail("PDF is password locked") }
if doc.pageCount == 0 { fail("PDF has no pages") }
let first = args.count > 1 ? Int(args[1]) : 1
let last = args.count > 2 ? Int(args[2]) : first
guard let start = first, let end = last, start >= 1, end >= start, end <= doc.pageCount else {
    fail("page range must be within 1...\(doc.pageCount)")
}
if end - start >= 20 { fail("at most 20 pages may be requested at once") }
let limit = 12000
let ocrLimit = 5
let maxEdge: CGFloat = 2400
var ocrCount = 0
var pages = [[String: Any]]()
var incomplete = false
for number in start...end {
    guard let page = doc.page(at: number - 1) else { fail("could not read page \(number)") }
    let selectableText = page.string ?? ""
    let noExtractableText = selectableText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    var text = selectableText
    var method = "pdf-text"
    var ocrSkipped = false
    if noExtractableText && ocrMissing {
        if ocrCount >= ocrLimit {
            ocrSkipped = true
        } else {
            ocrCount += 1
            let bounds = page.bounds(for: .cropBox)
            guard bounds.width > 0, bounds.height > 0 else { fail("page \(number) has invalid bounds") }
            let scale = maxEdge / max(bounds.width, bounds.height)
            let thumbnail = page.thumbnail(of: CGSize(width: bounds.width * scale, height: bounds.height * scale), for: .cropBox)
            guard let image = thumbnail.cgImage(forProposedRect: nil, context: nil, hints: nil) else { fail("could not render page \(number)") }
            let request = VNRecognizeTextRequest()
            request.recognitionLevel = .accurate
            request.usesLanguageCorrection = false
            do { try VNImageRequestHandler(cgImage: image).perform([request]) }
            catch { fail("OCR failed on page \(number): \(error.localizedDescription)") }
            text = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
            method = "vision-ocr"
        }
    }
    let empty = text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    let truncated = text.count > limit
    if empty || truncated || ocrSkipped { incomplete = true }
    pages.append(["page": number, "text": String(text.prefix(limit)), "characters": text.count,
                  "truncated": truncated, "no_extractable_text": noExtractableText,
                  "no_recognized_text": noExtractableText && !ocrSkipped && empty,
                  "ocr_skipped": ocrSkipped, "method": method])
}
let result: [String: Any] = ["source": args[0], "page_count": doc.pageCount, "pages": pages]
guard let json = try? JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]),
      let string = String(data: json, encoding: .utf8) else { fail("could not encode output") }
print(string)
if incomplete { exit(1) }
