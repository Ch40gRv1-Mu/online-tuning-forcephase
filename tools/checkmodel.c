// Independent SAT model checker for online-tuning-forcephase.
//
//   checkmodel <cnf> <solver-output>
//
// Reads a DIMACS CNF (plain, or compressed if the name ends in .xz/.gz/.bz2/
// .zst, decompressed via a pipe) and a solver output file in SAT-competition
// format ('s SATISFIABLE' plus 'v' lines).  Checks that the model is
// consistent (no literal and its negation) and satisfies every clause.
// Unassigned variables are allowed only if every clause is satisfied
// without them.  Prints one line 'checkmodel: OK|FAIL <reason>' and exits
// with 0 on success, 1 on failure, 2 on usage or parse errors.

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void die (int code, const char *fmt, const char *arg) {
  printf ("checkmodel: %s ", code == 1 ? "FAIL" : "ERROR");
  printf (fmt, arg);
  printf ("\n");
  exit (code);
}

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

static signed char *val;
static long max_var;

static void set_val (long lit) {
  long v = labs (lit);
  if (v > max_var)
    die (1, "model variable %s exceeds header", "");
  signed char s = lit > 0 ? 1 : -1;
  if (val[v] && val[v] != s)
    die (1, "inconsistent model %s", "");
  val[v] = s;
}

int main (int argc, char **argv) {
  if (argc != 3)
    die (2, "usage: %s <cnf> <solver-output>", argv[0]);
  int is_pipe;
  FILE *cnf = open_input (argv[1], &is_pipe);
  if (!cnf)
    die (2, "can not read '%s'", argv[1]);
  int ch;
  long clauses = 0;
  // skip comments, read header
  for (;;) {
    ch = getc (cnf);
    if (ch == 'c') {
      while ((ch = getc (cnf)) != '\n' && ch != EOF)
        ;
      continue;
    }
    if (ch == 'p')
      break;
    if (ch == EOF || !isspace (ch))
      die (2, "missing header in '%s'", argv[1]);
  }
  if (fscanf (cnf, " cnf %ld %ld", &max_var, &clauses) != 2 || max_var < 0)
    die (2, "invalid header in '%s'", argv[1]);
  val = calloc (max_var + 1, 1);
  // parse model
  FILE *out = fopen (argv[2], "r");
  if (!out)
    die (2, "can not read '%s'", argv[2]);
  char line[1 << 16];
  int sat = 0, seen_end = 0;
  while (fgets (line, sizeof line, out)) {
    if (!strncmp (line, "s SATISFIABLE", 13))
      sat = 1;
    if (line[0] != 'v')
      continue;
    char *p = line + 1;
    for (;;) {
      while (*p == ' ' || *p == '\t')
        p++;
      if (!*p || *p == '\n')
        break;
      char *end;
      long lit = strtol (p, &end, 10);
      if (end == p)
        die (2, "invalid 'v' line in '%s'", argv[2]);
      p = end;
      if (!lit)
        seen_end = 1;
      else
        set_val (lit);
    }
  }
  fclose (out);
  if (!sat)
    die (1, "no 's SATISFIABLE' line in '%s'", argv[2]);
  if (!seen_end)
    die (1, "model not terminated by 0 in '%s'", argv[2]);
  // check clauses
  long checked = 0, lit;
  int satisfied = 0, empty = 1;
  for (;;) {
    ch = getc (cnf);
    if (ch == EOF)
      break;
    if (isspace (ch))
      continue;
    if (ch == 'c') {
      while ((ch = getc (cnf)) != '\n' && ch != EOF)
        ;
      continue;
    }
    ungetc (ch, cnf);
    if (fscanf (cnf, "%ld", &lit) != 1)
      die (2, "invalid literal in '%s'", argv[1]);
    if (labs (lit) > max_var)
      die (2, "literal exceeds header in '%s'", argv[1]);
    if (lit) {
      empty = 0;
      if ((lit > 0 && val[lit] > 0) || (lit < 0 && val[-lit] < 0))
        satisfied = 1;
    } else {
      if (empty || !satisfied) {
        char buf[64];
        sprintf (buf, "%ld", checked + 1);
        die (1, "clause %s not satisfied", buf);
      }
      checked++;
      satisfied = 0, empty = 1;
    }
  }
  if (!empty)
    die (2, "last clause not terminated in '%s'", argv[1]);
  if (is_pipe)
    pclose (cnf);
  else
    fclose (cnf);
  if (checked != clauses) {
    char buf[64];
    sprintf (buf, "%ld", checked);
    printf ("checkmodel: note header clause count differs, checked %s\n",
            buf);
  }
  printf ("checkmodel: OK %ld clauses\n", checked);
  return 0;
}
