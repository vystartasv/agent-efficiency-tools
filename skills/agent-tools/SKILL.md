---
name: agent-tools
description: Use local agent utilities for bounded image, PDF, audio, video, browser text, test-report, and command-output inspection when those artifacts are relevant. Prefer existing task-specific tools when they already provide the needed information.
---

# Agent tools

Find `agent-tools` on PATH, or use `bin/agent-tools` from its checkout. Run `agent-tools --help` or `agent-tools COMMAND --help`, and consult the checkout's README for command options and exit codes. Run `agent-tools doctor` to identify available local dependencies.

- For screenshots, `image-prepare` creates a smaller copy and `image-batch` prepares many while reporting byte changes; `image-crop` preserves a selected region; `image-diff` reports pixel changes between PNGs; `image-text --regions` returns text locations and confidence, and `image-text --batch` OCRs several images in one process. Check the original or a suitable crop when visual details matter.
- For PDFs, `pdf-find` searches selectable text by page, `pdf-text --ocr-missing` extracts selected pages and OCRs up to five pages without a text layer, and `pdf-ocr` recognizes selected image-only pages. Respect page limits and incomplete-result flags; neither preserves all visual evidence.
- For recordings, `media-info` identifies audio and video streams, `video-frame` extracts a moment, and `audio-transcribe` uses an explicitly supplied local Whisper model. Timestamps and recognition are approximate. Do not record, upload, or download models without authorization.
- For test results, `test-report` extracts JUnit failures and flags empty or inconsistent reports. For verbose commands, `output-capture` saves full combined output and shows a tail; `log-scan` searches the saved log for common failures with bounded context. Inspect the saved output when diagnostics may be omitted. Captured logs can contain secrets.
- `browser-read` uses a fresh isolated browser, not the user's authenticated browser. Use `--main` when page chrome is irrelevant; inspect `content_scope` and `scope_fallback`. Use the available shared browser for requested browser work when required by the environment. Page scripts and network requests still run.

Check exit status and output flags. OCR, page extraction, cropping, and summaries can omit information. Preserve originals and do not claim token or task savings without measurement.
