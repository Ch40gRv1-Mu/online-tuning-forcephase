#!/usr/bin/env bash
# Build verification and feature tools into build/tools/:
#   lrat-trim   (third_party/lrat-trim, pinned submodule)   LRAT proof checker
#   drat-trim   (third_party/drat-trim, pinned submodule)   DRAT checker (spot checks)
#   checkmodel  (tools/checkmodel.c)                         independent model checker
#   cnffeatures (tools/cnffeatures.c)                        static CNF features
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/build/tools"
mkdir -p "$OUT"
CC="${CC:-gcc}"
$CC -O3 -DNDEBUG -static -o "$OUT/lrat-trim" "$ROOT/third_party/lrat-trim/lrat-trim.c"
$CC -O3 -static -o "$OUT/drat-trim" "$ROOT/third_party/drat-trim/drat-trim.c" -lm
$CC -O2 -Wall -static -o "$OUT/checkmodel" "$ROOT/tools/checkmodel.c"
$CC -O2 -Wall -static -o "$OUT/cnffeatures" "$ROOT/tools/cnffeatures.c" -lm
$CC -O2 -Wall -static -o "$OUT/cnfscramble" "$ROOT/tools/cnfscramble.c"
{
  echo "lrat_trim_sha=$(git -C "$ROOT/third_party/lrat-trim" rev-parse HEAD)"
  echo "drat_trim_sha=$(git -C "$ROOT/third_party/drat-trim" rev-parse HEAD)"
  echo "cc=$($CC --version | head -1)"
  for t in lrat-trim drat-trim checkmodel cnffeatures cnfscramble; do
    echo "${t}_sha256=$(sha256sum "$OUT/$t" | cut -d' ' -f1)"
  done
} > "$OUT/BUILDINFO"
cat "$OUT/BUILDINFO"
