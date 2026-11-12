// R51 reuses TA I031/I032 helper definitions on the current three-action population.
#include "../ta100/graph_extra_features.hpp"
#include <sys/resource.h>
#include <unistd.h>

using namespace ta100_graph;

static void guard(const Budget &budget) {
  if (budget.done()) throw std::runtime_error("gate feature CPU budget");
  rusage usage;
  if (getrusage(RUSAGE_SELF, &usage)) throw std::runtime_error("getrusage failed");
#ifdef __APPLE__
  const uint64_t bytes = usage.ru_maxrss;
#else
  const uint64_t bytes = uint64_t(usage.ru_maxrss) * 1024;
#endif
  if (bytes > 512ULL * 1024 * 1024) throw std::runtime_error("gate feature512MiB RSS");
}

// This is the I032 reverse-CO recursion, factored for full and one-hop CC values.
static std::vector<double> observability(const ta100::CNF &f, const GateData &data,
                                         const CCData &cc, Budget &budget) {
  std::vector<double> co(f.n + 1, INFINITY);
  for (U v : cc.order) if (cc.consumers[v].empty()) co[v] = 0;
  for (U cid = 0; cid < f.clauses.size(); ++cid) {
    if (!f.tautological[cid] && !data.pool.count(f.clauses[cid]))
      for (auto l : f.clauses[cid]) co[std::abs(l)] = 0;
    if ((cid & 8191) == 0) guard(budget);
  }
  for (auto it = cc.order.rbegin(); it != cc.order.rend(); ++it) {
    const U v = *it;
    const auto &g = data.gates.at(v);
    if (!std::isfinite(co[v])) continue;
    const double a1 = g.a > 0 ? cc.one[std::abs(g.a)] : cc.zero[std::abs(g.a)];
    const double b1 = g.b > 0 ? cc.one[std::abs(g.b)] : cc.zero[std::abs(g.b)];
    co[std::abs(g.a)] = std::min(co[std::abs(g.a)], co[v] + b1 + 1);
    co[std::abs(g.b)] = std::min(co[std::abs(g.b)], co[v] + a1 + 1);
  }
  guard(budget);
  return co;
}

static std::vector<double> profile(const ta100::CNF &f, const CCData &cc,
                                    const std::vector<double> &co) {
  std::vector<double> out(16);
  double degree_sum = 0, finite_co = 0;
  for (U v : cc.order) {
    const double z = cc.zero[v], o = cc.one[v], sum = z + o, c = (o - z) / sum;
    const double degree = f.pos[v].size() + f.neg[v].size();
    const double bias = (double(f.pos[v].size()) - f.neg[v].size()) / std::max(degree, 1.);
    out[0] += c; out[1] += std::abs(c); out[2] += c * c;
    out[3] += std::log1p(sum); out[4] = std::max(out[4], std::log1p(sum));
    out[5] += degree * c; out[6] += degree * std::abs(c); degree_sum += degree;
    out[7] += c * bias; out[8] += std::abs(c * bias);
    if (std::isfinite(co[v])) {
      ++finite_co;
      const double normalized = co[v] / (co[v] + sum);
      out[10] += normalized; out[11] += normalized * c; out[12] += normalized * std::abs(c);
    }
    out[13] += c > 0; out[14] += c < 0;
    out[15] += std::log1p(o) - std::log1p(z);
  }
  const double count = std::max<size_t>(cc.order.size(), 1);
  for (U j : {0, 1, 2, 3, 7, 8, 13, 14, 15}) out[j] /= count;
  out[5] /= std::max(degree_sum, 1.); out[6] /= std::max(degree_sum, 1.);
  out[9] = finite_co / count;
  for (U j : {10, 11, 12}) out[j] /= std::max(finite_co, 1.);
  return out;
}

static void json_vector(const std::vector<double> &values) {
  std::cout << '[';
  for (size_t i = 0; i < values.size(); ++i) {
    if (!std::isfinite(values[i])) throw std::runtime_error("nonfinite gate statistic");
    if (i) std::cout << ',';
    std::cout << values[i];
  }
  std::cout << ']';
}

int main(int argc, char **argv) {
  rlimit core = {0, 0}, cpu = {4, 5};
  setrlimit(RLIMIT_CORE, &core);
  if (setrlimit(RLIMIT_CPU, &cpu)) return 70;
  alarm(7);
  try {
    if (argc != 2) throw std::runtime_error("expected one public CNF input");
    Budget budget(2.5);
    const auto f = ta100::read_cnf(argv[1]); guard(budget);
    const auto data = gates(f, budget);
    if (!data.complete) throw std::runtime_error("incomplete gate index");
    guard(budget);
    const auto full = controllability(f, data, budget); guard(budget);
    auto local = full;
    for (U v : local.order) {
      const bool positive = data.gates.at(v).z > 0;
      local.zero[v] = positive ? 2 : 3;
      local.one[v] = positive ? 3 : 2;
    }
    const auto full_co = observability(f, data, full, budget);
    const auto local_co = observability(f, data, local, budget);
    const auto full_profile = profile(f, full, full_co), local_profile = profile(f, local, local_co);
    Q primary = 0, output_mass = 0, fanout_mass = 0, sharing = 0;
    double log_fanout = 0, direction = 0;
    std::vector<U> fanout(f.n + 1);
    for (const auto &item : data.gates) if (!item.second.ambiguous) {
      const auto &g = item.second;
      ++fanout[std::abs(g.a)]; ++fanout[std::abs(g.b)];
      output_mass += f.pos[item.first].size() + f.neg[item.first].size();
      direction += g.z > 0 ? 1 : -1;
    }
    for (U v = 1; v <= f.n; ++v) {
      if (!data.gates.count(v) && (!f.pos[v].empty() || !f.neg[v].empty())) ++primary;
      if (fanout[v]) sharing += fanout[v] - 1;
      fanout_mass += fanout[v];
      log_fanout += std::log1p(fanout[v]);
    }
    const double gate_count = data.gates.size(), unique = gate_count - data.ambiguous;
    const std::vector<double> shared = {
      gate_count / std::max<double>(f.active_variables, 1),
      double(data.matches) / std::max<double>(f.raw_clauses, 1),
      double(data.ambiguous) / std::max(gate_count, 1.),
      double(full.order.size()) / std::max(gate_count, 1.),
      double(primary) / std::max<double>(f.active_variables, 1),
      double(sharing) / std::max<Q>(fanout_mass, 1),
      log_fanout / std::max<double>(f.active_variables, 1), direction / std::max(unique, 1.)};
    guard(budget);
    std::cout << std::setprecision(17) << "{\"schema\":\"forcephase.gate_cost.R51.v1\",\"shared8\":";
    json_vector(shared); std::cout << ",\"full16\":"; json_vector(full_profile);
    std::cout << ",\"local16\":"; json_vector(local_profile);
    std::cout << ",\"gate_variables\":" << gate_count << ",\"evaluable_outputs\":" << full.order.size()
      << ",\"ambiguous_gate_variables\":" << data.ambiguous << ",\"header_variables\":" << f.n
      << ",\"clauses\":" << f.raw_clauses << ",\"parse_CPU_s\":" << f.parse_cpu_s
      << ",\"SAT_calls\":0,\"assignments_constructed\":0}\n";
    return 0;
  } catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 2; }
}
