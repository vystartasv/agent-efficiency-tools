# Agent Tools Native

`agent-tools-native` is a standalone Go binary for image and PDF inspection on Windows, Linux, and macOS. It does not need Node.js or Python.

Download the archive for your OS and CPU from [GitHub Releases](https://github.com/vystartasv/agent-efficiency-tools/releases). Compare its digest with the matching entry in `SHA256SUMS` using `shasum -a 256 ARCHIVE` or PowerShell's `Get-FileHash ARCHIVE -Algorithm SHA256`, then extract the binary and run:

```sh
agent-tools-native image-prepare input.png smaller.png 1600
agent-tools-native image-crop input.png region.png 100 80 600 400
agent-tools-native pdf-text report.pdf 1 3
agent-tools-native pdf-find report.pdf "invoice number"
```

The image commands support BMP, GIF, JPEG, PNG, TIFF, and WebP. They preserve the input, refuse to overwrite an existing output, and use top-left pixel coordinates for cropping. Crop refuses JPEGs and TIFFs with non-normalized orientation metadata. SVG and HEIC are not supported by this binary; the npm-installed macOS command continues to use Apple's image frameworks.

`image-prepare` defaults to a 1,600-pixel longest edge and writes PNG or JPEG. `image-crop` requires a PNG destination. Decoded images are limited to 100 million pixels.

`pdf-text` uses 1-based pages, defaults to page 1, and accepts at most 20 pages per request. Text is capped at 12,000 characters per page. `--ocr-missing` OCRs up to five textless pages that contain embedded images. `pdf-find` searches selectable text on every page and returns at most 20 excerpts. `pdf-ocr` accepts at most five pages and recognizes text in embedded images. It does not rasterize vector pages.

Exit status 0 means the requested extraction completed; 1 indicates empty or incomplete extraction; 2 indicates invalid input, an unreadable file, or a missing/failed Tesseract command. JSON responses include truncation, missing-text, and parser-warning details where applicable.

PDF text extraction and search are built in. Scanned-image OCR is optional and uses a local Tesseract installation; no network calls or model downloads are made. Install Tesseract and its English language data for `image-text`, `pdf-ocr`, and `pdf-text --ocr-missing`:

- macOS: `brew install tesseract`
- Debian or Ubuntu: `sudo apt install tesseract-ocr tesseract-ocr-eng`
- Windows: install a current Tesseract 5 build and add its executable and `tessdata` directory to `PATH`; see the [Tesseract installation guide](https://tesseract-ocr.github.io/tessdoc/Installation.html).

```sh
agent-tools-native image-text screen.png --json --regions
agent-tools-native pdf-ocr scan.pdf 1 2
agent-tools-native pdf-text scan.pdf 1 2 --ocr-missing
```

Image OCR defaults to 12,000 output characters; `--max-chars N` accepts 1–100,000. Add `--json` for status fields and `--regions` for recognized line boxes and confidence. OCR output is a text aid, not visual verification.

OCR can miss or reorder content. It handles images embedded in scanned PDF pages; it does not render text converted to vector outlines. Check the source when accuracy or layout matters. PDF extraction is powered by the [Go PDF package](https://github.com/giraffesyo/pdf), Apache-2.0 licensed. The image resampler uses `golang.org/x/image`.

The native binary is a separate download from the npm package. It covers the commands listed above; the existing `agent-tools` npm package retains browser, media, transcription, and macOS Vision features.

## Build from source

Go 1.27.3 or newer is required to build this version.

```sh
cd native
go test ./...
go build -trimpath -ldflags='-s -w' -o agent-tools-native .
```
