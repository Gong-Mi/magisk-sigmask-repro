#!/usr/bin/env python3
"""Compile production-source slices, not rewritten bug simulations.

Only test seams: app_process executable path, 70s -> 100ms poll timeout,
provider return -> boolean observation; path/logging wrappers are scaffolding.
A compile/setup failure is never an expected RED result.
"""
import argparse
import hashlib
import json
import os
import shlex
import time
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def function(source, marker):
    start = source.index(marker)
    opening = source.index("{", start)
    # These selected functions have balanced braces, including format strings.
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def generate(source):
    if "fn app_process()" in source:
        app = function(source, "fn app_process()")
    else:
        # Old production command construction; assert there are exactly two sites.
        original = 'Command::new("/system/bin/app_process")'
        assert source.count(original) == 2
        app = "fn app_process() -> Command { " + original + " }"
    app = app.replace('"/system/bin/app_process"', 'std::env::current_exe().expect("self exe")')

    start = source.index("            if let Ok(output) = cmd.output()")
    end = source.index("\n            }", start) + len("\n            }")
    provider = source[start:end]
    assert provider.count("return;") == 1
    provider = provider.replace("return;", "return true;")

    start = source.index("            // Open with O_RDWR to prevent FIFO open block")
    end = source.index("            Ok(fd)", start) + len("            Ok(fd)")
    fifo = source[start:end]
    assert fifo.count("70 * 1000") == 1
    fifo = fifo.replace("70 * 1000", "100")
    template = (HERE / "harness.rs.in").read_text()
    return template.replace("@@APP_PROCESS@@", app).replace("@@PROVIDER@@", provider).replace("@@FIFO@@", fifo)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Magisk connect.rs")
    parser.add_argument("--expect", choices=["legacy", "upstream", "provider-only", "fifo-only", "fixed"], required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.read_text()
    build = HERE / ".build"
    (build / "src").mkdir(parents=True, exist_ok=True)
    (build / "Cargo.toml").write_text('''[package]
name = "magisk-source-regression"
version = "0.1.0"
edition = "2024"
[dependencies]
nix = { version = "=0.31.3", features = ["signal", "poll", "fs"] }
libc = "=0.2.189"
''')
    (build / "src/main.rs").write_text(generate(source))
    (build / "Cargo.lock").write_bytes((HERE / "Cargo.lock").read_bytes())
    prefix = shlex.split(os.environ.get("MAGISK_TOOL_PREFIX", ""))
    subprocess.run([*prefix, "cargo", "build", "--locked", "--manifest-path", str(build / "Cargo.toml")], check=True)
    binary = build / "target/debug/magisk-source-regression"
    rows: list[dict] = []
    cases = [("signal_mask", ["check-mask"])]
    for mode in ["success", "empty-success", "failure", "signal", "error-text", "stderr-error"]:
        cases.append(("provider_" + mode, ["check-provider", mode]))
    with tempfile.TemporaryDirectory(prefix="magisk-fifo-") as temp:
        for mode in ["reply", "deny", "delayed", "timeout"]:
            path = str(Path(temp) / mode)
            os.mkfifo(path, 0o600)
            cases.append(("fifo_" + mode, ["check-fifo", path, mode]))
        for name, argv in cases:
            row: dict
            started = time.monotonic()
            try:
                p = subprocess.run([str(binary), *argv], capture_output=True, text=True, timeout=3)
                row = dict(name=name, passed=p.returncode == 0, exit_code=p.returncode,
                           stdout=p.stdout, stderr=p.stderr)
            except subprocess.TimeoutExpired as exc:
                row = dict(name=name, passed=False, timed_out=True,
                           stdout=(exc.stdout or b"").decode(errors="replace"),
                           stderr=(exc.stderr or b"").decode(errors="replace"))
            row["elapsed_seconds"] = time.monotonic() - started
            rows.append(row)
            print(json.dumps(row), flush=True)
    expected_failures = {
        "legacy": {"signal_mask", "provider_failure", "provider_signal", "fifo_timeout"},
        "upstream": {"provider_failure", "provider_signal", "fifo_timeout"},
        "provider-only": {"fifo_timeout"},
        "fifo-only": {"provider_failure", "provider_signal"},
        "fixed": set(),
    }[args.expect]
    failures = {row["name"] for row in rows if not row["passed"]}
    # A failure must have the intended cause, not merely the same test name.
    for row in rows:
        if row["passed"] or row["name"] not in expected_failures:
            continue
        if row["name"] == "fifo_timeout":
            row["expected_cause"] = row.get("timed_out", False) and "BUG: poll timeout accepted" in row.get("stdout", "")
        elif row["name"] == "signal_mask":
            row["expected_cause"] = row.get("exit_code") == 101 and "SEGV=true BUS=true USR1=true" in row.get("stdout", "")
        else:
            mode = row["name"].removeprefix("provider_")
            row["expected_cause"] = row.get("exit_code") == 101 and f"provider mode={mode}" in row.get("stderr", "")
    matched = failures == expected_failures and all(row.get("expected_cause", True) for row in rows)
    result = dict(source=str(args.source.resolve()), source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                  expectation=args.expect, matched=matched, expected_failures=sorted(expected_failures),
                  actual_failures=sorted(failures), results=rows,
                  scope="Extracted production Rust control flow; real POSIX IO/spawn. Not a running Magisk daemon or ART test.")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n")
    print("EXPECTED_FAILURE_SET_MATCH=" + str(matched))
    raise SystemExit(0 if matched else 1)


if __name__ == "__main__":
    main()
