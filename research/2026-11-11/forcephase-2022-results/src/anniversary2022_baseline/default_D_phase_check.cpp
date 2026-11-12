#include "internal.hpp"
#include <iostream>

int main() {
    CaDiCaL::Internal solver;
    solver.opts.phase = 1;
    solver.opts.forcephase = 0;
    solver.init_vars(8);
    const int queue = solver.next_decision_variable_on_queue();
    const int score = solver.next_decision_variable_with_best_score();
    const int initial = solver.decide_phase(3, false);
    solver.phases.saved[3] = -1;
    const int remembered = solver.decide_phase(3, false);
    solver.phases.target[3] = 1;
    const int target = solver.decide_phase(3, true);
    solver.opts.forcephase = 1;
    const int plus = solver.decide_phase(3, true);
    solver.opts.phase = 0;
    const int minus = solver.decide_phase(3, true);
    solver.phases.forced[3] = 1;
    const int explicit_phase = solver.decide_phase(3, true);
    assert(queue == 8 && score == 1 && initial == 3);
    assert(remembered == -3 && target == 3 && plus == 3 && minus == -3);
    assert(explicit_phase == 3);
    std::cout << "{\"queue_first\":" << queue << ",\"score_first\":" << score
              << ",\"D_initial\":" << initial << ",\"D_saved_negative\":" << remembered
              << ",\"D_target_positive\":" << target << ",\"Fplus\":" << plus
              << ",\"Fminus\":" << minus << ",\"explicit_override\":" << explicit_phase
              << ",\"solve_calls\":0,\"propagate_calls\":0}\n";
}
