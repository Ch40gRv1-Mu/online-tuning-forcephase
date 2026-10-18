#!/usr/bin/env bash
# Build pinned CaDiCaL variants from third_party/cadical (git submodule).
#
#   scripts/build_solver.sh [variant ...]
#
# Variants (default: upstream fpc upstream-check fpc-check):
#   upstream        unmodified pinned source, ./configure -static (-O3 -DNDEBUG)
#   fpc             pinned source + patches/cadical-fpc.patch + solver/*.{hpp,cpp}
#   upstream-check  as 'upstream' but with assertions (./configure -c)
#   fpc-check       as 'fpc' but with assertions
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
[ ${#variants[@]} -eq 0 ] && variants=(upstream fpc upstream-check fpc-check)

head="$(git -C "$SUB" rev-parse HEAD)"
if [ "$head" != "$PIN" ]; then
  echo "error: third_party/cadical is at $head, expected pinned $PIN" >&2
  echo "       run: git submodule update --init third_party/cadical" >&2
  exit 1
fi

for v in "${variants[@]}"; do
  case "$v" in
    upstream)        patched=0; cfg=(-static) ;;
    fpc)             patched=1; cfg=(-static) ;;
    upstream-check)  patched=0; cfg=(-static -c) ;;
    fpc-check)       patched=1; cfg=(-static -c) ;;
    *) echo "unknown variant $v" >&2; exit 1 ;;
  esac
  out="$ROOT/build/$v"
  rm -rf "$out"
  mkdir -p "$out/src"
  # Export exactly the pinned tree (ignores any local edits in the submodule).
  git -C "$SUB" archive "$PIN" | tar -x -C "$out/src"
  if [ "$patched" = 1 ]; then
    (cd "$out/src" && patch -p1 --quiet --forward < "$PATCH")
    cp "$ROOT"/solver/*.hpp "$ROOT"/solver/*.cpp "$out/src/src/"
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
      echo "solver_sources_sha256=$(cat "$ROOT"/solver/*.hpp "$ROOT"/solver/*.cpp | sha256sum | cut -d' ' -f1)"
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
