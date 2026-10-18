#!/usr/bin/env python3
"""Experiment runner for online-tuning-forcephase (stdlib only).

  fprun.py plan  --exp configs/experiments/X.json        # list runs, budget
  fprun.py run   --exp ... [--shard i/n] [--jobs J]      # execute (resumable)
  fprun.py status --exp ...                              # done / missing

An experiment spec names instances (by split from benchmarks/manifest.csv or
an explicit hash list), solver configurations (configs/solver_configs.json),
seeds, the CPU-time cutoff T, a memory limit and the proof policy.  Every
(configuration, instance, seed, ...) tuple gets a content-addressed run id
that includes the solver binary hash and the policy file content, so equal
runs are shared between experiments and never repeated.  Results are
immutable JSON files under $FP_DATA/runs/results/<id[:2]>/<id>.json, raw
logs (stdout, stderr, telemetry, checker output; zstd) under
$FP_DATA/runs/raw/<id[:2]>/<id>/.  Each attempt (also interrupted ones) is
appended to $FP_DATA/runs/attempts/<host>-<pid>.jsonl for the compute
ledger.

Seeds: seed 0 is the original CNF; seed s > 0 is 'cnfscramble perm s'
(variable renaming + clause/literal shuffling, signs kept).  Instance
variants for encoding tests use 'variant' (flipall, flipr:<s>, ...).

Timing: CPU time (user+sys of the solver process from wait4) against T.
The runner polls the solver's CPU time and sends SIGTERM at T (SIGKILL
after a grace period); a run is 'solved' only if the solver answered within
T CPU seconds and the answer was verified (SAT: independent model check
against the CNF given to the solver; UNSAT: LRAT proof checked by lrat-trim
when proof='lrat').  Proof generation counts towards solver time; checker
time is recorded separately.
"""

import argparse
import fcntl
import gzip
import traceback
import hashlib
import json
import os
import random
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import csv
import multiprocessing as mp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("FP_DATA", "/mnt/data/zhaofeng/projects/workspace/online-tuning-forcephase")
LOCAL = os.environ.get("FP_LOCAL", f"/tmp/fp_local_{os.environ.get('USER', 'user')}")
TOOLS = os.path.join(ROOT, "build", "tools")
SCHEMA = 1

STAT_RE = re.compile(r"^c (\w+):\s+(\d+)")
STAT_KEYS = {"conflicts", "decisions", "propagations", "restarts", "rephased", "reused",
             "stabilizing", "learned", "eliminated", "subsumed", "walked", "searches"}


# ------------------------------------------------------------------ helpers

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path):
    with open(path) as f:
        return json.load(f)


def atomic_write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=None, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.link(tmp, path)  # never overwrite an existing result
    except FileExistsError:
        pass
    finally:
        os.unlink(tmp)


def manifest():
    rows = list(csv.DictReader(open(os.path.join(ROOT, "benchmarks", "manifest.csv"))))
    return {r["hash"]: r for r in rows}


def binary_info(variant):
    info = {}
    path = os.path.join(ROOT, "build", variant, "BUILDINFO")
    for line in open(path):
        k, _, v = line.strip().partition("=")
        info[k] = v
    info["path"] = os.path.join(ROOT, "build", variant, "cadical")
    actual = sha256_file(info["path"])
    if actual != info["binary_sha256"]:
        raise SystemExit(f"binary hash mismatch for {variant}: rebuild needed")
    return info


def physical_cores():
    """One logical CPU per physical core among the CPUs we may use."""
    allowed = sorted(os.sched_getaffinity(0))
    seen, cores = set(), []
    for c in allowed:
        try:
            sib = open(f"/sys/devices/system/cpu/cpu{c}/topology/thread_siblings_list").read().strip()
        except OSError:
            sib = str(c)
        if sib not in seen:
            seen.add(sib)
            cores.append(c)
    return cores


# ------------------------------------------------------------ experiments

def load_experiment(path):
    exp = load_json(path)
    exp.setdefault("seeds", [0])
    exp.setdefault("variants", ["orig"])
    exp.setdefault("memory_mb", 16000)
    exp.setdefault("proof", "lrat")
    exp.setdefault("telemetry", True)
    exp.setdefault("extra_args", [])
    exp.setdefault("repeats", [0])
    return exp


def instances_of(exp, man):
    sel = exp["instances"]
    if "hashes" in sel:
        hs = list(sel["hashes"])
    elif "hash_file" in sel:
        hs = [l.split()[0] for l in open(os.path.join(ROOT, sel["hash_file"])) if l.strip() and not l.startswith("#")]
    else:
        splits = set(sel["splits"])
        hs = sorted(h for h, r in man.items() if r["split"] in splits)
    if "filter_years" in sel:
        ys = set(map(str, sel["filter_years"]))
        hs = [h for h in hs if ys & set(man[h]["years"].split("+"))]
    return hs


def config_spec(name, configs):
    if name not in configs:
        raise SystemExit(f"unknown solver configuration {name}")
    c = dict(configs[name])
    c["name"] = name
    c.setdefault("variant", "fpc")
    c.setdefault("args", [])
    c.setdefault("env", {})
    c.setdefault("telemetry", True)
    return c


def plan(exp, man=None, configs=None):
    man = man or manifest()
    configs = configs or load_json(os.path.join(ROOT, "configs", "solver_configs.json"))
    bins = {}
    runs = []
    for cname in exp["configs"]:
        c = config_spec(cname, configs)
        if c["variant"] not in bins:
            bins[c["variant"]] = binary_info(c["variant"])
        policy_sha = None
        if "FPC_POLICY" in c["env"]:
            policy_sha = sha256_file(os.path.join(ROOT, c["env"]["FPC_POLICY"]))
        args = list(c["args"]) + list(exp["extra_args"])
        if exp["proof"] == "lrat":
            args = ["--lrat=1"] + args
        for h in instances_of(exp, man):
            for variant in exp["variants"]:
                for seed in exp["seeds"]:
                  for rep in exp["repeats"]:
                    key = {"schema": SCHEMA, "config_args": args, "env": c["env"], "policy_sha": policy_sha,
                           "binary_sha256": bins[c["variant"]]["binary_sha256"], "instance": h,
                           "variant": variant, "seed": seed, "timeout": exp["timeout"],
                           "memory_mb": exp["memory_mb"], "proof": exp["proof"],
                           "telemetry": bool(c["telemetry"] and exp["telemetry"])}
                    if rep:  # repeated measurement of an otherwise identical run
                        key["repeat"] = rep
                    rid = hashlib.sha1(json.dumps(key, sort_keys=True).encode()).hexdigest()
                    runs.append({"run_id": rid, "key": key, "config": cname, "variant_build": c["variant"],
                                 "binary": bins[c["variant"]]["path"], "exp": exp["name"]})
    return runs


def result_path(rid):
    return os.path.join(DATA, "runs", "results", rid[:2], rid + ".json")


def raw_dir(rid):
    return os.path.join(DATA, "runs", "raw", rid[:2], rid)


# ------------------------------------------------------------- CNF staging

def stage_cnf(h, variant, seed):
    """Return a node-local plain CNF path for (instance, variant, seed)."""
    os.makedirs(os.path.join(LOCAL, "cnf"), exist_ok=True)
    plain = os.path.join(LOCAL, "cnf", h + ".cnf")
    src = os.path.join(DATA, "benchmarks", "cnf", h + ".cnf.xz")
    with open(plain + ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        if not os.path.exists(plain):
            tmp = plain + ".tmp"
            with open(tmp, "wb") as out:
                subprocess.run(["xz", "-dc", src], stdout=out, check=True)
            os.rename(tmp, plain)
    transforms = []
    if variant != "orig":
        transforms.append(tuple(variant.split(":")) if ":" in variant else (variant, "0"))
    if seed:
        transforms.append(("perm", str(seed)))
    if not transforms:
        return plain
    tag = "_".join(f"{m}{s}" for m, s in transforms)
    out = os.path.join(LOCAL, "cnf", f"{h}.{tag}.cnf")
    with open(out + ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        if not os.path.exists(out):
            cur = plain
            for i, (m, s) in enumerate(transforms):
                nxt = out + f".tmp{i}"
                subprocess.run([os.path.join(TOOLS, "cnfscramble"), cur, nxt, m, s], check=True)
                if cur != plain:
                    os.unlink(cur)
                cur = nxt
            os.rename(cur, out)
    return out


# ------------------------------------------------------------- execution

def cpu_of(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            parts = f.read().rsplit(")", 1)[1].split()
        return (int(parts[11]) + int(parts[12])) / os.sysconf("SC_CLK_TCK")
    except (OSError, IndexError, ValueError):
        return None


def run_limited(cmd, env, cpu_limit, mem_mb, core, stdout_path, stderr_path, wall_limit):
    """Run cmd pinned to core; terminate at cpu_limit CPU seconds."""
    def pre():
        import resource
        if core is not None:
            os.sched_setaffinity(0, {core})
        resource.setrlimit(resource.RLIMIT_AS, (mem_mb << 20, mem_mb << 20))
        hard = int(cpu_limit) + 60
        resource.setrlimit(resource.RLIMIT_CPU, (hard, hard + 5))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.setsid()
    t0 = time.time()
    with open(stdout_path, "wb") as so, open(stderr_path, "wb") as se:
        p = subprocess.Popen(cmd, stdout=so, stderr=se, env=env, preexec_fn=pre)
        killed_by = None
        term_sent = None
        while True:
            pid, status, ru = os.wait4(p.pid, os.WNOHANG)
            if pid:
                break
            now = time.time()
            c = cpu_of(p.pid)
            if term_sent is None and ((c is not None and c >= cpu_limit) or now - t0 >= wall_limit):
                killed_by = "cpu" if (c is not None and c >= cpu_limit) else "wall"
                os.killpg(p.pid, signal.SIGTERM)
                term_sent = now
            elif term_sent is not None and now - term_sent > 10:
                os.killpg(p.pid, signal.SIGKILL)
            time.sleep(0.05 if now - t0 < 2 else 0.2)
    wall = time.time() - t0
    code = os.waitstatus_to_exitcode(status)
    return {"exit_code": code, "wall": wall, "cpu_user": ru.ru_utime, "cpu_sys": ru.ru_stime,
            "cpu": ru.ru_utime + ru.ru_stime, "maxrss_kb": ru.ru_maxrss, "terminated_by": killed_by}


def parse_solver_output(path):
    status, stats = None, {}
    has_model_end = False
    with open(path, "rb") as f:
        for raw in f:
            if raw.startswith(b"v "):
                if raw.rstrip().endswith(b" 0"):
                    has_model_end = True
                continue
            line = raw.decode("utf-8", "replace")
            if line.startswith("s "):
                status = line[2:].strip()
            m = STAT_RE.match(line)
            if m and m.group(1) in STAT_KEYS and m.group(1) not in stats:
                stats[m.group(1)] = int(m.group(2))
            if "total process time since initialization" in line:
                try:
                    stats["solver_process_time"] = float(line.split(":")[1].split()[0])
                except (IndexError, ValueError):
                    pass
            if "maximum resident set size" in line:
                try:
                    stats["solver_maxrss_mb"] = float(line.split(":")[1].split()[0])
                except (IndexError, ValueError):
                    pass
    return status, stats, has_model_end


def telemetry_summary(path):
    if not os.path.exists(path):
        return None
    fin, last_win, decision, switches, nlines, cps = None, None, None, 0, 0, []
    with open(path) as f:
        for line in f:
            nlines += 1
            try:
                x = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = x.get("type")
            if t == "final":
                fin = x
            elif t == "window":
                last_win = {k: x[k] for k in ("index", "conflicts", "time", "action")}
            elif t == "decision":
                decision = x
            elif t == "switch":
                switches += 1
            elif t == "checkpoint":
                cps.append({"crossed": x["crossed"], "conflicts": x["conflicts"], "digest": x["digest"]})
    return {"final": fin, "last_window": last_win, "decision": decision, "switch_records": switches,
            "lines": nlines, "checkpoints": cps}


def compress_into(src, dst):
    if os.path.exists(src):
        with open(src, "rb") as fi, gzip.open(dst + ".tmp", "wb", compresslevel=6) as fo:
            shutil.copyfileobj(fi, fo, 1 << 20)
        os.replace(dst + ".tmp", dst)


def verify(code, cnf, stdout_path, proof_path, timeout, mem_mb, workdir):
    t0 = time.time()
    if code == 10:
        out = os.path.join(workdir, "check.txt")
        r = run_limited([os.path.join(TOOLS, "checkmodel"), cnf, stdout_path], dict(os.environ),
                        max(600, timeout), 32000, None, out, out + ".err", 4 * max(600, timeout))
        text = open(out).read().strip()
        ok = r["exit_code"] == 0 and text.startswith("checkmodel: OK")
        return {"method": "checkmodel", "ok": ok, "cpu": r["cpu"], "wall": r["wall"], "output": text[-300:],
                "terminated_by": r["terminated_by"]}
    if code == 20:
        if not proof_path or not os.path.exists(proof_path):
            return {"method": "none", "ok": None, "cpu": 0, "wall": 0, "output": "no proof"}
        out = os.path.join(workdir, "check.txt")
        limit = max(1800, 4 * timeout)
        r = run_limited([os.path.join(TOOLS, "lrat-trim"), "-q", cnf, proof_path], dict(os.environ),
                        limit, 64000, None, out, out + ".err", 2 * limit)
        text = (open(out).read() + open(out + ".err").read()).strip()
        if r["terminated_by"] or r["exit_code"] < 0:
            ok = None  # checker resource limit: unverified
        else:
            ok = r["exit_code"] == 20
        return {"method": "lrat-trim", "ok": ok, "cpu": r["cpu"], "wall": r["wall"], "exit_code": r["exit_code"],
                "output": text[-300:], "terminated_by": r["terminated_by"],
                "proof_bytes": os.path.getsize(proof_path)}
    return {"method": "none", "ok": None, "cpu": 0, "wall": time.time() - t0, "output": ""}


def classify(res, ver, timeout):
    code = res["exit_code"]
    answered = code in (10, 20)
    within = res["cpu"] <= timeout and res["terminated_by"] is None
    err = res.get("stderr_tail", "") + res.get("stdout_tail", "")
    if answered and within:
        if ver["ok"] is True:
            return "solved"
        if ver["ok"] is False:
            return "wrong"
        return "unverified"
    if answered and not within:
        return "timeout"  # answered only after the cutoff
    if res["terminated_by"] is not None:
        return "timeout"
    if code != 0 and ("out of memory" in err or "bad_alloc" in err or "memory" in err.lower()):
        return "memout"
    if code < 0:
        return "crash"
    return "error"


def execute(run, core, attempts_log):
    rid = run["run_id"]
    key = run["key"]
    if os.path.exists(result_path(rid)):
        return "exists"
    host = socket.gethostname()
    start_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    os.makedirs(os.path.join(LOCAL, "work"), exist_ok=True)
    work = tempfile.mkdtemp(prefix=rid[:12] + "_", dir=os.path.join(LOCAL, "work"))
    attempt = {"run_id": rid, "host": host, "core": core, "start": start_utc,
               "slurm_job": os.environ.get("SLURM_JOB_ID"), "array_task": os.environ.get("SLURM_ARRAY_TASK_ID")}
    with open(attempts_log, "a") as f:
        f.write(json.dumps(dict(attempt, event="start")) + "\n")
    try:
        t_stage = time.time()
        cnf = stage_cnf(key["instance"], key["variant"], key["seed"])
        t_stage = time.time() - t_stage
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C"}
        for k, v in key["env"].items():
            env[k] = os.path.join(ROOT, v) if k == "FPC_POLICY" else v
        tel = os.path.join(work, "telemetry.jsonl")
        args = list(key["config_args"])
        if key["telemetry"]:
            if not any(a.startswith("--fpc=") for a in args):
                args.append("--fpc=1")
            env["FPC_LOG"] = tel
        proof = os.path.join(work, "proof.lrat") if key["proof"] == "lrat" else None
        cmd = [run["binary"]] + args + [cnf] + ([proof] if proof else [])
        so, se = os.path.join(work, "stdout.txt"), os.path.join(work, "stderr.txt")
        res = run_limited(cmd, env, key["timeout"], key["memory_mb"], core, so, se,
                          wall_limit=1.5 * key["timeout"] + 60)
        status_line, stats, model_end = parse_solver_output(so)
        res["stdout_tail"] = open(so, "rb").read()[-2000:].decode("utf-8", "replace") if res["exit_code"] not in (10, 20) else ""
        res["stderr_tail"] = open(se, "rb").read()[-2000:].decode("utf-8", "replace")
        ver = verify(res["exit_code"], cnf, so, proof, key["timeout"], key["memory_mb"], work)
        status = classify(res, ver, key["timeout"])
        tsum = telemetry_summary(tel) if key["telemetry"] else None
        rd = raw_dir(rid)
        os.makedirs(rd, exist_ok=True)
        compress_into(so, os.path.join(rd, "stdout.txt.gz"))
        compress_into(se, os.path.join(rd, "stderr.txt.gz"))
        if key["telemetry"]:
            compress_into(tel, os.path.join(rd, "telemetry.jsonl.gz"))
        if os.path.exists(os.path.join(work, "check.txt")):
            compress_into(os.path.join(work, "check.txt"), os.path.join(rd, "check.txt.gz"))
        proof_info = None
        if proof and os.path.exists(proof):
            proof_info = {"bytes": os.path.getsize(proof)}
        record = {
            "schema": SCHEMA, "run_id": rid, "key": key, "config": run["config"], "exp": run["exp"],
            "build": run["variant_build"], "host": host, "core": core,
            "cpu_model": cpu_model(), "slurm_job": attempt["slurm_job"], "array_task": attempt["array_task"],
            "start_utc": start_utc, "end_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cnf_stage_seconds": t_stage, "cmd": [os.path.relpath(c, ROOT) if c.startswith(ROOT) else c for c in cmd],
            "exit_code": res["exit_code"], "terminated_by": res["terminated_by"],
            "cpu": res["cpu"], "cpu_user": res["cpu_user"], "cpu_sys": res["cpu_sys"], "wall": res["wall"],
            "maxrss_kb": res["maxrss_kb"], "solver_status": status_line, "model_terminated": model_end,
            "status": status, "result": {10: "SAT", 20: "UNSAT"}.get(res["exit_code"]) if status in ("solved", "wrong", "unverified") else None,
            "verification": ver, "stats": stats, "telemetry": tsum, "proof": proof_info,
            "stderr_tail": res["stderr_tail"][-500:], "stdout_tail": res["stdout_tail"][-500:],
        }
        atomic_write_json(result_path(rid), record)
        with open(attempts_log, "a") as f:
            f.write(json.dumps(dict(attempt, event="done", status=status, cpu=res["cpu"],
                                    checker_cpu=ver.get("cpu", 0))) + "\n")
        return status
    finally:
        shutil.rmtree(work, ignore_errors=True)


_cpu_model = None


def cpu_model():
    global _cpu_model
    if _cpu_model is None:
        _cpu_model = "?"
        for line in open("/proc/cpuinfo"):
            if line.startswith("model name"):
                _cpu_model = line.split(":", 1)[1].strip()
                break
    return _cpu_model


def worker(args):
    idx, runs, core, attempts_log = args
    out = {}
    for r in runs:
        try:
            st = execute(r, core, attempts_log)
        except Exception as e:  # keep going; failure is logged and run stays missing
            st = "runner-error"
            with open(attempts_log, "a") as f:
                f.write(json.dumps({"run_id": r["run_id"], "event": "runner-error", "error": repr(e),
                                    "traceback": traceback.format_exc()[-2000:]}) + "\n")
        out[st] = out.get(st, 0) + 1
    return out


# ------------------------------------------------------------------- CLI

def cmd_plan(a):
    exp = load_experiment(a.exp)
    runs = plan(exp)
    done = sum(os.path.exists(result_path(r["run_id"])) for r in runs)
    hours = len(runs) * exp["timeout"] / 3600
    print(json.dumps({"experiment": exp["name"], "runs": len(runs), "done": done,
                      "worst_case_core_hours": round(hours, 1),
                      "remaining_worst_case_core_hours": round((len(runs) - done) * exp["timeout"] / 3600, 1)}))


def cmd_run(a):
    exp = load_experiment(a.exp)
    runs = plan(exp)
    i, n = map(int, a.shard.split("/"))
    mine = [r for r in runs if int(r["run_id"][:8], 16) % n == i and not os.path.exists(result_path(r["run_id"]))]
    random.Random(a.order_seed).shuffle(mine)
    cores = physical_cores()
    if a.jobs and a.jobs < len(cores):
        # spread workers evenly over physical cores (and thus over CCDs)
        step = len(cores) / a.jobs
        cores = [cores[int(k * step)] for k in range(a.jobs)]
    if a.no_pin:
        cores = [None] * (a.jobs or len(cores))
    jobs = min(a.jobs or len(cores), len(cores), max(1, len(mine)))
    os.makedirs(os.path.join(DATA, "runs", "attempts"), exist_ok=True)
    tag = f"{socket.gethostname()}-{os.getpid()}"
    attempts_log = os.path.join(DATA, "runs", "attempts", f"{exp['name']}-{tag}.jsonl")
    print(f"[fprun] {exp['name']} shard {i}/{n}: {len(mine)} runs on {jobs} cores {cores[:jobs]}", flush=True)
    chunks = [mine[k::jobs] for k in range(jobs)]
    with mp.Pool(jobs) as pool:
        totals = {}
        for out in pool.imap_unordered(worker, [(k, chunks[k], cores[k], attempts_log) for k in range(jobs)]):
            for s, c in out.items():
                totals[s] = totals.get(s, 0) + c
    print(f"[fprun] done {totals}", flush=True)


def cmd_status(a):
    exp = load_experiment(a.exp)
    runs = plan(exp)
    counts = {}
    for r in runs:
        p = result_path(r["run_id"])
        st = load_json(p)["status"] if os.path.exists(p) else "missing"
        counts[st] = counts.get(st, 0) + 1
    print(json.dumps({"experiment": exp["name"], "runs": len(runs), "status": counts}))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run", "status"):
        p = sub.add_parser(name)
        p.add_argument("--exp", required=True)
        if name == "run":
            p.add_argument("--shard", default="0/1")
            p.add_argument("--jobs", type=int, default=0)
            p.add_argument("--order-seed", type=int, default=1)
            p.add_argument("--no-pin", action="store_true")
    a = ap.parse_args()
    {"plan": cmd_plan, "run": cmd_run, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    main()
