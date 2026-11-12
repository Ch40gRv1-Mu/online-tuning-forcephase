// Signed structural features from a validated DIMACS stream.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <random>
#include <sstream>
#include <string>
#include <vector>

using Graph = std::vector<std::vector<int>>;

static int literal(int x) {
    return 2 * (std::abs(x) - 1) + (x < 0);
}

struct Components {
    std::vector<int> id, size, positive, depth;
};

static Components components(const Graph& graph) {
    std::vector<int> order;
    std::vector<bool> seen(graph.size());
    std::vector<std::pair<int, size_t>> path;
    for (int u = 0; u < int(graph.size()); ++u) {
        if (seen[u] || (graph[u].empty() && graph[u ^ 1].empty())) continue;
        seen[u] = true;
        path.emplace_back(u, 0);
        while (!path.empty()) {
            auto& [v, i] = path.back();
            if (i == graph[v].size()) {
                order.push_back(v);
                path.pop_back();
            } else {
                int w = graph[v][i++];
                if (!seen[w]) {
                    seen[w] = true;
                    path.emplace_back(w, 0);
                }
            }
        }
    }
    Components out;
    out.id.assign(graph.size(), -1);
    std::vector<int> todo;
    for (auto it = order.rbegin(); it != order.rend(); ++it) {
        if (out.id[*it] >= 0) continue;
        int id = int(out.size.size()), n = 0, p = 0;
        out.id[*it] = id;
        todo.push_back(*it);
        while (!todo.empty()) {
            int v = todo.back();
            todo.pop_back();
            ++n;
            p += !(v & 1);
            // Each arc a -> b has a complementary arc ~b -> ~a.
            for (int opposite : graph[v ^ 1]) {
                int w = opposite ^ 1;
                if (out.id[w] < 0) {
                    out.id[w] = id;
                    todo.push_back(w);
                }
            }
        }
        out.size.push_back(n);
        out.positive.push_back(p);
    }
    out.depth.assign(out.size.size(), 0);
    // Process component members in reverse topological component order.
    std::stable_sort(order.begin(), order.end(), [&](int a, int b) { return out.id[a] > out.id[b]; });
    for (int v : order) {
        int id = out.id[v];
        for (int w : graph[v])
            if (out.id[w] != id)
                out.depth[id] = std::max(out.depth[id], 1 + out.depth[out.id[w]]);
    }
    return out;
}

static double ratio(double a, double b) {
    return b > 0 ? a / b : 0;
}

#include "signed_boundary.hpp"
#include "scc_root_propagation.hpp"
#include "gate_dependency.hpp"

int main(int argc, char** argv) {
    bool root_mode = argc == 2 && std::string(argv[1]) == "--root-up";
    bool conditioned_mode = argc == 2 && std::string(argv[1]) == "--conditioned-up";
    bool walk_mode = argc == 2 && std::string(argv[1]) == "--signed-walk";
    bool gate_mode = argc == 2 && std::string(argv[1]) == "--gate-dependency";
    bool polarity_mode = conditioned_mode || walk_mode || (argc == 2 && std::string(argv[1]) == "--root-polarity");
    bool selector_mode = argc == 3 && std::string(argv[1]) == "--selector" &&
                         (std::string(argv[2]) == "width" || std::string(argv[2]) == "scc");
    bool selector_scc = selector_mode && std::string(argv[2]) == "scc";
    bool boundary_mode = root_mode || (argc == 2 && std::string(argv[1]) == "--boundary");
    if (argc != 1 && !boundary_mode && !polarity_mode && !selector_mode && !gate_mode) return 2;
    std::ios::sync_with_stdio(false);
    auto start = std::clock();
    int n = 0, expected = -1, count = 0;
    size_t literal_count = 0;
    Graph graph;
    std::vector<std::array<int, 3>> ternaries;
    std::vector<std::vector<int>> choices;
    std::vector<int> clause;
    SignedBoundary boundary;
    RootFormula formula;
    for (std::string line; std::getline(std::cin, line);) {
        auto first = line.find_first_not_of(" \t\r");
        if (first == std::string::npos || line[first] == 'c') continue;
        std::istringstream tokens(line);
        if (line[first] == 'p') {
            std::string p, cnf;
            if (expected >= 0 || !(tokens >> p >> cnf >> n >> expected) || cnf != "cnf" ||
                n < 1 || (!selector_mode && n > ((boundary_mode || polarity_mode || gate_mode) ? 250000 : 100000)) ||
                expected < 1) return 2;
            selector_scc = selector_scc && n <= 100000;
            if (!polarity_mode && (!selector_mode || selector_scc)) graph.resize(2 * n);
            if (boundary_mode || selector_scc) boundary = SignedBoundary(n);
            if (root_mode || polarity_mode) formula = RootFormula(n);
            continue;
        }
        if (expected < 0) return 2;
        for (int x; tokens >> x;) {
            if (x) {
                if (x < -n || x > n) return 2;
                clause.push_back(selector_mode && !selector_scc ? 0 : literal(x));
                continue;
            }
            ++count;
            if (selector_mode) {
                literal_count += clause.size();
                if (!selector_scc) {
                    clause.clear();
                    continue;
                }
            }
            if (polarity_mode) {
                formula.add(clause);
                clause.clear();
                continue;
            }
            if (boundary_mode || selector_scc) boundary.add(clause);
            if (root_mode) formula.add(clause);
            if (clause.size() == 2) {
                int a = clause[0], b = clause[1];
                if (a != b && a != (b ^ 1)) {
                    graph[a ^ 1].push_back(b);
                    graph[b ^ 1].push_back(a);
                }
            } else if (!root_mode && !selector_mode && clause.size() >= 3 && clause.size() <= 32) {
                std::sort(clause.begin(), clause.end());
                if (std::adjacent_find(clause.begin(), clause.end()) == clause.end()) {
                    if (clause.size() == 3 && clause[0] / 2 != clause[1] / 2 && clause[1] / 2 != clause[2] / 2)
                        ternaries.push_back({clause[0], clause[1], clause[2]});
                    if (!boundary_mode && !gate_mode && std::all_of(clause.begin(), clause.end(),
                                                      [&](int v) { return (v & 1) == (clause[0] & 1); }))
                        choices.push_back(clause);
                }
            }
            clause.clear();
        }
        if (!tokens.eof()) return 2;
    }
    if (count != expected || !clause.empty()) return 2;
    auto print_selector = [&](double scc) {
        const double elapsed = double(std::clock() - start) / CLOCKS_PER_SEC;
        std::cout << std::setprecision(12) << elapsed << ' ' << scc << ' '
                  << ratio(literal_count, count) << '\n';
    };
    if (selector_mode && !selector_scc) {
        print_selector(-1);
        return 0;
    }
    if (polarity_mode) {
        if (conditioned_mode) print_conditioned_up(formula, start);
        else if (walk_mode) print_signed_walk(formula, start);
        else print_root_polarity(formula, start);
        return 0;
    }
    for (auto& neighbors : graph) {
        std::sort(neighbors.begin(), neighbors.end());
        neighbors.erase(std::unique(neighbors.begin(), neighbors.end()), neighbors.end());
    }
    std::sort(ternaries.begin(), ternaries.end());
    ternaries.erase(std::unique(ternaries.begin(), ternaries.end()), ternaries.end());
    if (gate_mode) {
        print_gate_dependency(graph, ternaries, count, start);
        return 0;
    }
    std::vector<int> roots;
    for (int i = 0; i < n; ++i)
        if (!graph[2 * i].empty() || !graph[2 * i + 1].empty()) roots.push_back(i);
    const int active = int(roots.size());
    auto scc = components(graph);
    if (selector_mode) {
        const auto demand = equivalence_demand(boundary, scc);
        print_selector(ratio(demand.total, demand.nonbinary));
        return 0;
    }
    if (root_mode) {
        print_root_scc(boundary, scc, formula, start);
        return 0;
    }
    if (boundary_mode) {
        print_boundary(boundary, graph, scc, ternaries, count, active, start);
        return 0;
    }
    int largest = 0, nontrivial = 0, orientation = 0, depth_max = 0;
    double depth_signed = 0, depth_sum = 0;
    for (size_t i = 0; i < scc.size.size(); ++i) {
        int size = scc.size[i], balance = 2 * scc.positive[i] - size;
        largest = std::max(largest, size);
        if (size > 1) {
            nontrivial += size;
            orientation += std::abs(balance);
        }
        depth_max = std::max(depth_max, scc.depth[i]);
        depth_sum += double(scc.depth[i]) * size;
        depth_signed += double(scc.depth[i]) * balance;
    }

    std::mt19937 rng(20261110);
    std::shuffle(roots.begin(), roots.end(), rng);
    roots.resize(std::min<size_t>(roots.size(), 64));
    std::vector<int> mark(graph.size(), 0);
    int serial = 0, truncated = 0;
    double reach_signed = 0, reach_abs = 0, reach_mean = 0, collisions = 0, collision_signed = 0;
    for (int root : roots) {
        std::array<double, 2> reach{}, conflict{};
        for (int sign = 0; sign < 2; ++sign) {
            int u = 2 * root + sign, arcs = 0, touched = 0, pairs = 0;
            ++serial;
            mark[u] = serial;
            auto visit = [&](int v) {
                if (mark[v] == serial) return;
                pairs += mark[v ^ 1] == serial;
                mark[v] = serial;
                ++touched;
            };
            for (int v : graph[u]) visit(v);
            for (int v : graph[u]) {
                for (int w : graph[v]) {
                    if (arcs++ == 512) break;
                    visit(w);
                }
                if (arcs > 512) break;
            }
            truncated += arcs > 512;
            reach[sign] = std::log1p(touched);
            conflict[sign] = pairs > 0;
        }
        reach_signed += reach[0] - reach[1];
        reach_abs += std::abs(reach[0] - reach[1]);
        reach_mean += (reach[0] + reach[1]) / 2;
        collisions += (conflict[0] + conflict[1]) / 2;
        collision_signed += conflict[0] - conflict[1];
    }

    std::array<int, 2> gates{};
    std::array<double, 2> fanout{};
    for (const auto& t : ternaries) {
        for (int i = 0; i < 3; ++i) {
            int y = t[i];
            if (gate(graph, t, i)) {
                ++gates[y & 1];
                fanout[y & 1] += std::log1p(graph[y].size() - 2);
            }
        }
    }

    std::sort(choices.begin(), choices.end());
    choices.erase(std::unique(choices.begin(), choices.end()), choices.end());
    std::vector<int> exclusion_degree(graph.size());
    for (int v = 0; v < int(graph.size()); ++v)
        exclusion_degree[v] = int(std::count_if(graph[v].begin(), graph[v].end(),
                                              [&](int w) { return (w & 1) != (v & 1); }));
    std::array<int, 2> choice_count{};
    std::array<double, 2> external_max{}, inside_sum{};
    for (const auto& c : choices) {
        int sign = c[0] & 1, inside = 0, degree = 0;
        for (int v : c) {
            const auto& out = graph[v];
            degree += exclusion_degree[v];
            for (int w : c)
                if (w != v) inside += std::binary_search(out.begin(), out.end(), w ^ 1);
        }
        ++choice_count[sign];
        inside_sum[sign] += ratio(inside, c.size() * (c.size() - 1));
        external_max[sign] = std::max(external_max[sign], ratio(degree - inside, c.size()));
    }

    const double sample = roots.size(), all_gates = gates[0] + gates[1];
    const double elapsed = double(std::clock() - start) / CLOCKS_PER_SEC;
    std::cout << std::setprecision(12) << elapsed << ' ' << active << ' '
              << ratio(truncated, 2 * sample) << ' '
              << ratio(nontrivial, 2 * active) << ' ' << ratio(largest, 2 * active) << ' '
              << ratio(orientation, nontrivial) << ' ' << std::log1p(depth_max) << ' '
              << std::log1p(ratio(depth_sum, 2 * active)) << ' ' << ratio(depth_signed, depth_sum) << ' '
              << ratio(reach_signed, sample) << ' ' << ratio(reach_abs, sample) << ' '
              << ratio(reach_mean, sample) << ' ' << ratio(collisions, sample) << ' '
              << ratio(collision_signed, sample) << ' '
              << ratio(all_gates, count) << ' ' << ratio(gates[0] - gates[1], all_gates) << ' '
              << ratio(fanout[0] - fanout[1], fanout[0] + fanout[1]) << ' '
              << ratio(choice_count[0] + choice_count[1], count) << ' '
              << ratio(inside_sum[0], choice_count[0]) << ' ' << ratio(inside_sum[1], choice_count[1]) << ' '
              << std::log1p(external_max[0]) << ' ' << std::log1p(external_max[1]) << '\n';
}
