# Agent efficiency research

## Principles

- Smaller tool output can increase total cost if it hides facts and causes retries. Measure task success, total tokens, latency, and recovery.
- Preserve complete source output and images; return bounded excerpts with clear limits and a path to the original.
- Prefer stable operating-system features and established utilities over duplicate parsers or services.
- Mark incomplete extraction clearly. OCR, summaries, and sampled media are not complete evidence.

## Tool areas

| Area | Useful operation | Main limit |
| --- | --- | --- |
| Images | Resize, crop, compare, and OCR | Small text and layout can be lost. |
| Documents | Search pages and extract selected text | Tables, images, and annotations may be missed. |
| Browser | Read focused rendered text | Dynamic content, authentication, and visual state need separate checks. |
| Logs and tests | Preserve full output; return likely failures and structured reports | Filters can miss unfamiliar errors. |
| Audio and video | Inspect metadata, selected frames, and timestamped speech | Samples and transcripts can omit context. |
| Environment | Report optional tools and capabilities | Availability does not prove successful operation. |

## Evaluation

Use representative success and failure cases. Record exact input and output tokens, correctness, elapsed time, and any recovery reads. Label synthetic results and avoid extrapolating them to other models or tasks. See [synthetic experiment results](experiments/RESULTS.md).
