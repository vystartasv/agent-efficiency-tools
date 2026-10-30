#!/usr/bin/swift
import Foundation
import ImageIO
import Vision

func fail(_ message: String) -> Never {
    fputs("image-text: \(message)\n", stderr)
    exit(2)
}

let args = Array(CommandLine.arguments.dropFirst())
var sources: [String] = []
var jsonOutput = false
var includeRegions = false
var batchMode = false
var limit = 12000
var i = 0
while i < args.count {
    switch args[i] {
    case "--json": jsonOutput = true
    case "--regions": includeRegions = true; jsonOutput = true
    case "--batch": batchMode = true; jsonOutput = true
    case "--max-chars":
        i += 1
        guard i < args.count, let value = Int(args[i]), (1...100000).contains(value) else {
            fail("--max-chars must be between 1 and 100000")
        }
        limit = value
    default:
        guard !args[i].hasPrefix("--") else { fail("unknown option: \(args[i])") }
        sources.append(args[i])
    }
    i += 1
}
guard !sources.isEmpty else { fail("usage: image-text [--batch] IMAGE... [--json] [--regions] [--max-chars N]") }
guard batchMode || sources.count == 1 else { fail("multiple images require --batch") }

func recognize(_ source: String) throws -> [String: Any] {
    guard FileManager.default.fileExists(atPath: source) else {
        throw NSError(domain: "image-text", code: 2,
                      userInfo: [NSLocalizedDescriptionKey: "input file not found"])
    }
    let url = URL(fileURLWithPath: source)
    guard let imageSource = CGImageSourceCreateWithURL(url as CFURL, nil),
          let properties = CGImageSourceCopyPropertiesAtIndex(imageSource, 0, nil) as? [CFString: Any],
          let width = properties[kCGImagePropertyPixelWidth] as? Int,
          let height = properties[kCGImagePropertyPixelHeight] as? Int,
          width > 0, height > 0 else {
        throw NSError(domain: "image-text", code: 2,
                      userInfo: [NSLocalizedDescriptionKey: "image is empty or has no readable dimensions"])
    }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    try VNImageRequestHandler(url: url).perform([request])
    let candidates = (request.results ?? []).compactMap { observation -> (VNRecognizedTextObservation, VNRecognizedText)? in
        guard let candidate = observation.topCandidates(1).first else { return nil }
        return (observation, candidate)
    }
    let text = candidates.map { $0.1.string }.joined(separator: "\n")
    let empty = text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    let truncated = text.count > limit
    var result: [String: Any] = ["source": source, "text": String(text.prefix(limit)), "characters": text.count,
                                "truncated": truncated, "no_recognized_text": empty]
    if includeRegions {
        result["regions"] = candidates.map { observation, candidate in
            let box = observation.boundingBox
            return ["text": candidate.string, "confidence": candidate.confidence,
                    "x": box.minX, "y": 1 - box.maxY, "width": box.width, "height": box.height] as [String: Any]
        }
    }
    return result
}

func printJSON(_ value: Any) {
    guard let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]),
          let output = String(data: data, encoding: .utf8) else { fail("could not encode output") }
    print(output)
}

if batchMode {
    var results: [[String: Any]] = []
    var failed = false
    var incomplete = false
    for source in sources {
        do {
            let result = try recognize(source)
            if (result["no_recognized_text"] as? Bool == true) || (result["truncated"] as? Bool == true) {
                incomplete = true
            }
            results.append(result)
        } catch {
            failed = true
            results.append(["source": source, "error": error.localizedDescription])
        }
    }
    printJSON(["results": results, "failed": failed, "incomplete": incomplete])
    if failed { exit(2) }
    if incomplete { exit(1) }
} else {
    do {
        let result = try recognize(sources[0])
        if jsonOutput {
            printJSON(result)
        } else {
            let text = result["text"] as? String ?? ""
            if !text.isEmpty { print(text) }
            if result["no_recognized_text"] as? Bool == true { fputs("image-text: no text recognized\n", stderr) }
            if result["truncated"] as? Bool == true { fputs("image-text: output truncated; inspect the image or a crop\n", stderr) }
        }
        if result["no_recognized_text"] as? Bool == true || result["truncated"] as? Bool == true { exit(1) }
    } catch {
        fail("OCR failed for \(sources[0]): \(error.localizedDescription)")
    }
}
