# Initial tool selection

The first CLI should contain these capabilities, subject to the tests and limits below:

1. **Image preparation and OCR:** resize or encode a separate image; extract text locally. Success means inputs are preserved, existing destinations are refused, invalid options fail, and supported fixtures preserve required text. File bytes are not model tokens; OCR is not visual verification.
2. **Command output capture:** preserve complete combined output in a private new file, show a bounded explicitly incomplete excerpt, and return the child status. Success means failures and signals are surfaced, existing files are never overwritten, and omitted text remains recoverable. The caller controls log retention.
3. **Browser reading:** provide a bounded isolated-browser text fallback with explicit status and truncation. Success means navigation errors and HTTP failures are signaled, browser processes close, and tests cover redirects and slow or dynamic pages. It does not replace authenticated shared-browser state, accessibility trees, frames or visual inspection.
4. **Measurement:** run reproducible fixtures and record correctness, latency, output volume and failure recovery. Later measure actual model-token usage and complete task outcomes, comparing native tools and RTK.

Reuse `jq`, `rg`, RTK, FFmpeg, existing document converters and speech engines. Defer test/CI adapters, structured-data discovery, audio, document extraction and browser interaction until representative tasks show a gap and a reliable comparison is available. No automatic hooks, network uploads or global configuration changes in the package.

## Release gates

Support and test macOS and Linux where applicable; report missing optional dependencies clearly. Verify success, invalid inputs, existing outputs, failures, malformed input, process cleanup and privacy. Test real screenshots and full tasks alongside synthetic fixtures. Track total tokens, cost, completion quality, latency and recovery; do not claim universal improvement or require an impossible perfect score. Choose explicit thresholds from representative workloads before claiming a metric is met. The current prototypes and single-run results do not meet all release gates.
