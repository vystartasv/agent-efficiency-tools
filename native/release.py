#!/usr/bin/env python3
"""Cross-compile and package the standalone native binaries for a release."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

NATIVE = Path(__file__).resolve().parent
ROOT = NATIVE.parent
TARGETS = (
    ("darwin", "arm64"), ("darwin", "amd64"),
    ("linux", "arm64"), ("linux", "amd64"),
    ("windows", "arm64"), ("windows", "amd64"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="release tag, such as v0.1.8")
    parser.add_argument("--output", type=Path, default=NATIVE / "dist")
    args = parser.parse_args()
    if not args.version.startswith("v"):
        parser.error("--version must be a v-prefixed release tag")
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="agent-tools-release-") as temp:
        temp = Path(temp)
        for goos, goarch in TARGETS:
            target = f"{goos}-{goarch}"
            stage = temp / target / "agent-tools-native"
            stage.mkdir(parents=True)
            executable = "agent-tools-native.exe" if goos == "windows" else "agent-tools-native"
            env = os.environ.copy()
            env.update({"GOOS": goos, "GOARCH": goarch, "CGO_ENABLED": "0"})
            subprocess.run([
                "go", "build", "-trimpath", "-ldflags", f"-s -w -X main.version={args.version}",
                "-o", str(stage / executable), ".",
            ], cwd=NATIVE, env=env, check=True)
            shutil.copy2(NATIVE / "README.md", stage / "README.md")
            shutil.copy2(ROOT / "LICENSE", stage / "LICENSE-MIT.txt")
            shutil.copytree(NATIVE / "licenses", stage / "licenses")
            name = f"agent-tools-native-{args.version}-{target}"
            archive = args.output / (name + (".zip" if goos == "windows" else ".tar.gz"))
            if goos == "windows":
                with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
                    for file in sorted(stage.rglob("*")):
                        if file.is_file():
                            bundle.write(file, file.relative_to(stage.parent))
            else:
                with tarfile.open(archive, "w:gz") as bundle:
                    bundle.add(stage, arcname="agent-tools-native")
            print(f"{archive} ({archive.stat().st_size} bytes)")
    checksums = []
    for archive in sorted(args.output.glob(f"agent-tools-native-{args.version}-*")):
        if archive.name == "SHA256SUMS":
            continue
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        checksums.append(f"{digest}  {archive.name}")
    (args.output / "SHA256SUMS").write_text("\n".join(checksums) + "\n")


if __name__ == "__main__":
    main()
