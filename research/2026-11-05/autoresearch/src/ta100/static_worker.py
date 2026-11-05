#!/usr/bin/env python3
"""TA100 owner-fixed static group collection, only eligible public fit/feedback."""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import queue
import re
import resource
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

BASE_PATH = Path(__file__).with_name("base_static_worker.py")
if not BASE_PATH.exists():
    BASE_PATH = Path(__file__).resolve().parents[1] / "ta_feature_discovery/node_worker.py"
spec = importlib.util.spec_from_file_location("ta100_base_worker", BASE_PATH)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

PROFILE = {"kind": "ta100_static_group_v1", "cpu_s": 5., "wall_s": 12.,
           "memory_bytes": 3*1024**3, "output_bytes": 8*1024**2,
           "input_max_bytes": 100000000, "header_max_variables": 5000000,
           "parser_max_clauses": 2000000, "parser_max_literals": 20000000,
           "reservation_cpu_s": 30.}
METHOD_FIELDS = {"group", "extractor_source_sha256", "parser_source_sha256", "binary_sha256",
                 "cpu_helper_sha256", "worker_source_sha256", "base_worker_source_sha256", "dependency_sha256"}
MISSING_BLOCK_STATUSES = {"CAPPED", "UNDEFINED", "EMPTY", "FAILED", "TIMEOUT", "RESOURCE_LIMIT"}
FEATURE_NAME = re.compile(r"^(?:f_|graph_|algebra_)[A-Za-z0-9_]+$")


def task_key(task, manifest):
    return hashlib.sha256(base.canonical({"instance_id":task["instance_id"],"input_sha256":task["input_sha256"],
        "method":manifest["method"],"profile":PROFILE,"feature_keys":manifest["feature_keys"]})).hexdigest()


def normalize_task(raw, manifest):
    raw = dict(raw); given = raw.pop("task_key", None)
    task = base.normalize_task(raw, manifest["method"]["extractor_source_sha256"])
    task["task_key"] = task_key(task, manifest)
    if given is not None and given != task["task_key"]:
        raise ValueError("task key differs from frozen group/input/profile identity")
    return task


def load_manifest(args):
    manifest = json.loads(args.manifest.read_text())
    if manifest.get("profile") != PROFILE or set(manifest.get("method", {})) != METHOD_FIELDS:
        raise ValueError("TA100 profile/method differs from frozen contract")
    method = manifest["method"]
    expected = {"extractor_source_sha256":base.sha(args.extractor_source),
        "parser_source_sha256":base.sha(args.parser_source),"binary_sha256":base.sha(args.binary),
        "cpu_helper_sha256":base.sha(args.cpu_helper),"worker_source_sha256":base.sha(__file__),
        "base_worker_source_sha256":base.sha(BASE_PATH)}
    dependency_paths=getattr(args,"dependency_source",None) or []
    if len({p.name for p in dependency_paths})!=len(dependency_paths):raise ValueError("dependency filenames must be distinct")
    expected["dependency_sha256"]={p.name:base.sha(p) for p in dependency_paths}
    if any(method.get(k) != v for k,v in expected.items()):
        raise ValueError("worker/parser/binary/helper source identity mismatch")
    for key in ("experiment_id", "shard_id", "node_id"):
        if not base.SAFE_ID.fullmatch(str(manifest.get(key, ""))):
            raise ValueError("unsafe owner identity")
    if manifest["node_id"] != args.node_id or not base.SAFE_ID.fullmatch(method["group"]):
        raise ValueError("node/group differs from central assignment")
    keys = manifest.get("feature_keys")
    if not isinstance(keys,list) or not keys or len(set(keys)) != len(keys) or any(not isinstance(k,str) or not FEATURE_NAME.fullmatch(k) for k in keys):
        raise ValueError("a distinct safe f_/graph_/algebra_ feature registry is required")
    allocated = manifest.get("allocated_cpu_s")
    if isinstance(allocated,bool) or not isinstance(allocated,(int,float)) or not math.isfinite(allocated) or allocated <= 0:
        raise ValueError("central owner must allocate this node/group's shared CPU budget")
    manifest["tasks"] = [normalize_task(t,manifest) for t in manifest["tasks"]]
    if len({t["task_key"] for t in manifest["tasks"]}) != len(manifest["tasks"]):
        raise ValueError("duplicate group task in manifest")
    return manifest


def validate_output(payload, manifest, task):
    if payload.get("schema") != "ta100.static.v1" or payload.get("group") != manifest["method"]["group"]:
        raise ValueError("extractor returned wrong group/schema")
    features, blocks = payload.get("features",{}), payload.get("blocks",{})
    if set(features) != set(manifest["feature_keys"]) or set(blocks) != set(features):
        raise ValueError("extractor fields differ from frozen registry")
    for key, value in features.items():
        status = blocks[key].get("status")
        if status == "COMPLETE":
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                raise ValueError("complete block lacks a finite scalar")
        elif status not in MISSING_BLOCK_STATUSES or value is not None:
            raise ValueError("missing/capped block must be explicit and null")
    metadata=payload.get("metadata",{})
    if metadata.get("header_clauses") != metadata.get("raw_clauses"):
        raise ValueError("parsed original clause count differs from header")
    for public, actual in (("variables","header_variables"),("clauses","header_clauses"),("bytes","input_bytes")):
        if public in task.get("metadata",{}) and task["metadata"][public] != metadata.get(actual):
            raise ValueError("extractor input metadata differs from frozen public input")
    return payload


def limited_exec(helper,binary,group,cnf):
    resource.setrlimit(resource.RLIMIT_AS,(PROFILE["memory_bytes"],)*2)
    resource.setrlimit(resource.RLIMIT_FSIZE,(PROFILE["output_bytes"],)*2)
    resource.setrlimit(resource.RLIMIT_CPU,(6,6))
    command=[str(Path(helper).resolve()),"5",str(Path(binary).resolve()),"--module",group,str(Path(cnf).resolve())]
    os.execv(command[0],command)


def run_group(args,manifest,task,cnf,directory,marker):
    directory=Path(directory);started=time.monotonic();killed=False
    with (directory/"stdout.json").open("xb") as out,(directory/"stderr.txt").open("xb") as err:
        child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),"_limit",str(args.cpu_helper),
            str(args.binary),manifest["method"]["group"],str(cnf)],stdout=out,stderr=err,stdin=subprocess.DEVNULL,start_new_session=True)
        base.atomic_json(marker,{"owner_pid":os.getpid(),"child_pid":child.pid,"hostname":socket.gethostname()})
        while True:
            pid,status,usage=os.wait4(child.pid,os.WNOHANG)
            if pid:break
            if time.monotonic()-started >= PROFILE["wall_s"] and not killed:
                try:os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                killed=True
            time.sleep(.01)
        child.returncode=os.waitstatus_to_exitcode(status)
    cpu=usage.ru_utime+usage.ru_stime
    stderr=(directory/"stderr.txt").read_text(errors="replace")[:4000]
    result={"feature_cpu_s":cpu,"feature_wall_s":time.monotonic()-started,"exit_code":child.returncode,"stderr":stderr}
    if killed or child.returncode in (-signal.SIGPROF,-signal.SIGXCPU) or cpu>PROFILE["cpu_s"]:
        return {**result,"status":"TIMEOUT","error":"group CPU/wall budget before complete output"}
    if child.returncode:
        return {**result,"status":"RESOURCE_LIMIT" if "RESOURCE_LIMIT:" in stderr else "FAILED"}
    try:payload=validate_output(json.loads((directory/"stdout.json").read_text()),manifest,task)
    except Exception as exc:return {**result,"status":"FAILED","error":type(exc).__name__+": "+str(exc)}
    return {**result,"status":"COMPLETE","features":payload["features"],"blocks":payload["blocks"],"extractor_metadata":payload["metadata"]}


def reusable(path,task,manifest):
    record=json.loads(Path(path).read_text())
    for key,value in {"task_key":task["task_key"],"input_sha256":task["input_sha256"],"method":manifest["method"],"profile":PROFILE,"feature_keys":manifest["feature_keys"],"role":task["role"]}.items():
        if record.get(key)!=value:raise ValueError("existing group receipt identity mismatch: "+key)
    digest=record.pop("receipt_content_sha256",None)
    if hashlib.sha256(base.canonical(record)).hexdigest()!=digest:raise ValueError("group receipt content SHA mismatch")
    record["receipt_content_sha256"]=digest;return record


def publish_verified_input(cnf,cache,expected_sha):
    """Only a newly fetched, verified public input; immutable SHA-addressed cache."""
    import fcntl
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    target=cache/(expected_sha+".cnf")
    with (cache/".publish.lock").open("a+") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if target.exists():
            if base.sha(target)!=expected_sha:raise ValueError("existing persistent input cache SHA mismatch")
            return "REUSED"
        # Serialize publications; preserve12GiB floor plus1GiB for up to four
        # unfinished bounded preparations, beyond disk already occupied.
        if shutil.disk_usage(cache).free-Path(cnf).stat().st_size < 13*1024**3:return "SKIPPED_DISK_RESERVE"
        temporary=cache/("."+expected_sha+"."+str(os.getpid())+"."+str(threading.get_ident())+".partial")
        try:
            with Path(cnf).open("rb") as src,temporary.open("xb") as out:
                shutil.copyfileobj(src,out);out.flush();os.fsync(out.fileno())
            if base.sha(temporary)!=expected_sha:raise ValueError("new persistent input cache SHA mismatch")
            os.link(temporary,target)  # Atomic exclusive publication, never overwrite.
        finally:
            if temporary.exists():temporary.unlink()
        return "PUBLISHED"


def process_task(args,manifest,task):
    output=args.output_dir;receipt=output/"results"/(task["task_key"]+".json")
    if receipt.exists():return reusable(receipt,task,manifest),True
    marker=output/"inflight"/(task["task_key"]+".json")
    if marker.exists():raise RuntimeError("unresolved inflight group, do not auto-requeue after disconnect")
    base.atomic_json(marker,{"owner_pid":os.getpid(),"hostname":socket.gethostname()})
    record={"schema_version":1,"instance_id":task["instance_id"],"id":task["instance_id"],"role":task["role"],
        "task_key":task["task_key"],"input_sha256":task["input_sha256"],"method":manifest["method"],
        "profile":PROFILE,"feature_keys":manifest["feature_keys"],"features":dict.fromkeys(manifest["feature_keys"]),
        "node_id":args.node_id,"hostname":socket.gethostname(),"platform":platform.platform(),
        "feature_cpu_s":0.,"feature_wall_s":0.}
    cpu_start,wall_start=time.thread_time(),time.monotonic()
    try:
        if base.worker_capacity(output,1)<1:record.update(status="RESOURCE_UNAVAILABLE",error="no actual group headroom")
        else:
            with tempfile.TemporaryDirectory(prefix=task["task_key"]+"-",dir=output/"temporary") as temporary:
                verified_cache=getattr(args,"verified_cache",None)
                cached=verified_cache is not None and (verified_cache/(task["input_sha256"]+".cnf")).exists()
                cnf=base.prepare_input(task,temporary,verified_cache if cached else args.input_cache)
                if verified_cache is not None and Path(cnf).parent==Path(temporary):
                    record["persistent_cache_publication"]=publish_verified_input(cnf,verified_cache,task["input_sha256"])
                else:record["persistent_cache_publication"]="EXISTING_VERIFIED_SOURCE"
                record.update(preparation_cpu_s=time.thread_time()-cpu_start,preparation_wall_s=time.monotonic()-wall_start,
                              source_check="input_sha256_match")
                record.update(run_group(args,manifest,task,cnf,temporary,marker))
    except Exception as exc:record.update(status="FAILED",error=type(exc).__name__+": "+str(exc))
    record.setdefault("preparation_cpu_s",time.thread_time()-cpu_start)
    record.setdefault("preparation_wall_s",time.monotonic()-wall_start)
    record["controller_cpu_s"]=max(0.,time.thread_time()-cpu_start-record["preparation_cpu_s"])
    record["total_accounted_cpu_s"]=record["preparation_cpu_s"]+record["controller_cpu_s"]+record["feature_cpu_s"]
    if record["status"]!="COMPLETE":
        record["features"]=dict.fromkeys(manifest["feature_keys"])
        record["blocks"]={key:{"status":record["status"],"reason":record.get("error",record.get("stderr",""))} for key in manifest["feature_keys"]}
    record["receipt_content_sha256"]=hashlib.sha256(base.canonical(record)).hexdigest()
    base.atomic_json(receipt,record);marker.unlink();return record,False


def run(args):
    if not sys.platform.startswith("linux"):raise RuntimeError("fractional CPU helper qualified on Linux only")
    manifest=load_manifest(args);args.output_dir=args.output_dir.resolve()
    identity={"manifest_sha256":hashlib.sha256(base.canonical(manifest)).hexdigest(),"node_id":args.node_id}
    with base.owner_lock(args.output_dir,identity):
        for name in ("results","inflight","temporary"):(args.output_dir/name).mkdir(exist_ok=True)
        slots=base.worker_capacity(args.output_dir,args.max_workers)
        if slots<1:raise RuntimeError("no resource-qualified group slot")
        tasks=queue.Queue();records=[];accounted=reserved=0.
        for task in manifest["tasks"]:
            path=args.output_dir/"results"/(task["task_key"]+".json")
            if path.exists():
                record=reusable(path,task,manifest);records.append(record);accounted+=record["total_accounted_cpu_s"]
            else:tasks.put(task)
        mutex,stop=threading.Lock(),threading.Event()
        def progress():
            base.atomic_json(args.output_dir/"progress.json",{**identity,"planned":len(manifest["tasks"]),"completed":len(records),
                "statuses":dict(collections.Counter(r["status"] for r in records)),"accounted_cpu_s":accounted,"reserved_cpu_s":reserved,
                "allocated_cpu_s":manifest["allocated_cpu_s"],"worker_count":slots})
        def work():
            nonlocal accounted,reserved
            while not stop.is_set():
                with mutex:
                    if accounted+reserved+PROFILE["reservation_cpu_s"]>manifest["allocated_cpu_s"]:return
                    try:task=tasks.get_nowait()
                    except queue.Empty:return
                    reserved+=PROFILE["reservation_cpu_s"];progress()
                record,_=process_task(args,manifest,task)
                with mutex:
                    accounted+=record["total_accounted_cpu_s"];reserved-=PROFILE["reservation_cpu_s"];records.append(record)
                    if record["status"] in {"FAILED","RESOURCE_UNAVAILABLE"}:stop.set()
                    progress()
        progress()
        with concurrent.futures.ThreadPoolExecutor(max_workers=slots) as pool:
            for future in [pool.submit(work) for _ in range(slots)]:future.result()
        summary={**identity,"planned":len(manifest["tasks"]),"completed":len(records),"complete":len(records)==len(manifest["tasks"]),
            "statuses":dict(collections.Counter(r["status"] for r in records)),"accounted_cpu_s":accounted,"worker_count":slots}
        base.atomic_json(args.output_dir/"completion.json",summary);return summary


def main():
    if len(sys.argv)>1 and sys.argv[1]=="_limit":limited_exec(*sys.argv[2:]);return
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ("manifest","extractor-source","parser-source","binary","cpu-helper","output-dir"):
        parser.add_argument("--"+flag,required=True,type=Path)
    parser.add_argument("--node-id",required=True);parser.add_argument("--max-workers",type=int,default=1)
    parser.add_argument("--input-cache",type=Path)
    parser.add_argument("--verified-cache",type=Path,help="New SHA-addressed namespace; persist only newly fetched verified inputs")
    parser.add_argument("--dependency-source",nargs="*",type=Path,help="All implementation headers beyond the shared parser")
    args=parser.parse_args()
    print(json.dumps(run(args)))


if __name__=="__main__":main()
