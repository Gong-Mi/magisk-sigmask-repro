// blockall.c — block ALL signals in the current thread, then exec the given command.
// This reproduces what Magisk v30.3+ does: its ThreadPool workers run with
// SigSet::all().thread_set_mask() (native/src/core/thread.rs) and su's
// connect.rs spawns app_process via std::process::Command, which never resets
// the signal mask. The child therefore inherits a fully-blocked sigmask across
// execve (POSIX: sigprocmask state survives exec).
//
// usage:
//   blockall            # self-check: print own SigBlk, exit 0
//   blockall CMD [ARGS] # block everything, then execvp(CMD)

#define _GNU_SOURCE
#include <signal.h>
#include <stdio.h>
#include <unistd.h>
#include <string.h>

static int print_sigblk(void) {
    FILE *f = fopen("/proc/self/status", "r");
    if (!f) { perror("fopen"); return 1; }
    char line[512];
    while (fgets(line, sizeof(line), f)) {
        if (!strncmp(line, "SigBlk:", 7)) {
            fputs(line, stdout);
            fclose(f);
            return 0;
        }
    }
    fclose(f);
    return 1;
}

int main(int argc, char **argv) {
    sigset_t set;
    sigfillset(&set);
    sigdelset(&set, SIGKILL); /* unblockable anyway */
    sigdelset(&set, SIGSTOP); /* unblockable anyway */
    if (sigprocmask(SIG_SETMASK, &set, NULL) != 0) {
        perror("sigprocmask");
        return 2;
    }

    if (argc < 2) {
        return print_sigblk();
    }

    execvp(argv[1], &argv[1]);
    perror("execvp");
    return 127;
}
