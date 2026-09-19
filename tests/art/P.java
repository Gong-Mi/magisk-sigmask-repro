// P.java — ART signal-dependency probe.
//
// Two deterministic tests for ART's reliance on synchronous signal delivery:
//   npe: implicit null check  -> ART delivers SIGSEGV -> handler throws NPE
//   soe: stack overflow       -> guard page SIGSEGV    -> handler throws StackOverflowError
//
// With SIGSEGV blocked (as inherited from a Magisk v30.3+ ThreadPool worker),
// Linux re-executes the faulting instruction forever: the process hangs and
// burns CPU instead of printing CAUGHT:*.

public final class P {
    static void triggerNpe() {
        Object o = null;
        o.toString(); // implicit null check => SIGSEGV => art_sigsegv_handler
    }

    static void recurse() {
        recurse(); // guard page fault => SIGSEGV => StackOverflowError
    }

    public static void main(String[] args) {
        if (args.length < 1) {
            System.out.println("usage: P npe|soe");
            System.exit(2);
        }
        try {
            if (args[0].equals("npe")) {
                triggerNpe();
                System.out.println("UNEXPECTED: no exception");
                System.exit(3);
            } else if (args[0].equals("soe")) {
                recurse();
                System.out.println("UNEXPECTED: no exception");
                System.exit(3);
            } else {
                System.out.println("unknown mode");
                System.exit(2);
            }
        } catch (Throwable t) {
            System.out.println("CAUGHT:" + t.getClass().getSimpleName());
            System.exit(0);
        }
    }
}
