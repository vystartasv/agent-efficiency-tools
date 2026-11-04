# Development plan

## Current tools

The npm CLI covers image preparation and OCR, PDF text and OCR, browser text, media metadata and transcription, log scanning, command capture, and test reports. The standalone Go binary adds cross-platform image preparation/cropping, OCR through optional Tesseract, and PDF text/search/OCR.

## Next

1. Measure complete tasks with and without each tool, including retries and correctness.
2. Check OCR and document extraction on varied languages, layouts, and small text.
3. Measure native OCR against varied real screenshots and scanned PDFs before recommending it over Vision.
4. Improve browser extraction and failure recovery using representative pages.
5. Keep platform requirements, output limits, and incomplete-result flags explicit.

## Evidence rule

Report token savings only when measured with the target model and task. File size and synthetic fixtures alone do not establish task-level savings. Keep original inputs available for verification.
