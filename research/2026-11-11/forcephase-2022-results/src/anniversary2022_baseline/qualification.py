"""Actual small Linux CLI executions; never submits the 5355-parent matrix."""
import argparse
import csv
import functools
import http.server
import json
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path
from .common import ACTIONS, read, sha, utc, write


def pigeonhole(pigeons, holes):
    v=lambda p,h:1+p*holes+h
    clauses=[[v(p,h) for h in range(holes)] for p in range(pigeons)]
    clauses += [[-v(p,h),-v(q,h)] for h in range(holes) for p in range(pigeons) for q in range(p+1,pigeons)]
    return f"p cnf {pigeons*holes} {len(clauses)}\n"+"".join(" ".join(map(str,c))+" 0\n" for c in clauses)


def qualify(base, solver, checker):
    base=Path(base).resolve()
    if base.exists():raise ValueError("qualification output is immutable; use a new version")
    base.mkdir(parents=True); fixtures=base/"fixtures";fixtures.mkdir()
    for name,text in {"sat":"p cnf 2 2\n1 2 0\n-1 2 0\n", "unsat_units":"p cnf 1 2\n1 0\n-1 0\n",
                      "unsat_search":pigeonhole(4,3), "timeout":pigeonhole(24,23)}.items():
        (fixtures/(name+".cnf")).write_text(text)
    handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(fixtures))
    server=http.server.ThreadingHTTPServer(("127.0.0.1",0),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    port=server.server_address[1]
    manifest=base/"manifest.csv"
    with manifest.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["instance_key","url","role","expected_sha256_cnf"]);w.writeheader()
        for p in sorted(fixtures.glob("*.cnf")):
            w.writerow({"instance_key":p.stem,"url":f"http://127.0.0.1:{port}/{p.name}","role":"qualification","expected_sha256_cnf":sha(p)})
    spec={"status":"QUALIFICATION","expected_inputs":4,"manifest_sha256":sha(manifest),
          "solver_path":solver,"solver_sha256":sha(solver),"checker_path":checker,"checker_sha256":sha(checker),
          "solver_commit":"c60730422e758ef1cebe7aeddf2dda31c996bf04","actions":ACTIONS,"seeds":[0],
          "cutoff_s":2,"wall_watchdog_s":10,"termination_grace_s":2,"checker_cpu_s":20,"checker_wall_s":30,
          "workers":4,"memory_bytes":512*1024**2,"memory_reserve_bytes":1024**3,
          "proof_limit_bytes":128*1024**2,"disk_reserve_bytes":16*1024**3,
          "download_workers":2,"download_wall_s":10,"prefetch_parents":4,
          "max_physical_cpu_hours":0.05,"evict_completed_inputs":False}
    spec_path=base/"spec.json";write(spec_path,spec);root=base/"matrix"
    def cmd(module,*args):return [sys.executable,"-m","src.anniversary2022_baseline."+module,*map(str,args)]
    log=(base/"first_launch.log").open("w")
    child=subprocess.Popen(cmd("run_baselines","start","--root",root,"--spec",spec_path,"--manifest",manifest),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    deadline=time.monotonic()+15
    while not (root/"owner.json").exists() and child.poll() is None and time.monotonic()<deadline:time.sleep(.02)
    second=subprocess.run(cmd("run_baselines","resume","--root",root),capture_output=True,text=True,timeout=10)
    if second.returncode==0 or "healthy owner already holds" not in second.stderr:
        raise AssertionError("second owner was not rejected: "+second.stderr[-1000:])
    child.wait(timeout=90);log.close();server.shutdown();server.server_close()
    if child.returncode:raise AssertionError("actual launch failed; inspect first_launch.log")
    paths=sorted(root.glob("runs/*/result.json")); before={str(p):sha(p) for p in paths}
    records=[read(p) for p in paths]
    if len(records)!=12 or len({r["physical_execution_id"] for r in records})!=12:raise AssertionError("wrong physical run count")
    for r in records:
        expected="SAT" if r["instance_key"]=="sat" else "CPU_TIMEOUT" if r["instance_key"]=="timeout" else "UNSAT"
        if r["status"]!=expected or not r["valid_measurement"]:raise AssertionError("incorrect result: "+json.dumps(r))
        if r["conflicts"] is None:raise AssertionError("missing final/termination conflict statistics")
    resumed=subprocess.run(cmd("run_baselines","resume","--root",root),capture_output=True,text=True,timeout=20)
    (base/"resume.log").write_text(resumed.stdout+resumed.stderr)
    after={str(p):sha(p) for p in root.glob("runs/*/result.json")}
    if resumed.returncode or before!=after:raise AssertionError("resume changed or duplicated physical runs")
    snapshot=root/"analysis"
    subprocess.run(cmd("collect_results","--root",root,"--snapshot",snapshot),check=True,timeout=20)
    summary=read(snapshot/"summary.json")
    if summary["complete_parents"]!=4 or summary["all_censored"]!=1 or summary["solved_union"]!=3:
        raise AssertionError("wrong complete population or censoring semantics")
    subprocess.run(cmd("export_results","--root",root,"--out",base/"qualification_receipts.tar.gz","--require-complete"),check=True,timeout=20)
    with tarfile.open(base/"qualification_receipts.tar.gz") as tf:
        m=json.load(tf.extractfile("MANIFEST.json"))
        import hashlib
        for entry in m["files"]:
            if hashlib.sha256(tf.extractfile(entry["path"]).read()).hexdigest()!=entry["sha256"]:
                raise AssertionError("export content SHA mismatch")
    report={"status":"PASS","scope":"Functional qualification only, not formal T600 evidence",
            "finished_utc":utc(),"solver_sha256":spec["solver_sha256"],"checker_sha256":spec["checker_sha256"],
            "real_solver_runs":12,"verified_sat":3,"verified_unsat":6,"cpu_timeouts":3,
            "stats_complete":12,"concurrent_owner_rejected":True,"resume_new_physical_runs":0,
            "http_staging_and_exact_cnf_sha_passed":True,"complete_parent_triads":4,
            "independent_export_member_shas_passed":True,"formal5355_queue_started":False,
            "archive_sha256":sha(base/"qualification_receipts.tar.gz"),
            "plots":"To be rendered locally from immutable snapshot using bundled matplotlib"}
    write(base/"QUALIFICATION.json",report);print(json.dumps(report,sort_keys=True))


def main():
    p=argparse.ArgumentParser();p.add_argument("--root",required=True);p.add_argument("--solver",required=True);p.add_argument("--checker",required=True);a=p.parse_args()
    try:qualify(a.root,a.solver,a.checker)
    except Exception as e:
        write(Path(a.root)/"QUALIFICATION_FAILURE.json",{"status":"FAIL","error":repr(e),"finished_utc":utc()})
        raise


if __name__=="__main__":main()
