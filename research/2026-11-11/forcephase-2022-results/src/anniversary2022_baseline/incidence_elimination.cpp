// R49: bounded graph elimination, not CNF resolution or assignment search.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <new>
#include <queue>
#include <random>
#include <tuple>
#include <unordered_set>
#include <vector>

using I = int32_t;
using Q = int64_t;
static uint64_t priority(uint64_t x) {
  x += 20261149ULL + 0x9e3779b97f4a7c15ULL;
  x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
  x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
  return x ^ (x >> 31);
}
static uint64_t edge(I v, I c) { return (uint64_t(v) << 32) | uint32_t(c); }

extern "C" int typed_simple_rewire(I nv, I nc, I length, I kinds, I *variable,
    const I *clause, const I *kind, Q *receipt) {
  try {
    std::unordered_set<uint64_t> edges;
    edges.reserve(2ULL * length + 1);
    std::vector<std::vector<I>> groups(kinds);
    for (I i = 0; i < length; ++i) {
      if (variable[i] < 0 || variable[i] >= nv || clause[i] < 0 || clause[i] >= nc ||
          kind[i] < 0 || kind[i] >= kinds) return 2;
      if (!edges.insert(edge(variable[i], clause[i])).second) return 3;
      groups[kind[i]].push_back(i);
    }
    std::mt19937_64 rng(20261149);
    Q accepted = 0, attempted = 0;
    for (Q step = 0; length && step < 2LL * length; ++step) {
      const I i = rng() % length;
      const auto &group = groups[kind[i]];
      const I j = group[rng() % group.size()];
      ++attempted;
      const I a = variable[i], b = variable[j], c = clause[i], d = clause[j];
      if (a == b || c == d || edges.count(edge(a, d)) || edges.count(edge(b, c))) continue;
      edges.erase(edge(a, c)); edges.erase(edge(b, d));
      edges.insert(edge(a, d)); edges.insert(edge(b, c));
      std::swap(variable[i], variable[j]);
      ++accepted;
    }
    receipt[0] = attempted; receipt[1] = accepted;
    return 0;
  } catch (const std::bad_alloc &) { return 70; }
  catch (...) { return 71; }
}

extern "C" int incidence_elimination(I nv, I nc, I length, const I *variable,
    const I *clause, const double *bias, double *output, Q *receipt) {
  try {
    const I n = nv + nc;
    std::fill(output, output + 44, 0.);
    std::fill(receipt, receipt + 9, 0);
    if (n == 0) { output[10] = 1.; return 0; }
    std::vector<std::unordered_set<I>> adj(n);
    std::vector<Q> original_degree(n, 0);
    std::vector<char> alive(n, true);
    Q edges = 0;
    for (I i = 0; i < length; ++i) {
      const I u = variable[i], v = nv + clause[i];
      if (u < 0 || u >= nv || v < nv || v >= n) return 2;
      if (!adj[u].insert(v).second) return 3;
      adj[v].insert(u); ++edges;
    }
    using Entry = std::tuple<I, uint64_t, I>;
    std::priority_queue<Entry, std::vector<Entry>, std::greater<Entry>> queue;
    for (I v = 0; v < n; ++v) {
      original_degree[v] = adj[v].size();
      queue.emplace(adj[v].size(), priority(v), v);
    }
    Q removed = 0, removed_vars = 0, removed_clauses = 0, fill = 0, work = 0;
    Q max_degree = 0, variable_mass = 0, clause_mass = 0;
    Q residual_min = 0, reason = 0;
    double degree_sum = 0, degree_squared_sum = 0, degree_bands[4] = {};
    const Q fill_cap = std::min<Q>(1000000, 4LL * length + 1024);
    while (!queue.empty()) {
      const auto entry = queue.top(); queue.pop();
      const I v = std::get<2>(entry), d = std::get<0>(entry);
      if (!alive[v] || Q(d) != Q(adj[v].size())) continue;
      residual_min = d;
      if (d > 128) { reason = 1; break; }
      const Q pairs = Q(d) * (d - 1) / 2;
      if (work + pairs > 500000) { reason = 2; break; }
      std::vector<I> neighbors(adj[v].begin(), adj[v].end());
      std::vector<std::pair<I, I>> missing;
      work += pairs;
      for (I i = 0; i < d; ++i)
        for (I j = i + 1; j < d; ++j)
          if (!adj[neighbors[i]].count(neighbors[j])) missing.emplace_back(neighbors[i], neighbors[j]);
      if (fill + Q(missing.size()) > fill_cap) { reason = 3; break; }
      alive[v] = false;
      for (I u : neighbors) adj[u].erase(v);
      for (const auto &p : missing) { adj[p.first].insert(p.second); adj[p.second].insert(p.first); }
      adj[v].clear();
      edges += Q(missing.size()) - d;
      fill += missing.size();
      for (I u : neighbors) queue.emplace(adj[u].size(), priority(u), u);
      ++removed;
      max_degree = std::max<Q>(max_degree, d);
      degree_sum += d; degree_squared_sum += double(d) * d;
      ++degree_bands[d <= 1 ? 0 : (d <= 4 ? 1 : (d <= 16 ? 2 : 3))];
      if (v < nv) {
        ++removed_vars; variable_mass += original_degree[v];
        const I band = d <= 1 ? 0 : (d == 2 ? 1 : (d <= 4 ? 2 : (d <= 8 ? 3 :
            (d <= 16 ? 4 : (d <= 32 ? 5 : (d <= 64 ? 6 : 7))))));
        output[20 + 3 * band] += 1.;
        output[21 + 3 * band] += bias[v];
        output[22 + 3 * band] += std::abs(bias[v]);
      } else { ++removed_clauses; clause_mass += original_degree[v]; }
    }
    const bool complete = removed == n;
    if (complete) residual_min = 0;
    output[0] = double(removed) / n;
    output[1] = double(removed_vars) / std::max<I>(nv, 1);
    output[2] = double(removed_clauses) / std::max<I>(nc, 1);
    output[3] = std::log1p(max_degree);
    output[4] = std::log1p(degree_sum / std::max<Q>(removed, 1));
    output[5] = std::log1p(std::sqrt(degree_squared_sum / std::max<Q>(removed, 1)));
    output[6] = std::log1p(double(fill) / std::max<I>(length, 1));
    output[7] = std::log1p(double(work) / std::max<I>(length, 1));
    output[8] = double(edges) / std::max<I>(length, 1);
    output[9] = std::log1p(residual_min);
    output[10] = complete;
    for (I k = 1; k <= 3; ++k) output[10 + k] = reason == k;
    for (I k = 0; k < 4; ++k) output[14 + k] = degree_bands[k] / std::max<Q>(removed, 1);
    output[18] = double(variable_mass) / std::max<I>(length, 1);
    output[19] = double(clause_mass) / std::max<I>(length, 1);
    for (I k = 20; k < 44; ++k) output[k] /= std::max<I>(nv, 1);
    const Q values[9] = {removed, removed_vars, removed_clauses, max_degree, fill, work, edges, residual_min, reason};
    std::copy(values, values + 9, receipt);
    return 0;
  } catch (const std::bad_alloc &) { return 70; }
  catch (...) { return 71; }
}
