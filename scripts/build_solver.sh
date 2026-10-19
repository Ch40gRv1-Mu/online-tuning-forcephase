#!/usr/bin/env bash
# Build pinned CaDiCaL variants from third_party/cadical (git submodule).
#
#   scripts/build_solver.sh [variant ...]
#
# Variants (default: all six):
#   upstream        unmodified pinned source, ./configure -static (-O3 -DNDEBUG)
#   fpc             pinned source + patches/cadical-fpc.patch + solver/v1/*.{hpp,cpp}
#                   (round-1 controller, telemetry schema 1; used by every round-1 run)
#   fpc2            as 'fpc' but with solver/*.{hpp,cpp} (audit v2 controller, schema 2)
#   upstream-check  as 'upstream' but with assertions (./configure -c)
#   fpc-check, fpc2-check   as 'fpc' / 'fpc2' with assertions
# NOTE: run ids embed the binary hash and CaDiCaL embeds the build time, so
# rebuilding a variant in a checkout that already has results for it makes
# those results unreachable by 'fprun.py plan'; rebuild only in fresh clones.
#
# Outputs build/<variant>/cadical and build/<variant>/BUILDINFO (compiler,
# flags, source SHA, patch SHA-256, binary SHA-256).  Intended to run inside
# the gs-srun container so every experiment uses one toolchain.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIN=c60730422e758ef1cebe7aeddf2dda31c996bf04
SUB="$ROOT/third_party/cadical"
PATCH="$ROOT/patches/cadical-fpc.patch"
JOBS="${JOBS:-8}"

variants=("$@")
[ ${#variants[@]} -eq 0 ] && variants=(upstream fpc fpc2 upstream-check fpc-check fpc2-check)

head="$(git -C "$SUB" rev-parse HEAD)"
if [ "$head" != "$PIN" ]; then
  echo "error: third_party/cadical is at $head, expected pinned $PIN" >&2
  echo "       run: git submodule update --init third_party/cadical" >&2
  exit 1
fi

for v in "${variants[@]}"; do
  case "$v" in
    upstream)        patched=0; cfg=(-static) ;;
    fpc)             patched=1; srcdir=solver/v1; cfg=(-static) ;;
    fpc2)            patched=1; srcdir=solver; cfg=(-static) ;;
    upstream-check)  patched=0; cfg=(-static -c) ;;
    fpc-check)       patched=1; srcdir=solver/v1; cfg=(-static -c) ;;
    fpc2-check)      patched=1; srcdir=solver; cfg=(-static -c) ;;
    *) echo "unknown variant $v" >&2; exit 1 ;;
  esac
  out="$ROOT/build/$v"
  rm -rf "$out"
  mkdir -p "$out/src"
  # Export exactly the pinned tree (ignores any local edits in the submodule).
  git -C "$SUB" archive "$PIN" | tar -x -C "$out/src"
  if [ "$patched" = 1 ]; then
    (cd "$out/src" && patch -p1 --quiet --forward < "$PATCH")
    cp "$ROOT/$srcdir"/*.hpp "$ROOT/$srcdir"/*.cpp "$out/src/src/"
  fi
  (cd "$out/src" && ./configure "${cfg[@]}" > "$out/configure.log" 2>&1 \
     && make -j"$JOBS" > "$out/make.log" 2>&1) || {
       echo "build of $v failed; see $out/make.log" >&2; tail -30 "$out/make.log" >&2; exit 1; }
  cp "$out/src/build/cadical" "$out/cadical"
  {
    echo "variant=$v"
    echo "cadical_sha=$PIN"
    echo "cadical_version=$(cat "$out/src/VERSION")"
    echo "configure=${cfg[*]}"
    echo "patched=$patched"
    if [ "$patched" = 1 ]; then
      echo "patch_sha256=$(sha256sum "$PATCH" | cut -d' ' -f1)"
      echo "solver_sources=$srcdir"
      echo "solver_sources_sha256=$(cat "$ROOT/$srcdir"/*.hpp "$ROOT/$srcdir"/*.cpp | sha256sum | cut -d' ' -f1)"
    fi
    echo "repo_commit=$(git -C "$ROOT" rev-parse HEAD)"
    echo "repo_dirty=$(git -C "$ROOT" status --porcelain --untracked-files=no -- solver patches scripts/build_solver.sh | wc -l)"
    echo "cxx=$(g++ --version | head -1)"
    echo "cxxflags=$(grep -m1 '^CXXFLAGS' "$out/src/build/makefile" || true)"
    echo "host=$(hostname)"
    echo "os=$(. /etc/os-release && echo "$PRETTY_NAME")"
    echo "binary_sha256=$(sha256sum "$out/cadical" | cut -d' ' -f1)"
    echo "built_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$out/BUILDINFO"
  echo "built $v: $(grep binary_sha256 "$out/BUILDINFO")"
done
