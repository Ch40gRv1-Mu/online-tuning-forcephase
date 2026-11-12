// R53 streaming syntax histogram. No assignments, propagation or SAT solving.
#include <array>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <ctime>
#include <iostream>
#include <stdexcept>
#include <string>
#include <unistd.h>

class Input {
  std::array<unsigned char, 65536> buffer{};
  size_t at = 0, size = 0;
  bool line_start = true;
  int get() {
    if (at == size) { size = std::fread(buffer.data(), 1, buffer.size(), stdin); at = 0; }
    return at == size ? EOF : buffer[at++];
  }
public:
  bool token(std::string &out) {
    out.clear(); int c;
    for (;;) {
      c = get(); if (c == EOF) return false;
      if (c == '\n') { line_start = true; continue; }
      if (c == ' ' || c == '\r' || c == '\t' || c == '\f') continue;
      if (line_start && c == 'c') {
        do { c = get(); } while (c != EOF && c != '\n');
        line_start = true;
        if (c == EOF) return false;
        continue;
      }
      line_start = false; break;
    }
    for (;;) {
      if (out.size() >= 31) throw std::runtime_error("oversized token");
      out.push_back(char(c)); c = get();
      if (c == EOF) return true;
      if (c == '\n') { line_start = true; return true; }
      if (c == ' ' || c == '\r' || c == '\t' || c == '\f') return true;
    }
  }
};

static int64_t number(const std::string &s) {
  int64_t v = 0;
  const char *first = s.data();
  if (!s.empty() && s[0] == '+') ++first;
  if (first == s.data() + s.size()) throw std::runtime_error("empty integer");
  const auto result = std::from_chars(first, s.data() + s.size(), v);
  if (result.ec != std::errc() || result.ptr != s.data() + s.size()) throw std::runtime_error("invalid integer");
  return v;
}

int main(int argc, char **argv) {
  alarm(120);
  FILE *packed = nullptr;
  const double began = double(std::clock()) / CLOCKS_PER_SEC;
  try {
    if (argc != 2) throw std::runtime_error("expected owned packed-bin path");
    packed = std::fopen(argv[1], "wb");
    if (!packed) throw std::runtime_error("cannot create packed bins");
    Input input; std::string word;
    bool header = false;
    uint64_t n = 0, m = 0, clauses = 0, literals = 0, width = 0, positive = 0;
    std::array<uint64_t, 63> counts{};
    while (input.token(word)) {
      if (word == "p") {
        if (header || width || clauses) throw std::runtime_error("duplicate/misplaced header");
        if (!input.token(word) || word != "cnf") throw std::runtime_error("expected cnf");
        if (!input.token(word)) throw std::runtime_error("missing n");
        const int64_t nn = number(word);
        if (!input.token(word)) throw std::runtime_error("missing m");
        const int64_t mm = number(word);
        if (nn < 0 || mm < 0 || mm > 20000000) throw std::runtime_error("header/resource bound");
        n = nn; m = mm; header = true; continue;
      }
      if (!header) throw std::runtime_error("literal before header");
      const int64_t literal = number(word);
      if (literal) {
        if (literal == INT64_MIN || uint64_t(literal < 0 ? -literal : literal) > n)
          throw std::runtime_error("variable outside header");
        ++width; ++literals; positive += literal > 0;
      } else {
        if (++clauses > m) throw std::runtime_error("extra clause");
        const uint64_t upper[] = {0, 1, 2, 3, 4, 8, 16, 32};
        unsigned char w = 0;
        while (w < 8 && width > upper[w]) ++w;
        unsigned char p = !width ? 3 : (!positive ? 0 : (4 * positive < width ? 1 :
          (2 * positive < width ? 2 : (2 * positive == width ? 3 :
          (4 * positive <= 3 * width ? 4 : (positive < width ? 5 : 6))))));
        ++counts[7 * w + p];
        const unsigned char bins[] = {w, p};
        if (std::fwrite(bins, 1, 2, packed) != 2) throw std::runtime_error("packed-bin write failed");
        width = positive = 0;
      }
      if ((literals & 8191) == 0 && double(std::clock()) / CLOCKS_PER_SEC - began > 16)
        throw std::runtime_error("native16CPU limit");
    }
    if (!header || width || clauses != m) throw std::runtime_error("incomplete formula");
    if (std::fclose(packed)) throw std::runtime_error("packed-bin close failed");
    packed = nullptr;
    std::cout << "{\"schema\":\"forcephase.stream_clause_table.R53.v1\",\"header_variables\":" << n
      << ",\"clauses\":" << clauses << ",\"literals\":" << literals << ",\"counts\":[";
    for (unsigned j = 0; j < 63; ++j) { if (j) std::cout << ','; std::cout << counts[j]; }
    std::cout << "],\"SAT_calls\":0}\n";
    return 0;
  } catch (const std::exception &e) {
    if (packed) std::fclose(packed);
    std::cerr << e.what() << '\n'; return 2;
  }
}
