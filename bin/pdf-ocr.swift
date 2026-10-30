#!/usr/bin/swift
import Foundation
import PDFKit
import Vision
import AppKit

func fail(_ message: String) -> Never {
    fputs("pdf-ocr: \(message)\n", stderr)
    exit(2)
}
let args = CommandLine.arguments
if args.count < 2 || args.count > 4 { fail("usage: pdf-ocr INPUT.pdf [FIRST_PAGE [LAST_PAGE]]") }
guard let doc = PDFDocument(url: URL(fileURLWithPath: args[1])) else { fail("could not open PDF") }
if doc.isLocked { fail("PDF is password locked") }
if doc.pageCount == 0 { fail("PDF has no pages") }
let first = args.count > 2 ? Int(args[2]) : 1
let last = args.count > 3 ? Int(args[3]) : first
guard let start = first, let end = last, start >= 1, end >= start, end <= doc.pageCount else {
    fail("page range must be within 1...\(doc.pageCount)")
}
if end - start >= 5 { fail("at most 5 pages may be requested at once") }
let maxEdge: CGFloat = 2400
let limit = 12000
var pages = [[String: Any]]()
var incomplete = false
for number in start...end {
    guard let page = doc.page(at: number - 1) else { fail("could not read page \(number)") }
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
    let text = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
    let empty = text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    let truncated = text.count > limit
    if empty || truncated { incomplete = true }
    pages.append(["page": number, "text": String(text.prefix(limit)), "characters": text.count,
                  "truncated": truncated, "no_recognized_text": empty,
                  "image_width": image.width, "image_height": image.height])
}
let result: [String: Any] = ["source": args[1], "page_count": doc.pageCount, "pages": pages]
guard let json = try? JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]),
      let string = String(data: json, encoding: .utf8) else { fail("could not encode output") }
print(string)
if incomplete { exit(1) }
