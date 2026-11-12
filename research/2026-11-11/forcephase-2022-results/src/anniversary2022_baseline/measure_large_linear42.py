"""Durable row-local identity/native-cost measurements for all1876 large2022 inputs."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import fcntl
import gzip
import hashlib
import json
import lzma
import os
from pathlib import Path
import resource
import shutil
import signal
import socket
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.request

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from .common import sha
from .gbd_native_vectors import vectorize
from .linear42_candidate import predict_vector
from .score_static_seed_agreement import load_views
from .structural_clusters import BASE, DATA, ROOT, read_csv


CONFIG = ROOT / "configs/anniversary2022_baseline/linear42_large_cost_20261111"
MODEL = DATA / "linear42_candidate_20261111/model.joblib"
BINARY = ROOT / "work/native_gbd_features_v2_20261111/native_gbd_features"
CHECKER = ROOT / "work/positive_binary_replay_20261110/count"
CHECKER_SHA = "67edcbcc38d6d4e3e049c35f904aacb5700e7ce7c3105e87a6bf8bc9db9e5899"
GIB = 1024**3
WIRE_LIMIT = GIB
FREE_FLOOR = 3*GIB
CACHE_LIMIT = GIB


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True)+"\n")
    os.replace(temporary, path)


def timer_for(process, seconds):
    # An unreaped child PID cannot have been reassigned to another process.
    def kill_owned_child():
        try: os.kill(process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
    timer = threading.Timer(seconds, kill_owned_child)
    timer.daemon = True
    timer.start()
    return timer


def wait4(process):
    _, status, usage = os.wait4(process.pid, 0)
    process.returncode = os.waitstatus_to_exitcode(status)
    return process.returncode, usage.ru_utime+usage.ru_stime, usage.ru_maxrss


def download(row, work):
    key = row["instance_key"]
    path, meta = work/(key+".input"), work/(key+".download.json")
    if path.exists() and meta.exists():
        old = json.loads(meta.read_text())
        if old["url"] == row["url"] and sha(path) == old["wire_sha256"]:
            return {**old, "reused_download": True, "path": str(path)}
        raise ValueError("owned download cache does not match its receipt")
    if shutil.disk_usage(work).free < FREE_FLOOR+WIRE_LIMIT:
        raise OSError("available disk cannot admit one bounded compressed input")
    began, cpu = time.monotonic(), time.thread_time()
    partial = path.with_suffix(".part")
    digest, total = hashlib.sha256(), 0
    try:
        request = urllib.request.Request(row["url"], headers={"User-Agent":"forcephase-2022-feature-cost/1"})
        with urllib.request.urlopen(request, timeout=20) as response, partial.open("wb") as out:
            while True:
                if time.monotonic()-began > 180:
                    raise TimeoutError("benchmark transfer exceeded180 wall seconds")
                block = response.read(1024*1024)
                if not block: break
                total += len(block)
                if total > WIRE_LIMIT:
                    raise OSError("compressed input exceeds1GiB temporary-file bound")
                if shutil.disk_usage(work).free < FREE_FLOOR:
                    raise OSError("benchmark transfer reached reserved disk floor")
                digest.update(block); out.write(block)
        os.replace(partial, path)
        receipt = {"instance_key":key,"url":row["url"],"wire_bytes":total,
            "wire_sha256":digest.hexdigest(),"transfer_wall_s":time.monotonic()-began,
            "transfer_parent_CPU_s":time.thread_time()-cpu,"reused_download":False}
        atomic(meta,receipt)
        return {**receipt,"path":str(path)}
    except BaseException:
        if partial.exists(): partial.unlink()
        raise


def open_plain(path):
    with path.open("rb") as stream: magic=stream.read(6)
    if magic.startswith(b"\xfd7zXZ\x00"): return lzma.open(path,"rb")
    if magic.startswith(b"\x1f\x8b"): return gzip.open(path,"rb")
    return path.open("rb")


def identity(path, row, expected, wire_sha256, out):
    if out.exists():
        rec=json.loads(out.read_text())
        assert rec["instance_key"]==row["instance_key"] and rec["verified"] and rec["wire_sha256"]==wire_sha256
        return {**rec,"reused_physical_measurement":True}
    began,cpu=time.monotonic(),time.thread_time()
    process=subprocess.Popen([str(CHECKER)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    timer=timer_for(process,180)
    digest,total=hashlib.sha256(),0
    try:
        with open_plain(path) as stream:
            while True:
                block=stream.read(1024*1024)
                if not block: break
                total+=len(block)
                if total>4*GIB or time.monotonic()-began>180:
                    raise TimeoutError("input identity pass exceeded its byte/wall limit")
                digest.update(block);process.stdin.write(block)
        process.stdin.close()
        output=process.stdout.read(1000001)
        process.stdout.close()
        code,child,rss=wait4(process)
    except BaseException:
        try: os.kill(process.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        try: code,child,rss=wait4(process)
        except ChildProcessError: pass
        raise
    finally: timer.cancel()
    parts=output.decode(errors="replace").split()
    verified=code==0 and len(parts)>=5 and parts[0]==row["instance_key"] and int(parts[1])==expected[0] and int(parts[2])==expected[1]
    rec={"instance_key":row["instance_key"],"verified":bool(verified),"raw_sha256":digest.hexdigest(),"wire_sha256":wire_sha256,
        "raw_bytes":total,"checker_exit":code,"checker_output":output.decode(errors="replace")[:800],
        "identity_child_CPU_s":child,"identity_parent_CPU_s":time.thread_time()-cpu,
        "identity_wall_s":time.monotonic()-began,"checker_maxrss":rss,
        "reused_physical_measurement":False}
    atomic(out,rec)
    if not verified: raise ValueError("downloaded CNF does not match frozen GBD identity/counts")
    return rec


def native(path, key, raw_sha256, out):
    if out.exists():
        old=json.loads(out.read_text())
        assert old["instance_key"]==key and old["native_binary_sha256"]==sha(BINARY) and old["raw_sha256"]==raw_sha256
        return {**old,"reused_physical_measurement":True}
    began,cpu=time.monotonic(),time.thread_time()
    process=subprocess.Popen([str(BINARY),str(path)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    timer=timer_for(process,14)
    try:
        output=process.stdout.read(1000001)
        if len(output)>1000000: os.kill(process.pid,signal.SIGKILL)
        process.stdout.close()
        code,child,rss=wait4(process)
    except BaseException:
        try: os.kill(process.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        try: wait4(process)
        except ChildProcessError: pass
        raise
    finally: timer.cancel()
    rec={"instance_key":key,"raw_sha256":raw_sha256,"native_exit":code,"native_CPU_s":child,
        "native_wrapper_parent_CPU_s":time.thread_time()-cpu,"native_wall_s":time.monotonic()-began,
        "native_maxrss":rss,"native_binary_sha256":sha(BINARY),"reused_physical_measurement":False}
    if code==0:
        rec["features"]=json.loads(output)["features"]
    else: rec["native_error"]=output.decode(errors="replace")[:800]
    atomic(out,rec)
    return rec


def prune(work, records, protected):
    files=sorted(work.glob("*.input"),key=lambda p:p.stat().st_mtime)
    total=sum(p.stat().st_size for p in files)
    for path in files:
        key=path.stem
        if total<=CACHE_LIMIT: break
        if key in protected or not (records/(key+".json")).exists(): continue
        total-=path.stat().st_size
        path.unlink()


def run(args):
    start,cpu=time.monotonic(),time.process_time()
    usage=resource.getrusage(resource.RUSAGE_CHILDREN)
    initial_child=usage.ru_utime+usage.ru_stime
    args.out.mkdir(parents=True,exist_ok=True)
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    records=args.out/"records";records.mkdir(exist_ok=True)
    stages=args.out/"stages";stages.mkdir(exist_ok=True)
    with (args.out/"owner.lock").open("w") as lock,threadpool_limits(limits=1):
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        rows=read_csv(CONFIG/"manifest.csv")
        assert len(rows)==1876 and [int(r["ordinal"]) for r in rows]==list(range(1,1877))
        assert [r["instance_key"] for r in rows]==sorted(r["instance_key"] for r in rows)
        assert 1<=args.through<=1876
        policy=json.loads((MODEL.parent/"policy.json").read_text())
        assert sha(MODEL)==policy["model_sha256"] and sha(BINARY)==policy["native_binary_sha256"]
        assert sha(BASE)==policy["GBD_sha256"]
        assert sha(CHECKER)==CHECKER_SHA
        identity_spec={"source_sha256":sha(__file__),"manifest_sha256":sha(CONFIG/"manifest.csv"),
            "model_sha256":sha(MODEL),"native_binary_sha256":sha(BINARY),"checker_sha256":sha(CHECKER),
            "GBD_sha256":sha(BASE),"native_CPU_limit_s":8,"native_alarm_s":12,"native_wrapper_wall_s":14,
            "wire_limit":WIRE_LIMIT,"disk_floor":FREE_FLOOR,"cache_limit":CACHE_LIMIT}
        binding=args.out/"identity.json"
        if binding.exists(): assert json.loads(binding.read_text())==identity_spec
        else: atomic(binding,identity_spec)
        atomic(args.out/"owner.json",{"PID":os.getpid(),"host":socket.gethostname(),"through":args.through,
            "source_sha256":identity_spec["source_sha256"],"status":"running"})
        with sqlite3.connect("file:"+str(BASE)+"?mode=ro",uri=True) as db:
            expected={k:(int(c),int(b)) for k,c,b in db.execute("select hash,clauses,cls2 from features")}
        from .structural_clusters import load
        keys=load()[0]
        x,valid=load_views(keys)[0]["linear42"]
        assert valid.all()
        reference={k:v.astype(np.float32) for k,v in zip(keys,x)}
        payload=joblib.load(MODEL)
        assert payload["view"]=="linear42" and len(payload["models"])==3
        assert all(m.n_features_in_==42 for m in payload["models"])
        missing=[r for r in rows[:args.through] if not (records/(r["instance_key"]+".json")).exists()]
        atomic(args.out/"progress.json",{"status":"running","through":args.through,
            "completed_prefix":args.through-len(missing),"remaining_prefix":len(missing),"total_missing_scope":1876})
        session=str(time.time_ns())
        outcome="running"
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(download,missing[0],work) if missing else None
                for at,row in enumerate(missing):
                    if time.monotonic()-start>3600: raise TimeoutError("native acquisition invocation exceeded one hour")
                    key=row["instance_key"]
                    try: got=future.result()
                    except Exception as exc:
                        atomic(args.out/"acquisition_failures"/(key+"_"+session+".json"),
                            {"instance_key":key,"error":repr(exc),"status":"missing_measurement_not_solver_timeout"})
                        raise
                    following=missing[at+1] if at+1<len(missing) else None
                    future=pool.submit(download,following,work) if following else None
                    path=Path(got["path"])
                    ident=identity(path,row,expected[key],got["wire_sha256"],stages/(key+".identity.json"))
                    actual=native(path,key,ident["raw_sha256"],stages/(key+".native.json"))
                    rec={"instance_key":key,"ordinal":int(row["ordinal"]),"download":got,"identity":ident,
                        "native":{k:v for k,v in actual.items() if k!="features"},"action":"D",
                        "status":"native_error_D_fallback","acquisition_CPU_s":actual["native_CPU_s"]+actual["native_wrapper_parent_CPU_s"]}
                    if actual["native_exit"]==0:
                        tick=time.thread_time()
                        vector=vectorize(actual["features"])["linear42"]
                        vector_cpu=time.thread_time()-tick
                        rec["acquisition_CPU_s"]+=vector_cpu
                        rec["vectorize_CPU_s"]=vector_cpu
                        rec["model_input_float32_match"]=bool(np.array_equal(vector.astype(np.float32),reference[key]))
                        if not rec["model_input_float32_match"]:
                            atomic(args.out/"input_mismatches"/(key+".json"),{**rec,"native_vector":vector.tolist(),"reference_vector":reference[key].tolist()})
                            raise ValueError("large-input native vector does not match trained42-feature representation")
                        tick=time.thread_time()
                        action,gain=predict_vector(payload,vector)
                        rec.update(status="ok",action=("D","Fplus","Fminus")[action],
                            decision_CPU_s=time.thread_time()-tick,min_predicted_PAR2_savings=gain.tolist())
                        reference_action,_=predict_vector(payload,reference[key])
                        assert action==reference_action
                    rec["policy_query_CPU_s"]=rec["acquisition_CPU_s"]+rec.get("decision_CPU_s",0.)
                    rec["scope"]="Full candidate interface/cost; no in-sample performance reward"
                    atomic(records/(key+".json"),rec)
                    done=sum((records/(r["instance_key"]+".json")).exists() for r in rows[:args.through])
                    atomic(args.out/"progress.json",{"status":"running","through":args.through,"completed_prefix":done,
                        "remaining_prefix":args.through-done,"total_missing_scope":1876,"last_status":rec["status"]})
                    print(f"MEASURED {done}/{args.through} of1876 large inputs: {rec['status']}, acquisition={rec['acquisition_CPU_s']:.4f}CPU_s",flush=True)
                    prune(work,records,{key,following["instance_key"]} if following else {key})
            values=[json.loads((records/(r["instance_key"]+".json")).read_text()) for r in rows[:args.through]]
            fees=np.array([v["acquisition_CPU_s"] for v in values])
            atomic(args.out/("prefix_"+str(args.through)+".json"),{"status":"complete_prefix","through":args.through,
                "all_missing_scope":1876,"remaining_unmeasured_large":1876-args.through,
                "native_ok":sum(v["status"]=="ok" for v in values),"native_error_D":sum(v["status"]!="ok" for v in values),
                "acquisition_CPU_sum_s":float(fees.sum()),"acquisition_CPU_quantiles_s":np.quantile(fees,[.5,.9,.99,1]).tolist(),
                "sample_selection":"Frozen original sorted prefix, no phase outcomes used","new_solver_calls":0,
                "scope":"Measured costs only; not whole1876 completion, independent performance, or same-machine end-to-end"})
            atomic(args.out/"progress.json",{"status":"complete_prefix","through":args.through,"completed_prefix":args.through,
                "remaining_prefix":0,"remaining_large":1876-args.through})
            outcome="complete_prefix"
        except BaseException as exc:
            outcome="failed_invocation"
            atomic(args.out/"failures"/(session+".json"),{"status":"failed_invocation","error":repr(exc),"through":args.through})
            old=json.loads((args.out/"progress.json").read_text())
            atomic(args.out/"progress.json",{**old,"status":outcome,"last_error":repr(exc)})
            raise
        finally:
            usage=resource.getrusage(resource.RUSAGE_CHILDREN)
            atomic(args.out/"sessions"/(session+".json"),{"through":args.through,"physical_parent_CPU_s":time.process_time()-cpu,
                "physical_child_CPU_s":usage.ru_utime+usage.ru_stime-initial_child,"wall_s":time.monotonic()-start,
                "new_solver_calls":0,"source_sha256":identity_spec["source_sha256"],
                "logical_reused_fees_are_not_new_physical_CPU":True})
            atomic(args.out/"owner.json",{"PID":os.getpid(),"host":socket.gethostname(),"status":outcome,
                "through":args.through,"source_sha256":identity_spec["source_sha256"]})


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through",type=int,required=True)
    parser.add_argument("--out",type=Path,default=DATA/"linear42_large_cost_20261111")
    parser.add_argument("--work",type=Path,default=ROOT/"work/linear42_large_cost_20261111/cache")
    run(parser.parse_args())
