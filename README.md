# Magisk v30.3+ Rust 迁移信号屏蔽回归 — CI 实证

上游问题：topjohnwu/Magisk 自 cd0eca20b039（"Migrate connect.cpp to Rust"）
起，su 通知/授权路径改用 `std::process::Command` spawn `app_process`，
丢失了旧 C++ `exec_command` 在 fork 子进程中 `pthread_sigmask(SIG_UNBLOCK)`
的行为；而 Magisk daemon 的 ThreadPool 工作线程以 `SigSet::all()`
屏蔽全部信号（native/src/core/thread.rs），屏蔽集跨 execve 继承，
导致 ART 以全屏蔽 sigmask 启动。ART 的隐式空检查/栈溢出 guard page 依赖
SIGSEGV 投递（art/runtime/fault_handler.cc），同步信号被屏蔽时 Linux 重放
故障指令 → 进程挂死并自旋发热（su 授权卡住、整机异常发热的根因）。

本仓库在 GitHub Actions Android 模拟器（API 34 x86_64）上做**确定性机制复现**，
不需要 root、不需要安装 Magisk：

- `blockall.c` — 复刻 Magisk 池线程语义：先屏蔽全部信号再 exec
- `P.java` — ART 探针：`npe`（隐式空检查）、`soe`（栈溢出 guard page）
- `run_tests.sh` — T1 掩码继承实证 + T2/T3 对照实验

## 判定语义

CI job 变绿 = **bug 被复现**（对照组健康 + 屏蔽组挂死）。
CI job 变红 = 未复现或实验不一致。

对照预期：
- 干净环境跑 `dalvikvm P npe` → 捕获 NullPointerException，exit 0
- 干净环境跑 `dalvikvm P soe` → 捕获 StackOverflowError，exit 0
- 全屏蔽环境跑同样命令 → 30s 超时挂死（exit 124/137/143）

## 源码证据（~/magisk-sig 全量 clone，2026-09-17 核实）

- 引入 commit：cd0eca20b039（2025-08-08），含于 v30.3–v31.0，v30.2 干净
- master tip 37063225d（2026-09-05）仍未修复；上游无对应 issue
- 旧 C++ 解屏蔽：`git show cd0eca20b039^:native/src/base/misc.cpp`
- 池线程全屏蔽：`native/src/core/thread.rs:29-33`（`SigSet::all().thread_set_mask()`）
- su 弹窗 spawn 点：`native/src/core/su/connect.rs:102-166`
