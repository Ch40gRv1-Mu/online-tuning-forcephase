// Satisfiability-preserving CNF transformations for online-tuning-forcephase.
//
//   cnfscramble <in.cnf> <out.cnf> <mode> <seed>
//
// Modes (all bijective on assignments, hence preserve SAT/UNSAT; models map
// back by the inverse transformation):
//   shuffle  shuffle clause order and literal order inside clauses
//   perm     'shuffle' plus a random renaming (permutation) of variables;
//            signs are kept, so the polarity bias of the encoding is kept
//   flipall  negate every literal (variable x is renamed to NOT x);
//            clause and literal order are kept
//   flipr    negate the literals of a random half of the variables (each
//            variable independently with probability 1/2); order is kept
// The random generator is seeded with <seed> only (splitmix64), so outputs
// are reproducible.  Input may be compressed (.xz/.gz/.bz2/.zst).

#include <ctype.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint64_t state;
static uint64_t next (void) {
  uint64_t z = (state += 0x9e3779b97f4a7c15ull);
  z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ull;
  z = (z ^ (z >> 27)) * 0x94d049bb133111ebull;
  return z ^ (z >> 31);
}
static uint64_t pick (uint64_t n) { return next () % n; }

static FILE *open_input (const char *path, int *pipe) {
  const char *cmd = 0;
  size_t n = strlen (path);
  if (n > 3 && !strcmp (path + n - 3, ".xz"))
    cmd = "xz -dc";
  else if (n > 3 && !strcmp (path + n - 3, ".gz"))
    cmd = "gzip -dc";
  else if (n > 4 && !strcmp (path + n - 4, ".bz2"))
    cmd = "bzip2 -dc";
  else if (n > 4 && !strcmp (path + n - 4, ".zst"))
    cmd = "zstd -dcq";
  if (!cmd) {
    *pipe = 0;
    return fopen (path, "r");
  }
  char *buf = malloc (strlen (cmd) + n + 8);
  sprintf (buf, "%s '%s'", cmd, path);
  *pipe = 1;
  FILE *f = popen (buf, "r");
  free (buf);
  return f;
}

static void die (const char *msg) {
  fprintf (stderr, "cnfscramble: %s\n", msg);
  exit (1);
}

int main (int argc, char **argv) {
  if (argc != 5)
    die ("usage: cnfscramble <in.cnf> <out.cnf> shuffle|perm|flipall|flipr <seed>");
  const char *mode = argv[3];
  int m_shuffle = !strcmp (mode, "shuffle"), m_perm = !strcmp (mode, "perm");
  int m_flipall = !strcmp (mode, "flipall"), m_flipr = !strcmp (mode, "flipr");
  if (!(m_shuffle || m_perm || m_flipall || m_flipr))
    die ("unknown mode");
  state = strtoull (argv[4], 0, 10) * 0x2545F4914F6CDD1Dull + 12345;
  int is_pipe;
  FILE *in = open_input (argv[1], &is_pipe);
  if (!in)
    die ("can not read input");
  int ch;
  for (;;) {
    ch = getc (in);
    if (ch == 'c') {
      while ((ch = getc (in)) != '\n' && ch != EOF)
        ;
      continue;
    }
    if (ch == 'p')
      break;
    if (ch == EOF || !isspace (ch))
      die ("missing header");
  }
  long vars, clauses;
  if (fscanf (in, " cnf %ld %ld", &vars, &clauses) != 2)
    die ("invalid header");
  size_t cap = 1 << 20, n = 0;
  int *lits = malloc (cap * sizeof *lits);
  size_t ccap = clauses + 1, nc = 0;
  size_t *start = malloc ((ccap + 1) * sizeof *start);
  start[0] = 0;
  long lit;
  for (;;) {
    ch = getc (in);
    if (ch == EOF)
      break;
    if (isspace (ch))
      continue;
    if (ch == 'c') {
      while ((ch = getc (in)) != '\n' && ch != EOF)
        ;
      continue;
    }
    ungetc (ch, in);
    if (fscanf (in, "%ld", &lit) != 1)
      die ("parse error");
    if (labs (lit) > vars)
      die ("literal exceeds header");
    if (lit) {
      if (n == cap)
        lits = realloc (lits, (cap *= 2) * sizeof *lits);
      lits[n++] = (int) lit;
    } else {
      if (nc + 1 >= ccap)
        start = realloc (start, ((ccap *= 2) + 1) * sizeof *start);
      start[++nc] = n;
    }
  }
  if (is_pipe)
    pclose (in);
  else
    fclose (in);
  // variable map: x -> sign[x] * map[x]
  int *map = malloc ((vars + 1) * sizeof *map);
  for (long v = 0; v <= vars; v++)
    map[v] = (int) v;
  if (m_perm)
    for (long v = vars; v > 1; v--) {
      long u = 1 + (long) pick ((uint64_t) v);
      int t = map[v];
      map[v] = map[u];
      map[u] = t;
    }
  if (m_flipall)
    for (long v = 1; v <= vars; v++)
      map[v] = -map[v];
  if (m_flipr)
    for (long v = 1; v <= vars; v++)
      if (next () & 1)
        map[v] = -map[v];
  size_t *order = malloc ((nc + 1) * sizeof *order);
  for (size_t i = 0; i < nc; i++)
    order[i] = i;
  if (m_shuffle || m_perm) {
    for (size_t i = nc; i > 1; i--) {
      size_t j = pick (i);
      size_t t = order[i - 1];
      order[i - 1] = order[j];
      order[j] = t;
    }
    for (size_t c = 0; c < nc; c++) {
      size_t a = start[c], b = start[c + 1];
      for (size_t i = b - a; i > 1; i--) {
        size_t j = pick (i);
        int t = lits[a + i - 1];
        lits[a + i - 1] = lits[a + j];
        lits[a + j] = t;
      }
    }
  }
  FILE *out = fopen (argv[2], "w");
  if (!out)
    die ("can not write output");
  fprintf (out, "p cnf %ld %zu\n", vars, nc);
  for (size_t k = 0; k < nc; k++) {
    size_t c = order[k];
    for (size_t i = start[c]; i < start[c + 1]; i++) {
      int l = lits[i];
      int v = abs (l), m = map[v];
      fprintf (out, "%d ", l < 0 ? -m : m);
    }
    fputs ("0\n", out);
  }
  if (fclose (out))
    die ("write error");
  return 0;
}
