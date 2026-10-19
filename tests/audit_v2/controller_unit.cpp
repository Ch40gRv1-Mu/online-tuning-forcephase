// Audit v2 unit tests for the v2 controller (links build/fpc2/src/build/libcadical.a).
//
//   controller_unit                      run the unit tests (exit 1 on failure)
//   controller_unit eval <policy> <csv>  print one score per CSV row (header =
//                                        feature names, empty = missing), using
//                                        the controller's own parser/evaluator
//
// Unit cases: flip statistics for real flips, no flips, inactive variables,
// invalid history (first record of a stream, after a compaction reset), and
// policy parsing/evaluation including missing-value directions.

#include "fpcontrol.hpp"

#include <cmath>
#include <cstdio>
#include <fstream>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

using namespace CaDiCaL::FPC;

static int failures = 0;
static void expect (bool ok, const char *name) {
  printf ("%s %s\n", ok ? "ok" : "FAIL", name);
  failures += !ok;
}

static void flip_cases () {
  std::vector<int> sample = {1, 2, 3, 4};
  std::vector<signed char> saved = {0, 1, -1, 1, -1}; // index 0 unused
  std::vector<char> alive = {1, 1, 1, 1};
  std::vector<signed char> hist (4, 0);
  int64_t cmp, fl;
  flip_update (sample, saved.data (), alive, hist, cmp, fl);
  expect (cmp == 0 && fl == 0, "first record of a stream has no comparable history (null)");
  flip_update (sample, saved.data (), alive, hist, cmp, fl);
  expect (cmp == 4 && fl == 0, "unchanged phases: 4 compared, 0 flips");
  saved[2] = 1, saved[4] = 1;
  flip_update (sample, saved.data (), alive, hist, cmp, fl);
  expect (cmp == 4 && fl == 2, "two real flips counted");
  alive[0] = 0, saved[1] = -1;
  flip_update (sample, saved.data (), alive, hist, cmp, fl);
  expect (cmp == 3 && fl == 0, "inactive variable excluded (and its flip ignored)");
  alive[0] = 1;
  flip_update (sample, saved.data (), alive, hist, cmp, fl);
  expect (cmp == 3 && fl == 0, "variable re-activated: no stale comparison");
  std::vector<signed char> other (4, 0); // separate stream: own history
  flip_update (sample, saved.data (), alive, other, cmp, fl);
  expect (cmp == 0, "independent stream does not reuse the other stream's history");
  std::fill (hist.begin (), hist.end (), 0); // compaction reset
  flip_update (sample, saved.data (), alive, hist, cmp, fl);
  expect (cmp == 0, "after a reset (compaction) the flip is null again");
}

static void policy_cases () {
  const char *path = "/tmp/fpc_unit_policy.txt";
  {
    std::ofstream f (path);
    f << "fpc-policy 1\ntype oneshot\nprefix 10000\nthreshold 0.5\n"
         "model tree ( c_glue_mean 7.5 R 0.2 ( r_stable 0.5 L 0.9 0.1 ) )\n";
  }
  Policy p;
  parse_policy (path, p);
  std::vector<double> f (Controller::num_features (),
                         std::numeric_limits<double>::quiet_NaN ());
  const int g = Controller::feature_index ("c_glue_mean");
  const int st = Controller::feature_index ("r_stable");
  f[g] = 5, f[st] = 0;
  expect (p.model.eval (f.data ()) == 0.2, "tree: x <= threshold goes left");
  f[g] = 9, f[st] = 0;
  expect (p.model.eval (f.data ()) == 0.9, "tree: right subtree, then left");
  f[g] = std::numeric_limits<double>::quiet_NaN ();
  f[st] = 1;
  expect (p.model.eval (f.data ()) == 0.1, "tree: missing value follows declared direction (R)");
  {
    std::ofstream f2 (path);
    f2 << "fpc-policy 1\ntype oneshot\nprefix 1000\nthreshold 0.5\n"
          "model linear 0.5 2 c_glue_mean 10 2 10 1.0 r_stable 0.5 0.5 0 -2\n";
  }
  Policy q;
  parse_policy (path, q);
  f[g] = 12, f[st] = std::numeric_limits<double>::quiet_NaN ();
  const double z = 0.5 + 1.0 * (12 - 10) / 2 + -2 * (0 - 0.5) / 0.5;
  expect (std::fabs (q.model.eval (f.data ()) - 1 / (1 + std::exp (-z))) < 1e-12,
          "linear: standardized logit with imputation");
}

static int eval_csv (const char *policy, const char *csv) {
  Policy p;
  parse_policy (policy, p);
  std::ifstream in (csv);
  std::string line;
  std::getline (in, line);
  std::vector<int> idx;
  std::stringstream hs (line);
  std::string name;
  while (std::getline (hs, name, ',')) {
    int i = Controller::feature_index (name.c_str ());
    if (i < 0) {
      fprintf (stderr, "unknown feature %s\n", name.c_str ());
      return 2;
    }
    idx.push_back (i);
  }
  while (std::getline (in, line)) {
    std::vector<double> f (Controller::num_features (),
                           std::numeric_limits<double>::quiet_NaN ());
    std::stringstream ls (line);
    std::string cell;
    for (size_t k = 0; k < idx.size () && std::getline (ls, cell, ','); k++)
      if (!cell.empty () && cell != "nan")
        f[idx[k]] = std::stod (cell);
    printf ("%.17g\n", p.model.eval (f.data ()));
  }
  return 0;
}

int main (int argc, char **argv) {
  if (argc == 4 && std::string (argv[1]) == "eval")
    return eval_csv (argv[2], argv[3]);
  flip_cases ();
  policy_cases ();
  return failures ? 1 : 0;
}
