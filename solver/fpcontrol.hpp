#ifndef _fpcontrol_hpp_INCLUDED
#define _fpcontrol_hpp_INCLUDED

// Forcephase research controller (FPC) for the online-tuning-forcephase
// project.  This file is NOT part of upstream CaDiCaL.  It is copied into
// 'src/' of the pinned source tree by 'scripts/build_solver.sh' together
// with 'patches/cadical-fpc.patch', which adds the hooks.
//
// Two tracks (see 'docs/DESIGN.md'):
//
//   C (fpctrack=0)  an action is an effective '(forcephase, phase)' pair
//                   read by every place that upstream reads these options
//                   (decide_phase, likely_phase, rephasing, rephase
//                   original/inverted, enlarge, walk/warmup initial phase).
//   P (fpctrack=1)  an action only overrides the sign of free CDCL
//                   decisions in 'decide' (same priority as forcephase);
//                   everything else keeps native semantics.
//
// Actions are only applied in 'at_restart', i.e., directly after a natural
// restart in the CDCL loop (a safe point).  No restarts are added and no
// solver state (saved/target/best phases, clauses, scores, RNG) is touched.

#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

namespace CaDiCaL {

struct Internal;

namespace FPC {

enum Mode { OFF = 0, TELEMETRY = 1, FIXED = 2, SCHEDULE = 3, POLICY = 4,
            RANDOM = 5 };

// Action identifiers (values of options 'fpca0' and 'fpca1').
enum Action { NATIVE = 0, NEGATIVE = 1, NATIVE_INIT_NEG = 2, POSITIVE = 3 };

// Source of the phase returned by 'decide_phase' (for decision counting).
enum Source { SRC_FORCE_SAVED = 0, SRC_API = 1, SRC_FORCEPHASE = 2,
              SRC_TARGET = 3, SRC_SAVED = 4, SRC_STUBBORN = 5,
              SRC_FALLBACK = 6, NUM_SOURCES = 7 };

// Cheap counters maintained unconditionally in hot paths (a few additions
// per conflict / decision / original clause).  They never influence search.
struct Counters {
  int64_t glue_sum = 0;     // sum of 1st UIP glue
  int64_t glue_low = 0;     // learned with glue <= 2
  int64_t minsize_sum = 0;  // learned size after shrinking/minimization
  int64_t backjump_sum = 0; // conflict level minus backtrack level
  int64_t analyzed = 0;     // conflicts analyzed on the main path
  int64_t dec_free = 0;     // free CDCL decisions (via 'decide_phase')
  int64_t dec_neg = 0;      // ... assigning a negative literal
  int64_t dec_native_pos = 0; // ... where native suggests positive (fpc>0)
  int64_t dec_p_override = 0; // ... overridden by track P
  int64_t dec_p_flip = 0;     // ... overridden with sign change
  int64_t dec_src[NUM_SOURCES] = {0};
  // Static features of original clauses (accumulated while parsing).
  int64_t orig_clauses = 0, orig_lits = 0, orig_pos = 0, orig_unit = 0,
          orig_bin = 0, orig_ter = 0, orig_horn = 0, orig_antihorn = 0,
          orig_max_var = 0; // largest internal variable in a clause
};

// Snapshot of cumulative solver counters at a hook.
struct Snapshot {
  double time = 0;
  int64_t conflicts = 0, decisions = 0, propagations = 0, ticks = 0,
          restarts = 0, reused = 0, rephased = 0, stabconflicts = 0,
          chrono = 0, units = 0, binaries = 0, learned = 0,
          learned_lits = 0;
  Counters c;
};

// Tiny decision model: depth-limited tree or standardized logistic model.
struct Model {
  // tree nodes: feature < 0 means leaf with 'value'
  struct Node {
    int feature = -1;
    double threshold = 0, value = 0;
    bool missing_left = true;
    int left = -1, right = -1;
  };
  std::vector<Node> nodes;
  bool linear = false;
  double bias = 0;
  struct Term {
    int feature;
    double mean, scale, impute, weight;
  };
  std::vector<Term> terms;
  double eval (const double *features) const;
};

// Flip statistics of one record stream over the fixed variable sample:
// 'hist' holds the saved phase seen at the previous record of the same
// stream (0 = no comparable value).  Only samples that are active now and
// had a valid previous value count towards 'compared'.  Exposed for tests.
void flip_update (const std::vector<int> &sample, const signed char *saved,
                  const std::vector<char> &active, std::vector<signed char> &hist,
                  int64_t &compared, int64_t &flipped);

struct Policy {
  bool loaded = false;
  bool repeat = false;     // 'oneshot' otherwise
  int64_t prefix = 10000;  // oneshot: decide at checkpoint >= prefix
  double threshold = 0.5;  // oneshot: choose a1 iff score > threshold
  double enter = 0.5;      // repeat: switch a0 -> a1 iff score > enter
  double exit = 0.5;       // repeat: switch a1 -> a0 iff score < exit
  Model model;
};

// Parse a policy file (format in docs/DESIGN.md); calls exit(1) on errors.
// Exposed so that tests can evaluate exported models with this exact code.
void parse_policy (const std::string &path, Policy &policy);

class Controller {
public:
  Controller (Internal *);
  ~Controller ();

  void at_restart (); // safe point directly after a natural restart
  void finish (int res);

  static int pair_force (int action);
  static int pair_phase (int action);
  static const char *action_name (int action);

  // Feature table (names fixed at compile time; see 'fpcontrol.cpp').
  static int feature_index (const char *name);
  static int num_features ();
  static const char *feature_name (int);

private:
  Internal *internal;
  int mode, track, a[2], cur;
  int64_t win, next_window, window_index;
  int64_t next_switch, switches, dwell, maxsw, mindwell;
  int checkpoint_index;
  bool decided; // oneshot decision taken
  uint64_t action_rng, sample_rng; // independent of each other and of the solver
  int64_t seen_compacts, sample_epoch;
  FILE *log;
  std::string log_path, policy_path;
  Policy policy;
  Snapshot zero, last_window, last_checkpoint;
  std::vector<int> sample;                 // sampled variable indices
  std::vector<signed char> hist_cp, hist_win; // per-stream previous phases
  std::vector<double> features_cp, features_win;
  double hook_time;                 // time spent in heavy hook work
  int64_t hook_calls;
  // occupancy per action slot
  int64_t occ_conflicts[2], occ_decisions[2], occ_since_conflicts,
      occ_since_decisions;
  double occ_time[2], occ_since_time;
  int64_t applied_at_conflicts;

  static uint64_t next_random (uint64_t &state);
  double random_double ();
  void take (Snapshot &) const;
  void refresh_sample ();
  void compute_features (const Snapshot &now, const Snapshot &ref,
                         std::vector<signed char> &hist,
                         std::vector<double> &features);
  void write_features (const std::vector<double> &features);
  void apply (int slot, const char *reason, int64_t requested);
  uint64_t digest () const;
  void header ();
  void load_policy ();
  void account ();
};

} // namespace FPC
} // namespace CaDiCaL

#endif
