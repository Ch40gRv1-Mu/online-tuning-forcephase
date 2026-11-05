// Compile/run only after root commits the observer source/protocol.
#include "ta100_observer.hpp"
#include <cstdio>
int main () {
  if (!CaDiCaL::TA100::Observer::selftest ()) return 1;
  std::puts ("ta100 observer synthetic arithmetic invariants passed");
  return 0;
}
