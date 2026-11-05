/* Fractional process CPU budget preserved across exec, Linux qualification required. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

int main(int argc, char **argv) {
  if (argc < 3) { fputs("usage: cpu-budget-exec CPU_SECONDS PROGRAM [ARG...]\n", stderr); return 64; }
  errno = 0;
  char *end = 0;
  double limit = strtod(argv[1], &end);
  if (errno || end == argv[1] || *end || !isfinite(limit) || limit <= 0 || limit > 86400) {
    fputs("invalid CPU budget\n", stderr); return 64;
  }
  struct timespec used;
  if (clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &used)) { perror("clock_gettime"); return 70; }
  double remaining = limit - used.tv_sec - used.tv_nsec / 1e9;
  if (signal(SIGPROF, SIG_DFL) == SIG_ERR) { perror("signal"); return 70; }
  if (remaining <= 0) { raise(SIGPROF); return 70; }
  long long microseconds = (long long) ceil(remaining * 1e6);
  struct itimerval timer = {0};
  timer.it_value.tv_sec = microseconds / 1000000;
  timer.it_value.tv_usec = microseconds % 1000000;
  if (setitimer(ITIMER_PROF, &timer, 0)) { perror("setitimer"); return 70; }
  execvp(argv[2], argv + 2);
  int error = errno;
  perror("execvp");
  return error == ENOENT ? 127 : 126;
}
