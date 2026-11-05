// ta100-observer-v1: passive bounded observations, no policy or RNG writes.
#include "internal.hpp"
#include "ta100_observer.hpp"
#include <array>
#include <functional>
#include <limits>
#include <map>
#include <set>
#include <unordered_map>
#include <unordered_set>

namespace CaDiCaL {
namespace TA100 {
namespace {
const size_t K = 256, Q = 8, LIT_CAP = 256, EDGE_CAP = 10000;
const double missing = std::numeric_limits<double>::quiet_NaN ();
uint64_t mix (uint64_t x) {
  x += 0x9e3779b97f4a7c15ULL;
  x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
  x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
  return x ^ (x >> 31);
}
double ratio (double a, double b) { return b > 0 ? a / b : missing; }
double median (std::vector<double> values) {
  if (values.empty ()) return missing;
  std::sort (values.begin (), values.end ());
  size_t n = values.size ();
  return n & 1 ? values[n / 2] : (values[n / 2 - 1] + values[n / 2]) / 2;
}
void bottom_insert (std::set<uint64_t> &values, uint64_t value) {
  values.insert (value);
  if (values.size () > K) values.erase (--values.end ());
}
double jaccard (const std::set<uint64_t> &a, const std::set<uint64_t> &b) {
  if (a.empty () || b.empty ()) return missing;
  uint64_t cap = std::min (a.size () == K ? *a.rbegin () : UINT64_MAX,
                           b.size () == K ? *b.rbegin () : UINT64_MAX);
  size_t inter = 0, uni = 0;
  std::set<uint64_t> united = a;
  united.insert (b.begin (), b.end ());
  for (auto value : united) if (value <= cap) {
    uni++;
    inter += a.count (value) && b.count (value);
  }
  return ratio (inter, uni);
}
int bucket (int value, const int *bounds) {
  int b = 0;
  while (b < 8 && value > bounds[b]) b++;
  return b;
}
}

struct Observer::State {
  Internal *I;
  bool stopped = false, pending_chrono = false, chrono_backtrack = false;
  struct Variable {
    int external = 0, sign = 0, chrono_sign = 0, pre_restart = 0;
    int64_t born = 0, bumps = 0;
    bool born_here = false, pending_redecision = false;
  };
  std::array<Variable, K> sample;
  std::unordered_map<int, size_t> slot;
  size_t sample_size = 0;
  int64_t positive_lifetimes = 0, negative_lifetimes = 0;
  double positive_lifetime_sum = 0, negative_lifetime_sum = 0;
  int64_t chrono_matches = 0, chrono_flips = 0;
  int64_t pre_pos = 0, pre_neg = 0, keep_pos = 0, keep_neg = 0;
  int64_t watch_examined = 0, watch_skips = 0;
  int64_t learned_n = 0, pure_pos = 0, pure_neg = 0, phase_evaluable = 0, phase_violated = 0;
  int64_t saved_evaluable = 0, saved_violated = 0;
  double compression_sum = 0, localization_sum = 0, entropy_sum = 0, depth_sum = 0;
  int64_t compression_n = 0, localization_n = 0, entropy_n = 0, depth_n = 0;
  bool entropy_capped = false, depth_saturated = false, external_variable_seen = false;
  uint16_t reason_depth = 0, next_depth = 1;
  std::unordered_set<int64_t> reason_ids;
  bool reasons_capped = false, compression_capped = false;
  std::array<std::array<uint64_t, 9>, 9> joint = {};
  int64_t analyses = 0, last_free = 0, gap_n = 0;
  double gap_mean = 0, gap_m2 = 0;
  std::set<uint64_t> current_variables, recent_variables, previous_variables;
  struct Learned {
    bool valid = false, exact_literals = false;
    size_t n = 0;
    std::array<int, LIT_CAP> external_variables = {};
    std::array<uint64_t, Q> hashes = {};
  };
  std::array<Learned, K> clauses;
  size_t clauses_seen = 0;
  struct Reuse {
    uint64_t key = UINT64_MAX;
    int64_t id = 0, born = 0;
    bool assertion_skipped = false, first_observed = false, post_observed = false;
    double first_age = missing, post_age = missing;
  };
  std::array<Reuse, K> reuse;
  std::unordered_map<int64_t, size_t> reuse_slot;
  size_t reuse_n = 0;
  int64_t driving_assignment_id = 0;
  size_t graph_queries = 0, graph_edges = 0, graph_revisited = 0;
  bool graph_capped = false, graph_invalid = false;
  int64_t unique_ancestor = 0, same_ancestor_sign = 0, opposite_ancestor_sign = 0;
  std::vector<double> graph_depths;

  explicit State (Internal *internal) : I (internal) {
    // Stable external identities survive compaction. No solver RNG is used.
    std::priority_queue<std::pair<uint64_t, int>> selected;
    for (int idx : I->vars) {
      if (!I->flags (idx).active ()) continue;
      int external = std::abs (I->externalize (idx));
      if (!external) continue;
      auto pair = std::make_pair (mix ((uint64_t) external ^ 0x7461313030ULL), external);
      if (selected.size () < K) selected.push (pair);
      else if (pair < selected.top ()) { selected.pop (); selected.push (pair); }
    }
    while (!selected.empty ()) {
      int external = selected.top ().second; selected.pop ();
      if (slot.count (external)) continue;
      slot[external] = sample_size;
      sample[sample_size++].external = external;
    }
    // This graph begins at observer activation. Existing/inprocessing
    // boundary clauses have depth0; this is not an LRAT proof-height claim.
    for (Clause *c : I->clauses) c->ta100_depth = 0;
  }
  int internal_of (int external) const {
    if (external <= 0 || (size_t) external >= I->external->e2i.size ()) return 0;
    int idx = std::abs (I->external->e2i[external]);
    return idx <= I->max_var ? idx : 0;
  }
  Variable *variable (int lit) {
    int external = std::abs (I->externalize (lit));
    auto it = slot.find (external);
    return it == slot.end () ? nullptr : &sample[it->second];
  }
  int external_sign (int lit) const { return I->externalize (lit) < 0 ? -1 : 1; }
  int sampled_value (const Variable &v) const {
    int idx = internal_of (v.external);
    if (!idx || !I->flags (idx).active ()) return 0;
    int mapped = I->external->e2i[v.external];
    return I->val (mapped);
  }
  void query_graph () {
    if (graph_queries >= K || graph_capped || graph_invalid) return;
    int selected = 0; uint64_t best = UINT64_MAX;
    for (int lit : *I->conflict) {
      int idx = std::abs (lit);
      if (!I->var (idx).reason || !I->var (idx).level) continue;
      uint64_t key = mix ((uint64_t) idx ^ 0x726561736f6eULL);
      if (key < best) best = key, selected = idx;
    }
    if (!selected) return;
    graph_queries++;
    struct Node { int color = 0, depth = 0; };
    std::unordered_map<int, Node> nodes;
    std::set<int> decisions;
    std::function<int(int,int)> visit = [&] (int idx, int depth) -> int {
      if (depth > 256 || graph_edges >= EDGE_CAP) { graph_capped = true; return 0; }
      Node &node = nodes[idx];
      if (node.color == 1) { graph_invalid = true; return 0; }
      if (node.color == 2) return node.depth;
      node.color = 1;
      const Var &v = I->var (idx);
      Clause *reason = v.reason;
      int result = 0;
      if (!reason) { if (v.level) decisions.insert (idx); }
      else if (reason == I->external_reason) graph_invalid = true;
      else for (int other : *reason) {
        int parent = std::abs (other);
        if (parent == idx) continue;
        if (graph_edges == EDGE_CAP) { graph_capped = true; break; }
        graph_edges++;
        if (!I->val (parent)) { graph_invalid = true; break; }
        auto old = nodes.find (parent);
        if (old != nodes.end () && old->second.color == 2) graph_revisited++;
        result = std::max (result, 1 + visit (parent, depth + 1));
        if (graph_capped || graph_invalid) break;
      }
      // Recursive insertions may rehash nodes; reacquire the reference.
      nodes[idx].depth = result; nodes[idx].color = 2;
      return result;
    };
    int depth = visit (selected, 0);
    if (graph_capped || graph_invalid) return;
    graph_depths.push_back (depth);
    if (decisions.size () == 1) {
      int ancestor = *decisions.begin ();
      unique_ancestor++;
      bool same = (I->val (selected) < 0) == (I->val (ancestor) < 0);
      same_ancestor_sign += same; opposite_ancestor_sign += !same;
    }
  }
  void reuse_clause (Clause *reason, bool driving = false) {
    if (!reason || reason == I->external_reason) return;
    if (driving_assignment_id == reason->id) return;
    auto found = reuse_slot.find (reason->id);
    if (found != reuse_slot.end ()) {
      Reuse &r = reuse[found->second];
      double age = (double) (I->stats.conflicts - r.born);
      if (!r.first_observed) r.first_age = age, r.first_observed = true;
      if (driving && !r.assertion_skipped && age == 0) r.assertion_skipped = true;
      else if (r.assertion_skipped && !r.post_observed) r.post_age = age, r.post_observed = true;
      return;
    }
  }
  double rank_enrichment () {
    if (!clauses_seen) return missing;
    size_t count = std::min (clauses_seen, K);
    for (size_t n = 0; n < count; n++) if (!clauses[n].exact_literals) return missing;
    std::vector<int> active;
    for (int idx : I->vars) if (I->flags (idx).active ()) active.push_back (idx);
    if (active.empty ()) return missing;
    const bool scores = I->use_scores ();
    auto better = [&] (int a, int b) {
      if (scores && I->score (a) != I->score (b)) return I->score (a) > I->score (b);
      if (!scores && I->bumped (a) != I->bumped (b)) return I->bumped (a) > I->bumped (b);
      return std::abs (I->externalize (a)) < std::abs (I->externalize (b));
    };
    size_t top = std::max ((size_t) 1, (active.size () + 9) / 10);
    std::nth_element (active.begin (), active.begin () + top - 1, active.end (), better);
    int boundary = active[top - 1];
    double hits = 0, total = 0;
    for (size_t n = 0; n < count; n++) for (size_t j = 0; j < clauses[n].n; j++) {
      int idx = internal_of (clauses[n].external_variables[j]);
      if (!idx || !I->flags (idx).active ()) return missing;
      hits += idx == boundary || better (idx, boundary); total++;
    }
    return total ? hits / total - 0.1 : missing;
  }
  double recurrence () const {
    if (clauses_seen < K) return missing;
    double sum = 0;
    for (size_t i = 0; i < 128; i++) {
      const Learned &recent = clauses[(clauses_seen - 128 + i) % K];
      if (!recent.valid) return missing;
      double best = 0;
      for (size_t j = 0; j < 128; j++) {
        const Learned &previous = clauses[(clauses_seen - K + j) % K];
        if (!previous.valid) return missing;
        size_t equal = 0;
        for (size_t q = 0; q < Q; q++) equal += recent.hashes[q] == previous.hashes[q];
        best = std::max (best, (double) equal / Q);
      }
      sum += best;
    }
    return sum / 128;
  }
  double dependence () const {
    double x[9] = {}, y[9] = {}, total = 0;
    for (int i = 0; i < 9; i++) for (int j = 0; j < 9; j++) {
      double n = joint[i][j]; x[i] += n; y[j] += n; total += n;
    }
    if (!total) return missing;
    double rx[9], ry[9], sx = 0, sy = 0;
    for (int i = 0; i < 9; i++) {
      rx[i] = (sx + .5 * x[i]) / total; sx += x[i];
      ry[i] = (sy + .5 * y[i]) / total; sy += y[i];
    }
    double cov = 0, vx = 0, vy = 0;
    for (int i = 0; i < 9; i++) for (int j = 0; j < 9; j++) {
      double n = joint[i][j], a = rx[i] - .5, b = ry[j] - .5;
      cov += n * a * b; vx += n * a * a; vy += n * b * b;
    }
    return vx > 0 && vy > 0 ? cov / std::sqrt (vx * vy) : missing;
  }
};

Observer::Observer (Internal *I) : state (new State (I)) {}
Observer::~Observer () { delete state; }
bool Observer::selftest () {
  if (std::isfinite (ratio (1, 0)) || std::isfinite (median ({}))) return false;
  if (median ({1, 9, 3}) != 3 || median ({1, 3}) != 2) return false;
  std::set<uint64_t> a = {1,2,3}, b = {2,3,4};
  if (std::abs (jaccard (a,b) - .5) > 1e-12) return false;
  if (jaccard (a,a) != 1 || std::isfinite (jaccard ({},a))) return false;
  std::set<uint64_t> bounded;
  for (uint64_t i=1000;i;i--) bottom_insert (bounded,i);
  if (bounded.size()!=K || *bounded.begin()!=1 || *bounded.rbegin()!=K) return false;
  const int bounds[8]={1,2,3,4,8,16,32,64};
  if (bucket(1,bounds)!=0 || bucket(5,bounds)!=4 || bucket(65,bounds)!=8) return false;
  return mix(123)==mix(123) && mix(123)!=mix(124);
}
void Observer::begin_analysis () {
  State &s = *state; if (s.stopped) return;
  if (s.analyses && s.analyses % 128 == 0) {
    s.previous_variables.swap (s.recent_variables);
    s.recent_variables.swap (s.current_variables); s.current_variables.clear ();
  }
  s.analyses++; s.reason_ids.clear (); s.reasons_capped = false; s.reason_depth = 0;
  int64_t now = s.I->fpcc.dec_free, gap = now - s.last_free; s.last_free = now;
  if (s.analyses > 1) {
    double delta = gap - s.gap_mean; s.gap_n++;
    s.gap_mean += delta / s.gap_n; s.gap_m2 += delta * (gap - s.gap_mean);
  }
  s.query_graph ();
}
void Observer::dependency (Clause *c) {
  State &s = *state; if (s.stopped || !c || c == s.I->external_reason) return;
  s.reason_depth = std::max (s.reason_depth, c->ta100_depth);
}
void Observer::analyze_reason (Clause *c) {
  State &s = *state; if (s.stopped || !c || c == s.I->external_reason) return;
  dependency (c);
  if (s.reason_ids.size () < EDGE_CAP || s.reason_ids.count (c->id)) s.reason_ids.insert (c->id);
  else s.reasons_capped = s.compression_capped = true;
}
void Observer::analyzed_literal (int lit) {
  State &s = *state; if (s.stopped) return;
  int external = std::abs (s.I->externalize (lit));
  if (!external) s.external_variable_seen = true;
  else bottom_insert (s.current_variables, mix ((uint64_t) external ^ 0x7475726eULL));
}
void Observer::learned (int glue, int uip) {
  State &s = *state; if (s.stopped || s.I->clause.empty ()) return;
  Internal *I = s.I;
  size_t size = I->clause.size (); int positives = 0, satisfied = 0, saved_satisfied = 0;
  bool evaluable = true, saved_evaluable = true;
  std::map<int, int> levels;
  State::Learned &record = s.clauses[s.clauses_seen % K];
  record = State::Learned (); record.valid = true; record.exact_literals = size <= LIT_CAP;
  record.hashes.fill (UINT64_MAX); record.n = std::min (size, LIT_CAP);
  for (size_t j = 0; j < size; j++) {
    int lit = I->clause[j], idx = std::abs (lit), saved = I->phases.saved[idx], target = I->phases.target[idx];
    positives += lit > 0;
    evaluable &= target != 0; satisfied += target && ((target < 0) == (lit < 0));
    saved_evaluable &= saved != 0; saved_satisfied += saved && ((saved < 0) == (lit < 0));
    if (levels.size () < K || levels.count (I->var (idx).level)) levels[I->var (idx).level]++;
    else s.entropy_capped = true;
    int external = I->externalize (lit);
    if (!external) record.valid = record.exact_literals = false;
    if (j < LIT_CAP) record.external_variables[j] = std::abs (external);
    for (size_t q = 0; q < Q; q++) record.hashes[q] = std::min (record.hashes[q], mix ((uint64_t) (int64_t) external ^ mix (q + 73)));
  }
  s.clauses_seen++; s.learned_n++; s.pure_pos += positives == (int) size; s.pure_neg += positives == 0;
  s.phase_evaluable += evaluable; s.phase_violated += evaluable && !satisfied;
  s.saved_evaluable += saved_evaluable; s.saved_violated += saved_evaluable && !saved_satisfied;
  if (!s.reasons_capped) { s.compression_sum += ratio (s.reason_ids.size (), size); s.compression_n++; }
  if (uip && I->level > 0) {
    size_t begin = I->control[I->level].trail, end = I->trail.size (); int at = I->var (uip).trail;
    if (at >= (int) begin && at < (int) end && end > begin) {
      s.localization_sum += (double) (end - at) / (end - begin); s.localization_n++;
    }
  }
  if (!s.entropy_capped) {
    double h = 0;
    if (levels.size () > 1) for (auto item : levels) {
      double p = (double) item.second / size; h -= p * std::log (p) / std::log ((double) levels.size ());
    }
    s.entropy_sum += h; s.entropy_n++;
  }
  const int sb[8] = {1,2,3,4,8,16,32,64}, gb[8] = {1,2,3,4,6,8,16,32};
  s.joint[bucket ((int) size, sb)][bucket (glue, gb)]++;
  if (s.reason_depth >= UINT16_MAX - 1) s.next_depth = UINT16_MAX, s.depth_saturated = true;
  else s.next_depth = s.reason_depth + 1;
  s.depth_sum += std::log1p ((double) s.next_depth); s.depth_n++;
}
void Observer::driving (Clause *c) {
  State &s = *state; if (s.stopped || !c) return;
  c->ta100_depth = s.next_depth;
  uint64_t key = mix ((uint64_t) c->id ^ 0x7265757365ULL);
  size_t slot = s.reuse_n;
  if (slot == K) {
    slot = 0;
    for (size_t i = 1; i < K; i++) if (s.reuse[i].key > s.reuse[slot].key) slot = i;
    if (key >= s.reuse[slot].key) return;
  } else s.reuse_n++;
  if (s.reuse[slot].id) s.reuse_slot.erase (s.reuse[slot].id);
  s.reuse[slot] = State::Reuse (); s.reuse[slot].key = key;
  s.reuse[slot].id = c->id; s.reuse[slot].born = s.I->stats.conflicts;
  s.reuse_slot[c->id] = slot;
}
void Observer::assigned (int lit, Clause *reason) {
  State &s = *state; if (s.stopped) return;
  s.reuse_clause (reason);
  auto *v = s.variable (lit); if (!v) return;
  v->born = s.I->stats.conflicts; v->born_here = true; v->sign = s.external_sign (lit);
}
void Observer::before_driving_assignment (Clause *c) {
  if (!state->stopped) state->driving_assignment_id = c ? c->id : 0;
}
void Observer::after_driving_assignment (Clause *c) {
  if (state->stopped) return;
  state->driving_assignment_id = 0;
  // Capture the raw driving clause even when search_assign canonicalizes
  // its root-level reason to null. Do not double-count the nested assign.
  state->reuse_clause (c, true);
}
void Observer::unassigned (int lit) {
  State &s = *state; if (s.stopped) return;
  auto *v = s.variable (lit); if (!v) return;
  if (v->born_here) {
    double lifetime = s.I->stats.conflicts - v->born;
    if (v->sign < 0) s.negative_lifetime_sum += lifetime, s.negative_lifetimes++;
    else s.positive_lifetime_sum += lifetime, s.positive_lifetimes++;
  }
  v->born_here = false;
  if (s.chrono_backtrack) v->chrono_sign = s.external_sign (lit), v->pending_redecision = true;
}
void Observer::free_decision (int lit) {
  State &s = *state; if (s.stopped) return;
  auto *v = s.variable (lit); if (!v || !v->pending_redecision) return;
  s.chrono_matches++; s.chrono_flips += v->chrono_sign != s.external_sign (lit);
  v->pending_redecision = false;
}
void Observer::bumped (int lit) {
  State &s = *state; if (s.stopped) return;
  auto *v = s.variable (lit); if (v) v->bumps++;
}
void Observer::watch (bool satisfied) {
  State &s = *state; if (s.stopped) return;
  s.watch_examined++; s.watch_skips += satisfied;
}
void Observer::set_chrono (bool value) { if (!state->stopped) state->pending_chrono = value; }
void Observer::begin_backtrack () {
  state->chrono_backtrack = state->pending_chrono; state->pending_chrono = false;
}
void Observer::end_backtrack () { state->chrono_backtrack = false; }
void Observer::before_restart () {
  State &s = *state; if (s.stopped) return;
  for (size_t i = 0; i < s.sample_size; i++) s.sample[i].pre_restart = s.sampled_value (s.sample[i]);
}
void Observer::after_restart () {
  State &s = *state; if (s.stopped) return;
  for (size_t i = 0; i < s.sample_size; i++) {
    auto &v = s.sample[i]; int before = v.pre_restart;
    if (!before) continue;
    bool keep = before == s.sampled_value (v);
    if (before < 0) s.pre_neg++, s.keep_neg += keep;
    else s.pre_pos++, s.keep_pos += keep;
  }
}
void Observer::write (FILE *log) {
  State &s = *state;
  if (s.stopped) { fputs (",\"ta100\":null", log); return; }
  double sum = 0, squares = 0;
  for (size_t i = 0; i < s.sample_size; i++) { double n = s.sample[i].bumps; sum += n; squares += n*n; }
  std::vector<double> first_ages, post_ages;
  for (size_t i = 0; i < s.reuse_n; i++) {
    if (s.reuse[i].first_observed) first_ages.push_back (s.reuse[i].first_age);
    if (s.reuse[i].post_observed) post_ages.push_back (s.reuse[i].post_age);
  }
  bool graph_ok = !s.graph_capped && !s.graph_invalid;
  double turnover = s.external_variable_seen ? missing : 1 - jaccard (s.previous_variables, s.recent_variables);
  double values[20] = {
    ratio (s.pure_pos-s.pure_neg, s.learned_n),
    graph_ok ? ratio (s.same_ancestor_sign-s.opposite_ancestor_sign, s.unique_ancestor) : missing,
    ratio (s.negative_lifetime_sum,s.negative_lifetimes)-ratio(s.positive_lifetime_sum,s.positive_lifetimes),
    s.compression_capped ? missing : ratio(s.compression_sum,s.compression_n),
    graph_ok ? median(s.graph_depths) : missing,
    graph_ok ? ratio(s.graph_revisited,s.graph_edges) : missing,
    ratio(s.localization_sum,s.localization_n),
    s.entropy_capped ? missing : ratio(s.entropy_sum,s.entropy_n),
    ratio(s.phase_violated,s.phase_evaluable), turnover, ratio(squares,sum*sum),
    s.rank_enrichment(), s.recurrence(), median(post_ages), ratio(s.watch_skips,s.watch_examined),
    ratio(s.keep_neg,s.pre_neg)-ratio(s.keep_pos,s.pre_pos), ratio(s.chrono_flips,s.chrono_matches),
    s.gap_n>=32 && s.gap_mean>0 ? std::sqrt(std::max(0.0,s.gap_m2/s.gap_n))/s.gap_mean : missing,
    s.dependence(), s.depth_saturated ? missing : ratio(s.depth_sum,s.depth_n)
  };
  const char *names[20] = {"td_learned_pure_sign_balance","td_reason_sign_transmission","td_sign_lifetime_gap",
    "td_resolution_compression","td_reason_depth","td_reason_reconvergence","td_uip_trail_localization",
    "td_cut_level_entropy","td_clause_target_phase_violation","td_conflict_variable_turnover","td_bump_concentration",
    "td_activity_rank_enrichment","td_learned_recurrence","td_learned_postassertion_reuse_age",
    "td_blocker_success_share","td_restart_signed_retention","td_chrono_redecision_flip","td_conflict_burstiness",
    "td_glue_size_dependence","td_lemma_dependency_depth"};
  fputs (",\"ta100\":{\"observer\":\"ta100-observer-v1\",\"features\":{", log);
  for (int i=0;i<20;i++) {
    fprintf(log,"%s\"%s\":",i?",":"",names[i]);
    if (std::isfinite(values[i])) fprintf(log,"%.12g",values[i]); else fputs("null",log);
  }
  fprintf(log,"},\"support\":{\"learned\":%lld,\"reason_queries\":%zu,\"reason_edges\":%zu,"
    "\"unique_ancestor\":%lld,\"sample_variables\":%zu,\"positive_lifetimes\":%lld,\"negative_lifetimes\":%lld,"
    "\"postassertion_reused\":%zu,\"chrono_matches\":%lld,\"gap_n\":%lld,\"target_evaluable\":%lld},"
    "\"caps\":{\"reason_cap\":%s,\"reason_invalid\":%s,\"level_hist_cap\":%s,\"depth_saturated\":%s},"
    "\"diagnostic_first_use_age\":", (long long)s.learned_n,s.graph_queries,s.graph_edges,(long long)s.unique_ancestor,
    s.sample_size,(long long)s.positive_lifetimes,(long long)s.negative_lifetimes,post_ages.size(),
    (long long)s.chrono_matches,(long long)s.gap_n,(long long)s.phase_evaluable,s.graph_capped?"true":"false",s.graph_invalid?"true":"false",
    s.entropy_capped?"true":"false",s.depth_saturated?"true":"false");
  double first = median(first_ages);
  if (std::isfinite(first)) fprintf(log,"%.12g",first); else fputs("null",log);
  fputs(",\"diagnostic_saved_violation\":",log);
  double saved_violation = ratio(s.saved_violated,s.saved_evaluable);
  if (std::isfinite(saved_violation)) fprintf(log,"%.12g",saved_violation); else fputs("null",log);
  fputs("}",log);
  s.stopped = true;
}

} // namespace TA100
} // namespace CaDiCaL
