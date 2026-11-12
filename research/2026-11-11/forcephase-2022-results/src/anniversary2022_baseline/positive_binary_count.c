/* Count raw DIMACS clauses and verify the GBD hash in one pass on stdin. */
#include <ctype.h>
#include <inttypes.h>
#include <limits.h>
#include <math.h>
#include <openssl/evp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>

static EVP_MD_CTX *digest;
static unsigned char normalized[1 << 16];
static size_t used;

static void fail(const char *reason) {
    fprintf(stderr, "%s\n", reason);
    exit(2);
}

static void flush(void) {
    if (used && EVP_DigestUpdate(digest, normalized, used) != 1)
        fail("digest update failed");
    used = 0;
}

static void append(unsigned char value) {
    normalized[used++] = value;
    if (used == sizeof normalized) flush();
}

static double contrast(double positive, double negative) {
    double total = positive + negative;
    return total ? (positive - negative) / total : 0;
}

int main(int argc, char **argv) {
    int pressure_mode = argc == 2 && !strcmp(argv[1], "--pressure");
    if (argc != 1 && !pressure_mode) fail("unknown parser option");
    digest = EVP_MD_CTX_new();
    if (!digest || EVP_DigestInit_ex(digest, EVP_md5(), NULL) != 1)
        fail("cannot initialize GBD digest");
    uint64_t vars = 0, declared = 0, clauses = 0, binary = 0, posbin = 0;
    uint64_t length = 0, positive = 0;
    uint64_t pure[2] = {0}, occurrences = 0;
    double aligned[2] = {0}, opposed[2] = {0}, conflict[2] = {0};
    int ch, header = 0, has_token = 0;
    while ((ch = getc_unlocked(stdin)) != EOF) {
        if (isspace(ch)) continue;
        if (ch == 'c') {
            while ((ch = getc_unlocked(stdin)) != EOF && ch != '\n') {}
            continue;
        }
        if (ch == 'p' && !header) {
            char line[256], extra;
            if (!fgets(line, sizeof line, stdin) ||
                sscanf(line, " cnf %" SCNu64 " %" SCNu64 " %c", &vars, &declared, &extra) != 2)
                fail("invalid DIMACS header");
            header = 1;
            continue;
        }
        if (!header) fail("missing DIMACS header");
        if (has_token) append(' ');
        has_token = 1;
        int negative = (ch == '-');
        if (negative) {
            append('-');
            ch = getc_unlocked(stdin);
        }
        if (ch < '0' || ch > '9') fail("invalid DIMACS token");
        uint64_t value = 0;
        do {
            uint64_t digit = (uint64_t)(ch - '0');
            if (value > (UINT64_MAX - digit) / 10) fail("literal overflow");
            value = 10 * value + digit;
            append((unsigned char)ch);
            ch = getc_unlocked(stdin);
        } while (ch >= '0' && ch <= '9');
        if (ch != EOF && !isspace(ch)) fail("missing literal separator");
        if (value > vars) fail("literal exceeds declared variables");
        if (value) {
            ++length;
            positive += !negative;
        } else {
            if (negative) fail("invalid negative clause terminator");
            ++clauses;
            binary += (length == 2);
            posbin += (length == 2 && positive == 2);
            if (pressure_mode && length) {
                occurrences += length;
                pure[0] += positive == length;
                pure[1] += positive == 0;
                double weight = length < INT_MAX ? ldexp(1.0, -(int)length) : 0;
                uint64_t satisfied[2] = {positive, length - positive};
                for (int s = 0; s < 2; ++s) {
                    if (satisfied[s] == 1) aligned[s] += weight;
                    if (satisfied[s] == 0) {
                        opposed[s] += length * weight;
                        conflict[s] += weight;
                    }
                }
            }
            length = positive = 0;
        }
    }
    if (!header || ferror(stdin) || length || clauses != declared)
        fail("incomplete DIMACS input or clause count mismatch");
    flush();
    unsigned char hash[EVP_MAX_MD_SIZE];
    unsigned int hash_size;
    if (EVP_DigestFinal_ex(digest, hash, &hash_size) != 1 || hash_size != 16)
        fail("digest finalization failed");
    EVP_MD_CTX_free(digest);
    struct rusage usage;
    if (getrusage(RUSAGE_SELF, &usage)) fail("getrusage failed");
    double cpu = usage.ru_utime.tv_sec + usage.ru_stime.tv_sec +
                 (usage.ru_utime.tv_usec + usage.ru_stime.tv_usec) * 1e-6;
    for (unsigned int i = 0; i < hash_size; ++i) printf("%02x", hash[i]);
    printf(" %" PRIu64 " %" PRIu64 " %" PRIu64 " %.6f", clauses, binary, posbin, cpu);
    if (pressure_mode && clauses) {
        printf(" %.12g %.12g %.12g %.12g %.12g %.12g %.12g %.12g",
               contrast(aligned[0], aligned[1]), contrast(opposed[0], opposed[1]),
               contrast(conflict[0], conflict[1]),
               (aligned[0] + aligned[1] + opposed[0] + opposed[1]) / clauses,
               (double)pure[0] / clauses, (double)pure[1] / clauses,
               (double)binary / clauses, (double)occurrences / clauses);
    }
    putchar('\n');
    return 0;
}
