# SU verification workbench

This branch imports the official Magisk tree and history, not a rewritten
implementation. Original standalone ART probes are preserved under `tests/art/`.
Official `native/`, `app/`, `scripts/`, `build.py`, license and submodules retain
their paths. Production changes are separate commits and limited to
`native/src/core/su/connect.rs`.

## Pinned baselines

- Legacy: `37063225d4f344a8f41de8201f679e57098cb7e6`.
- Imported upstream: `6d391dd5b1904122dae315bf2c07e100827c86ef`.
- Upstream PR #10108, commit `a11ef9a4dee81cd8b6bb240e3033d5b811ee4bac`,
  already restores the child signal mask and asynchronous activity launch.
  Do not describe those two issues as still unfixed on this baseline.

## Minimal fixes

1. Provider: require `output.status.success()` as well as the existing output
   checks. A failed/signalled process with empty output must reach fallback.
   The weak exit-status check predates the Rust migration; this is not claimed
   to be newly introduced by Rust.
2. Authorization FIFO: preserve the `poll` ready count and require `POLLIN`.
   `Ok(0)` is a timeout, not a successful reply. Use the existing error path,
   which removes the pathname and selects Deny. Old C++ explicitly checked
   `xpoll(...) <= 0`; that behavior was lost in the migration.

No signal policy change in the daemon parent, no retry-policy redesign,
no protocol change, no lock/fork rewrite, no device installation.

## Minimal verification and evidence limits

`tests/su-regression/run.py` extracts and compiles production Rust slices:

- `app_process()` command construction (old source has two inline sites);
- the complete Provider success predicate and early return;
- FIFO open/poll/return block.

Real `Command`, real child exit/signal status, nix signal masks/poll and real
named FIFOs are used. Explicit test seams:

- `/system/bin/app_process` -> probe executable, to observe its inherited mask;
- `70 * 1000` -> `100` milliseconds, to test timeout behavior cheaply;
- Provider `return` -> observed boolean;
- path and diagnostic wrappers are scaffold implementations, not the entire
  Magisk base crate. Their return contracts must match production. In particular
  `log_err!` returns **Err**, not a bare error. Full native compilation is an
  independent mandatory gate, since a scaffold can hide a type mismatch.

These tests do NOT prove manager UI launch, Binder behavior, SELinux permissions,
FIFO final policy handling in a running daemon, ART implicit checks, or whole
phone heat/root behavior. Do not promote this layer into device acceptance.

`matrix.py` tests six variants, eleven scenarios per variant:

| Source variant | Expected contract failures |
| --- | --- |
| Legacy | child signal mask; Provider nonzero/signal; FIFO no response |
| Imported upstream | Provider nonzero/signal; FIFO no response |
| Withdraw FIFO fix only | FIFO no response |
| Withdraw Provider fix only | Provider nonzero/signal |
| Both fixes | none |
| Withdraw both fixes | same failures as imported upstream |

A matching failure set is NOT enough: expected failures must have the intended
assertion or timeout marker. Setup errors, compilation errors, early FIFO errors
and unexpected failures fail the matrix. Controls include allow/deny/delayed
FIFO replies, successful/empty-success Provider output, and stdout/stderr Error.
The parent signal mask must stay blocked while the child mask becomes clean.

Reports include source SHA-256, expected/actual failures and raw child output.
Every hung test is isolated and forcibly killed by the Python parent. Temporary
FIFOs are deleted; this never connects to a live Magisk daemon.

## Commands

With official ONDK and JDK 25 installed:

    python3 build.py gen
    MAGISK_TOOL_PREFIX='python3 scripts/env.py' python3 tests/su-regression/matrix.py --repo . --output verification/source-matrix
    python3 build.py -v native magisk

The `SU source validation` workflow runs the same matrix and official codegen /
all-default-ABI native build. Its artifact contains reports and native executables.
Check run.headSha against the branch, not just a green historical run.

A Termux-only isolated harness can be copied OUTSIDE the Magisk checkout and
compiled with the host Rust toolchain, using `--repo` to read this checkout. This
is Android/Bionic mechanism evidence, not a replacement for the official build.
The local full build was blocked by missing ONDK; it is not recorded as passing.

## Remaining independent investigations

- Full manager request/no-reply/timeout/cleanup integration on a disposable,
  rooted emulator. Never patch or restart the user's active root daemon to test.
- Partial/truncated FIFO replies after POLLIN: the existing blocking four-byte
  read has no total deadline. The present patch only fixes **no response**.
- A Provider call stuck inside `cmd.output()` is not bounded by this patch.
- Async launch failure: upstream no longer waits for app_process exit, so launch
  acknowledgement and child reaping/timeout semantics deserve separate tests.
- Multithreaded fork and logging/allocation locks: inspect atfork handlers and
  force contention before claiming a reproduced deadlock; removing one debug!
  call alone does not prove the whole child path safe.
- ThreadPool `CORE_POOL_SIZE=3` is not a cap; non-core threads are created when
  none are idle. Audit lock/cache ownership before claiming a global outage.
- Small ART heap causality is unproven without paired heap/JIT/GC experiments.
- Shamiko's Unsupported environment is a different, unresolved binary path.

No claim is made about all Magisk bugs being fixed, release-tag inclusion of the
upstream patch, or how long upstream maintainers need for future work.
