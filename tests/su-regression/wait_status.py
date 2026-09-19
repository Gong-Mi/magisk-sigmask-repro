#!/usr/bin/env python3
"""Extract the production wait block verbatim; run real children and causal controls.

No daemon/Binder/SELinux emulation. Harness compilation errors never count as RED.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
SOURCE = "native/src/core/su/daemon.rs"
BASE = "6d391dd5b1904122dae315bf2c07e100827c86ef"
CASES = ("exit0", "exit7", "exit255", "term", "kill", "int", "not-a-child")


def block(source):
    begin = "        let mut status = 0;\n"
    end = '        debug!("su: return code=[{}]", code);'
    assert source.count(begin) == source.count(end) == 1
    return source[source.index(begin):source.index(end)]


def run_variant(label, source, expectation, output):
    # Reuse the existing locked, standalone harness package and cache.
    build = HERE / ".build"
    (build / "src").mkdir(parents=True, exist_ok=True)
    manifest = '''[package]
name = "magisk-source-regression"
version = "0.1.0"
edition = "2024"
[dependencies]
nix = { version = "=0.31.3", features = ["signal", "poll", "fs"] }
libc = "=0.2.189"
'''
    (build / "Cargo.toml").write_text(manifest)
    (build / "Cargo.lock").write_bytes((HERE / "Cargo.lock").read_bytes())
    template = (HERE / "wait_status.rs.in").read_text()
    assert template.count("@@WAIT@@") == 2  # comment plus insertion point
    generated = template.replace("@@WAIT@@.", "the production block.").replace("@@WAIT@@", block(source))
    (build / "src/main.rs").write_text(generated)
    (output / f"{label}.rs").write_text(generated)
    prefix = shlex.split(os.environ.get("MAGISK_TOOL_PREFIX", ""))
    subprocess.run([*prefix, "cargo", "build", "--locked", "--manifest-path", str(build / "Cargo.toml")], check=True)
    rows = []
    expected_failures = {"term", "kill", "int"} if expectation == "legacy" else set()
    for case in CASES:
        # Any timeout/setup failure aborts the matrix; never accepted as RED.
        p = subprocess.run([str(build / "target/debug/magisk-source-regression"), case],
                           text=True, capture_output=True, timeout=5)
        passed = p.returncode == 0
        cause = (p.returncode == 101 and "actual=0 reaped=true" in p.stdout
                 and f"wait status contract: {case}" in p.stderr)
        row = dict(case=case, passed=passed, exit_code=p.returncode, stdout=p.stdout,
                   stderr=p.stderr, matched=(passed if case not in expected_failures else cause))
        rows.append(row)
        print(json.dumps(dict(variant=label, **row)), flush=True)
    result = dict(variant=label, expectation=expectation,
                  source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                  block_sha256=hashlib.sha256(block(source).encode()).hexdigest(),
                  expected_failures=sorted(expected_failures),
                  actual_failures=[r["case"] for r in rows if not r["passed"]],
                  matched=all(r["matched"] for r in rows), results=rows)
    (output / f"{label}.json").write_text(json.dumps(result, indent=2) + "\n")
    assert result["matched"], f"{label}: unexpected failure set or cause"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=HERE.parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expect", choices=("legacy", "fixed"), help="single current-source pre-fix check")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    current = (args.repo / SOURCE).read_text()
    if args.expect:
        variants = [("current", current, args.expect)]
    else:
        old = subprocess.check_output(["git", "-C", str(args.repo), "show", f"{BASE}:{SOURCE}"], text=True)
        assert block(old) != block(current), "wait status fix must be present"
        withdrawn = current.replace(block(current), block(old))
        assert block(withdrawn) == block(old)
        variants = [("upstream", old, "legacy"), ("fixed", current, "fixed"),
                    ("withdrawn", withdrawn, "legacy")]
    results = [run_variant(label, source, expectation, args.output)
               for label, source, expectation in variants]
    result = dict(base=BASE, head=subprocess.check_output(
        ["git", "-C", str(args.repo), "rev-parse", "HEAD"], text=True).strip(),
        matched=all(r["matched"] for r in results), variants=results,
        scope="Verbatim production waitpid block and real child processes; not the running Magisk daemon.")
    (args.output / "matrix.json").write_text(json.dumps(result, indent=2) + "\n")
    print("WAIT_STATUS_MATRIX_MATCH=" + str(result["matched"]))


if __name__ == "__main__":
    main()
