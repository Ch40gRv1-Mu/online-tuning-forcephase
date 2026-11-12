#pragma once

// Retain the original clauses for an exact root closure, without search.
struct RootFormula {
    std::vector<int> literals, offsets{0}, clause_marks;

    explicit RootFormula(int variables = 0) : clause_marks(2 * variables) {}

    void add(const std::vector<int>& clause) {
        const int mark = int(offsets.size());
        for (int l : clause) {
            if (clause_marks[l ^ 1] == mark) {
                literals.resize(offsets.back());
                // A later clause can safely reuse this offset and mark.
                for (int t : clause)
                    if (clause_marks[t] == mark) clause_marks[t] = 0;
                return;
            }
            if (clause_marks[l] != mark) {
                literals.push_back(l);
                clause_marks[l] = mark;
            }
        }
        offsets.push_back(int(literals.size()));
    }
};

struct RootClosure {
    std::vector<signed char> values;
    int assigned = 0, clauses = 0, binaries = 0;
    bool conflict = false;
};

struct RootOccurrences {
    std::vector<std::vector<int>> clauses_by_literal;
    std::vector<int> widths, units;
    bool empty = false;

    explicit RootOccurrences(const RootFormula& formula)
        : clauses_by_literal(formula.clause_marks.size()) {
        widths.reserve(formula.offsets.size() - 1);
        for (int c = 0; c + 1 < int(formula.offsets.size()); ++c) {
            int first = formula.offsets[c], end = formula.offsets[c + 1];
            widths.push_back(end - first);
            for (int i = first; i < end; ++i)
                clauses_by_literal[formula.literals[i]].push_back(c);
            empty |= first == end;
            if (end == first + 1) units.push_back(formula.literals[first]);
        }
    }
};

static RootClosure propagate_root(const RootFormula& formula, const RootOccurrences& occurrences,
                                  int assumption = -1) {
    RootClosure result;
    result.values.resize(formula.clause_marks.size());
    result.conflict = occurrences.empty;
    std::vector<int> remaining = occurrences.widths, trail;

    auto enqueue = [&](int l) {
        if (result.values[l] < 0) result.conflict = true;
        if (result.values[l]) return;
        result.values[l] = 1;
        result.values[l ^ 1] = -1;
        trail.push_back(l);
    };

    for (int l : occurrences.units) enqueue(l);
    if (assumption >= 0) enqueue(assumption);

    for (size_t i = 0; i < trail.size() && !result.conflict; ++i) {
        const int l = trail[i];
        for (int c : occurrences.clauses_by_literal[l]) remaining[c] = -1;
        for (int c : occurrences.clauses_by_literal[l ^ 1]) {
            if (remaining[c] < 0 || --remaining[c] > 1) continue;
            int unassigned = -1;
            bool satisfied = false;
            for (int j = formula.offsets[c]; j < formula.offsets[c + 1]; ++j) {
                int other = formula.literals[j];
                if (result.values[other] > 0) {
                    satisfied = true;
                    break;
                }
                if (!result.values[other]) unassigned = other;
            }
            if (satisfied) remaining[c] = -1;
            else if (unassigned >= 0) enqueue(unassigned);
            else result.conflict = true;
            if (result.conflict) break;
        }
    }

    result.assigned = int(trail.size());
    if (!result.conflict) {
        for (int size : remaining) {
            result.clauses += size > 0;
            result.binaries += size == 2;
        }
    }
    return result;
}

static RootClosure propagate_root(const RootFormula& formula) {
    return propagate_root(formula, RootOccurrences(formula));
}

static void print_root_scc(const SignedBoundary& boundary, const Components& scc,
                           const RootFormula& formula, std::clock_t start) {
    auto root = propagate_root(formula);
    auto demand = equivalence_demand(boundary, scc);
    std::vector<bool> fixed(scc.size.size());
    if (!root.conflict) {
        for (int l = 0; l < int(scc.id.size()); ++l)
            if (scc.id[l] >= 0 && root.values[l]) fixed[scc.id[l]] = true;
    }
    double fixed_demand = 0;
    for (size_t c = 0; c < fixed.size(); ++c)
        if (fixed[c]) fixed_demand += demand.weights[c];
    int binaries = 0;
    for (size_t c = 1; c < formula.offsets.size(); ++c)
        binaries += formula.offsets[c] - formula.offsets[c - 1] == 2;
    const double elapsed = double(std::clock() - start) / CLOCKS_PER_SEC;
    std::cout << std::setprecision(12) << elapsed << ' '
              << ratio(demand.total, demand.nonbinary) << ' ' << ratio(fixed_demand, demand.total) << ' '
              << root.conflict << ' ' << root.assigned << ' ' << root.clauses << ' ' << root.binaries << ' '
              << formula.offsets.size() - 1 << ' ' << binaries << '\n';
}

static void print_root_polarity(const RootFormula& formula, std::clock_t start) {
    const auto root = propagate_root(formula);
    std::array<double, 2> original_mass{}, remaining_mass{};
    int original_binary = 0, new_binary = 0, new_binary_signed = 0;
    if (!root.conflict && root.assigned) {
        for (size_t c = 1; c < formula.offsets.size(); ++c) {
            int before = formula.offsets[c] - formula.offsets[c - 1];
            int before_pos = 0, after = 0, after_pos = 0;
            bool satisfied = false;
            for (int i = formula.offsets[c - 1]; i < formula.offsets[c]; ++i) {
                int l = formula.literals[i];
                before_pos += !(l & 1);
                satisfied |= root.values[l] > 0;
                if (!root.values[l]) {
                    ++after;
                    after_pos += !(l & 1);
                }
            }
            original_binary += before == 2;
            if (before_pos == before) original_mass[0] += std::ldexp(1.0, -before);
            if (before_pos == 0) original_mass[1] += std::ldexp(1.0, -before);
            if (satisfied || !after) continue;
            if (after_pos == after) remaining_mass[0] += std::ldexp(1.0, -after);
            if (after_pos == 0) remaining_mass[1] += std::ldexp(1.0, -after);
            if (after == 2 && before > 2) {
                ++new_binary;
                new_binary_signed += (after_pos == 2) - (after_pos == 0);
            }
        }
    }
    const double elapsed = double(std::clock() - start) / CLOCKS_PER_SEC;
    const double binary_delta = root.assigned && !root.conflict ?
        ratio(root.binaries, root.clauses) - ratio(original_binary, formula.offsets.size() - 1) : 0;
    std::cout << std::setprecision(12) << elapsed << ' ' << root.conflict << ' ' << root.assigned << ' '
              << sign_contrast(remaining_mass) - sign_contrast(original_mass) << ' '
              << ratio(new_binary_signed, new_binary) << ' ' << binary_delta << ' '
              << ratio(new_binary, root.binaries) << '\n';
}

static void print_conditioned_up(const RootFormula& formula, std::clock_t start) {
    const RootOccurrences occurrences(formula);
    const auto root = propagate_root(formula, occurrences);
    std::vector<int> candidates;
    if (!root.conflict) {
        std::vector<int> degree(root.values.size() / 2);
        for (size_t c = 1; c < formula.offsets.size(); ++c) {
            bool satisfied = false;
            for (int i = formula.offsets[c - 1]; i < formula.offsets[c]; ++i)
                satisfied |= root.values[formula.literals[i]] > 0;
            if (satisfied) continue;
            for (int i = formula.offsets[c - 1]; i < formula.offsets[c]; ++i) {
                int l = formula.literals[i];
                if (!root.values[l]) ++degree[l / 2];
            }
        }
        for (size_t v = 0; v < degree.size(); ++v)
            if (degree[v]) candidates.push_back(int(v));
        auto keep = std::min<size_t>(4, candidates.size());
        std::partial_sort(candidates.begin(), candidates.begin() + keep, candidates.end(),
                          [&](int a, int b) { return degree[a] != degree[b] ? degree[a] > degree[b] : a < b; });
        candidates.resize(keep);
    }
    int paired = 0, live = 0, signed_conflicts = 0;
    double signed_reach = 0, asymmetry = 0, reach = 0;
    for (int v : candidates) {
        auto positive = propagate_root(formula, occurrences, 2 * v);
        auto negative = propagate_root(formula, occurrences, 2 * v + 1);
        double plus = std::log1p(std::max(0, positive.assigned - root.assigned - 1));
        double minus = std::log1p(std::max(0, negative.assigned - root.assigned - 1));
        signed_conflicts += int(positive.conflict) - int(negative.conflict);
        if (!positive.conflict) { reach += plus; ++live; }
        if (!negative.conflict) { reach += minus; ++live; }
        if (!positive.conflict && !negative.conflict) {
            signed_reach += plus - minus;
            asymmetry += std::abs(plus - minus);
            ++paired;
        }
    }
    const double elapsed = double(std::clock() - start) / CLOCKS_PER_SEC;
    std::cout << std::setprecision(12) << elapsed << ' ' << root.conflict << ' ' << root.assigned << ' '
              << candidates.size() << ' ' << ratio(signed_reach, paired) << ' '
              << ratio(asymmetry, paired) << ' ' << ratio(signed_conflicts, candidates.size()) << ' '
              << ratio(reach, live) << '\n';
}

static void print_signed_walk(const RootFormula& formula, std::clock_t start) {
    const auto root = propagate_root(formula);
    using Channels = std::array<double, 2>;
    std::vector<int> literals, offsets{0};
    std::vector<double> weights;
    std::vector<bool> active(root.values.size() / 2);
    if (!root.conflict) {
        for (size_t c = 1; c < formula.offsets.size(); ++c) {
            bool satisfied = false;
            for (int i = formula.offsets[c - 1]; i < formula.offsets[c]; ++i)
                satisfied |= root.values[formula.literals[i]] > 0;
            if (satisfied) continue;
            for (int i = formula.offsets[c - 1]; i < formula.offsets[c]; ++i) {
                int l = formula.literals[i];
                if (!root.values[l]) {
                    literals.push_back(l);
                    active[l / 2] = true;
                }
            }
            int width = int(literals.size()) - offsets.back();
            if (width < 2) {
                // A successful root closure leaves neither empty nor unit clauses.
                std::cerr << "invalid root closure for signed walk\n";
                std::exit(2);
            }
            weights.push_back(std::ldexp(1.0, 2 - width));
            offsets.push_back(int(literals.size()));
        }
    }
    std::vector<Channels> mass(root.values.size()), next(mass.size());
    const double seed = ratio(1, std::count(active.begin(), active.end(), true));
    for (size_t v = 0; v < active.size(); ++v)
        if (active[v]) {
            mass[2 * v][0] = seed;
            mass[2 * v + 1][1] = seed;
        }
    for (int step = 0; step < 3; ++step) {
        std::fill(next.begin(), next.end(), Channels{});
        for (size_t c = 0; c < weights.size(); ++c) {
            Channels incoming{};
            for (int i = offsets[c]; i < offsets[c + 1]; ++i)
                for (int s = 0; s < 2; ++s) incoming[s] += mass[literals[i] ^ 1][s];
            // Canonical clauses contain no complementary pair. Flow emitted by a
            // clause cannot immediately reenter it through the opposite literal.
            for (int i = offsets[c]; i < offsets[c + 1]; ++i) {
                int l = literals[i];
                for (int s = 0; s < 2; ++s)
                    next[l][s] += weights[c] * (incoming[s] - mass[l ^ 1][s]);
            }
        }
        mass.swap(next);
    }
    Channels total{}, aligned{}, overlap{};
    for (size_t l = 0; l < mass.size(); ++l) {
        for (int s = 0; s < 2; ++s) {
            total[s] += mass[l][s];
            if ((l & 1) == size_t(s)) aligned[s] += mass[l][s];
            if (!(l & 1)) overlap[s] += std::min(mass[l][s], mass[l ^ 1][s]);
        }
    }
    const double elapsed = double(std::clock() - start) / CLOCKS_PER_SEC;
    std::cout << std::setprecision(12) << elapsed << ' ' << root.conflict << ' ' << root.assigned << ' '
              << std::log1p(total[0]) - std::log1p(total[1]) << ' '
              << ratio(aligned[0], total[0]) - ratio(aligned[1], total[1]) << ' '
              << ratio(overlap[0], total[0]) - ratio(overlap[1], total[1]) << ' '
              << (std::log1p(total[0]) + std::log1p(total[1])) / 2 << '\n';
}
