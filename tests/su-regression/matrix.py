#!/usr/bin/env python3
"""Run causal controls against pinned source and reversible one-fix ablations."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from run import function

HERE = Path(__file__).resolve().parent
SOURCE = "native/src/core/su/connect.rs"
LEGACY = "37063225d4f344a8f41de8201f679e57098cb7e6"
UPSTREAM = "6d391dd5b1904122dae315bf2c07e100827c86ef"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=HERE.parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    def show(ref):
        return subprocess.check_output(["git", "-C", str(args.repo), "show", f"{ref}:{SOURCE}"], text=True)

    upstream = show(UPSTREAM)
    fixed = (args.repo / SOURCE).read_text()
    line = "                && output.status.success()\n"
    assert fixed.count(line) == 1, "provider fix must be present exactly once"
    without_provider = fixed.replace(line, "")
    fixed_request = function(fixed, "fn app_request(&mut self)")
    old_request = function(upstream, "fn app_request(&mut self)")
    assert fixed_request != old_request, "FIFO fix must be present"
    without_fifo = fixed.replace(fixed_request, old_request)
    # Reversing BOTH fixes must recover the baseline behavior slices exactly.
    withdrawn = without_fifo.replace(line, "")
    for marker in ["fn app_process()", "fn exec_cmd(", "fn app_request(&mut self)"]:
        assert function(withdrawn, marker) == function(upstream, marker), marker

    versions = [
        ("legacy", "legacy", show(LEGACY)),
        ("upstream", "upstream", upstream),
        ("without-fifo-fix", "provider-only", without_fifo),
        ("without-provider-fix", "fifo-only", without_provider),
        ("fixed", "fixed", fixed),
        ("withdrawn", "upstream", withdrawn),
    ]
    summary = []
    with tempfile.TemporaryDirectory(prefix="magisk-source-matrix-") as temp:
        for label, expected, source in versions:
            path = Path(temp) / f"{label}.rs"
            path.write_text(source)
            report = args.output / f"{label}.json"
            subprocess.run([sys.executable, str(HERE / "run.py"), str(path),
                            "--expect", expected, "--report", str(report)], check=True)
            data = json.loads(report.read_text())
            summary.append(dict(variant=label, source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                                tests=len(data["results"]), matched=data["matched"],
                                observed_failures=data["actual_failures"]))
    result = dict(legacy_ref=LEGACY, upstream_ref=UPSTREAM,
                  head=subprocess.check_output(["git", "-C", str(args.repo), "rev-parse", "HEAD"], text=True).strip(),
                  variants=summary)
    (args.output / "matrix.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
