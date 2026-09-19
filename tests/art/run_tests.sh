#!/system/bin/sh
# run_tests.sh — runs ON the emulator (adb shell sh /data/local/tmp/run_tests.sh)
# Verdict semantics: the BUG IS REPRODUCED when control cases are healthy AND
# blocked-signal cases hang. hang = timeout-ish exit (124/137/143/255).

TMP=/data/local/tmp
fail=0

check_eq() { # name actual expected
    if [ "$2" = "$3" ]; then
        echo "$1:PASS"
    else
        echo "$1:FAIL(actual=$2 expected=$3)"
        fail=1
    fi
}

check_hang() { # name rc  (PASS if rc indicates timeout/kill)
    case "$2" in
        124|137|143|255) echo "$1:PASS(hang rc=$2)" ;;
        *) echo "$1:FAIL(actual=$2 expected=hang)"; fail=1 ;;
    esac
}

has_f_mask() { # PASS if value contains a fully-blocked mask (ffffff)
    case "$1" in
        *ffffff*) return 0 ;;
        *) return 1 ;;
    esac
}

has_zero_mask() {
    case "$1" in
        *0000000000000000*) return 0 ;;
        *) return 1 ;;
    esac
}

echo "== T0: blockall self-check (expect fully-blocked mask) =="
OUT0=$($TMP/blockall 2>&1)
echo "T0 raw: $OUT0"
if has_f_mask "$OUT0"; then echo "T0_SELFBLOCK:PASS"; else echo "T0_SELFBLOCK:FAIL(mask not blocked)"; fail=1; fi

echo "== T1: sigmask inheritance across execve =="
OUT1=$(sh -c 'grep ^SigBlk /proc/self/status')
OUT2=$($TMP/blockall sh -c 'grep ^SigBlk /proc/self/status')
echo "T1 control raw: $OUT1"
echo "T1 blocked raw: $OUT2"
if has_zero_mask "$OUT1"; then echo "T1_CONTROL_CLEAN:PASS"; else echo "T1_CONTROL_CLEAN:FAIL(mask not clean)"; fail=1; fi
if has_f_mask "$OUT2"; then echo "T1_INHERIT_BLOCKED:PASS"; else echo "T1_INHERIT_BLOCKED:FAIL(mask not inherited)"; fail=1; fi

echo "== T2: ART implicit null check (NPE) =="
timeout 30 dalvikvm -cp $TMP/p.dex P npe >/dev/null 2>&1
RC=$?
echo "T2 control exit: $RC"
check_eq T2_CONTROL_NPE "$RC" 0

timeout 30 $TMP/blockall dalvikvm -cp $TMP/p.dex P npe >/dev/null 2>&1
RC=$?
echo "T2 blocked exit: $RC"
check_hang T2_BLOCKED_NPE_HANG "$RC"

echo "== T3: ART stack overflow guard page (SOE) =="
timeout 30 dalvikvm -cp $TMP/p.dex P soe >/dev/null 2>&1
RC=$?
echo "T3 control exit: $RC"
check_eq T3_CONTROL_SOE "$RC" 0

timeout 30 $TMP/blockall dalvikvm -cp $TMP/p.dex P soe >/dev/null 2>&1
RC=$?
echo "T3 blocked exit: $RC"
check_hang T3_BLOCKED_SOE_HANG "$RC"

echo "== SUMMARY =="
if [ $fail -eq 0 ]; then
    echo "RESULT:REPRODUCED (healthy controls + hangs under blocked sigmask)"
else
    echo "RESULT:NOT_REPRODUCED_OR_INCONCLUSIVE"
fi
exit $fail
