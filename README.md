# Agent Efficiency Tools

Local utilities for images, PDFs, web pages, media, logs and test reports.

```sh
npm install -g agent-efficiency-tools
agent-tools doctor
```

Requires Node 20+, Python 3 and macOS or Linux. OCR and PDF tools require macOS. Browser reading needs Chromium; media tools need FFmpeg. Audio transcription also needs Whisper and a local model.

Windows, Linux, and macOS users can also download the standalone [Agent Tools Native](https://github.com/vystartasv/agent-efficiency-tools/blob/main/native/README.md) binary from [GitHub Releases](https://github.com/vystartasv/agent-efficiency-tools/releases). It provides image preparation/cropping, image and PDF OCR, and PDF text/search without Node.js or Python. OCR requires local Tesseract.

```sh
agent-tools image-text --batch screen-a.png screen-b.png
agent-tools browser-read https://example.org --main
agent-tools log-scan tests.log
```

## For agents

1. Run `agent-tools doctor` to see which optional local dependencies are available.
2. Run `agent-tools COMMAND --help` before using a command with unfamiliar options.
3. Check that command's exit status and completeness fields. Exit-code meanings vary by command; `output-capture` returns the child command's status.
4. Treat extraction as a lead when the result says it is incomplete, and keep the original file available for verification.

Output formats vary by command: many return JSON, image preparation and cropping print text, and `image-text` defaults to plain text. `output-capture` writes full output to a file and prints a bounded tail. Local extraction tools do not upload source files or download models. `browser-read` intentionally accesses network pages, and `audio-transcribe` requires a model file supplied by the user.

See the [command reference](https://github.com/vystartasv/agent-efficiency-tools/blob/main/docs/COMMANDS.md) for per-command options, exit codes, limits and caveats. The package includes an [agent skill](https://github.com/vystartasv/agent-efficiency-tools/tree/main/skills/agent-tools) and [setup notes](https://github.com/vystartasv/agent-efficiency-tools/blob/main/INTEGRATIONS.md).

Extraction can omit details; check originals when accuracy matters. Browser reading runs page scripts and network requests. Token savings vary by task and model.
