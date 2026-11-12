import csv
import hashlib
import json
import math
import os
import re
import resource
import time
from pathlib import Path

ACTIONS = {
    "D": ["--phase=1", "--forcephase=0"],
    "Fplus": ["--phase=1", "--forcephase=1"],
    "Fminus": ["--phase=0", "--forcephase=1"],
}
VALID_NONANSWERS = {"CPU_TIMEOUT", "UNKNOWN"}


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


def source_identity():
    # Presentation/exports do not change an already executed physical measurement.
    names = ["common.py", "stage_inputs.py", "run_one.py", "run_baselines.py"]
    return {name: sha(Path(__file__).parent/name) for name in names}


def load_manifest(path):
    with Path(path).open(newline="") as f:
        rows = list(csv.DictReader(f))
    keys = [r["instance_key"] for r in rows]
    if not rows or len(keys) != len(set(keys)):
        raise ValueError("empty or duplicate manifest")
    for r in rows:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", r["instance_key"]):
            raise ValueError("unsafe input identifier")
        if r["role"] not in {"baseline_development", "qualification"}:
            raise ValueError("unapproved input role")
    return rows


def validate_formal_cohort(spec, manifest, rows):
    if any(r["role"] != "baseline_development" for r in rows):
        raise ValueError("formal cohort has unapproved roles")
    if len(rows) == 5355 and not spec.get("cohort_filter_receipt_path"):
        return
    path = spec.get("cohort_filter_receipt_path")
    if not path or sha(path) != spec.get("cohort_filter_receipt_sha256"):
        raise ValueError("subset requires a frozen external-filter receipt")
    receipt = read(path)
    if receipt.get("policy") != "official_all_tracks_unsolved_v1" or receipt["manifest_sha256"] != sha(manifest):
        raise ValueError("unsupported filter or mismatched filtered manifest")
    selected = {r["instance_key"] for r in rows}
    retained, excluded = set(receipt["retained_ids"]), set(receipt["excluded_ids"])
    if selected != retained or retained & excluded or len(retained | excluded) != 5355 or \
            receipt["master_inputs"] != 5355 or receipt["retained_count"] != len(rows) or \
            receipt["excluded_count"] != len(excluded) or receipt.get("selection_uses_our_phase_outcomes") is not False:
        raise ValueError("external filter does not partition the original master")


def validate_spec(spec, manifest, tools=True):
    if spec.get("status") not in {"FROZEN", "QUALIFICATION"}:
        raise ValueError("only frozen or explicitly bounded qualification specifications may execute")
    rows = load_manifest(manifest)
    if len(rows) != spec["expected_inputs"] or sha(manifest) != spec["manifest_sha256"]:
        raise ValueError("manifest identity/count mismatch")
    if spec["status"] == "FROZEN":
        validate_formal_cohort(spec, manifest, rows)
    if spec["status"] == "QUALIFICATION" and (len(rows) > 8 or spec["cutoff_s"] > 10):
        raise ValueError("qualification exceeds 8 inputs / 10 CPU seconds")
    if spec["status"] == "QUALIFICATION" and spec.get("max_physical_cpu_hours", float("inf")) > 0.25:
        raise ValueError("qualification exceeds its quarter-core-hour ceiling")
    if spec["actions"] != ACTIONS or spec["seeds"] != [0]:
        raise ValueError("changed three-action static design")
    for key in ["cutoff_s", "wall_watchdog_s", "max_physical_cpu_hours", "memory_bytes", "proof_limit_bytes", "checker_cpu_s", "checker_wall_s"]:
        if not isinstance(spec.get(key), (float, int)) or not math.isfinite(spec[key]) or spec[key] <= 0:
            raise ValueError("missing or invalid resource limit: " + key)
    if spec["wall_watchdog_s"] < spec["cutoff_s"] or not 1 <= spec["workers"] <= 8:
        raise ValueError("invalid deadline/workers")
    if tools:
        for name in ["solver", "checker"]:
            if sha(spec[name + "_path"]) != spec[name + "_sha256"]:
                raise ValueError("changed " + name)
    return rows


def parse_stats(text):
    values = {}
    for key in ["conflicts", "decisions", "propagations", "restarts", "rephased"]:
        matches = re.findall(r"^c\s+" + key + r":\s+([0-9]+)(?:\s|$)", text, re.M)
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


def cpu_total():
    a = resource.getrusage(resource.RUSAGE_SELF)
    b = resource.getrusage(resource.RUSAGE_CHILDREN)
    return a.ru_utime + a.ru_stime + b.ru_utime + b.ru_stime


def process_state(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return {"start_ticks": fields[19], "cpu_s": (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")}
    except FileNotFoundError:
        return None
