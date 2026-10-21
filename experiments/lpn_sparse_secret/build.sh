#!/usr/bin/env bash
# Put the two binaries this experiment needs into $LPN_WORK/bin:
#   cadical     unmodified CaDiCaL at the project pin c607304 (VERSION 3.0.1)
#   lrat-check  LRAT checker from drat-trim at 2e3b2dc (plus drat-trim itself)
# cadical, in order of preference: $LPN_CADICAL; this repo's
# build/upstream/cadical (scripts/build_solver.sh upstream); otherwise a
# local build of the pinned source (submodule if initialised, else a fresh
# clone) without -static, which also works on macOS.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PIN=c60730422e758ef1cebe7aeddf2dda31c996bf04
DRAT_PIN=2e3b2dc0ecf938addbd779d42877b6ed69d9a985
WORK="${LPN_WORK:-${FP_DATA:+$FP_DATA/lpn_sparse_secret}}"
WORK="${WORK:-$HOME/lpn-sparse-secret-work}"
JOBS="${JOBS:-4}"
CC="${CC:-cc}"
mkdir -p "$WORK/bin" "$WORK/src"
sha() { if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }

if [ -n "${LPN_CADICAL:-}" ]; then
  cp "$LPN_CADICAL" "$WORK/bin/cadical"; cad_src="LPN_CADICAL=$LPN_CADICAL"
elif [ -x "$ROOT/build/upstream/cadical" ]; then
  cp "$ROOT/build/upstream/cadical" "$WORK/bin/cadical"; cad_src="$ROOT/build/upstream/cadical"
else
  src="$WORK/src/cadical"
  rm -rf "$src"
  if git -C "$ROOT/third_party/cadical" cat-file -e "$PIN^{commit}" 2>/dev/null; then
    mkdir -p "$src" && git -C "$ROOT/third_party/cadical" archive "$PIN" | tar -x -C "$src"
    cad_src="third_party/cadical@$PIN (local build)"
  else
    git clone -q https://github.com/arminbiere/cadical.git "$src" && git -C "$src" checkout -q "$PIN"
    cad_src="github arminbiere/cadical@$PIN (local build)"
  fi
  (cd "$src" && ./configure > configure.log 2>&1 && make -j"$JOBS" > make.log 2>&1) \
    || { echo "cadical build failed; see $src/make.log" >&2; exit 1; }
  cp "$src/build/cadical" "$WORK/bin/cadical"
fi
[ "$("$WORK/bin/cadical" --version)" = "3.0.1" ] || { echo "error: cadical is not version 3.0.1" >&2; exit 1; }

if [ "$(git -C "$ROOT/third_party/drat-trim" rev-parse HEAD 2>/dev/null || true)" = "$DRAT_PIN" ]; then
  dsrc="$ROOT/third_party/drat-trim"
else
  dsrc="$WORK/src/drat-trim"
  [ -d "$dsrc/.git" ] || git clone -q https://github.com/marijnheule/drat-trim.git "$dsrc"
  git -C "$dsrc" checkout -q "$DRAT_PIN"
fi
"$CC" -O2 -o "$WORK/bin/lrat-check" "$dsrc/lrat-check.c"
"$CC" -O2 -o "$WORK/bin/drat-trim" "$dsrc/drat-trim.c" -lm

{
  echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "cadical_source: $cad_src"
  echo "cadical_version: $("$WORK/bin/cadical" --version)"
  echo "cadical_sha256: $(sha "$WORK/bin/cadical")"
  echo "drat_trim_sha: $DRAT_PIN"
  echo "lrat_check_sha256: $(sha "$WORK/bin/lrat-check")"
  echo "cc: $("$CC" --version 2>&1 | head -1)"
  echo "python: $(python3 --version 2>&1)"
  echo "host: $(uname -srm)"
} > "$WORK/bin/BUILDINFO"
cat "$WORK/bin/BUILDINFO"
