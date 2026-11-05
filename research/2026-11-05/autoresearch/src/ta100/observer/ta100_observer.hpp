#ifndef TA100_OBSERVER_HPP
#define TA100_OBSERVER_HPP

#include <cstdio>

namespace CaDiCaL {
struct Internal;
struct Clause;
namespace TA100 {

// Logging-only observer. All mutation belongs to State, never to search.
class Observer {
  struct State;
  State *state;

public:
  explicit Observer (Internal *);
  ~Observer ();
  static bool selftest (); // synthetic arithmetic checks; never solves SAT
  void begin_analysis ();
  void analyze_reason (Clause *);
  void dependency (Clause *);
  void analyzed_literal (int);
  void learned (int glue, int uip);
  void driving (Clause *);
  void assigned (int lit, Clause *reason);
  void before_driving_assignment (Clause *);
  void after_driving_assignment (Clause *);
  void unassigned (int lit);
  void free_decision (int lit);
  void bumped (int lit);
  void watch (bool satisfied_blocker);
  void set_chrono (bool);
  void begin_backtrack ();
  void end_backtrack ();
  void before_restart ();
  void after_restart ();
  void write (FILE *);
};

} // namespace TA100
} // namespace CaDiCaL
#endif
