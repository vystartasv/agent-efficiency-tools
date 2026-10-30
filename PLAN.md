# Development plan

## Current tools

The CLI covers image preparation and OCR, PDF text and OCR, browser text, media metadata and transcription, log scanning, command capture, and test reports.

## Next

1. Measure complete tasks with and without each tool, including retries and correctness.
2. Check OCR and document extraction on varied languages, layouts, and small text.
3. Improve browser extraction and failure recovery using representative pages.
4. Keep platform requirements, output limits, and incomplete-result flags explicit.

## Evidence rule

Report token savings only when measured with the target model and task. File size and synthetic fixtures alone do not establish task-level savings. Keep original inputs available for verification.
