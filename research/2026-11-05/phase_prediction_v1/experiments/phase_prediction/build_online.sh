#!/usr/bin/env bash
# Separate build: never replaces the P1 binary or its immutable receipts.
set -euo pipefail
FPP_ROOT="${1:?experiment directory required}"
cd "$FPP_ROOT"
test ! -e bin/cadical-fpc2
mkdir -p build/fpc2-source
tar -xzf vendor/cadical-src.tar.gz --strip-components=1 -C build/fpc2-source
patch -d build/fpc2-source -p1 --forward < src/cadical-fpc.patch
cp src/fpcontrol.hpp src/fpcontrol.cpp build/fpc2-source/src/
(
  cd build/fpc2-source
  ./configure > ../../logs/fpc2-configure.log 2>&1
  # P1 owns CPUs 0..3; the compiler uses two other available CPUs.
  taskset -c 4,5 make -j2 > ../../logs/fpc2-make.log 2>&1
)
cp build/fpc2-source/build/cadical bin/cadical-fpc2
python3 src/online_gate.py --root "$FPP_ROOT"
