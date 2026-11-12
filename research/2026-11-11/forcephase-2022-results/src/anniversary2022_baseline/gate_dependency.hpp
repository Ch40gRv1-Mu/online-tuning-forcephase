#pragma once

struct GateDepth {
    std::vector<int> id, size, depth;
};

static GateDepth dependency_depth(const Graph& edges, const Graph& reverse) {
    std::vector<bool> seen(edges.size());
    std::vector<int> order;
    std::vector<std::pair<int, size_t>> path;
    for (int start = 0; start < int(edges.size()); ++start) {
        if (seen[start] || (edges[start].empty() && reverse[start].empty())) continue;
        seen[start] = true;
        path.emplace_back(start, 0);
        while (!path.empty()) {
            auto& [v, edge] = path.back();
            if (edge == edges[v].size()) {
                order.push_back(v);
                path.pop_back();
                continue;
            }
            int w = edges[v][edge++];
            if (!seen[w]) {
                seen[w] = true;
                path.emplace_back(w, 0);
            }
        }
    }
    GateDepth result;
    result.id.assign(edges.size(), -1);
    std::vector<int> pending;
    for (auto it = order.rbegin(); it != order.rend(); ++it) {
        if (result.id[*it] >= 0) continue;
        int size = 0, id = int(result.size.size());
        result.id[*it] = id;
        pending.push_back(*it);
        while (!pending.empty()) {
            int v = pending.back();
            pending.pop_back();
            ++size;
            for (int w : reverse[v])
                if (result.id[w] < 0) {
                    result.id[w] = id;
                    pending.push_back(w);
                }
        }
        result.size.push_back(size);
    }
    Graph condensed(result.size.size());
    for (int v : order)
        for (int w : edges[v])
            if (result.id[v] != result.id[w])
                condensed[result.id[v]].push_back(result.id[w]);
    result.depth.resize(result.size.size());
    for (int id = 0; id < int(condensed.size()); ++id)
        for (int next : condensed[id])
            result.depth[next] = std::max(result.depth[next], result.depth[id] + 1);
    return result;
}

// A parity denotes whether a variable's sign is flipped relative to its root.
struct GateAliases {
    std::vector<int> parent, size, parity;
    std::vector<bool> inconsistent;

    explicit GateAliases(int n) : parent(n), size(n, 1), parity(n), inconsistent(n) {
        for (int v = 0; v < n; ++v) parent[v] = v;
    }

    int root(int v) {
        if (parent[v] == v) return v;
        int p = parent[v];
        parent[v] = root(p);
        parity[v] ^= parity[p];
        return parent[v];
    }

    void join(int a, int b) {
        int x = root(a / 2), y = root(b / 2);
        int difference = (a & 1) ^ (b & 1) ^ parity[a / 2] ^ parity[b / 2];
        if (x == y) {
            if (difference) inconsistent[x] = true;
            return;
        }
        if (size[x] < size[y]) std::swap(x, y);
        parent[y] = x;
        parity[y] = difference;
        size[x] += size[y];
        inconsistent[x] = inconsistent[x] || inconsistent[y];
    }
};

static void print_gate_dependency(const Graph& binary, const std::vector<std::array<int, 3>>& triples,
                                  int clauses, std::clock_t start) {
    const int n = int(binary.size()) / 2;
    Graph edges(n), reverse(n);
    std::vector<std::array<int, 3>> gates;
    for (const auto& t : triples)
        for (int i = 0; i < 3; ++i)
            if (gate(binary, t, i)) {
                int y = t[i];
                int a = t[(i + 1) % 3] ^ 1, b = t[(i + 2) % 3] ^ 1;
                gates.push_back({y, a, b});
                for (int input : {a, b}) {
                    edges[input / 2].push_back(y / 2);
                    reverse[y / 2].push_back(input / 2);
                }
            }

    double signed_count = 0, signed_fanout = 0, fanout_mass = 0;
    double depth_mass = 0, depth_signed = 0, acyclic = 0, aliases_total = 0;
    double aliases_opposed = 0, same_var_opposed = 0, same_var_total = 0;
    if (!gates.empty()) {
        const auto depth = dependency_depth(edges, reverse);
        GateAliases aliases(n);
        for (int l = 0; l < int(binary.size()); ++l)
            for (int w : binary[l])
                if (l < w && std::binary_search(binary[w].begin(), binary[w].end(), l))
                    aliases.join(l, w);

        using Counts = std::array<double, 2>;
        std::vector<Counts> outputs(n), inputs(n), alias_outputs(n), alias_inputs(n);
        for (const auto& g : gates) {
            int y = g[0], block = depth.id[y / 2];
            int sign = (y & 1) ? 1 : -1;  // A false AND output is the controlling value.
            signed_count += sign;
            double fanout = std::log1p(binary[y].size() - 2);
            signed_fanout += sign * fanout;
            fanout_mass += fanout;
            depth_mass += depth.depth[block];
            depth_signed += sign * depth.depth[block];
            acyclic += depth.size[block] == 1;
            ++outputs[y / 2][y & 1];
            for (int i = 1; i <= 2; ++i)
                ++inputs[g[i] / 2][g[i] & 1];
        }
        auto opposite = [](const Counts& a, const Counts& b) { return a[0] * b[1] + a[1] * b[0]; };
        auto pairs = [](const Counts& a, const Counts& b) { return (a[0] + a[1]) * (b[0] + b[1]); };
        for (int v = 0; v < n; ++v) {
            same_var_opposed += opposite(outputs[v], inputs[v]);
            same_var_total += pairs(outputs[v], inputs[v]);
            int root = aliases.root(v), p = aliases.parity[v];
            if (aliases.inconsistent[root]) continue;
            for (int s = 0; s < 2; ++s) {
                alias_outputs[root][s ^ p] += outputs[v][s];
                alias_inputs[root][s ^ p] += inputs[v][s];
            }
            aliases_opposed -= opposite(outputs[v], inputs[v]);
            aliases_total -= pairs(outputs[v], inputs[v]);
        }
        for (int v = 0; v < n; ++v) {
            aliases_opposed += opposite(alias_outputs[v], alias_inputs[v]);
            aliases_total += pairs(alias_outputs[v], alias_inputs[v]);
        }
    }
    const double elapsed = double(std::clock() - start) / CLOCKS_PER_SEC;
    std::cout << std::setprecision(12) << elapsed << " 0 0 "
              << gates.size() << ' ' << aliases_total << ' '
              << ratio(depth_signed, depth_mass) << ' ' << std::log1p(ratio(depth_mass, gates.size())) << ' '
              << ratio(acyclic, gates.size()) << ' ' << ratio(aliases_opposed, aliases_total) << ' '
              << ratio(gates.size(), clauses) << ' ' << ratio(signed_count, gates.size()) << ' '
              << ratio(signed_fanout, fanout_mass) << ' ' << ratio(same_var_opposed, same_var_total) << '\n';
}
