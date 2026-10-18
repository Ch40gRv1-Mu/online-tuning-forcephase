// Forcephase research controller (FPC).  NOT part of upstream CaDiCaL.
// See 'fpcontrol.hpp' for the overall contract and 'docs/DESIGN.md' for
// the JSONL schema and policy file format.

#include "internal.hpp"

#include <cmath>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <limits>
#include <sstream>

namespace CaDiCaL {
namespace FPC {

static const int SCHEMA_VERSION = 1;
static const int SAMPLE_SIZE = 256;

// Checkpoints (cumulative conflicts) at which a 'checkpoint' record with a
// state digest is written in every mode.  Oneshot policies decide at one of
// them, schedule runs switch at the same hook if 'fpcat' equals one.
static const int64_t CHECKPOINTS[] = {1000,   2000,   5000,   10000,
                                      20000,  50000,  100000, 200000,
                                      500000, 1000000};
static const int NUM_CHECKPOINTS = sizeof CHECKPOINTS / sizeof *CHECKPOINTS;

/*------------------------------------------------------------------------*/

// Feature table.  Prefixes: 's_' static (original clauses), 'r_' progress
// and native mechanism, 'c_' cumulative since start, 'w_' since previous
// record of the same type (window or checkpoint), 'x_' current state.

#define FPC_RATIO_FEATURES(P) \
  X (P##dec_per_conf) X (P##props_per_dec) X (P##ticks_per_conf) \
  X (P##conf_per_sec) X (P##glue_mean) X (P##glue_low_frac) \
  X (P##size_mean) X (P##minsize_mean) X (P##backjump_mean) \
  X (P##chrono_frac) X (P##restarts_per_kconf) X (P##reuse_frac) \
  X (P##neg_dec_frac) X (P##native_pos_frac) X (P##target_src_frac) \
  X (P##saved_src_frac) X (P##units_per_kconf) X (P##bin_per_kconf) \
  X (P##stable_frac) X (P##rephases)

#define FPC_FEATURES \
  X (s_log_vars) X (s_log_clauses) X (s_cv_ratio) X (s_mean_len) \
  X (s_unit_frac) X (s_bin_frac) X (s_ter_frac) X (s_pos_frac) \
  X (s_horn_frac) X (s_antihorn_frac) \
  X (r_log_conflicts) X (r_time) X (r_stable) X (r_rephase_due) \
  X (r_action) X (r_switches) \
  FPC_RATIO_FEATURES (c_) FPC_RATIO_FEATURES (w_) \
  X (x_glue_fast) X (x_glue_slow) X (x_glue_ratio) X (x_trail_frac) \
  X (x_trail_ratio) X (x_jump_avg) X (x_level_avg) X (x_size_avg) \
  X (x_best_frac) X (x_target_frac) X (x_active_frac) \
  X (x_irr_per_var) X (x_red_per_irr) X (x_saved_neg_frac) \
  X (x_saved_flip_frac) X (x_target_set_frac) X (x_target_neg_frac)

enum FeatureId {
#define X(N) F_##N,
  FPC_FEATURES
#undef X
      NUM_FEATURES
};

static const char *feature_names[] = {
#define X(N) #N,
    FPC_FEATURES
#undef X
};

int Controller::num_features () { return NUM_FEATURES; }
const char *Controller::feature_name (int i) { return feature_names[i]; }
int Controller::feature_index (const char *name) {
  for (int i = 0; i < NUM_FEATURES; i++)
    if (!strcmp (feature_names[i], name))
      return i;
  return -1;
}

/*------------------------------------------------------------------------*/

int Controller::pair_force (int action) {
  return action == NEGATIVE || action == POSITIVE;
}
int Controller::pair_phase (int action) {
  return action == NATIVE || action == POSITIVE;
}
const char *Controller::action_name (int action) {
  switch (action) {
  case NATIVE:
    return "NATIVE";
  case NEGATIVE:
    return "NEGATIVE";
  case NATIVE_INIT_NEG:
    return "NATIVE_INIT_NEG";
  case POSITIVE:
    return "POSITIVE";
  default:
    return "?";
  }
}

static const double NaN = std::numeric_limits<double>::quiet_NaN ();

static inline double ratio (double num, double den) {
  return den > 0 ? num / den : NaN;
}

/*------------------------------------------------------------------------*/

double Model::eval (const double *f) const {
  if (linear) {
    double z = bias;
    for (const auto &t : terms) {
      double x = f[t.feature];
      if (std::isnan (x))
        x = t.impute;
      z += t.weight * ((x - t.mean) / t.scale);
    }
    return 1.0 / (1.0 + std::exp (-z));
  }
  int i = 0;
  while (nodes[i].feature >= 0) {
    const Node &n = nodes[i];
    const double x = f[n.feature];
    bool go_left = std::isnan (x) ? n.missing_left : x <= n.threshold;
    i = go_left ? n.left : n.right;
  }
  return nodes[i].value;
}

static void fatal (const char *msg, const std::string &arg) {
  fprintf (stderr, "fpc: fatal error: %s '%s'\n", msg, arg.c_str ());
  exit (1);
}

static int parse_tree (std::istream &in, Model &m) {
  std::string tok;
  if (!(in >> tok))
    fatal ("unexpected end of policy tree", "");
  const int idx = (int) m.nodes.size ();
  m.nodes.push_back (Model::Node ());
  if (tok != "(") {
    m.nodes[idx].value = std::stod (tok);
    return idx;
  }
  std::string feature, miss;
  double threshold;
  in >> feature >> threshold >> miss;
  const int fi = Controller::feature_index (feature.c_str ());
  if (fi < 0)
    fatal ("unknown feature in policy", feature);
  if (miss != "L" && miss != "R")
    fatal ("missing direction must be L or R, got", miss);
  const int left = parse_tree (in, m);
  const int right = parse_tree (in, m);
  in >> tok;
  if (tok != ")")
    fatal ("expected ')' in policy tree, got", tok);
  Model::Node &n = m.nodes[idx];
  n.feature = fi, n.threshold = threshold, n.missing_left = (miss == "L");
  n.left = left, n.right = right;
  return idx;
}

void Controller::load_policy () {
  const char *path = getenv ("FPC_POLICY");
  if (!path)
    fatal ("fpc=4 requires environment variable", "FPC_POLICY");
  policy_path = path;
  std::ifstream file (path);
  if (!file)
    fatal ("can not read policy file", policy_path);
  std::stringstream text;
  std::string line;
  while (std::getline (file, line)) {
    const size_t hash = line.find ('#');
    if (hash != std::string::npos)
      line.resize (hash);
    text << line << ' ';
  }
  std::string tok;
  text >> tok;
  int version = 0;
  text >> version;
  if (tok != "fpc-policy" || version != 1)
    fatal ("policy file must start with 'fpc-policy 1'", policy_path);
  while (text >> tok) {
    if (tok == "type") {
      text >> tok;
      if (tok == "oneshot")
        policy.repeat = false;
      else if (tok == "repeat")
        policy.repeat = true;
      else
        fatal ("unknown policy type", tok);
    } else if (tok == "prefix")
      text >> policy.prefix;
    else if (tok == "threshold")
      text >> policy.threshold;
    else if (tok == "enter")
      text >> policy.enter;
    else if (tok == "exit")
      text >> policy.exit;
    else if (tok == "model") {
      text >> tok;
      if (tok == "tree") {
        parse_tree (text, policy.model);
      } else if (tok == "linear") {
        policy.model.linear = true;
        int n;
        text >> policy.model.bias >> n;
        for (int i = 0; i < n; i++) {
          std::string name;
          Model::Term t;
          text >> name >> t.mean >> t.scale >> t.impute >> t.weight;
          t.feature = feature_index (name.c_str ());
          if (t.feature < 0)
            fatal ("unknown feature in policy", name);
          if (!(t.scale > 0))
            fatal ("non-positive scale for feature", name);
          policy.model.terms.push_back (t);
        }
      } else
        fatal ("unknown model kind", tok);
    } else
      fatal ("unknown policy keyword", tok);
  }
  if (!policy.model.linear && policy.model.nodes.empty ())
    fatal ("policy without model", policy_path);
  if (!policy.repeat) {
    bool ok = false;
    for (int i = 0; i < NUM_CHECKPOINTS; i++)
      ok |= (CHECKPOINTS[i] == policy.prefix);
    if (!ok)
      fatal ("oneshot prefix must be a checkpoint value",
             std::to_string (policy.prefix));
  }
  policy.loaded = true;
}

/*------------------------------------------------------------------------*/

Controller::Controller (Internal *i)
    : internal (i), cur (0), window_index (0), switches (0), dwell (0),
      checkpoint_index (0), decided (false), log (0), hook_time (0),
      hook_calls (0), occ_since_conflicts (0), occ_since_decisions (0),
      occ_since_time (0), applied_at_conflicts (-1) {
  const Options &o = internal->opts;
  mode = o.fpc;
  track = o.fpctrack;
  a[0] = o.fpca0;
  a[1] = o.fpca1;
  win = o.fpcwin;
  next_window = win;
  maxsw = o.fpcmaxsw;
  mindwell = o.fpcmindwell;
  next_switch = (mode == SCHEDULE) ? (int64_t) o.fpcat
                                   : std::numeric_limits<int64_t>::max ();
  rng = 0x9e3779b97f4a7c15ull ^ (uint64_t) o.fpcseed;
  occ_conflicts[0] = occ_conflicts[1] = 0;
  occ_decisions[0] = occ_decisions[1] = 0;
  occ_time[0] = occ_time[1] = 0;
  features.assign (NUM_FEATURES, NaN);
  if (track == 1 && (a[0] == NATIVE_INIT_NEG || a[1] == NATIVE_INIT_NEG))
    fatal ("track P has no NATIVE_INIT_NEG action", "fpctrack=1");
  if (mode == POLICY)
    load_policy ();
  const char *path = getenv ("FPC_LOG");
  if (path && *path) {
    log_path = path;
    log = fopen (path, "w");
    if (!log)
      fatal ("can not write telemetry log", log_path);
  }
  header ();
  // Initial action: applied before any variable is created (the controller
  // is constructed in the first 'enlarge'), so that fixed actions have the
  // same initialization as the corresponding command line configuration.
  // Telemetry mode never touches the effective configuration.
  if (mode != TELEMETRY)
    apply (o.fpcinit ? 1 : 0, "init", 0);
  else
    cur = 0;
}

Controller::~Controller () {
  if (log)
    fclose (log);
}

uint64_t Controller::next_random () { // splitmix64, independent of solver
  uint64_t z = (rng += 0x9e3779b97f4a7c15ull);
  z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ull;
  z = (z ^ (z >> 27)) * 0x94d049bb133111ebull;
  return z ^ (z >> 31);
}

double Controller::random_double () {
  return (next_random () >> 11) * (1.0 / 9007199254740992.0);
}

void Controller::header () {
  if (!log)
    return;
  const Options &o = internal->opts;
  fprintf (log,
           "{\"type\":\"header\",\"schema\":%d,\"cadical\":\"%s\","
           "\"mode\":%d,\"track\":\"%s\",\"a0\":\"%s\",\"a1\":\"%s\","
           "\"init\":%d,\"win\":%d,\"at\":%d,\"period\":%d,\"maxsw\":%d,"
           "\"mindwell\":%d,\"prob\":%d,\"rlim\":%d,\"seed\":%d,"
           "\"opt_phase\":%d,\"opt_forcephase\":%d,\"opt_rephase\":%d,"
           "\"opt_target\":%d,\"opt_seed\":%d,\"policy\":\"%s\","
           "\"checkpoints\":[",
           SCHEMA_VERSION, version (), mode, track ? "P" : "C",
           action_name (a[0]), action_name (a[1]), o.fpcinit, o.fpcwin,
           o.fpcat, o.fpcperiod, o.fpcmaxsw, o.fpcmindwell, o.fpcprob,
           o.fpcrlim, o.fpcseed, o.phase, o.forcephase, o.rephase,
           o.target, o.seed, policy_path.c_str ());
  for (int i = 0; i < NUM_CHECKPOINTS; i++)
    fprintf (log, "%s%" PRId64, i ? "," : "", CHECKPOINTS[i]);
  fputs ("],\"features\":[", log);
  for (int i = 0; i < NUM_FEATURES; i++)
    fprintf (log, "%s\"%s\"", i ? "," : "", feature_names[i]);
  fputs ("]}\n", log);
  fflush (log);
}

/*------------------------------------------------------------------------*/

void Controller::take (Snapshot &s) const {
  const Stats &st = internal->stats;
  s.time = internal->process_time ();
  s.conflicts = st.conflicts;
  s.decisions = st.decisions;
  s.propagations = st.propagations.search;
  s.ticks = st.ticks.search[0] + st.ticks.search[1];
  s.restarts = st.restarts;
  s.reused = st.reused;
  s.rephased = st.rephased.total;
  s.stabconflicts = st.stabconflicts;
  s.chrono = st.chrono;
  s.units = st.units;
  s.binaries = st.binaries;
  s.learned = st.learned.clauses;
  s.learned_lits = st.learned.literals;
  s.c = internal->fpcc;
}

void Controller::compute_features (const Snapshot &now,
                                   const Snapshot &ref) {
  double *f = features.data ();
  for (int i = 0; i < NUM_FEATURES; i++)
    f[i] = NaN;
  Internal *I = internal;
  const Counters &c = now.c;

  // static features of the original formula
  const double vars = (double) I->max_var;
  f[F_s_log_vars] = std::log10 (1.0 + (double) c.orig_max_var);
  f[F_s_log_clauses] = std::log10 (1.0 + (double) c.orig_clauses);
  f[F_s_cv_ratio] = ratio (c.orig_clauses, c.orig_max_var);
  f[F_s_mean_len] = ratio (c.orig_lits, c.orig_clauses);
  f[F_s_unit_frac] = ratio (c.orig_unit, c.orig_clauses);
  f[F_s_bin_frac] = ratio (c.orig_bin, c.orig_clauses);
  f[F_s_ter_frac] = ratio (c.orig_ter, c.orig_clauses);
  f[F_s_pos_frac] = ratio (c.orig_pos, c.orig_lits);
  f[F_s_horn_frac] = ratio (c.orig_horn, c.orig_clauses);
  f[F_s_antihorn_frac] = ratio (c.orig_antihorn, c.orig_clauses);

  // progress and native mechanism
  f[F_r_log_conflicts] = std::log10 (1.0 + (double) now.conflicts);
  f[F_r_time] = now.time;
  f[F_r_stable] = I->stable;
  f[F_r_rephase_due] =
      (double) I->lim.rephase -
      (double) (I->opts.rephase == 2 ? now.stabconflicts : now.conflicts);
  // effective action in every mode (telemetry: the command line pair)
  if (I->fpc_sign)
    f[F_r_action] = I->fpc_sign < 0 ? NEGATIVE : POSITIVE;
  else {
    const int force = I->eff_forcephase (), phase = I->eff_phase ();
    f[F_r_action] = force ? (phase ? POSITIVE : NEGATIVE)
                          : (phase ? NATIVE : NATIVE_INIT_NEG);
  }
  f[F_r_switches] = (double) switches;

  // ratio features over [base, now] for base in {zero, ref}
  for (int k = 0; k < 2; k++) {
    const Snapshot &b = k ? ref : zero;
    const int o = k ? (F_w_dec_per_conf - F_c_dec_per_conf) : 0;
    const double dconf = now.conflicts - b.conflicts;
    const double ddec = now.decisions - b.decisions;
    const double dfree = now.c.dec_free - b.c.dec_free;
    const double dlearned = now.learned - b.learned;
    const double danal = now.c.analyzed - b.c.analyzed;
    const double drest = now.restarts - b.restarts;
    f[F_c_dec_per_conf + o] = ratio (ddec, dconf);
    f[F_c_props_per_dec + o] =
        ratio (now.propagations - b.propagations, ddec);
    f[F_c_ticks_per_conf + o] = ratio (now.ticks - b.ticks, dconf);
    f[F_c_conf_per_sec + o] = ratio (dconf, now.time - b.time);
    f[F_c_glue_mean + o] = ratio (c.glue_sum - b.c.glue_sum, dlearned);
    f[F_c_glue_low_frac + o] = ratio (c.glue_low - b.c.glue_low, dlearned);
    f[F_c_size_mean + o] =
        ratio (now.learned_lits - b.learned_lits, dlearned);
    f[F_c_minsize_mean + o] =
        ratio (c.minsize_sum - b.c.minsize_sum, danal);
    f[F_c_backjump_mean + o] =
        ratio (c.backjump_sum - b.c.backjump_sum, danal);
    f[F_c_chrono_frac + o] = ratio (now.chrono - b.chrono, dconf);
    f[F_c_restarts_per_kconf + o] = ratio (1000.0 * drest, dconf);
    f[F_c_reuse_frac + o] = ratio (now.reused - b.reused, drest);
    f[F_c_neg_dec_frac + o] = ratio (c.dec_neg - b.c.dec_neg, dfree);
    f[F_c_native_pos_frac + o] =
        ratio (c.dec_native_pos - b.c.dec_native_pos, dfree);
    f[F_c_target_src_frac + o] =
        ratio (c.dec_src[SRC_TARGET] - b.c.dec_src[SRC_TARGET], dfree);
    f[F_c_saved_src_frac + o] =
        ratio (c.dec_src[SRC_SAVED] - b.c.dec_src[SRC_SAVED], dfree);
    f[F_c_units_per_kconf + o] =
        ratio (1000.0 * (now.units - b.units), dconf);
    f[F_c_bin_per_kconf + o] =
        ratio (1000.0 * (now.binaries - b.binaries), dconf);
    f[F_c_stable_frac + o] =
        ratio (now.stabconflicts - b.stabconflicts, dconf);
    f[F_c_rephases + o] = (double) (now.rephased - b.rephased);
  }

  // current state
  const double active = I->active ();
  const auto &av = I->averages.current;
  f[F_x_glue_fast] = (double) av.glue.fast;
  f[F_x_glue_slow] = (double) av.glue.slow;
  f[F_x_glue_ratio] = ratio (av.glue.fast, av.glue.slow);
  f[F_x_trail_frac] = ratio (av.trail.slow, active);
  f[F_x_trail_ratio] = ratio (av.trail.fast, av.trail.slow);
  f[F_x_jump_avg] = (double) av.jump;
  f[F_x_level_avg] = (double) av.level;
  f[F_x_size_avg] = (double) av.size;
  f[F_x_best_frac] = ratio (I->best_assigned, active);
  f[F_x_target_frac] = ratio (I->target_assigned, active);
  f[F_x_active_frac] = ratio (active, vars);
  f[F_x_irr_per_var] = ratio (I->stats.current.irredundant, active);
  f[F_x_red_per_irr] =
      ratio (I->stats.current.redundant, I->stats.current.irredundant);

  // saved / target phases of a fixed random sample of variables
  if (sample.empty () && I->max_var > 0) {
    const int n = I->max_var;
    if (n <= SAMPLE_SIZE)
      for (int idx = 1; idx <= n; idx++)
        sample.push_back (idx);
    else
      for (int j = 0; j < SAMPLE_SIZE; j++)
        sample.push_back (1 + (int) (next_random () % (uint64_t) n));
    sample_saved.assign (sample.size (), 0);
  }
  int64_t act = 0, neg = 0, flip = 0, prev = 0, tset = 0, tneg = 0;
  for (size_t j = 0; j < sample.size (); j++) {
    const int idx = sample[j];
    if (idx > I->max_var || !I->flags (idx).active ())
      continue;
    const signed char s = I->phases.saved[idx];
    const signed char t = I->phases.target[idx];
    act++;
    neg += (s < 0);
    tset += (t != 0);
    tneg += (t < 0);
    if (sample_saved[j]) {
      prev++;
      flip += (sample_saved[j] != s);
    }
    sample_saved[j] = s;
  }
  f[F_x_saved_neg_frac] = ratio (neg, act);
  f[F_x_saved_flip_frac] = ratio (flip, prev);
  f[F_x_target_set_frac] = ratio (tset, act);
  f[F_x_target_neg_frac] = ratio (tneg, tset);
}

void Controller::write_features () {
  fputs (",\"f\":{", log);
  for (int i = 0; i < NUM_FEATURES; i++) {
    const double x = features[i];
    if (std::isnan (x) || std::isinf (x))
      fprintf (log, "%s\"%s\":null", i ? "," : "", feature_names[i]);
    else
      fprintf (log, "%s\"%s\":%.6g", i ? "," : "", feature_names[i], x);
  }
  fputc ('}', log);
}

/*------------------------------------------------------------------------*/

// FNV-1a digest of search state used to verify identical prefixes in
// deterministic replays.  O(variables + trail), only computed at
// checkpoints, switches and at the end.

uint64_t Controller::digest () const {
  uint64_t h = 1469598103934665603ull;
  auto mix = [&h] (uint64_t x) {
    for (int i = 0; i < 8; i++) {
      h ^= (x >> (8 * i)) & 0xff;
      h *= 1099511628211ull;
    }
  };
  const Internal *I = internal;
  mix (I->stats.conflicts);
  mix (I->stats.decisions);
  mix (I->stats.propagations.search);
  mix (I->stats.restarts);
  mix (I->stats.rephased.total);
  mix (I->stats.current.irredundant);
  mix (I->stats.current.redundant);
  mix (I->stable);
  mix (I->level);
  mix (I->lim.rephase);
  mix (I->num_assigned);
  mix (I->trail.size ());
  for (const int lit : I->trail)
    mix ((uint64_t) (int64_t) lit);
  for (int idx = 1; idx <= I->max_var; idx++) {
    mix ((uint64_t) (int64_t) I->phases.saved[idx]);
    mix ((uint64_t) (int64_t) I->phases.target[idx]);
  }
  return h;
}

/*------------------------------------------------------------------------*/

void Controller::account () {
  const Stats &st = internal->stats;
  const double t = internal->process_time ();
  occ_conflicts[cur] += st.conflicts - occ_since_conflicts;
  occ_decisions[cur] += st.decisions - occ_since_decisions;
  occ_time[cur] += t - occ_since_time;
  occ_since_conflicts = st.conflicts;
  occ_since_decisions = st.decisions;
  occ_since_time = t;
}

void Controller::apply (int slot, const char *reason, int64_t requested) {
  Internal *I = internal;
  const bool initial = !strcmp (reason, "init");
  if (!initial)
    account ();
  const int old_force = I->fpc_pair ? I->fpc_force : I->opts.forcephase;
  const int action = a[slot];
  if (track == 0) {
    I->fpc_pair = true;
    I->fpc_force = pair_force (action);
    I->fpc_phase = pair_phase (action);
    I->fpc_sign = 0;
  } else {
    I->fpc_pair = false;
    I->fpc_sign = action == NEGATIVE ? -1 : action == POSITIVE ? 1 : 0;
  }
  int64_t postponed = -1;
  if (!initial && I->opts.fpcrlim && track == 0 && old_force &&
      !I->fpc_force) {
    // Optional ablation: do not let the rephase limit, which stood still
    // while forcing, fire immediately after returning to native.
    const int64_t base = I->opts.rephase == 2 ? I->stats.stabconflicts
                                              : I->stats.conflicts;
    if (I->lim.rephase < base) {
      postponed = I->lim.rephase;
      I->lim.rephase =
          base + I->opts.rephaseint * (I->stats.rephased.total + 1);
    }
  }
  if (!initial) {
    switches++;
    dwell = 0;
  }
  cur = slot;
  applied_at_conflicts = I->stats.conflicts;
  if (log) {
    fprintf (log,
             "{\"type\":\"%s\",\"reason\":\"%s\",\"action\":\"%s\","
             "\"slot\":%d,\"requested\":%" PRId64 ",\"conflicts\":%" PRId64
             ",\"decisions\":%" PRId64 ",\"time\":%.6f,\"stable\":%d,"
             "\"level\":%d,\"switches\":%" PRId64 ",\"rephase_lim\":%" PRId64
             ",\"rephase_postponed_from\":%" PRId64,
             initial ? "init" : "switch", reason, action_name (action), slot,
             requested, I->stats.conflicts, I->stats.decisions,
             I->process_time (), (int) I->stable, I->level, switches,
             I->lim.rephase, postponed);
    if (!initial && switches <= 32)
      fprintf (log, ",\"digest\":\"%016" PRIx64 "\"", digest ());
    fputs ("}\n", log);
    fflush (log);
  }
}

/*------------------------------------------------------------------------*/

void Controller::at_restart () {
  Internal *I = internal;
  const int64_t conflicts = I->stats.conflicts;
  const bool cp = checkpoint_index < NUM_CHECKPOINTS &&
                  conflicts >= CHECKPOINTS[checkpoint_index];
  const bool wc = conflicts >= next_window;
  const bool sw = conflicts >= next_switch && switches < maxsw;
  if (!cp && !wc && !sw)
    return;
  const double start = absolute_process_time ();
  hook_calls++;
  Snapshot now;
  take (now);

  if (cp) {
    const int first = checkpoint_index;
    while (checkpoint_index < NUM_CHECKPOINTS &&
           conflicts >= CHECKPOINTS[checkpoint_index])
      checkpoint_index++;
    compute_features (now, last_checkpoint);
    if (log) {
      fprintf (log,
               "{\"type\":\"checkpoint\",\"crossed\":[%" PRId64 ",%" PRId64
               "],\"conflicts\":%" PRId64 ",\"decisions\":%" PRId64
               ",\"time\":%.6f,\"digest\":\"%016" PRIx64 "\"",
               CHECKPOINTS[first], CHECKPOINTS[checkpoint_index - 1],
               conflicts, now.decisions, now.time, digest ());
      write_features ();
      fputs ("}\n", log);
    }
    if (mode == POLICY && !policy.repeat && !decided &&
        conflicts >= policy.prefix) {
      decided = true;
      const double score = policy.model.eval (features.data ());
      const int slot = score > policy.threshold ? 1 : 0;
      if (log)
        fprintf (log,
                 "{\"type\":\"decision\",\"score\":%.6g,\"slot\":%d,"
                 "\"action\":\"%s\",\"prefix\":%" PRId64
                 ",\"conflicts\":%" PRId64 "}\n",
                 score, slot, action_name (a[slot]), policy.prefix,
                 conflicts);
      if (slot != cur)
        apply (slot, "oneshot", policy.prefix);
    }
    last_checkpoint = now;
  }

  if (wc) {
    compute_features (now, last_window);
    double score = NaN;
    int want = cur;
    if (mode == POLICY && policy.repeat) {
      score = policy.model.eval (features.data ());
      if (cur == 0 && score > policy.enter)
        want = 1;
      else if (cur == 1 && score < policy.exit)
        want = 0;
    } else if (mode == RANDOM) {
      if (random_double () * 1000.0 < I->opts.fpcprob)
        want = 1 - cur;
    }
    if (log) {
      fprintf (log,
               "{\"type\":\"window\",\"index\":%" PRId64
               ",\"conflicts\":%" PRId64 ",\"decisions\":%" PRId64
               ",\"time\":%.6f,\"action\":\"%s\",\"dwell\":%" PRId64,
               window_index, conflicts, now.decisions, now.time,
               mode == TELEMETRY ? "CLI" : action_name (a[cur]), dwell);
      if (!std::isnan (score))
        fprintf (log, ",\"score\":%.6g", score);
      write_features ();
      fputs ("}\n", log);
    }
    last_window = now;
    next_window = conflicts + win;
    window_index++;
    dwell++;
    if (want != cur && dwell >= mindwell && switches < maxsw)
      apply (want, mode == RANDOM ? "random" : "repeat", conflicts);
  }

  if (sw && mode == SCHEDULE) {
    const int64_t requested = next_switch;
    next_switch = I->opts.fpcperiod
                      ? conflicts + I->opts.fpcperiod
                      : std::numeric_limits<int64_t>::max ();
    apply (1 - cur, "schedule", requested);
  } else if (sw)
    next_switch = std::numeric_limits<int64_t>::max ();

  if (log)
    fflush (log);
  hook_time += absolute_process_time () - start;
}

void Controller::finish (int res) {
  if (mode != TELEMETRY)
    account ();
  else {
    const Stats &st = internal->stats;
    occ_conflicts[0] = st.conflicts;
    occ_decisions[0] = st.decisions;
    occ_time[0] = internal->process_time ();
  }
  if (!log)
    return;
  const Stats &st = internal->stats;
  const Counters &c = internal->fpcc;
  fprintf (log,
           "{\"type\":\"final\",\"result\":%d,\"conflicts\":%" PRId64
           ",\"decisions\":%" PRId64 ",\"propagations\":%" PRId64
           ",\"restarts\":%" PRId64 ",\"rephased\":%" PRId64
           ",\"stabphases\":%" PRId64 ",\"time\":%.6f,\"switches\":%" PRId64
           ",\"action\":\"%s\",\"applied_at\":%" PRId64
           ",\"occ_conflicts\":[%" PRId64 ",%" PRId64
           "],\"occ_decisions\":[%" PRId64 ",%" PRId64
           "],\"occ_time\":[%.6f,%.6f],\"hook_time\":%.6f,"
           "\"hook_calls\":%" PRId64 ",\"dec_free\":%" PRId64
           ",\"dec_neg\":%" PRId64 ",\"dec_native_pos\":%" PRId64
           ",\"dec_p_override\":%" PRId64 ",\"dec_p_flip\":%" PRId64
           ",\"dec_src\":[",
           res, st.conflicts, st.decisions, st.propagations.search,
           st.restarts, st.rephased.total, st.stabphases,
           internal->process_time (), switches,
           mode == TELEMETRY ? "CLI" : action_name (a[cur]),
           applied_at_conflicts, occ_conflicts[0], occ_conflicts[1],
           occ_decisions[0], occ_decisions[1], occ_time[0], occ_time[1],
           hook_time, hook_calls, c.dec_free, c.dec_neg, c.dec_native_pos,
           c.dec_p_override, c.dec_p_flip);
  for (int i = 0; i < NUM_SOURCES; i++)
    fprintf (log, "%s%" PRId64, i ? "," : "", c.dec_src[i]);
  fprintf (log, "],\"digest\":\"%016" PRIx64 "\"}\n", digest ());
  fflush (log);
}

} // namespace FPC
} // namespace CaDiCaL
