#!/usr/bin/swift
import Foundation
import PDFKit

func fail(_ message: String) -> Never {
    fputs("pdf-find: \(message)\n", stderr)
    exit(2)
}
let args = CommandLine.arguments
guard args.count == 3 else { fail("usage: pdf-find INPUT.pdf SEARCH_TEXT") }
let query = args[2]
if query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || query.count > 256 {
    fail("search text must be nonempty and at most 256 characters")
}
guard let doc = PDFDocument(url: URL(fileURLWithPath: args[1])) else { fail("could not open PDF") }
if doc.isLocked { fail("PDF is password locked") }
if doc.pageCount == 0 { fail("PDF has no pages") }
let matchLimit = 20
let pageLimit = 100
var count = 0
var noText = 0
var noTextPages = [Int]()
var matches = [[String: Any]]()
for index in 0..<doc.pageCount {
    guard let page = doc.page(at: index) else { fail("could not read page \(index + 1)") }
    let text = page.string ?? ""
    if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        noText += 1
        if noTextPages.count < pageLimit { noTextPages.append(index + 1) }
        continue
    }
    var position = text.startIndex
    while position < text.endIndex,
          let found = text.range(of: query, options: [.caseInsensitive], range: position..<text.endIndex) {
        count += 1
        if matches.count < matchLimit {
            let before = text.index(found.lowerBound, offsetBy: -80, limitedBy: text.startIndex) ?? text.startIndex
            let after = text.index(found.upperBound, offsetBy: 80, limitedBy: text.endIndex) ?? text.endIndex
            matches.append(["page": index + 1, "excerpt": String(text[before..<after])])
        }
        position = found.upperBound
    }
}
let truncated = count > matchLimit
let result: [String: Any] = ["source": args[1], "query": query, "page_count": doc.pageCount,
    "match_count": count, "matches": matches, "matches_truncated": truncated,
    "no_text_page_count": noText, "no_text_pages": noTextPages, "no_text_pages_truncated": noText > pageLimit]
guard let data = try? JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]),
      let json = String(data: data, encoding: .utf8) else { fail("could not encode output") }
print(json)
if truncated || noText > 0 { exit(1) }
