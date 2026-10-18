// API-level phase priority test for online-tuning-forcephase (M0).
//
// Builds against the patched library (build/fpc/src/build/libcadical.a).
// Checks on a trivially satisfiable formula with lucky phases, walking and
// preprocessing disabled (so that the model is produced by CDCL decisions):
//
//  1. bare 'forcephase=1' (phase=1 default) decides positive,
//  2. 'forcephase=1, phase=0' decides negative,
//  3. API 'phase(lit)' has priority over 'forcephase' (both tracks),
//  4. track P (fpc=2, fpctrack=1, NEGATIVE) decides negative but keeps API
//     phases, and native defaults decide positive.
//
// Prints 'ok <name>' or 'FAIL <name>' per check and exits non-zero on any
// failure.

#include "cadical.hpp"

#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

static const int N = 40;

static void common (CaDiCaL::Solver &s) {
  s.set ("lucky", 0);
  s.set ("walk", 0);
  s.set ("warmup", 0);
  s.set ("elim", 0);
  s.set ("probe", 0);
  s.set ("subsume", 0);
  s.set ("vivify", 0);
  s.set ("factor", 0);
  s.set ("congruence", 0);
  s.set ("sweep", 0);
}

// Formula: independent clauses (x_i | x_{i+N}) for i in 1..N, satisfiable
// with either polarity, so every decision sign is visible in the model.
static void add_formula (CaDiCaL::Solver &s) {
  for (int i = 1; i <= N; i++) {
    s.add (i);
    s.add (i + N);
    s.add (0);
  }
}

static int failures = 0;

static void expect (bool ok, const std::string &name) {
  printf ("%s %s\n", ok ? "ok" : "FAIL", name.c_str ());
  if (!ok)
    failures++;
}

// Count positive values among variables 1..2N in the model.
static int positives (CaDiCaL::Solver &s) {
  int res = 0;
  for (int v = 1; v <= 2 * N; v++)
    res += s.val (v) > 0;
  return res;
}

struct Case {
  std::string name;
  std::vector<std::pair<const char *, int>> opts;
  int api; // 0 = none, -1 = all negative via API, +1 = all positive
};

int main () {
  std::vector<Case> cases = {
      {"default", {}, 0},
      {"bare_forcephase", {{"forcephase", 1}}, 0},
      {"forcephase_phase0", {{"forcephase", 1}, {"phase", 0}}, 0},
      {"fixed_C_negative", {{"fpc", 2}, {"fpcinit", 1}}, 0},
      {"fixed_C_positive", {{"fpc", 2}, {"fpca0", 3}}, 0},
      {"fixed_P_negative", {{"fpc", 2}, {"fpcinit", 1}, {"fpctrack", 1}}, 0},
      {"api_neg_over_bare_forcephase", {{"forcephase", 1}}, -1},
      {"api_pos_over_forcephase_phase0", {{"forcephase", 1}, {"phase", 0}},
       +1},
      {"api_pos_over_P_negative",
       {{"fpc", 2}, {"fpcinit", 1}, {"fpctrack", 1}},
       +1},
      {"api_pos_over_C_negative", {{"fpc", 2}, {"fpcinit", 1}}, +1},
  };
  for (const auto &c : cases) {
    CaDiCaL::Solver s;
    common (s);
    for (const auto &o : c.opts)
      s.set (o.first, o.second);
    add_formula (s);
    if (c.api)
      for (int v = 1; v <= 2 * N; v++)
        s.phase (c.api * v);
    const int res = s.solve ();
    const int pos = positives (s);
    bool ok = res == 10;
    std::string expectation;
    if (c.api > 0 || c.name == "default" || c.name == "bare_forcephase" ||
        c.name == "fixed_C_positive") {
      // All decisions positive: every clause satisfied by its first
      // decided literal, other variable may be decided positive too.
      ok = ok && pos == 2 * N;
      expectation = "all positive";
    } else {
      // All decisions negative: exactly one literal per clause is forced
      // positive by propagation.
      ok = ok && pos == N;
      expectation = "exactly N positive";
    }
    char buf[256];
    snprintf (buf, sizeof buf, "%s (res=%d positives=%d expected %s)",
              c.name.c_str (), res, pos, expectation.c_str ());
    expect (ok, buf);
  }
  return failures ? 1 : 0;
}
