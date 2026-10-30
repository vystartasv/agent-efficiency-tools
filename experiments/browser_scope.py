"""Compare full-body and semantic-main browser extraction on a synthetic page."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    navigation = " ".join(f'<a href="/section-{n}">Navigation link {n}</a>' for n in range(250))
    html = f'<title>Fixture</title><nav>{navigation}</nav><main><h1>Release notes</h1><p>Version 4.2 fixes issue ID R-17.</p></main>'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/fixture"
    results = {}
    try:
        for name, options in (("body", []), ("main", ["--main"])):
            start = time.perf_counter()
            run = subprocess.run([str(ROOT / "bin/browser-read"), url, *options], capture_output=True, text=True)
            results[name] = {"exit": run.returncode, "seconds": round(time.perf_counter() - start, 4),
                             "output_bytes": len(run.stdout.encode()), "result": json.loads(run.stdout)}
    finally:
        server.shutdown()
        server.server_close()
    body, focused = results["body"]["result"], results["main"]["result"]
    report = {
        "body_characters": body["characters"],
        "main_characters": focused["characters"],
        "character_reduction_fraction": round(1 - focused["characters"] / body["characters"], 4),
        "body_output_bytes": results["body"]["output_bytes"],
        "main_output_bytes": results["main"]["output_bytes"],
        "version_and_issue_preserved": "Version 4.2" in focused["text"] and "R-17" in focused["text"],
        "navigation_removed": "Navigation link" not in focused["text"],
        "timing_seconds": {"body": results["body"]["seconds"], "main": results["main"]["seconds"]},
    }
    try:
        import tiktoken
        encoding = tiktoken.get_encoding("o200k_base")
        report["body_text_tokens"] = len(encoding.encode(results["body"]["result"]["text"]))
        report["main_text_tokens"] = len(encoding.encode(results["main"]["result"]["text"]))
    except ImportError:
        report["tokenizer"] = "tiktoken unavailable; byte and character counts only"
    print(json.dumps(report, indent=2))
    if not (report["version_and_issue_preserved"] and report["navigation_removed"]):
        raise SystemExit("main-scope fidelity check failed")


if __name__ == "__main__":
    main()
