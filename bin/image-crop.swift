#!/usr/bin/swift
import Foundation
import ImageIO
import UniformTypeIdentifiers
import Darwin

func fail(_ message: String) -> Never {
    fputs("image-crop: \(message)\n", stderr)
    exit(1)
}
let args = CommandLine.arguments
guard args.count == 7 else { fail("usage: image-crop INPUT OUTPUT.png X Y WIDTH HEIGHT") }
let input = URL(fileURLWithPath: args[1])
let output = URL(fileURLWithPath: args[2])
guard output.pathExtension.lowercased() == "png" else { fail("output must be a PNG file") }
guard let x = Int(args[3]), let y = Int(args[4]), let width = Int(args[5]), let height = Int(args[6]),
      x >= 0, y >= 0, width > 0, height > 0 else { fail("coordinates must be nonnegative integers and dimensions positive integers") }
guard let source = CGImageSourceCreateWithURL(input as CFURL, nil),
      let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else { fail("could not decode input image") }
let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
if let orientation = properties?[kCGImagePropertyOrientation] as? Int, orientation != 1 {
    fail("image orientation is not normalized; normalize it before cropping")
}
guard x <= image.width, y <= image.height, width <= image.width - x, height <= image.height - y else {
    fail("crop extends beyond image bounds \(image.width)x\(image.height)")
}
guard let crop = image.cropping(to: CGRect(x: x, y: y, width: width, height: height)) else { fail("could not crop image") }
var template = Array(output.deletingLastPathComponent().appendingPathComponent(".image-crop.XXXXXX").path.utf8CString)
let fd = mkstemp(&template)
guard fd >= 0 else { fail("could not create temporary file in output directory") }
close(fd)
let temp = String(cString: template)
func failTemp(_ message: String) -> Never { unlink(temp); fail(message) }
guard let destination = CGImageDestinationCreateWithURL(URL(fileURLWithPath: temp) as CFURL, UTType.png.identifier as CFString, 1, nil) else { failTemp("could not create PNG encoder") }
CGImageDestinationAddImage(destination, crop, nil)
guard CGImageDestinationFinalize(destination) else { failTemp("could not write PNG") }
guard link(temp, output.path) == 0 else { failTemp("could not create output (it may already exist)") }
unlink(temp)
print("\(output.path)\n  pixelWidth: \(crop.width)\n  pixelHeight: \(crop.height)")
