// Cheap static CNF features for online-tuning-forcephase.
//
//   cnffeatures <cnf>
//
// Prints one JSON object with the same 's_*' features that the in-solver
// controller computes while parsing (see solver/fpcontrol.cpp), plus the
// CPU time used.  Clauses are counted as given (duplicate literals and
// tautologies are not removed), variables are the distinct variables that
// occur in some clause.  Compressed inputs (.xz/.gz/.bz2/.zst) are read via
// a decompression pipe.

#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>

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

static double cpu_time (void) {
  struct rusage u;
  double res = 0;
  getrusage (RUSAGE_SELF, &u);
  res += u.ru_utime.tv_sec + 1e-6 * u.ru_utime.tv_usec;
  res += u.ru_stime.tv_sec + 1e-6 * u.ru_stime.tv_usec;
  getrusage (RUSAGE_CHILDREN, &u);
  res += u.ru_utime.tv_sec + 1e-6 * u.ru_utime.tv_usec;
  res += u.ru_stime.tv_sec + 1e-6 * u.ru_stime.tv_usec;
  return res;
}

static double ratio (double a, double b) { return b > 0 ? a / b : NAN; }

static void print (const char *name, double x, int last) {
  if (isnan (x))
    printf ("\"%s\":null%s", name, last ? "" : ",");
  else
    printf ("\"%s\":%.6g%s", name, x, last ? "" : ",");
}

int main (int argc, char **argv) {
  if (argc != 2) {
    fprintf (stderr, "usage: cnffeatures <cnf>\n");
    return 2;
  }
  int is_pipe;
  FILE *f = open_input (argv[1], &is_pipe);
  if (!f) {
    fprintf (stderr, "cnffeatures: can not read %s\n", argv[1]);
    return 2;
  }
  long header_vars = -1, header_clauses = -1;
  int ch;
  for (;;) {
    ch = getc (f);
    if (ch == 'c') {
      while ((ch = getc (f)) != '\n' && ch != EOF)
        ;
      continue;
    }
    if (ch == 'p')
      break;
    if (ch == EOF || !isspace (ch)) {
      fprintf (stderr, "cnffeatures: missing header\n");
      return 2;
    }
  }
  if (fscanf (f, " cnf %ld %ld", &header_vars, &header_clauses) != 2) {
    fprintf (stderr, "cnffeatures: invalid header\n");
    return 2;
  }
  unsigned char *seen = calloc (header_vars + 1, 1);
  long distinct = 0;
  long clauses = 0, lits = 0, pos = 0, unit = 0, bin = 0, ter = 0, horn = 0,
       antihorn = 0;
  long size = 0, cpos = 0, lit;
  for (;;) {
    ch = getc (f);
    if (ch == EOF)
      break;
    if (isspace (ch))
      continue;
    if (ch == 'c') {
      while ((ch = getc (f)) != '\n' && ch != EOF)
        ;
      continue;
    }
    ungetc (ch, f);
    if (fscanf (f, "%ld", &lit) != 1) {
      fprintf (stderr, "cnffeatures: parse error\n");
      return 2;
    }
    if (lit) {
      long v = labs (lit);
      if (v > header_vars) {
        fprintf (stderr, "cnffeatures: literal exceeds header\n");
        return 2;
      }
      if (!seen[v])
        seen[v] = 1, distinct++;
      size++;
      cpos += (lit > 0);
    } else {
      clauses++, lits += size, pos += cpos;
      unit += (size == 1), bin += (size == 2), ter += (size == 3);
      horn += (cpos <= 1), antihorn += (size - cpos <= 1);
      size = cpos = 0;
    }
  }
  if (is_pipe)
    pclose (f);
  else
    fclose (f);
  printf ("{");
  print ("header_vars", header_vars, 0);
  print ("header_clauses", header_clauses, 0);
  print ("vars", distinct, 0);
  print ("clauses", clauses, 0);
  print ("s_log_vars", log10 (1.0 + distinct), 0);
  print ("s_log_clauses", log10 (1.0 + clauses), 0);
  print ("s_cv_ratio", ratio (clauses, distinct), 0);
  print ("s_mean_len", ratio (lits, clauses), 0);
  print ("s_unit_frac", ratio (unit, clauses), 0);
  print ("s_bin_frac", ratio (bin, clauses), 0);
  print ("s_ter_frac", ratio (ter, clauses), 0);
  print ("s_pos_frac", ratio (pos, lits), 0);
  print ("s_horn_frac", ratio (horn, clauses), 0);
  print ("s_antihorn_frac", ratio (antihorn, clauses), 0);
  print ("cpu_time", cpu_time (), 1);
  printf ("}\n");
  return 0;
}
