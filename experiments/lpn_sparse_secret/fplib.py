"""Shared helpers for the LPN sparse-secret experiment: static
configurations, DIMACS I/O, solver invocation, model and proof checking.
Pure stdlib.

Paths (all overridable by environment variables):
  LPN_WORK        working directory for binaries, CNFs, raw logs, proofs
                  (default: $FP_DATA/lpn_sparse_secret if FP_DATA is set,
                  else ~/lpn-sparse-secret-work)
  LPN_CADICAL     CaDiCaL binary (default: $LPN_WORK/bin/cadical, see build.sh)
  LPN_LRAT_CHECK  lrat-check binary (default: $LPN_WORK/bin/lrat-check)
"""

import hashlib
import lzma
import os
import re
import subprocess
import sys
import time
from pathlib import Path

PKG = Path(__file__).resolve().parent
RESULTS = PKG / "results"
_default_work = (Path(os.environ["FP_DATA"]) / "lpn_sparse_secret" if os.environ.get("FP_DATA")
                 else Path.home() / "lpn-sparse-secret-work")
FP_WORK = Path(os.environ.get("LPN_WORK", _default_work))
CADICAL = Path(os.environ.get("LPN_CADICAL", FP_WORK / "bin" / "cadical"))
LRAT_CHECK = Path(os.environ.get("LPN_LRAT_CHECK", FP_WORK / "bin" / "lrat-check"))
DRAT_TRIM = Path(os.environ.get("LPN_DRAT_TRIM", FP_WORK / "bin" / "drat-trim"))

# Static configurations (EXPERIMENT_PROTOCOL.md section 2). Every relevant
# option is spelled out explicitly; nothing relies on the default value.
CONFIGS = {
    "D": ["--phase=1", "--forcephase=0"],
    "Im": ["--phase=0", "--forcephase=0"],  # I-  : negative init only
    "Fm": ["--phase=0", "--forcephase=1"],  # F-  : forced negative
    "Fp": ["--phase=1", "--forcephase=1"],  # F+  : forced positive
    "D_noR": ["--phase=1", "--forcephase=0", "--rephase=0"],
    "Im_noR": ["--phase=0", "--forcephase=0", "--rephase=0"],
    # S: saved-only CLI diagnostic (docs/SOURCE_AUDIT.md section 1)
    "S": ["--phase=0", "--forcephase=0", "--target=0", "--rephase=0",
          "--stubbornIOfocused=0"],
}
CONFIG_LABELS = {"D": "D", "Im": "I−", "Fm": "F−", "Fp": "F+",
                 "D_noR": "D/no-R", "Im_noR": "I−/no-R", "S": "S"}


def open_cnf(path):
    path = str(path)
    if path.endswith(".xz"):
        return lzma.open(path, "rt")
    return open(path, "r")


def parse_dimacs(path):
    """Return (nvars, clauses). Tolerates missing/incorrect header counts."""
    nvars, clauses, cur = 0, [], []
    with open_cnf(path) as f:
        for line in f:
            if not line or line[0] in "cp%":
                if line.startswith("p"):
                    nvars = max(nvars, int(line.split()[2]))
                continue
            for tok in line.split():
                lit = int(tok)
                if lit == 0:
                    clauses.append(cur)
                    cur = []
                else:
                    cur.append(lit)
                    nvars = max(nvars, abs(lit))
    if cur:
        clauses.append(cur)
    return nvars, clauses


def write_dimacs(path, nvars, clauses):
    with open(path, "w") as f:
        f.write(f"p cnf {nvars} {len(clauses)}\n")
        for c in clauses:
            f.write(" ".join(map(str, c)) + " 0\n")


def parse_witness(stdout):
    vals = {}
    for line in stdout.splitlines():
        if line.startswith("v "):
            for tok in line[2:].split():
                lit = int(tok)
                if lit:
                    vals[abs(lit)] = lit > 0
    return vals


def check_model(cnf_path, vals):
    """Stream the ORIGINAL CNF and check every clause is satisfied."""
    cur_ok = False
    with open_cnf(cnf_path) as f:
        for line in f:
            if not line or line[0] in "cp%":
                continue
            for tok in line.split():
                lit = int(tok)
                if lit == 0:
                    if not cur_ok:
                        return False
                    cur_ok = False
                elif not cur_ok:
                    v = vals.get(abs(lit))
                    if v is not None and v == (lit > 0):
                        cur_ok = True
    return True


STATS_PATTERNS = {
    "conflicts": r"^c conflicts:\s+(\d+)",
    "decisions": r"^c decisions:\s+(\d+)",
    "propagations": r"^c propagations:\s+(\d+)",
    "restarts": r"^c restarts:\s+(\d+)",
    "rephased": r"^c rephased:\s+(\d+)",
    "stabilizing": r"^c stabilizing:\s+(\d+)",
    "learned": r"^c learned:\s+(\d+)",
    "process_time": r"^c total process time since initialization:\s+([\d.]+)",
    "max_rss_mb": r"^c maximum resident set size of process:\s+([\d.]+)",
}


def parse_stats(stdout):
    out = {}
    for key, pat in STATS_PATTERNS.items():
        m = re.search(pat, stdout, re.M)
        if m:
            out[key] = float(m.group(1)) if "." in m.group(1) else int(m.group(1))
    return out


def run_solver(cnf, config, extra=(), binary=CADICAL, timeout=None,
               proof=None, stdout_path=None, hard_kill_grace=30):
    """Run one solver process. Returns dict with status, exit code, child
    CPU time (user+sys via wait4), wall time, peak RSS and parsed stats.
    `timeout` is passed to CaDiCaL as its own (wall-clock) `-t` limit; the
    runner additionally hard-kills at timeout + grace."""
    cmd = [str(binary), *CONFIGS[config], *extra]
    if timeout is not None:
        cmd += ["-t", str(int(timeout))]
    cmd.append(str(cnf))
    if proof is not None:
        cmd.append(str(proof))
    tmp_out = stdout_path is None
    if tmp_out:
        import tempfile
        fd, stdout_path = tempfile.mkstemp(prefix="fp-run-", suffix=".log")
        os.close(fd)
    t0 = time.monotonic()
    with open(stdout_path, "w") as out_f:
        p = subprocess.Popen(cmd, stdout=out_f, stderr=subprocess.STDOUT)
        deadline = None if timeout is None else t0 + timeout + hard_kill_grace
        killed = False
        while True:
            pid, status, ru = os.wait4(p.pid, os.WNOHANG)
            if pid:
                break
            if deadline and time.monotonic() > deadline and not killed:
                p.kill()
                killed = True
            time.sleep(0.01)
    p.returncode = os.waitstatus_to_exitcode(status)  # keep Popen quiet
    wall = time.monotonic() - t0
    stdout = Path(stdout_path).read_text(errors="replace")
    if tmp_out:
        os.unlink(stdout_path)
    code = p.returncode
    res = {
        "cmd": cmd,
        "exit_code": code,
        "wall_s": wall,
        "cpu_s": ru.ru_utime + ru.ru_stime,
        "user_s": ru.ru_utime,
        "maxrss_bytes": ru.ru_maxrss if sys.platform == "darwin" else ru.ru_maxrss * 1024,
        "killed": killed,
    }
    if code == 10:
        res["status"] = "SAT"
    elif code == 20:
        res["status"] = "UNSAT"
    elif killed:
        res["status"] = "TIMEOUT"
    elif code == 0:
        res["status"] = "UNKNOWN"  # CaDiCaL hit its own time/conflict limit
    elif code < 0:
        res["status"] = "CRASH"  # killed by a signal (e.g. SIGSEGV, SIGKILL)
    else:
        res["status"] = "ERROR"
    res.update(parse_stats(stdout))
    res["_stdout"] = stdout
    return res


def lrat_check(cnf, proof, timeout=600):
    try:
        p = subprocess.run([str(LRAT_CHECK), str(cnf), str(proof)],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "CHECK_TIMEOUT"
    out = p.stdout + p.stderr
    if re.search(r"^c VERIFIED|^s VERIFIED", out, re.M):
        return "VERIFIED"
    return "FAILED:" + out[-300:].replace("\n", " | ")


def drat_check(cnf, proof, timeout=600):
    try:
        p = subprocess.run([str(DRAT_TRIM), str(cnf), str(proof), "-t",
                            str(timeout)], capture_output=True, text=True,
                           timeout=timeout + 30)
    except subprocess.TimeoutExpired:
        return "CHECK_TIMEOUT"
    out = p.stdout + p.stderr
    if re.search(r"^s VERIFIED", out, re.M):
        return "VERIFIED"
    if "TIMEOUT" in out:
        return "CHECK_TIMEOUT"
    return "FAILED:" + out[-300:].replace("\n", " | ")


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()
