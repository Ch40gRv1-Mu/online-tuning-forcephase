// Execute pinned upstream structural statistics; there is no SAT solver here.
#include <algorithm>
#include <cmath>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <sys/resource.h>
#include <unistd.h>

#include "src/extract/CNFBaseFeatures.h"
#include "src/util/StreamBuffer.h"

int main(int argc, char **argv) {
    if (argc != 2) return 64;
    rlimit core{0, 0}, cpu{8, 8};
    setrlimit(RLIMIT_CORE, &core);
    if (setrlimit(RLIMIT_CPU, &cpu)) return 70;
    alarm(12);
    const auto start = std::clock();
    try {
        // Bound allocations before upstream resizes arrays by literal ID.
        // This extra read is included in every feature-time measurement.
        StreamBuffer scan(argv[1]);
        Cl clause;
        while (scan.readClause(clause)) {
            if (clause.empty()) throw std::runtime_error("upstream empty-clause feature path unsupported");
            for (auto lit : clause)
                if (static_cast<unsigned>(lit.var()) > 5000000)
                    throw std::runtime_error("feature variable allocation limit");
        }
        CNF::BaseFeatures features(argv[1]);
        features.run();
        const auto names = features.getNames();
        const auto values = features.getFeatures();
        for (auto value : values)
            if (!std::isfinite(value)) throw std::runtime_error("nonfinite upstream feature");
        std::cout << std::setprecision(17) << "{\"features\":{";
        for (size_t i = 0; i < names.size(); ++i) {
            if (i) std::cout << ',';
            std::cout << '\"' << names[i] << "\":" << values[i];
        }
        std::cout << "},\"inner_CPU_s\":" << double(std::clock() - start) / CLOCKS_PER_SEC << "}\n";
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 65;
    }
    return 0;
}
