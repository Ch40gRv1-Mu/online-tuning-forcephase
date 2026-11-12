#pragma once

struct SignedBoundary {
    std::vector<int> degrees, opposed_count;
    std::vector<double> mass, nonbinary_mass;
    std::array<int, 2> opposed_clauses{};
    std::array<double, 2> aligned_unit{}, opposed_unit{}, conflict{};

    explicit SignedBoundary(int n = 0)
        : degrees(2 * n), opposed_count(2 * n), mass(2 * n), nonbinary_mass(2 * n) {}

    void add(const std::vector<int>& clause) {
        int width = int(clause.size());
        if (!width) return;
        int positive = 0;
        double weight = 1.0 / width;
        for (int v : clause) {
            ++degrees[v];
            mass[v] += weight;
            if (width > 2) nonbinary_mass[v] += weight;
            positive += !(v & 1);
        }
        if (positive == 0 || positive == width) {
            ++opposed_clauses[positive == width];
            for (int v : clause) ++opposed_count[v];
        }
        double half_power = std::ldexp(1.0, -width);
        for (int sign = 0; sign < 2; ++sign) {
            int satisfied = sign ? width - positive : positive;
            if (satisfied == 1) aligned_unit[sign] += half_power;
            if (satisfied == 0) {
                opposed_unit[sign] += width * half_power;
                conflict[sign] += half_power;
            }
        }
    }
};

static bool gate(const Graph& graph, const std::array<int, 3>& t, int i) {
    const auto& out = graph[t[i]];
    return std::binary_search(out.begin(), out.end(), t[(i + 1) % 3] ^ 1) &&
           std::binary_search(out.begin(), out.end(), t[(i + 2) % 3] ^ 1);
}

static double sign_contrast(const std::array<double, 2>& x) {
    return ratio(x[0] - x[1], x[0] + x[1]);
}

struct EquivalenceDemand {
    std::vector<double> weights;
    double total = 0;
    double oriented = 0;
    double nonbinary = 0;
};

static EquivalenceDemand equivalence_demand(const SignedBoundary& b, const Components& scc) {
    EquivalenceDemand result;
    std::vector<double> demand(scc.size.size());
    std::vector<bool> contradictory(scc.size.size());
    for (int v = 0; v < int(scc.id.size()); ++v) {
        int id = scc.id[v];
        result.nonbinary += b.nonbinary_mass[v];
        if (id < 0 || scc.size[id] < 2) continue;
        if (id == scc.id[v ^ 1]) contradictory[id] = true;
        demand[id] += b.nonbinary_mass[v] - b.nonbinary_mass[v ^ 1];
    }
    result.weights.resize(demand.size());
    for (size_t c = 0; c < demand.size(); ++c) {
        if (contradictory[c]) continue;
        result.oriented += demand[c] * ratio(2 * scc.positive[c] - scc.size[c], scc.size[c]);
        result.weights[c] = std::abs(demand[c]);
        result.total += result.weights[c];
    }
    return result;
}

static void print_boundary(const SignedBoundary& b, const Graph& graph, const Components& scc,
                           const std::vector<std::array<int, 3>>& ternaries,
                           int clauses, int active_binary, std::clock_t start) {
    int n = int(graph.size()) / 2;
    const auto demand = equivalence_demand(b, scc);

    std::vector<bool> gate_literals(2 * n);
    for (const auto& t : ternaries)
        for (int i = 0; i < 3; ++i)
            if (gate(graph, t, i)) gate_literals[t[i]] = true;
    double gate_boundary = 0, absolute_gate_boundary = 0, gate_degree = 0;
    for (int v = 0; v < 2 * n; ++v) {
        if (!gate_literals[v]) continue;
        int external_degree = b.degrees[v] + b.degrees[v ^ 1] - 3;
        // The three template clauses contribute 1/3 - 2/2 to signed demand.
        double contrast = (b.mass[v] - b.mass[v ^ 1] + 2.0 / 3) * (1 + external_degree);
        gate_boundary += (v & 1) ? -contrast : contrast;
        absolute_gate_boundary += std::abs(contrast);
        gate_degree += 1 + external_degree;
    }

    std::vector<bool> seen(n);
    std::vector<int> stack;
    double block_signed = 0, block_absolute = 0, var_absolute = 0;
    int used = 0, largest = 0;
    std::array<double, 2> squared{}, hits{};
    for (int seed = 0; seed < n; ++seed) {
        int degree = b.degrees[2 * seed] + b.degrees[2 * seed + 1];
        used += degree > 0;
        for (int s = 0; s < 2; ++s) {
            int k = b.opposed_count[2 * seed + (s ^ 1)];
            hits[s] += k;
            squared[s] += double(k) * k;
        }
        if (seen[seed] || !degree) continue;
        seen[seed] = true;
        stack.push_back(seed);
        double q = 0;
        int members = 0;
        while (!stack.empty()) {
            int v = stack.back();
            stack.pop_back();
            ++members;
            double local = ratio(b.mass[2 * v] - b.mass[2 * v + 1],
                                 b.degrees[2 * v] + b.degrees[2 * v + 1]);
            q += local;
            var_absolute += std::abs(local);
            for (int s = 0; s < 2; ++s)
                for (int w : graph[2 * v + s])
                    if (!seen[w / 2]) {
                        seen[w / 2] = true;
                        stack.push_back(w / 2);
                    }
        }
        largest = std::max(largest, members);
        block_signed += q;
        block_absolute += std::abs(q);
    }
    std::array<double, 2> concentration{};
    for (int s = 0; s < 2; ++s)
        concentration[s] = std::log1p(used * ratio(squared[s], hits[s] * hits[s]));
    double elapsed = double(std::clock() - start) / CLOCKS_PER_SEC;
    std::cout << std::setprecision(12) << elapsed << ' ' << active_binary << " 0 "
              << ratio(demand.oriented, demand.total) << ' ' << ratio(demand.total, demand.nonbinary) << ' '
              << ratio(gate_boundary, absolute_gate_boundary) << ' ' << ratio(absolute_gate_boundary, gate_degree) << ' '
              << (block_absolute > 0 ? 1 - ratio(std::abs(block_signed), block_absolute) : 0) << ' '
              << ratio(block_signed, var_absolute) << ' ' << ratio(block_absolute, var_absolute) << ' '
              << ratio(largest, used) << ' '
              << concentration[0] << ' ' << concentration[1] << ' '
              << ratio(b.opposed_clauses[0] - b.opposed_clauses[1], clauses) << ' '
              << sign_contrast(b.aligned_unit) << ' ' << sign_contrast(b.opposed_unit) << ' '
              << sign_contrast(b.conflict) << ' '
              << ratio(b.aligned_unit[0] + b.aligned_unit[1] + b.opposed_unit[0] + b.opposed_unit[1], clauses) << '\n';
}
