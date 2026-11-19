#!/bin/sh
# Build and run the host unit tests for the hardware independent firmware code.
#
#   CC=gcc ./run_host_tests.sh
#   CC="zig cc" ./run_host_tests.sh
#
# No ARM toolchain and no board are needed: the same .c files that the
# firmware build compiles are compiled here for the development machine.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
CC=${CC:-cc}
OUT=${OUT:-$HERE/build}
mkdir -p "$OUT"

SRC="$HERE/../src/app.c $HERE/../src/keys.c $HERE/../src/protocol.c $HERE/../src/ui.c"

echo "== compiler: $CC"
$CC --version 2>&1 | head -1 || true

echo "== building test_logic"
$CC -std=c11 -O2 -Wall -Wextra -Wshadow -Wundef \
    -I"$HERE/../include" \
    "$HERE/test_logic.c" $SRC -o "$OUT/test_logic"

echo "== running test_logic"
"$OUT/test_logic"

echo "== building host_sim"
$CC -std=c11 -O2 -Wall -Wextra -Wshadow -Wundef \
    -I"$HERE/../include" \
    "$HERE/host_sim.c" $SRC -o "$OUT/host_sim"

echo "== host_sim built: $OUT/host_sim"
echo "OK"
