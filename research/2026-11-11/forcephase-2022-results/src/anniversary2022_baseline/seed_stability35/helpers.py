"""Exact public baseline helper bodies, selected without behavior changes.
Source: imported evaluation commit0d82f6ed932e3f5ad0bde8d96d847dadc9ee8aa0;
common.py SHA256 a5f9c7d490b7dbf51bc27894e430eb3f07b259fe45dd6f5e895b6556ec2ebe87. Model check runs ONLY in a resource-bounded child.
"""
import hashlib
import json
import os
import re
import time
from pathlib import Path

ACTIONS = {
    "D": ["--phase=1", "--forcephase=0"],
    "Fplus": ["--phase=1", "--forcephase=1"],
    "Fminus": ["--phase=0", "--forcephase=1"],
}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fingerprint(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w") as f:
        json.dump(obj, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def read(path):
    return json.loads(Path(path).read_text())


def utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_stats(text):
    values = {}
    for key in ["conflicts", "decisions", "propagations", "restarts", "rephased"]:
        # Top-level statistics only ("c conflicts:"). CaDiCaL 3.0.1 also prints indented sub-statistics such as
        # "c   conflicts: 0 ... per warmup" after the main entry; matching those recorded 0 conflicts (fixed 2026-11-08).
        matches = re.findall(r"^c " + key + r":\s+([0-9]+)(?:\s|$)", text, re.M)
        values[key] = int(matches[-1]) if matches else None
    return values


def check_model(path, log):
    values = {}
    with Path(log).open(errors="replace") as f:
        for line in f:
            if line.startswith("v "):
                for word in line[2:].split():
                    lit = int(word)
                    if not lit:
                        continue
                    var, truth = abs(lit), lit > 0
                    if var in values and values[var] != truth:
                        return False
                    values[var] = truth
    clause = []
    nv = None
    declared = actual = 0
    with Path(path).open() as f:
        for line in f:
            line = line.lstrip()
            if not line or line.startswith("c"):
                continue
            if line.startswith("p"):
                _, fmt, n, m = line.split()
                if fmt != "cnf" or nv is not None:
                    return False
                nv, declared = int(n), int(m)
                continue
            for word in line.split():
                lit = int(word)
                if lit:
                    if nv is None or abs(lit) > nv:
                        return False
                    clause.append(lit)
                else:
                    if not any(values.get(abs(x)) == (x > 0) for x in clause):
                        return False
                    clause = []
                    actual += 1
    return nv is not None and not clause and actual == declared and all(v <= nv for v in values)


def process_state(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return {"start_ticks": fields[19], "cpu_s": (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")}
    except FileNotFoundError:
        return None
