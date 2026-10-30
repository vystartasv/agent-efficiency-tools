# Agent Efficiency Tools

Local utilities for images, PDFs, web pages, media, logs and test reports.

```sh
npm install -g agent-efficiency-tools
agent-tools doctor
```

Requires Node 20+, Python 3 and macOS or Linux. OCR and PDF tools require macOS. Browser reading needs Chromium; media tools need FFmpeg. Audio transcription also needs Whisper and a local model.

```sh
agent-tools image-text --batch screen-a.png screen-b.png
agent-tools browser-read https://example.org --main
agent-tools log-scan tests.log
```

Use `agent-tools --help` for commands. See the [command reference](https://github.com/vystartasv/agent-efficiency-tools/blob/main/docs/COMMANDS.md) and [agent setup](https://github.com/vystartasv/agent-efficiency-tools/blob/main/INTEGRATIONS.md). The package includes an [agent skill](https://github.com/vystartasv/agent-efficiency-tools/tree/main/skills/agent-tools).

Extraction can omit details; check originals when accuracy matters. Browser reading runs page scripts and network requests. Token savings vary by task and model.
