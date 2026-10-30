"""Repeatable synthetic size and fidelity probe for log-scan."""
from pathlib import Path
import json
import subprocess
import tempfile
import time
import sys

ROOT = Path(__file__).resolve().parents[1]
LINES = 5000


def main():
    source = [f"PASS test_{number:04d} completed in 0.01s" for number in range(LINES)]
    source[1024:1024] = ["ERROR: fixture failure code=E-42", "  expected: 17", "  actual: 0"]
    with tempfile.TemporaryDirectory() as directory:
        log = Path(directory) / "synthetic.log"
        log.write_text("\n".join(source) + "\n")
        start = time.perf_counter()
        run = subprocess.run([sys.executable, str(ROOT / "bin/log-scan"), str(log), "--context", "2"],
                             capture_output=True, text=True)
        elapsed = time.perf_counter() - start
        result = json.loads(run.stdout)
        facts = " ".join(line["text"] for line in result["lines"])
        report = {
            "fixture_lines": LINES + 3,
            "input_bytes": log.stat().st_size,
            "output_bytes": len(run.stdout.encode()),
            "output_fraction_of_input": len(run.stdout.encode()) / log.stat().st_size,
            "seconds": round(elapsed, 4),
            "exit": run.returncode,
            "line_count_reported": result["lines_scanned"],
            "match_count": result["match_count"],
            "failure_code_preserved": "E-42" in facts,
            "expected_actual_preserved": "expected: 17" in facts and "actual: 0" in facts,
            "line_number_preserved": any(line["line"] == 1025 for line in result["lines"]),
        }
        try:
            import tiktoken
            encoding = tiktoken.get_encoding("o200k_base")
            report["input_tokens"] = len(encoding.encode(log.read_text()))
            report["output_tokens"] = len(encoding.encode(run.stdout))
        except ImportError:
            report["tokenizer"] = "tiktoken unavailable; byte counts only"
        print(json.dumps(report, indent=2))
        if run.returncode != 1 or not all((report["failure_code_preserved"], report["expected_actual_preserved"], report["line_number_preserved"])):
            raise SystemExit("log-scan failed fidelity check")


if __name__ == "__main__":
    main()
